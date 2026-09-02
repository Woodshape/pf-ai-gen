import copy
import json
import unittest
from pathlib import Path

from monster_builder import Engine
from monster_builder.exports import render_html, render_markdown, structured_sheet


ROOT = Path(__file__).parents[1]
FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "human-warrior-3.json").read_text(encoding="utf-8"))


def request(request_id, operation, payload):
    return {"protocolVersion": "1", "requestId": request_id, "operation": operation, "payload": payload}


class NpcExportTests(unittest.TestCase):
    def snapshot(self):
        engine = Engine()
        created = engine.execute(request("export-create", "draft.create", {"draft": copy.deepcopy(FIXTURE)}))
        self.assertTrue(created["ok"], created)
        draft = created["result"]["draft"]
        finalized = engine.execute(request("export-finalize", "monster.finalize", {
            "draftId": draft["draftId"],
            "baseRevision": draft["revision"],
            "baseFingerprint": draft["fingerprint"],
        }))
        self.assertTrue(finalized["ok"], finalized)
        snapshot = finalized["result"]["monster"]
        snapshot.pop("status")
        return snapshot

    def test_npc_projection_arranges_canonical_values_without_recalculation(self):
        snapshot = self.snapshot()
        original = copy.deepcopy(snapshot)
        model = structured_sheet(snapshot)

        self.assertEqual(model["creationSystem"], "npc")
        self.assertEqual(model["header"]["label"], "Human Warrior 3 Level 3")
        fields = {field["key"]: field for field in model["statistics"]["fields"]}
        for key in ("abilityScores", "bab", "classProgression", "feats", "gear", "languages"):
            self.assertEqual(fields[key]["value"], snapshot["result"][key])
        self.assertEqual(snapshot, original)

        markdown = render_markdown(snapshot, "audit")
        html = render_html(snapshot, "audit")
        for expected in ("Ability Scores Str 15", "BAB +3", "Class Progression Warrior 3", "Gear Longsword"):
            self.assertIn(expected, markdown)
            self.assertIn(expected, html)


if __name__ == "__main__":
    unittest.main()
