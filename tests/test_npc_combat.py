"""Shared routine arithmetic and public Engine integration."""
import copy
import json
import unittest
from pathlib import Path

from monster_builder.npc.combat import calculate_routine
from test_npc_composition import draft_for, evaluate

ROOT = Path(__file__).resolve().parents[1]


class NpcCombatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((ROOT / "catalog/npc.json").read_text())

    def warrior(self, level=16):
        draft = draft_for(self.catalog, "npc-race.human", "npc-class.warrior", level)
        draft["selections"]["gear"] = [{"itemId": "item.longbow"}, {"itemId": "item.longsword"},
                                          {"itemId": "item.shortsword"}, {"itemId": "item.greatsword"}]
        return draft

    def valid(self, draft):
        result = evaluate(draft)
        self.assertEqual(result["status"], "valid", result["issues"])
        return result["canonical"]

    def test_full_attack_thresholds_and_gear_rows_via_engine(self):
        for level in (6, 11, 16, 20):
            base = self.valid(self.warrior(level))
            self.assertEqual(len(base["attacks"][0]["attackBonuses"]), 1 + (level - 1) // 5)
            self.assertEqual(base["gearBudget"]["level"], level)
        self.assertEqual(base["gearBudget"]["budgetCp"], 12300000)

    def test_ranged_composition_and_incompatible_actions_via_engine(self):
        draft = self.warrior(6)
        draft["selections"]["feats"] = [
            {"slotId": "general-1", "featId": "feat.point-blank-shot"},
            {"slotId": "human-bonus-1", "featId": "feat.rapid-shot"},
            {"slotId": "general-3", "featId": "feat.deadly-aim"},
            {"slotId": "general-5", "featId": "feat.iron-will"},
        ]
        # Race slot IDs are catalogued, not hard-coded character gates.
        draft["selections"]["feats"][1]["slotId"] = self.catalog["races"]["npc-race.human"]["featSlots"][0]["slotId"]
        base = self.valid(draft)
        draft["selections"]["combatOptions"] = [{"weaponId": "item.longbow", "action": "full-attack",
            "options": ["feat.rapid-shot", "feat.deadly-aim", "feat.point-blank-shot"]}]
        result = self.valid(draft)
        self.assertEqual(result["attacks"], base["attacks"])
        routine = next(row for row in result["combatRoutines"] if row.get("selected"))
        self.assertEqual(routine["attacks"][0]["attackBonuses"], [5, 5, 0])
        self.assertEqual(routine["attacks"][0]["damageExpression"], "1d8+5")
        self.assertTrue(routine["sourceRefs"])
        draft["selections"]["combatOptions"][0]["action"] = "attack"
        result = evaluate(draft)
        self.assertIn("npc.combat-option-invalid", {issue["code"] for issue in result["issues"]})

    def test_shared_damage_hand_and_vital_strike_math(self):
        base = self.valid(self.warrior())
        items, attacks = base["gear"], base["attacks"]
        original = copy.deepcopy((items, attacks))
        modifiers = {**base["abilityModifiers"], "strength": 1}
        owned = ["feat.power-attack", "feat.two-weapon-fighting", "feat.improved-two-weapon-fighting", "feat.greater-two-weapon-fighting",
                 "feat.vital-strike", "feat.improved-vital-strike", "feat.greater-vital-strike"]
        request = {"weaponId": "item.longsword", "offHandWeaponId": "item.shortsword", "action": "full-attack",
                   "options": ["feat.two-weapon-fighting", "feat.power-attack"]}
        routine = calculate_routine(items, attacks, owned, 16, modifiers, request)
        self.assertEqual([len(line["attackBonuses"]) for line in routine["attacks"]], [4, 3])
        self.assertEqual(routine["attacks"][0]["damageExpression"], "1d8+11")
        self.assertEqual(routine["attacks"][1]["damageExpression"], "1d6+5")
        sliced = calculate_routine(items, attacks, owned + ["feat.double-slice"], 16, modifiers, request)
        self.assertEqual(sliced["attacks"][1]["damageExpression"], "1d6+6")
        shield = {"category": "armor", "effects": {"shieldCategory": "shield", "shieldBonus": 1}}
        with self.assertRaisesRegex(ValueError, "shield-equipped"):
            calculate_routine([*items, shield], attacks, owned, 16, modifiers, request)
        for feat, dice in (("feat.vital-strike", 4), ("feat.improved-vital-strike", 6), ("feat.greater-vital-strike", 8)):
            request = {"weaponId": "item.greatsword", "action": "attack", "options": [feat, "feat.power-attack"]}
            routine = calculate_routine(items, attacks, owned, 16, modifiers, request)
            self.assertEqual(routine["attacks"][0]["damageExpression"], f"{dice}d6+16")
            self.assertEqual(len(routine["attacks"][0]["attackBonuses"]), 1)
            self.assertTrue(routine["state"]["extraDiceNotMultipliedOnCritical"])
            request["action"] = "full-attack"
            with self.assertRaises(ValueError):
                calculate_routine(items, attacks, owned, 16, modifiers, request)
        self.assertEqual((items, attacks), original)

    def test_manyshot_keeps_per_arrow_damage_and_rejects_non_bows(self):
        base = self.valid(self.warrior())
        request = {"weaponId": "item.longbow", "action": "full-attack", "options": ["feat.rapid-shot", "feat.manyshot", "feat.deadly-aim"]}
        routine = calculate_routine(base["gear"], base["attacks"], request["options"], 16, base["abilityModifiers"], request)
        self.assertEqual(len(routine["attacks"][0]["attackBonuses"]), 5)
        self.assertEqual(routine["attacks"][0]["firstAttackProjectiles"], 2)
        self.assertEqual(routine["attacks"][0]["damageExpression"], "1d8+10")
        request["weaponId"] = "item.longsword"
        with self.assertRaises(ValueError):
            calculate_routine(base["gear"], base["attacks"], request["options"], 16, base["abilityModifiers"], request)


if __name__ == "__main__":
    unittest.main()
