import copy
import json
import tempfile
import unittest
from pathlib import Path

from monster_builder import Engine
from test_npc_composition import draft_for, evaluate

ROOT = Path(__file__).parents[1]


class StatblockRulesTests(unittest.TestCase):
    def test_warchanter_base_statblock(self):
        draft = json.loads((ROOT / 'docs/goblin-warchanter-draft.json').read_text())
        result = evaluate(draft)
        self.assertEqual(result['status'], 'valid', result['issues'])
        npc = result['canonical']
        self.assertEqual(npc['hp'], 9)
        self.assertEqual(npc['cr'], '1/2')
        self.assertEqual(npc['spells']['concentration'], 2)
        self.assertEqual(npc['defenses']['ac'], 18)
        self.assertEqual(npc['languages'], ['Goblin', 'Common'])
        skills = {entry['name']: entry['total'] for entry in npc['skills']}
        self.assertEqual(skills, {'Acrobatics': 7, 'Linguistics': 3, 'Perception': 5,
                                 'Perform (sing)': 5, 'Stealth': 15, 'Ride': 7})
        attacks = {entry['name']: entry for entry in npc['attacks']}
        self.assertEqual(attacks['Dogslicer']['attackBonuses'], [0])
        self.assertEqual(attacks['Dogslicer']['damageExpression'], '1d4-1')
        self.assertEqual(attacks['Whip']['attackBonuses'], [0])
        self.assertEqual(attacks['Shortbow']['attackBonuses'], [5])
        self.assertEqual(attacks['Shortbow']['damageExpression'], '1d4-1')
        self.assertTrue(attacks['Whip']['nonlethal'])
        features = {entry['featureId']: entry for entry in npc['classFeatures']}
        self.assertEqual(features['npc-class-feature.bardic-performance']['roundsPerDay'], 5)
        self.assertFalse(npc.get('conditionalSaves'))

    def test_three_classes_require_precise_but_precise_build_works(self):
        catalog = json.loads((ROOT / 'catalog/npc.json').read_text())
        draft = draft_for(catalog, 'npc-race.goblin', 'npc-class.bard', 1)
        selections = draft['selections']
        selections['classProgression'] += [{'classId': 'npc-class.warrior', 'levels': 1},
                                          {'classId': 'npc-class.rogue', 'levels': 1}]
        selections['feats'].append({'slotId': 'general-3', 'featId': 'feat.iron-will'})
        result = evaluate(draft)
        self.assertIn('npc.simplified-skills-multiclass', {i['code'] for i in result['issues']})
        # Int 13: bard 7 + warrior 3 + rogue 9 = 19 ranks, at most 3 per skill.
        selections['skillGeneration'] = {'method': 'precise', 'ranks': dict(zip(
            ['skill.acrobatics', 'skill.bluff', 'skill.climb', 'skill.linguistics',
             'skill.perform', 'skill.stealth', 'skill.perception'], [3, 3, 3, 3, 3, 3, 1]))}
        result = evaluate(draft)
        self.assertEqual(result['status'], 'valid', result['issues'])
        response = Engine().execute({'protocolVersion': '1', 'requestId': 'precise-budget',
                                     'operation': 'draft.choiceRequirements', 'payload': {'draft': draft}})
        self.assertTrue(response['ok'], response)
        self.assertEqual(response['result']['selectionBudgets']['skills']['rankBudget'], 19)
        self.assertEqual(response['result']['selectionBudgets']['skills']['maxRanks'], 3)
        method = next(entry for entry in response['result']['requirements'] if entry['path'] == '/selections/skillGeneration/method')
        self.assertEqual(method['values'], ['precise'])
        selections['skillGeneration']['ranks']['skill.acrobatics'] = 4
        self.assertIn('npc.skill-ranks-invalid', {i['code'] for i in evaluate(draft)['issues']})

    def test_basic_npc_cr_steps_below_one(self):
        catalog = json.loads((ROOT / 'catalog/npc.json').read_text())
        for level, cr in ((1, '1/3'), (2, '1/2'), (3, 1)):
            result = evaluate(draft_for(catalog, 'npc-race.human', 'npc-class.warrior', level))
            self.assertEqual(result['status'], 'valid', result['issues'])
            self.assertEqual(result['canonical']['cr'], cr)

    def test_non_class_skill_is_legal_without_class_bonus(self):
        catalog = json.loads((ROOT / 'catalog/npc.json').read_text())
        draft = draft_for(catalog, 'npc-race.goblin', 'npc-class.bard', 1)
        draft['selections']['skillGeneration']['skills'][0] = 'skill.ride'
        result = evaluate(draft)
        self.assertEqual(result['status'], 'valid', result['issues'])
        skill = next(s for s in result['canonical']['skills'] if s['skillId'] == 'skill.ride')
        self.assertEqual((skill['ranks'], skill['classSkill'], skill['total']), (1, False, 9))

    def test_spell_list_metadata_suffices_without_description(self):
        catalog = json.loads((ROOT / 'catalog/npc.json').read_text())
        draft = draft_for(catalog, 'npc-race.goblin', 'npc-class.bard', 1)
        draft['selections']['spellLoadout']['known']['1'] = ['spell.hideous-laughter', 'spell.alarm']
        result = evaluate(draft)
        self.assertEqual(result['status'], 'valid', result['issues'])
        draft['selections']['spellLoadout']['known']['1'][0] = 'spell.fireball'
        self.assertIn('npc.spell-level-invalid', {i['code'] for i in evaluate(draft)['issues']})

    def test_descriptive_equipment_has_no_mechanical_effects(self):
        catalog = json.loads((ROOT / 'catalog/npc.json').read_text())
        draft = draft_for(catalog, 'npc-race.goblin', 'npc-class.bard', 1)
        baseline = evaluate(draft)['canonical']
        draft['selections']['gear'] = ['painted mask', 'potion of cure light wounds', '+5 armor (carried only)']
        result = evaluate(draft)
        self.assertEqual(result['status'], 'valid', result['issues'])
        self.assertEqual(result['canonical']['defenses'], baseline['defenses'])
        self.assertEqual(result['canonical']['attacks'], baseline['attacks'])
        self.assertEqual(result['canonical']['gearBudget']['spentCp'], 0)
        self.assertTrue(all(not item['mechanical'] for item in result['canonical']['gear']))

    def test_proficiency_is_weapon_targeted_not_a_character_exception(self):
        draft = json.loads((ROOT / 'docs/goblin-warchanter-draft.json').read_text())
        for weapon in (None, 'item.whip', 'item.studded-leather-armor'):
            with self.subTest(weapon=weapon):
                candidate = copy.deepcopy(draft)
                if weapon is None:
                    candidate['selections']['feats'][0].pop('weaponId')
                else:
                    candidate['selections']['feats'][0]['weaponId'] = weapon
                self.assertIn('npc.feat-weapon-invalid', {i['code'] for i in evaluate(candidate)['issues']})
        candidate = copy.deepcopy(draft)
        candidate['selections']['feats'][0]['weaponId'] = 'item.battleaxe'
        self.assertIn('npc.catalog-gap', {i['code'] for i in evaluate(candidate)['issues']})
        catalog = json.loads((ROOT / 'catalog/npc.json').read_text())
        human = draft_for(catalog, 'npc-race.human', 'npc-class.bard', 1)
        for feat, weapon in zip(human['selections']['feats'], ['item.longbow', 'item.shortbow']):
            feat.update(featId='feat.martial-weapon-proficiency', weaponId=weapon)
        result = evaluate(human)
        self.assertEqual(result['status'], 'valid', result['issues'])
        human['selections']['feats'][1]['weaponId'] = 'item.longbow-plus-1'
        self.assertIn('npc.feat-duplicate', {i['code'] for i in evaluate(human)['issues']})
        draft['selections']['feats'] = [{'slotId': 'general-1', 'featId': 'feat.improved-initiative'}]
        result = evaluate(draft)
        self.assertEqual(result['status'], 'valid', result['issues'])
        attacks = {entry['name']: entry for entry in result['canonical']['attacks']}
        self.assertEqual(attacks['Dogslicer']['attackBonuses'], [-4])
        self.assertEqual(attacks['Whip']['attackBonuses'], [0])
        self.assertEqual(attacks['Shortbow']['attackBonuses'], [5])

    def test_nonproficient_armor_penalizes_weapon_and_feature_attacks(self):
        draft = json.loads((ROOT / 'tests/fixtures/goblin-sorcerer-6.json').read_text())
        draft['selections']['gear'] = [{'itemId': 'item.sickle'}]
        baseline = evaluate(draft)['canonical']
        draft['selections']['gear'].append({'itemId': 'item.chainmail'})
        result = evaluate(draft)
        self.assertEqual(result['status'], 'valid', result['issues'])
        for before, after in zip(baseline['attacks'], result['canonical']['attacks']):
            self.assertEqual(after['attackBonuses'], [bonus - 5 for bonus in before['attackBonuses']])
            self.assertEqual(after['damageExpression'], before['damageExpression'])

    def test_knowledge_and_language_choices_use_actual_ranks(self):
        draft = json.loads((ROOT / 'docs/goblin-warchanter-draft.json').read_text())
        draft['selections']['skillGeneration']['includeUntrained'].append('skill.knowledge-arcana')
        result = evaluate(draft)
        self.assertEqual(result['status'], 'valid', result['issues'])
        skill = next(entry for entry in result['canonical']['skills'] if entry['skillId'] == 'skill.knowledge-arcana')
        self.assertEqual((skill['ranks'], skill['total'], skill['classFeatureBonus']), (0, 0, 1))
        for languages in (['Common', 'Elven'], ['Goblin'], ['Druidic']):
            draft['selections']['skillGeneration']['languages'] = languages
            self.assertIn('npc.language-choice-invalid', {i['code'] for i in evaluate(draft)['issues']})

    def test_warchanter_finalizes_reloads_and_exports_without_active_buffs(self):
        draft = json.loads((ROOT / 'docs/goblin-warchanter-draft.json').read_text())
        with tempfile.TemporaryDirectory() as workspace:
            engine = Engine(workspace=workspace)
            def execute(operation, payload):
                response = engine.execute({'protocolVersion': '1', 'requestId': operation + str(payload.get('format', '')),
                                           'operation': operation, 'payload': payload})
                self.assertTrue(response['ok'], response)
                return response['result']
            created = execute('draft.create', {'draft': draft})
            self.assertEqual(execute('draft.choiceRequirements', {'draft': draft})['selectionBudgets']['skills']['rankBudget'], 5)
            saved = created['draft']
            monster = execute('monster.finalize', {'draftId': saved['draftId'], 'baseRevision': saved['revision'],
                                                'baseFingerprint': saved['fingerprint']})['monster']
            engine = Engine(workspace=workspace)
            self.assertEqual(execute('monster.get', {'monsterId': monster['monsterId']})['monster'], monster)
            for format_name in ('json', 'markdown', 'html'):
                exported = execute('monster.export', {'monsterId': monster['monsterId'], 'format': format_name})
                content = exported['content']
                if format_name == 'markdown':
                    for expected in ('Goblin Warchanter CR 1/2/Level 1', 'concentration +2', 'Dogslicer +0 (1d4-1/19-20)', 'Shortbow +5 (1d4-1/x3)', 'nonlethal',
                                     'Stealth +15', 'Ride +7', 'Bardic performance (5 rounds/day)', 'potion of cure light wounds'):
                        self.assertIn(expected, content)
                    self.assertNotIn('gp in coins and gear', content)


if __name__ == '__main__':
    unittest.main()
