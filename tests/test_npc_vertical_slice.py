import copy
import json
import unittest
from pathlib import Path

from monster_builder import Engine


ROOT = Path(__file__).parents[1]
FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "human-warrior-3.json").read_text(encoding="utf-8"))


def request(request_id, operation, payload):
    return {
        "protocolVersion": "1",
        "requestId": request_id,
        "operation": operation,
        "payload": payload,
    }


class NpcVerticalSliceTests(unittest.TestCase):
    def test_production_catalog_builds_a_valid_human_warrior_three(self):
        computed = {
            "level", "totalLevel", "npcCategory", "abilityScores", "abilityModifiers", "hp", "bab",
            "defenses", "initiative", "attacks", "cmb", "cmd", "skills", "canonical", "effective",
            "derivationTrace", "evaluation",
        }
        self.assertFalse(computed.intersection(FIXTURE["selections"]))
        response = Engine().execute(request("human-warrior-3", "draft.create", {"draft": FIXTURE}))
        self.assertTrue(response["ok"], response)
        evaluation = response["result"]["evaluation"]
        self.assertEqual(evaluation["status"], "valid", evaluation["issues"])
        canonical = evaluation["canonical"]
        self.assertEqual(canonical["abilityScores"]["strength"], 15)
        self.assertEqual(canonical["bab"], 3)
        self.assertEqual(canonical["hp"], 19)
        self.assertEqual(canonical["defenses"]["ac"], 15)
        self.assertEqual(canonical["defenses"]["will"], 3)
        self.assertEqual(canonical["attacks"][0]["damageExpression"], "1d8+2")
        self.assertEqual(canonical["gearBudget"]["budgetCp"], 78000)
        self.assertTrue(all(entry["sourceRefs"] for entry in evaluation["derivationTrace"] if entry["path"].startswith("/canonical/")))

    def test_production_catalog_supports_human_warrior_levels_one_through_five(self):
        expected = {
            1: (1, 6, 26000),
            2: (2, 13, 39000),
            3: (3, 19, 78000),
            4: (4, 26, 165000),
            5: (5, 32, 240000),
        }
        for level, (bab, hp, budget_cp) in expected.items():
            draft = copy.deepcopy(FIXTURE)
            draft["concept"]["name"] = f"Human Warrior {level}"
            draft["selections"]["classProgression"][0]["levels"] = level
            if level == 2:
                draft["selections"]["abilityGeneration"] = {
                    "method": "assigned-array",
                    "arrayId": "npc-ability-array.basic",
                    "assignments": {
                        "strength": 13, "dexterity": 11, "constitution": 12,
                        "intelligence": 9, "wisdom": 10, "charisma": 8,
                    },
                }
            if level >= 4:
                draft["selections"]["abilityGeneration"]["levelIncreases"] = {"4": "strength"}
            allowed_slots = {"general-1", "human-bonus-feat"}
            if level >= 3:
                allowed_slots.add("general-3")
            if level >= 5:
                allowed_slots.add("general-5")
                draft["selections"]["feats"].append({"slotId": "general-5", "featId": "feat.lightning-reflexes"})
            draft["selections"]["feats"] = [feat for feat in draft["selections"]["feats"] if feat["slotId"] in allowed_slots]
            response = Engine().execute(request(f"human-warrior-{level}", "draft.create", {"draft": draft}))
            self.assertTrue(response["ok"], response)
            evaluation = response["result"]["evaluation"]
            self.assertEqual(evaluation["status"], "valid", (level, evaluation["issues"]))
            canonical = evaluation["canonical"]
            self.assertEqual((canonical["bab"], canonical["hp"], canonical["gearBudget"]["budgetCp"]), (bab, hp, budget_cp))

    def test_choice_requirements_expose_nested_npc_slots_and_budgets(self):
        response = Engine().execute(request("human-warrior-3-requirements", "draft.choiceRequirements", {"draft": FIXTURE}))
        self.assertTrue(response["ok"], response)
        result = response["result"]
        paths = {item["path"] for item in result["requirements"]}
        self.assertTrue({
            "/selections/raceId",
            "/selections/classProgression/0/classId",
            "/selections/classProgression/0/levels",
            "/selections/abilityGeneration/method",
            "/selections/skillGeneration/method",
            "/selections/skillGeneration/skills",
            "/selections/gearProfile/experienceProgression",
            "/selections/gearProfile/fantasyLevel",
            "/selections/gear",
        } <= paths)
        self.assertEqual(result["creationSystem"], "npc")
        self.assertIn("feats", result["selectionBudgets"])
        self.assertIn("gear", result["selectionBudgets"])
        self.assertEqual(result["selectionBudgets"]["gear"]["budgetCp"], 78000)

    def test_derived_values_are_rejected_as_draft_selections(self):
        draft = copy.deepcopy(FIXTURE)
        draft["selections"]["hp"] = 19
        response = Engine().execute(request("computed-selection", "draft.create", {"draft": draft}))
        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "draft.computed-selection")


if __name__ == "__main__":
    unittest.main()
