import copy
import json
import tempfile
import unittest
from pathlib import Path

from monster_builder import Engine


WORG_DRAFT = json.loads((Path(__file__).parent / "fixtures" / "worg-cr2.json").read_text())
MEDUSA_DRAFT = json.loads((Path(__file__).parent / "fixtures" / "medusa-cr7.json").read_text())
NPC_FIXTURE = json.loads((Path(__file__).parents[1] / "tests" / "fixtures" / "human-warrior-3.json").read_text())


def request(request_id, operation, payload):
    return {"protocolVersion": "1", "requestId": request_id, "operation": operation, "payload": payload}


def guard(draft):
    return {"draftId": draft["draftId"], "baseRevision": draft["revision"], "baseFingerprint": draft["fingerprint"]}


class FinishedMonsterTests(unittest.TestCase):
    def create(self, engine, raw=WORG_DRAFT, request_id="create"):
        response = engine.execute(request(request_id, "draft.create", {"draft": raw}))
        self.assertTrue(response["ok"], response)
        return response["result"]

    def finalize(self, engine, draft, request_id="finalize"):
        response = engine.execute(request(request_id, "monster.finalize", guard(draft)))
        self.assertTrue(response["ok"], response)
        return response["result"]

    def test_valid_draft_finalizes_to_immutable_reloadable_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = Engine(workspace=directory)
            created = self.create(engine)
            finished = self.finalize(engine, created["draft"])
            monster = finished["monster"]

            self.assertEqual(monster["kind"], "FinishedMonster")
            self.assertEqual(monster["status"], "active")
            self.assertEqual(monster["sourceDraft"], {
                "draftId": created["draft"]["draftId"],
                "revision": created["draft"]["revision"],
                "fingerprint": created["draft"]["fingerprint"],
            })
            self.assertEqual(monster["result"], created["evaluation"]["effective"])
            self.assertEqual(monster["derivationTrace"], created["evaluation"]["derivationTrace"])
            self.assertEqual(finished["draft"]["status"], "finalized")
            self.assertEqual(finished["draft"]["monsterId"], monster["monsterId"])

            loaded = Engine(workspace=directory).execute(request("get", "monster.get", {"monsterId": monster["monsterId"]}))
            self.assertTrue(loaded["ok"], loaded)
            self.assertEqual(loaded["result"]["monster"], monster)

            path = Path(directory) / "monsters" / f"{monster['monsterId']}.json"
            document = json.loads(path.read_text())
            self.assertEqual(document["status"], "active")
            self.assertNotIn("status", document["monster"])
            self.assertEqual(document["monster"]["result"]["attacks"][0]["damageExpression"], "1d6+7")

            blocked = engine.execute(request("edit-finalized", "draft.applyChanges", {
                **guard(finished["draft"]),
                "changes": [{"changeId": "speed", "type": "set-selection", "field": "speed", "value": {"land": 60}}],
            }))
            self.assertFalse(blocked["ok"])
            self.assertEqual(blocked["error"]["code"], "draft.not-active")

            archived_draft = engine.execute(request("archive-draft", "draft.archive", guard(finished["draft"])))
            self.assertTrue(archived_draft["ok"], archived_draft)
            restored_draft = Engine(workspace=directory).execute(request(
                "restore-draft", "draft.restore", guard(archived_draft["result"]["draft"]),
            ))
            self.assertTrue(restored_draft["ok"], restored_draft)
            self.assertEqual(restored_draft["result"]["draft"]["status"], "finalized")
            self.assertEqual(restored_draft["result"]["draft"]["monsterId"], monster["monsterId"])

    def test_finalization_is_idempotent_across_requests_and_crash_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = Engine(workspace=directory)
            created = self.create(engine)
            first = self.finalize(engine, created["draft"], "finalize-1")
            second = self.finalize(Engine(workspace=directory), created["draft"], "finalize-2")
            self.assertEqual(second["monster"], first["monster"])

            draft_path = Path(directory) / "drafts" / f"{created['draft']['draftId']}.json"
            document = json.loads(draft_path.read_text())
            document["status"] = "active"
            document["monsterId"] = None
            draft_path.write_text(json.dumps(document))
            recovered = self.finalize(Engine(workspace=directory), created["draft"], "finalize-recover")
            self.assertEqual(recovered["monster"]["monsterId"], first["monster"]["monsterId"])
            self.assertEqual(recovered["draft"]["status"], "finalized")
            self.assertEqual(len(list((Path(directory) / "monsters").glob("*.json"))), 1)

    def test_incomplete_and_invalid_drafts_cannot_finalize(self):
        engine = Engine()
        incomplete = self.create(engine, {}, "create-incomplete")["draft"]
        response = engine.execute(request("finalize-incomplete", "monster.finalize", guard(incomplete)))
        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "monster.finalization-blocked")
        self.assertEqual(response["error"]["details"]["evaluation"]["status"], "incomplete")

        invalid_raw = copy.deepcopy(MEDUSA_DRAFT)
        invalid_raw["selections"]["options"] = []
        invalid = self.create(engine, invalid_raw, "create-invalid")["draft"]
        response = engine.execute(request("finalize-invalid", "monster.finalize", guard(invalid)))
        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["details"]["evaluation"]["status"], "invalid")

    def test_monster_archive_restore_and_duplicate_preserve_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = Engine(workspace=directory)
            monster = self.finalize(engine, self.create(engine)["draft"])["monster"]
            path = Path(directory) / "monsters" / f"{monster['monsterId']}.json"
            original_snapshot = json.loads(path.read_text())["monster"]

            archived = engine.execute(request("archive-monster", "monster.archive", {"monsterId": monster["monsterId"]}))
            self.assertTrue(archived["ok"], archived)
            self.assertEqual(archived["result"]["monster"]["status"], "archived")
            self.assertEqual(json.loads(path.read_text())["monster"], original_snapshot)

            restored = Engine(workspace=directory).execute(request("restore-monster", "monster.restore", {"monsterId": monster["monsterId"]}))
            self.assertTrue(restored["ok"], restored)
            self.assertEqual(restored["result"]["monster"]["status"], "active")

            duplicated = Engine(workspace=directory).execute(request("duplicate-monster", "monster.duplicate", {"monsterId": monster["monsterId"]}))
            self.assertTrue(duplicated["ok"], duplicated)
            draft = duplicated["result"]["draft"]
            self.assertEqual(draft["revision"], 1)
            self.assertEqual(draft["status"], "active")
            self.assertEqual(draft["derivedFrom"], {"type": "monster", "monsterId": monster["monsterId"]})
            self.assertEqual(draft["concept"], monster["concept"])
            self.assertEqual(draft["selections"], monster["selections"])

    def test_orphaned_monster_recovery_after_source_draft_delete(self):
        """Web app recovery for a finished monster whose source draft was deleted:
        monster.duplicate rehomes an editable copy, monster.get reloads the original."""
        cases = ((WORG_DRAFT, "simple"), (NPC_FIXTURE, "npc"))
        for raw, name in cases:
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as directory:
                    engine = Engine(workspace=directory)
                    created = engine.execute(request("create", "draft.create", {"draft": copy.deepcopy(raw)}))
                    self.assertTrue(created["ok"], created)
                    finalized = engine.execute(request("finalize", "monster.finalize", guard(created["result"]["draft"])))
                    self.assertTrue(finalized["ok"], finalized)
                    monster = finalized["result"]["monster"]

                    deleted = Engine(workspace=directory).execute(request("delete", "draft.delete", {"draftId": created["result"]["draft"]["draftId"]}))
                    self.assertTrue(deleted["ok"], deleted)
                    orphaned = Engine(workspace=directory).execute(request("get", "draft.get", {"draftId": created["result"]["draft"]["draftId"]}))
                    self.assertEqual(orphaned["error"]["code"], "draft.not-found")

                    duplicated = Engine(workspace=directory).execute(request("duplicate", "monster.duplicate", {"monsterId": monster["monsterId"]}))
                    self.assertTrue(duplicated["ok"], duplicated)
                    self.assertEqual(duplicated["result"]["draft"]["concept"], monster["concept"])
                    self.assertEqual(duplicated["result"]["evaluation"]["status"], "valid")
                    loaded = Engine(workspace=directory).execute(request("reload", "monster.get", {"monsterId": monster["monsterId"]}))
                    self.assertTrue(loaded["ok"], loaded)
                    self.assertEqual(loaded["result"]["monster"], monster)

    def test_json_export_is_the_self_contained_finished_snapshot(self):
        engine = Engine()
        monster = self.finalize(engine, self.create(engine)["draft"])["monster"]
        exported = engine.execute(request("export-json", "monster.export", {
            "monsterId": monster["monsterId"], "format": "json", "profile": "audit",
        }))
        self.assertTrue(exported["ok"], exported)
        content = exported["result"]["content"]
        self.assertNotIn("status", content)
        self.assertEqual(content["monsterId"], monster["monsterId"])
        self.assertEqual(content["result"], monster["result"])
        self.assertEqual([entry["step"] for entry in content["audit"]["creationDecisions"]], list(range(1, 10)))
        self.assertTrue(content["audit"]["sources"])

    def test_markdown_and_html_exports_project_strict_medusa_snapshot(self):
        raw = copy.deepcopy(MEDUSA_DRAFT)
        raw["concept"]["name"] = "Medusa <script>"
        engine = Engine()
        monster = self.finalize(engine, self.create(engine, raw)["draft"])["monster"]
        payload = {"monsterId": monster["monsterId"], "format": "markdown", "profile": "audit"}
        first = engine.execute(request("markdown-1", "monster.export", payload))
        second = engine.execute(request("markdown-2", "monster.export", payload))
        self.assertTrue(first["ok"], first)
        self.assertEqual(first["result"]["content"], second["result"]["content"])
        markdown = first["result"]["content"]
        self.assertIn("Medusa <script> CR/HD 7", markdown)
        self.assertIn("## DEFENSES", markdown)
        self.assertIn("## ATTACKS", markdown)
        self.assertIn("2d8+12", markdown)
        self.assertNotIn("2d8+6", markdown)
        self.assertIn("## SPECIAL ABILITIES", markdown)
        self.assertIn("Gaze", markdown)
        self.assertIn("Poison", markdown)
        self.assertIn("## MONSTER CONCEPT", markdown)
        self.assertIn("## SOURCES", markdown)

        html = engine.execute(request("html", "monster.export", {
            "monsterId": monster["monsterId"], "format": "html", "profile": "sheet",
        }))["result"]["content"]
        self.assertIn("<!doctype html>", html)
        self.assertIn("@media print", html)
        self.assertIn("Medusa &lt;script&gt;", html)
        self.assertNotIn("MONSTER CONCEPT", html)
        self.assertIn("2d8+12", html)

        invalid = engine.execute(request("bad-export", "monster.export", {
            "monsterId": monster["monsterId"], "format": "pdf", "profile": "sheet",
        }))
        self.assertFalse(invalid["ok"])
        self.assertEqual(invalid["error"]["code"], "export.format-invalid")

    def test_tampered_finished_snapshot_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = Engine(workspace=directory)
            monster = self.finalize(engine, self.create(engine)["draft"])["monster"]
            path = Path(directory) / "monsters" / f"{monster['monsterId']}.json"
            document = json.loads(path.read_text())
            document["monster"]["result"]["defenses"]["hp"] = 999
            path.write_text(json.dumps(document))

            response = Engine(workspace=directory).execute(request("get-tampered", "monster.get", {"monsterId": monster["monsterId"]}))
            self.assertFalse(response["ok"])
            self.assertEqual(response["error"]["code"], "monster.fingerprint-invalid")


if __name__ == "__main__":
    unittest.main()
