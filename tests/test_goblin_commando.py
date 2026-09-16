import json
import unittest
from pathlib import Path

from monster_builder import Engine


class GoblinCommandoTests(unittest.TestCase):
    def test_standard_equipment_recalculates_without_magic_weapon_bonuses(self):
        snapshot = json.loads((Path(__file__).parents[1] / 'docs/goblin-commando.json').read_text())
        draft = {key: snapshot[key] for key in ('creationSystem', 'concept', 'selections', 'mode')}
        response = Engine().execute({'protocolVersion': '1', 'requestId': 'commando',
                                     'operation': 'draft.create', 'payload': {'draft': draft}})
        self.assertTrue(response['ok'], response)
        evaluation = response['result']['evaluation']
        self.assertEqual(evaluation['status'], 'valid')
        result = evaluation['canonical']
        self.assertEqual(result['cr'], 1)
        self.assertEqual([(a['attackBonuses'], a['damageExpression']) for a in result['attacks']],
                         [([4], '1d4+1'), ([7], '1d4+1'), ([5, 5], '1d4+1')])
        self.assertEqual(draft['selections']['gear'][1], {'itemId': 'item.composite-shortbow-strength-1', 'masterwork': True})
        self.assertIn('potion of cure light wounds (CL 1, 1d8+1 hp)', draft['selections']['gear'])
        for item in draft['selections']['gear']:
            if isinstance(item, dict):
                self.assertFalse(item.get('properties'))
                self.assertFalse(item.get('enhancementBonus'))
        # Swap scores to preserve the required heroic array. Wisdom/Charisma
        # only donate scores; bow damage uses Strength after the goblin -2.
        # Below the bow's +1 rating: -2 attack; negative Strength reduces damage.
        import copy
        for ability, expected_strength, damage in [('wisdom', 10, '1d4'), ('charisma', 8, '1d4-1')]:
            changed = copy.deepcopy(draft)
            assignments = changed['selections']['abilityGeneration']['assignments']
            assignments['strength'], assignments[ability] = assignments[ability], assignments['strength']
            response = Engine().execute({'protocolVersion': '1', 'requestId': ability,
                                         'operation': 'draft.create', 'payload': {'draft': changed}})
            self.assertTrue(response['ok'], response)
            evaluation = response['result']['evaluation']
            self.assertEqual(evaluation['status'], 'valid', evaluation)
            result = evaluation['canonical']
            self.assertEqual(result['abilityScores']['strength'], expected_strength)
            bow = result['attacks'][1]
            self.assertEqual((bow['attackBonuses'], bow['damageExpression']), ([5], damage))
        changed = copy.deepcopy(draft)
        changed['selections']['activeEffects'] = [{'effectId': 'npc-effect.rage', 'sourceLevel': 1}]
        response = Engine().execute({'protocolVersion': '1', 'requestId': 'rage',
                                     'operation': 'draft.create', 'payload': {'draft': changed}})
        bow = response['result']['evaluation']['canonical']['attacks'][1]
        self.assertEqual(bow['damageExpression'], '1d4+1')
