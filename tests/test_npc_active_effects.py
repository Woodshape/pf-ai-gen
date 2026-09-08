import copy
import json
import tempfile
from pathlib import Path
import unittest

from monster_builder import Engine

ROOT = Path(__file__).resolve().parents[1]
ENCOUNTER = ROOT / 'docs/encounters/cinder-tithe'


def effect(name, level=3, **parameters):
    return {'effectId': 'npc-effect.' + name, 'sourceLevel': level, **parameters}


class ActiveEffectsTests(unittest.TestCase):
    def setUp(self):
        self.engine = Engine()
        self.request_id = 0

    def call(self, operation, payload):
        self.request_id += 1
        return self.engine.execute({'protocolVersion': '1', 'requestId': str(self.request_id),
                                    'operation': operation, 'payload': payload})

    def draft(self, name='varkesh', effects=()):
        draft = json.loads((ENCOUNTER / f'{name}.draft.json').read_text())
        draft['selections']['activeEffects'] = list(effects)
        return draft

    def create(self, draft):
        result = self.call('draft.create', {'draft': draft})
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['result']['evaluation']['status'], 'valid', result)
        return result['result']

    def canonical(self, effects, name='varkesh'):
        return self.create(self.draft(name, effects))['evaluation']['canonical']

    def test_mage_armor_shield_and_permanent_armor_overlap(self):
        base = self.canonical([])
        buffed = self.canonical([effect('mage-armor'), effect('shield')])
        self.assertEqual((buffed['defenses']['ac'], buffed['defenses']['touch'], buffed['defenses']['flatFooted']), (21, 13, 18))
        self.assertEqual(buffed['cmd'], base['cmd'])
        self.assertEqual(buffed['spells']['perDay'], base['spells']['perDay'])
        warrior = self.canonical([effect('mage-armor'), effect('shield')], 'goblin-warrior')
        self.assertEqual(warrior['defenses']['ac'], 21)
        self.assertEqual(warrior['defenses']['acBreakdown']['armor'], 4)
        self.assertEqual(warrior['defenses']['acBreakdown']['shield'], 4)
        self.assertEqual(self.canonical([effect('mage-armor', enabled=False)]), base)
        self.assertEqual(self.canonical([effect('shield'), effect('mage-armor')])['defenses'], buffed['defenses'])

    def test_alignment_protection_is_conditional_and_respects_cloak(self):
        draft = self.draft(effects=[effect('protection-from-evil')])
        draft['selections']['gear'].append({'itemId': 'item.cloak-of-resistance-1'})
        buffed = self.create(draft)['evaluation']['canonical']
        self.assertEqual(buffed['defenses']['ac'], 13)
        self.assertEqual(buffed['defenses']['will'], 5)
        conditional = buffed['conditionalModifiers']
        self.assertTrue(any(m['stat'] == 'ac' and m['bonus'] == 2 and 'evil' in m['condition'] for m in conditional))
        self.assertTrue(any(m['stat'] == 'will' and m['bonus'] == 1 and m.get('bonusType') == 'resistance' for m in conditional))
        self.assertNotIn('mental control', buffed['immunities'])

    def test_energy_resistance_and_absorption_are_not_added_or_permanent_immunity(self):
        for level, expected in [(1, 10), (7, 20), (11, 30)]:
            with self.subTest(level=level):
                result = self.canonical([effect('resist-energy', level, energyType='fire'),
                                         effect('protection-from-energy', level, energyType='fire')])
                self.assertEqual(result['resistances']['fire'], expected)
                self.assertEqual(result['energyProtection']['fire'], min(120, 12 * level))
                self.assertNotIn('fire', result['immunities'])
        result = self.canonical([effect('resist-energy', 7, energyType='cold'), effect('resist-energy', 11, energyType='fire')])
        self.assertEqual(result['resistances'], {'fire': 30, 'cold': 20})

    def test_rage_recalculates_strength_constitution_hp_skills_and_routines(self):
        result = self.canonical([effect('rage', 1)], 'goblin-warrior')
        self.assertEqual((result['abilityScores']['strength'], result['abilityScores']['constitution']), (15, 16))
        self.assertEqual((result['hp'], result['hitDiceExpression']), (8, '1d10+3'))
        self.assertEqual((result['defenses']['ac'], result['defenses']['touch'], result['defenses']['flatFooted']), (14, 11, 12))
        self.assertEqual((result['defenses']['fortitude'], result['defenses']['will']), (5, 2))
        self.assertEqual((result['cmb'], result['cmd']), (2, 12))
        self.assertEqual(result['attacks'][0]['attackBonuses'], [4])
        self.assertEqual(result['attacks'][0]['damageExpression'], '1d4+2')
        stealth = next(skill for skill in result['skills'] if skill['skillId'] == 'skill.stealth')
        self.assertFalse(stealth['usable'])
        result = self.canonical([effect('rage', 20)])
        self.assertEqual(result['hp'], 35)
        self.assertEqual(result['defenses']['will'], 8)
        self.assertTrue(result['spells']['castingRestricted'])

    def test_attack_bonuses_apply_to_rays_but_weapon_damage_bonuses_do_not(self):
        result = self.canonical([effect('heroism'), effect('bless'), effect('inspire-courage', 5)])
        self.assertEqual(result['attacks'][0]['attackBonuses'], [4])
        self.assertEqual(result['attacks'][0]['damageExpression'], '1d6+1')
        ray = next(a for a in result['attacks'] if a['name'] == 'Elemental Ray')
        self.assertEqual(ray['attackBonuses'], [8])
        self.assertEqual(ray['damageExpression'], '1d6+1')
        self.assertEqual(result['cmb'], 4)
        self.assertEqual(result['defenses']['will'], 6)
        self.assertEqual(result['spells']['concentration'], 5)
        self.assertFalse(any('fear' in m['condition'] for m in result['conditionalModifiers']))
        spellcraft = next(s for s in result['skills'] if s['skillId'] == 'skill.spellcraft')
        self.assertEqual(spellcraft['total'], 8)

    def test_other_performances_and_conditional_stacking(self):
        result = self.canonical([effect('inspire-competence', 7, skillId='skill.spellcraft'), effect('heroism')])
        self.assertEqual(next(s for s in result['skills'] if s['skillId'] == 'skill.spellcraft')['total'], 11)
        result = self.canonical([effect('inspire-heroics', 15), effect('heroism')])
        self.assertEqual((result['defenses']['ac'], result['defenses']['touch'], result['defenses']['flatFooted']), (17, 17, 10))
        self.assertEqual(result['cmd'], 17)
        self.assertEqual(result['defenses']['will'], 8)
        result = self.canonical([effect('rage', 1), effect('inspire-courage', 11)])
        self.assertTrue(any(m['stat'] == 'will' and m['bonus'] == 1 and 'fear' in m['condition'] for m in result['conditionalModifiers']))

    def test_finalization_and_both_exports_include_active_effects_and_escape_text(self):
        created = self.create(self.draft(effects=[effect('mage-armor', sourceName='<script>caster</script>', remainingDuration='2 hours')]))
        draft = created['draft']
        finalized = self.call('monster.finalize', {'draftId': draft['draftId'], 'baseRevision': draft['revision'], 'baseFingerprint': draft['fingerprint']})
        self.assertTrue(finalized['ok'], finalized)
        monster = finalized['result']['monster']
        self.assertEqual(monster['result'], created['evaluation']['canonical'])
        self.assertTrue(any(t['path'] == '/canonical/activeEffects' for t in created['evaluation']['derivationTrace']))
        for format_name in ('markdown', 'html'):
            response = self.call('monster.export', {'monsterId': monster['monsterId'], 'format': format_name, 'profile': 'sheet'})
            self.assertTrue(response['ok'], response)
            text = response['result']['content']
            self.assertIn('Active Effects', text)
            self.assertIn('Mage Armor', text)
            self.assertIn('2 hours', text)
            self.assertIn('AC 17, touch 13, flat-footed 14', text)
            self.assertNotIn('<script>caster</script>', text)

    def test_saved_profile_can_toggle_effects_without_changing_the_finished_snapshot(self):
        with tempfile.TemporaryDirectory() as workspace:
            self.engine = Engine(workspace=workspace)
            created = self.create(self.draft(effects=[effect('mage-armor')]))
            draft = created['draft']
            finalized = self.call('monster.finalize', {'draftId': draft['draftId'], 'baseRevision': draft['revision'], 'baseFingerprint': draft['fingerprint']})
            monster = finalized['result']['monster']
            duplicate = self.call('monster.duplicate', {'monsterId': monster['monsterId']})['result']['draft']
            changed = self.call('draft.applyChanges', {
                'draftId': duplicate['draftId'], 'baseRevision': duplicate['revision'], 'baseFingerprint': duplicate['fingerprint'],
                'changes': [{'changeId': 'off', 'type': 'set-selection', 'field': 'activeEffects', 'value': [effect('mage-armor', enabled=False)]}],
            })
            self.assertTrue(changed['ok'], changed)
            self.assertEqual(changed['result']['evaluation']['canonical']['defenses']['ac'], 13)
            self.engine = Engine(workspace=workspace)
            reloaded = self.call('draft.get', {'draftId': duplicate['draftId']})
            self.assertEqual(reloaded['result']['evaluation']['canonical']['defenses']['ac'], 13)
            saved = self.call('monster.get', {'monsterId': monster['monsterId']})
            self.assertEqual(saved['result']['monster'], monster)
            requirements = self.call('draft.choiceRequirements', {'draftId': duplicate['draftId']})['result']
            active = next(r for r in requirements['requirements'] if r['path'] == '/selections/activeEffects')
            self.assertFalse(active['required'])
            self.assertEqual(next(v for v in active['values'] if v['id'] == 'npc-effect.inspire-heroics')['minimumSourceLevel'], 15)
            for fmt in ('markdown', 'html'):
                text = self.call('monster.export', {'monsterId': monster['monsterId'], 'format': fmt, 'profile': 'audit'})['result']['content']
                self.assertIn('Active Effects', text)

    def test_routines_use_buffed_attacks_but_buffs_do_not_qualify_for_permanent_feats(self):
        draft = json.loads((ROOT / 'tests/fixtures/human-warrior-3.json').read_text())
        draft['selections']['feats'][-1]['featId'] = 'feat.power-attack'
        draft['selections']['activeEffects'] = [effect('rage', 1), effect('inspire-courage', 1)]
        result = self.create(draft)['evaluation']['canonical']
        self.assertEqual(result['attacks'][0]['attackBonuses'], [8])
        routine = next(r for r in result['combatRoutines'] if 'feat.power-attack' in r['feats'])
        self.assertEqual(routine['attacks'][0]['attackBonuses'], [7])
        self.assertEqual(routine['attacks'][0]['damageExpression'], '1d8+7')
        draft = self.draft('goblin-warrior', [effect('rage', 1)])
        draft['selections']['feats'][0]['featId'] = 'feat.power-attack'
        response = self.call('draft.create', {'draft': draft})
        self.assertTrue(response['ok'], response)
        self.assertEqual(response['result']['evaluation']['status'], 'invalid')

    def test_bad_effect_parameters_and_duplicates_are_rejected(self):
        cases = [effect('unknown'), effect('mage-armor', 0), effect('mage-armor', True),
                 effect('resist-energy'), effect('resist-energy', energyType='poison'),
                 effect('mage-armor', bonus=99), effect('mage-armor', enabled='yes'),
                 effect('inspire-heroics', 1), effect('mage-armor', energyType='fire')]
        for bad in cases:
            with self.subTest(effect=bad):
                self.assertFalse(self.call('draft.create', {'draft': self.draft(effects=[bad])})['ok'])
        self.assertFalse(self.call('draft.create', {'draft': self.draft(effects=[effect('shield'), effect('shield')])})['ok'])


if __name__ == '__main__':
    unittest.main()
