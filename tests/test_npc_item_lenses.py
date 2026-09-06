import copy
import json
import unittest
from pathlib import Path

from monster_builder import Engine

ROOT = Path(__file__).parents[1]
FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "goblin-druid-3-fire.json").read_text(encoding="utf-8"))


def request(request_id, operation, payload):
    return {"protocolVersion": "1", "requestId": request_id, "operation": operation, "payload": payload}


class NpcItemLensTests(unittest.TestCase):
    def test_masterwork_and_enhancement_lenses_apply_to_weapons_armor_and_shields(self):
        draft = copy.deepcopy(FIXTURE)
        draft["selections"]["gear"] = [
            {"itemId": "item.sickle", "masterwork": True},
            {"itemId": "item.leather-armor", "masterwork": True},
            {"itemId": "item.heavy-wooden-shield", "enhancementBonus": 1},
        ]
        response = Engine().execute(request("lenses", "draft.create", {"draft": draft}))
        self.assertTrue(response["ok"], response)
        evaluation = response["result"]["evaluation"]
        self.assertEqual(evaluation["status"], "valid", evaluation["issues"])
        gear = {entry["itemId"]: entry for entry in evaluation["canonical"]["gear"]}

        sickle = gear["item.sickle"]
        self.assertEqual((sickle["name"], sickle["priceCp"], sickle["effects"]["attackBonus"], sickle["lenses"]), ("mwk sickle", 30600, 1, {"masterwork": True}))
        armor = gear["item.leather-armor"]
        self.assertEqual((armor["priceCp"], armor["effects"]["armorBonus"], armor["effects"]["armorCheckPenalty"]), (16000, 2, 0))
        shield = gear["item.heavy-wooden-shield"]
        self.assertEqual((shield["name"], shield["priceCp"], shield["effects"]["shieldBonus"], shield["effects"]["armorCheckPenalty"], shield["lenses"]), ("+1 Heavy Wooden Shield", 215700, 3, -1, {"masterwork": True, "enhancementBonus": 1}))

    def test_enhancement_lens_is_limited_to_plus_five(self):
        draft = copy.deepcopy(FIXTURE)
        draft["selections"]["gear"] = [{"itemId": "item.sickle", "enhancementBonus": 6}]
        response = Engine().execute(request("bad-lens", "draft.create", {"draft": draft}))
        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "selection.value-invalid")


if __name__ == "__main__":
    unittest.main()
