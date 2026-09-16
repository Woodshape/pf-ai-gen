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
                         [([4], '1d4+1'), ([7], '1d4'), ([5, 5], '1d4')])
        self.assertEqual(draft['selections']['gear'][1], {'itemId': 'item.shortbow', 'masterwork': True})
        self.assertIn('potion of cure light wounds (CL 1, 1d8+1 hp)', draft['selections']['gear'])
        for item in draft['selections']['gear']:
            if isinstance(item, dict):
                self.assertFalse(item.get('properties'))
                self.assertFalse(item.get('enhancementBonus'))
