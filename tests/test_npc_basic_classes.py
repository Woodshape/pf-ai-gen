import json
import unittest
from pathlib import Path

from monster_builder import Engine

ROOT = Path(__file__).parents[1]


def request(request_id, operation, payload):
    return {
        "protocolVersion": "1",
        "requestId": request_id,
        "operation": operation,
        "payload": payload,
    }


def fixture(name):
    return json.loads((ROOT / "tests" / "fixtures" / name).read_text(encoding="utf-8"))


class NpcBasicClassTests(unittest.TestCase):
    def test_public_basic_fixtures_use_engine_and_preserve_catalog_gaps(self):
        for index, name in enumerate((
            "npc-commoner-1.json",
            "npc-expert-5.json",
            "npc-multiclass.json",
            "npc-aristocrat-multiclass.json",
            "npc-adept.json",
        )):
            response = Engine().execute(request(f"basic-{index}", "draft.create", {"draft": fixture(name)}))
            self.assertTrue(response["ok"], response)
            evaluation = response["result"]["evaluation"]
            self.assertEqual(evaluation["status"], "invalid", name)
            self.assertTrue(any(issue["code"] == "npc.catalog-gap" for issue in evaluation["issues"]), name)
            self.assertTrue(all(issue.get("sourceRefs") for issue in evaluation["issues"] if issue["kind"] == "catalog-data"), name)

    def test_three_classes_require_precise_skills_through_execute(self):
        draft = fixture("npc-multiclass.json")
        draft["selections"]["classProgression"].append({"classId": "npc-class.warrior", "levels": 1})
        draft["selections"]["skillGeneration"] = {"method": "simplified", "skills": []}
        response = Engine().execute(request("three-class", "draft.create", {"draft": draft}))
        self.assertTrue(response["ok"], response)
        codes = {issue["code"] for issue in response["result"]["evaluation"]["issues"]}
        self.assertIn("npc.simplified-skills-multiclass", codes)

    def test_target_cr_is_not_derived_into_basic_npc_statistics(self):
        draft = fixture("npc-commoner-1.json")
        draft["concept"]["targetCR"] = 12
        response = Engine().execute(request("target-cr", "draft.create", {"draft": draft}))
        self.assertTrue(response["ok"], response)
        canonical = response["result"]["evaluation"]["canonical"]
        self.assertIsNone(canonical)
        self.assertNotIn("recommendedCR", draft["selections"])

    def test_racial_choice_and_computed_selection_boundaries_are_public(self):
        draft = fixture("npc-commoner-1.json")
        draft["selections"]["racialChoices"] = {"size": "small"}
        draft["selections"]["details"]["ac"] = 20
        response = Engine().execute(request("computed-details", "draft.create", {"draft": draft}))
        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "draft.computed-selection")


if __name__ == "__main__":
    unittest.main()
