import copy
import json
import unittest
from pathlib import Path

from monster_builder import Engine


WORG = json.loads((Path(__file__).parent / "fixtures" / "worg-cr2.json").read_text())


def request(request_id, payload):
    return {
        "protocolVersion": "1",
        "requestId": request_id,
        "operation": "draft.choiceRequirements",
        "payload": payload,
    }


class ChoiceRequirementTests(unittest.TestCase):
    def test_system_provides_ranger_and_graveknight_controls(self):
        draft = copy.deepcopy(WORG)
        draft["selections"].update({
            "cr": 15,
            "classGraftId": "graft.class.ranger",
            "templateGraftId": "graft.template.graveknight",
            "classGraftChoices": {},
            "templateGraftChoices": {},
            "graftOptionChoices": {},
        })

        response = Engine().execute(request("requirements", {"draft": draft}))

        self.assertTrue(response["ok"], response)
        requirements = {item["path"]: item for item in response["result"]["requirements"]}
        automatic_skills = response["result"]["automaticSelections"]["skills"]
        self.assertEqual(response["result"]["selectionBudgets"]["skills"], {"master": 0, "good": 2})
        self.assertEqual(
            [(item["value"], item["label"]) for item in automatic_skills["master"]],
            [("skill.intimidate", "Intimidate"), ("skill.perception", "Perception"), ("skill.ride", "Ride")],
        )
        self.assertTrue(all(item["sourceRefs"] for item in automatic_skills["master"]))
        self.assertEqual(automatic_skills["good"], [])
        favored = requirements["/selections/classGraftChoices/favoredEnemyTargets"]
        self.assertEqual((favored["type"], favored["minCount"], favored["maxCount"]), ("enum-array", 4, 4))
        self.assertIn("graft.creature-type.undead", {item["value"] for item in favored["values"]})
        secondary = requirements["/selections/graftOptionChoices/graft.class.ranger/option.secondary-magic/spellListId"]
        self.assertEqual(secondary["type"], "enum")
        self.assertIn("Nature", {item["label"] for item in secondary["values"]})
        energy = requirements["/selections/templateGraftChoices/energyType"]
        self.assertEqual({item["value"] for item in energy["values"]}, {"acid", "cold", "electricity", "fire"})
        self.assertTrue(energy["sourceRefs"])
        self.assertNotIn("/selections/graftOptionChoices/graft.template.graveknight/option.breath-weapon/shape", requirements)
        self.assertNotIn("/selections/graftOptionChoices/graft.template.graveknight/option.channel-destruction/energyType", requirements)

        evaluated = Engine().execute({
            "protocolVersion": "1", "requestId": "evaluate", "operation": "draft.create", "payload": {"draft": draft},
        })["result"]["evaluation"]
        issue_paths = {issue["path"] for issue in evaluated["issues"]}
        self.assertIn("/selections/templateGraftChoices/energyType", issue_paths)
        self.assertNotIn("/selections/graftOptionChoices/graft.template.graveknight/option.breath-weapon/shape", issue_paths)
        self.assertNotIn("/selections/graftOptionChoices/graft.class.ranger/option.favored-enemy/targets", issue_paths)

    def test_every_catalogued_dynamic_schema_normalizes_to_supported_types(self):
        engine = Engine()
        catalog = engine.catalog.data
        requirements = []
        graft_groups = (
            ("classGraftId", catalog["grafts"]["classGrafts"]),
            ("templateGraftId", catalog["grafts"]["templates"]),
        )
        for field, records in graft_groups:
            for graft_id in records:
                draft = copy.deepcopy(WORG)
                draft["selections"].update({"cr": 20, field: graft_id})
                response = engine.execute(request(f"schema-{field}-{graft_id}", {"draft": draft}))
                self.assertTrue(response["ok"], response)
                requirements.extend(response["result"]["requirements"])
        for subtype_id in catalog["grafts"]["subtypes"]:
            draft = copy.deepcopy(WORG)
            draft["selections"].update({"cr": 20, "subtypeGraftIds": [subtype_id]})
            response = engine.execute(request(f"schema-subtype-{subtype_id}", {"draft": draft}))
            self.assertTrue(response["ok"], response)
            requirements.extend(response["result"]["requirements"])
        for option_id in catalog["options"]:
            draft = copy.deepcopy(WORG)
            draft["selections"]["options"] = [{"optionId": option_id, "parameters": {}}]
            response = engine.execute(request(f"schema-option-{option_id}", {"draft": draft}))
            self.assertTrue(response["ok"], response)
            requirements.extend(response["result"]["requirements"])
        for spell_list in catalog["spellLists"].values():
            draft = copy.deepcopy(WORG)
            draft["selections"]["spellListId"] = spell_list["id"]
            response = engine.execute(request(f"schema-spell-list-{spell_list['id']}", {"draft": draft}))
            self.assertTrue(response["ok"], response)
            requirements.extend(response["result"]["requirements"])

        self.assertTrue(requirements)
        self.assertLessEqual(
            {item["type"] for item in requirements},
            {"enum", "enum-array", "string", "string-array", "integer"},
        )
        self.assertTrue(all("path" in item and "label" in item and "required" in item for item in requirements))

    def test_persisted_draft_and_external_draft_use_same_interface(self):
        engine = Engine()
        created = engine.execute({
            "protocolVersion": "1", "requestId": "create", "operation": "draft.create", "payload": {"draft": WORG},
        })["result"]["draft"]

        persisted = engine.execute(request("persisted", {"draftId": created["draftId"]}))
        external = engine.execute(request("external", {"draft": WORG}))

        self.assertTrue(persisted["ok"], persisted)
        self.assertEqual(persisted["result"]["requirements"], external["result"]["requirements"])
        self.assertEqual(external["result"]["automaticSelections"]["skills"]["good"], [{
            "value": "skill.perception", "label": "Perception",
        }])
        self.assertEqual(persisted["result"]["basis"]["revision"], created["revision"])
        self.assertEqual(persisted["result"]["basis"]["fingerprint"], created["fingerprint"])

        preview = engine.execute(request("preview", {
            "draftId": created["draftId"],
            "selectionOverrides": {"cr": 15, "classGraftId": "graft.class.ranger"},
        }))
        self.assertTrue(preview["ok"], preview)
        self.assertIn(
            "/selections/classGraftChoices/favoredEnemyTargets",
            {item["path"] for item in preview["result"]["requirements"]},
        )
        reloaded = engine.execute({
            "protocolVersion": "1", "requestId": "reload", "operation": "draft.get",
            "payload": {"draftId": created["draftId"]},
        })
        self.assertEqual(reloaded["result"]["draft"], created)


if __name__ == "__main__":
    unittest.main()
