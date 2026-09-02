import copy
import json
import tempfile
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


class NpcLifecycleTests(unittest.TestCase):
    def test_production_npc_create_finalize_reload_and_export(self):
        with tempfile.TemporaryDirectory() as workspace:
            engine = Engine(workspace=workspace)
            created = engine.execute(request("npc-create", "draft.create", {"draft": copy.deepcopy(FIXTURE)}))
            self.assertTrue(created["ok"], created)
            draft = created["result"]["draft"]
            self.assertEqual(created["result"]["evaluation"]["status"], "valid")

            guard = {
                "draftId": draft["draftId"],
                "baseRevision": draft["revision"],
                "baseFingerprint": draft["fingerprint"],
            }
            finalized = engine.execute(request("npc-finalize", "monster.finalize", guard))
            self.assertTrue(finalized["ok"], finalized)
            monster = finalized["result"]["monster"]
            self.assertEqual(monster["creationSystem"], "npc")
            self.assertEqual(monster["result"]["hp"], 19)

            reloaded = Engine(workspace=workspace)
            loaded_draft = reloaded.execute(request("npc-reload-draft", "draft.get", {"draftId": draft["draftId"]}))
            loaded_monster = reloaded.execute(request("npc-reload-monster", "monster.get", {"monsterId": monster["monsterId"]}))
            self.assertTrue(loaded_draft["ok"], loaded_draft)
            self.assertTrue(loaded_monster["ok"], loaded_monster)
            self.assertEqual(loaded_draft["result"]["evaluation"]["status"], "valid")
            self.assertEqual(loaded_monster["result"]["monster"], monster)

            for format_name in ("json", "markdown", "html"):
                exported = reloaded.execute(request(f"npc-{format_name}", "monster.export", {
                    "monsterId": monster["monsterId"],
                    "format": format_name,
                }))
                self.assertTrue(exported["ok"], exported)
                self.assertTrue(exported["result"]["content"])


if __name__ == "__main__":
    unittest.main()
