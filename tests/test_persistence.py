import copy
import hashlib
import json
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path

from monster_builder import Engine


WORG_DRAFT = json.loads((Path(__file__).parent / "fixtures" / "worg-cr2.json").read_text())


def request(request_id, operation, payload):
    return {
        "protocolVersion": "1",
        "requestId": request_id,
        "operation": operation,
        "payload": payload,
    }


def draft_fingerprint(draft):
    selections = copy.deepcopy(draft["selections"])
    selections["subtypeGraftIds"] = sorted(selections.get("subtypeGraftIds", []))
    for rank in ("master", "good"):
        if rank in selections.get("skills", {}):
            selections["skills"][rank] = sorted(selections["skills"][rank])
    value = {
        "schemaVersion": draft["schemaVersion"],
        "catalogVersion": draft["catalogVersion"],
        "concept": draft["concept"],
        "selections": selections,
    }
    if "creationSystem" in draft:
        value["creationSystem"] = draft["creationSystem"]
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


class JsonPersistenceTests(unittest.TestCase):
    def create(self, engine, request_id="create"):
        response = engine.execute(request(request_id, "draft.create", {"draft": WORG_DRAFT}))
        self.assertTrue(response["ok"], response)
        return response["result"]["draft"]

    @staticmethod
    def guard(draft):
        return {
            "draftId": draft["draftId"],
            "baseRevision": draft["revision"],
            "baseFingerprint": draft["fingerprint"],
        }

    def test_library_search_lists_active_drafts_and_finished_monsters(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = Engine(workspace=directory)
            finished_draft = self.create(engine, "finished-draft")
            finalized = engine.execute(request("finalize", "monster.finalize", self.guard(finished_draft)))
            self.assertTrue(finalized["ok"], finalized)
            monster = finalized["result"]["monster"]
            active = engine.execute(request("active-draft", "draft.create", {"draft": {
                "concept": {"name": "Work in progress", "targetCR": 2},
            }}))["result"]["draft"]

            response = engine.execute(request("library", "library.search", {}))

            self.assertTrue(response["ok"], response)
            draft_entry = response["result"]["drafts"][0]
            self.assertEqual({key: draft_entry[key] for key in ("kind", "id", "name", "cr", "role", "status", "revision")}, {
                "kind": "draft", "id": active["draftId"], "name": "Work in progress",
                "cr": 2, "role": "", "status": "active", "revision": 0,
            })
            self.assertIsInstance(draft_entry["savedAt"], str)
            datetime.fromisoformat(draft_entry["savedAt"].replace("Z", "+00:00"))

            monster_entry = response["result"]["monsters"][0]
            self.assertEqual({key: monster_entry[key] for key in ("kind", "id", "name", "cr", "role", "status", "revision", "sourceDraftId")}, {
                "kind": "monster", "id": monster["monsterId"], "name": "Worg",
                "cr": 2, "role": "feral hunter", "status": "active", "revision": finished_draft["revision"],
                "sourceDraftId": finished_draft["draftId"],
            })
            self.assertIsInstance(monster_entry["savedAt"], str)
            datetime.fromisoformat(monster_entry["savedAt"].replace("Z", "+00:00"))

    def test_library_search_orders_entries_newest_first(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = Engine(workspace=directory)
            first = self.create(engine, "first")
            time.sleep(0.01)
            second = self.create(engine, "second")
            time.sleep(0.01)
            third = self.create(engine, "third")

            response = engine.execute(request("library", "library.search", {}))

            self.assertTrue(response["ok"], response)
            draft_ids = [entry["id"] for entry in response["result"]["drafts"]]
            self.assertEqual(draft_ids[:3], [third["draftId"], second["draftId"], first["draftId"]])
            saved = [entry["savedAt"] for entry in response["result"]["drafts"][:3]]
            self.assertEqual(saved, sorted(saved, reverse=True))

    def test_delete_removes_drafts_and_finished_monsters(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = Engine(workspace=directory)
            draft = self.create(engine, "doomed")
            finalized = engine.execute(request("finalize", "monster.finalize", self.guard(draft)))
            self.assertTrue(finalized["ok"], finalized)
            monster_id = finalized["result"]["monster"]["monsterId"]
            other = self.create(engine, "survivor")

            deleted = engine.execute(request("draft-delete", "draft.delete", {"draftId": draft["draftId"]}))
            self.assertTrue(deleted["ok"], deleted)
            self.assertIsNone(deleted["result"])
            monster_deleted = engine.execute(request("monster-delete", "monster.delete", {"monsterId": monster_id}))
            self.assertTrue(monster_deleted["ok"], monster_deleted)

            gone = engine.execute(request("get-gone", "draft.get", {"draftId": draft["draftId"]}))
            self.assertFalse(gone["ok"])
            self.assertEqual(gone["error"]["code"], "draft.not-found")
            monster_gone = engine.execute(request("monster-gone", "monster.get", {"monsterId": monster_id}))
            self.assertFalse(monster_gone["ok"])
            self.assertEqual(monster_gone["error"]["code"], "monster.not-found")

            library = engine.execute(request("library", "library.search", {}))
            self.assertEqual([entry["id"] for entry in library["result"]["drafts"]], [other["draftId"]])
            self.assertEqual(library["result"]["monsters"], [])

            again = engine.execute(request("again", "draft.delete", {"draftId": draft["draftId"]}))
            self.assertFalse(again["ok"])
            self.assertEqual(again["error"]["code"], "draft.not-found")

            stale_ok = engine.execute(request("stale", "draft.get", {"draftId": other["draftId"]}))
            self.assertTrue(stale_ok["ok"], stale_ok)

    def test_create_apply_and_get_reload_across_engine_instances(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Engine(workspace=directory)
            draft = self.create(first)
            payload = self.guard(draft)
            payload["changes"] = [{
                "changeId": "speed",
                "type": "set-selection",
                "field": "speed",
                "value": {"land": 60},
            }]
            applied = first.execute(request("apply", "draft.applyChanges", payload))
            self.assertTrue(applied["ok"], applied)
            current = applied["result"]["draft"]

            second = Engine(workspace=directory)
            loaded = second.execute(request("get", "draft.get", {"draftId": current["draftId"]}))
            self.assertTrue(loaded["ok"], loaded)
            self.assertEqual(loaded["result"]["draft"], current)
            self.assertEqual(loaded["result"]["evaluation"], applied["result"]["evaluation"])

            path = Path(directory) / "drafts" / f"{current['draftId']}.json"
            persisted = json.loads(path.read_text())
            self.assertEqual(persisted["schemaVersion"], "1")
            self.assertEqual(persisted["current"]["revision"], 1)
            self.assertEqual(len(persisted["history"]), 1)
            self.assertNotIn("evaluation", persisted["current"]["draft"])

    def test_history_is_capped_and_restore_creates_new_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = Engine(workspace=directory)
            created = engine.execute(request("create", "draft.create", {"draft": {}}))
            self.assertTrue(created["ok"], created)
            draft = created["result"]["draft"]
            snapshots = {draft["revision"]: draft}
            for revision in range(1, 26):
                payload = self.guard(draft)
                payload["changes"] = [{
                    "changeId": f"speed-{revision}",
                    "type": "set-selection",
                    "field": "speed",
                    "value": {"land": 30 + revision},
                }]
                response = engine.execute(request(f"apply-{revision}", "draft.applyChanges", payload))
                self.assertTrue(response["ok"], response)
                draft = response["result"]["draft"]
                snapshots[draft["revision"]] = draft

            history = engine.execute(request("history", "draft.history.get", {"draftId": draft["draftId"]}))
            self.assertTrue(history["ok"], history)
            self.assertEqual(len(history["result"]["history"]), 20)
            self.assertEqual([entry["revision"] for entry in history["result"]["history"]], list(range(24, 4, -1)))

            payload = self.guard(draft)
            payload["revision"] = 10
            restored = engine.execute(request("restore", "draft.restoreRevision", payload))
            self.assertTrue(restored["ok"], restored)
            restored_draft = restored["result"]["draft"]
            self.assertEqual(restored_draft["revision"], 26)
            self.assertEqual(restored_draft["selections"]["speed"], {"land": 40})
            self.assertNotEqual(restored_draft["fingerprint"], draft["fingerprint"])

    def test_duplicate_is_new_active_draft_without_history(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = Engine(workspace=directory)
            source = self.create(engine)
            payload = self.guard(source)
            duplicated = engine.execute(request("duplicate", "draft.duplicate", payload))
            self.assertTrue(duplicated["ok"], duplicated)
            draft = duplicated["result"]["draft"]
            self.assertNotEqual(draft["draftId"], source["draftId"])
            self.assertEqual(draft["revision"], 1)
            self.assertEqual(draft["status"], "active")
            self.assertEqual(draft["derivedFrom"], {
                "type": "draft",
                "draftId": source["draftId"],
                "revision": source["revision"],
                "fingerprint": source["fingerprint"],
            })
            history = engine.execute(request("duplicate-history", "draft.history.get", {"draftId": draft["draftId"]}))
            self.assertTrue(history["ok"], history)
            self.assertEqual(history["result"]["history"], [])

            reloaded = Engine(workspace=directory).execute(request("duplicate-get", "draft.get", {"draftId": draft["draftId"]}))
            self.assertTrue(reloaded["ok"], reloaded)
            self.assertEqual(reloaded["result"]["draft"], draft)

    def test_archive_blocks_changes_and_restore_reactivates_draft(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = Engine(workspace=directory)
            draft = self.create(engine)
            archived = engine.execute(request("archive", "draft.archive", self.guard(draft)))
            self.assertTrue(archived["ok"], archived)
            archived_draft = archived["result"]["draft"]
            self.assertEqual(archived_draft["status"], "archived")
            self.assertEqual(archived_draft["revision"], draft["revision"])

            payload = self.guard(archived_draft)
            payload["changes"] = [{
                "changeId": "blocked",
                "type": "set-selection",
                "field": "speed",
                "value": {"land": 60},
            }]
            blocked = engine.execute(request("blocked", "draft.applyChanges", payload))
            self.assertFalse(blocked["ok"])
            self.assertEqual(blocked["error"]["code"], "draft.not-active")

            restored = Engine(workspace=directory).execute(request("restore", "draft.restore", self.guard(archived_draft)))
            self.assertTrue(restored["ok"], restored)
            self.assertEqual(restored["result"]["draft"]["status"], "active")
            self.assertEqual(restored["result"]["draft"]["fingerprint"], draft["fingerprint"])

            loaded = Engine(workspace=directory).execute(request("get", "draft.get", {"draftId": draft["draftId"]}))
            self.assertEqual(loaded["result"]["draft"]["status"], "active")

    def test_v1_file_without_root_status_defaults_to_active(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = Engine(workspace=directory)
            draft = self.create(engine)
            path = Path(directory) / "drafts" / f"{draft['draftId']}.json"
            document = json.loads(path.read_text())
            document.pop("status")
            document.pop("previousStatus")
            path.write_text(json.dumps(document))

            loaded = Engine(workspace=directory).execute(request("get", "draft.get", {"draftId": draft["draftId"]}))
            self.assertTrue(loaded["ok"], loaded)
            self.assertEqual(loaded["result"]["draft"]["status"], "active")

    def test_archive_winning_an_apply_race_blocks_the_content_write(self):
        with tempfile.TemporaryDirectory() as directory:
            editor = Engine(workspace=directory)
            archiver = Engine(workspace=directory)
            draft = self.create(editor)
            original_replace = editor._replace_draft

            def archive_then_replace(previous, candidate):
                archived = archiver.execute(request("archive", "draft.archive", self.guard(previous)))
                self.assertTrue(archived["ok"], archived)
                original_replace(previous, candidate)

            editor._replace_draft = archive_then_replace
            payload = self.guard(draft)
            payload["changes"] = [{
                "changeId": "speed",
                "type": "set-selection",
                "field": "speed",
                "value": {"land": 60},
            }]
            response = editor.execute(request("apply", "draft.applyChanges", payload))
            self.assertFalse(response["ok"])
            self.assertEqual(response["error"]["code"], "draft.revision-conflict")

            loaded = Engine(workspace=directory).execute(request("get", "draft.get", {"draftId": draft["draftId"]}))
            self.assertEqual(loaded["result"]["draft"]["status"], "archived")
            self.assertEqual(loaded["result"]["draft"]["selections"]["speed"], draft["selections"]["speed"])

    def test_same_mutation_request_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = Engine(workspace=directory)
            draft = self.create(engine)
            payload = self.guard(draft)
            payload["changes"] = [{
                "changeId": "speed",
                "type": "set-selection",
                "field": "speed",
                "value": {"land": 60},
            }]
            first = engine.execute(request("same-apply", "draft.applyChanges", payload))
            second = engine.execute(request("same-apply", "draft.applyChanges", copy.deepcopy(payload)))
            self.assertEqual(first, second)
            current = engine.execute(request("get", "draft.get", {"draftId": draft["draftId"]}))
            self.assertEqual(current["result"]["draft"]["revision"], 1)

    def test_corrupt_or_incompatible_file_is_a_visible_error(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = Engine(workspace=directory)
            draft = self.create(engine)
            path = Path(directory) / "drafts" / f"{draft['draftId']}.json"
            path.write_text("not json")
            response = Engine(workspace=directory).execute(request("corrupt", "draft.get", {"draftId": draft["draftId"]}))
            self.assertFalse(response["ok"])
            self.assertEqual(response["error"]["code"], "draft.file-corrupt")

            path.write_text(json.dumps({"schemaVersion": "2", "current": {}, "history": []}))
            response = Engine(workspace=directory).execute(request("incompatible", "draft.get", {"draftId": draft["draftId"]}))
            self.assertFalse(response["ok"])
            self.assertEqual(response["error"]["code"], "draft.file-schema-unsupported")

            path.write_bytes(b"\xff")
            response = Engine(workspace=directory).execute(request("encoding", "draft.get", {"draftId": draft["draftId"]}))
            self.assertFalse(response["ok"])
            self.assertEqual(response["error"]["code"], "draft.file-corrupt")

    def test_malformed_persisted_draft_is_a_visible_error(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = Engine(workspace=directory)
            draft = self.create(engine)
            path = Path(directory) / "drafts" / f"{draft['draftId']}.json"
            document = json.loads(path.read_text())
            document["current"]["draft"]["selections"] = []
            path.write_text(json.dumps(document))

            response = Engine(workspace=directory).execute(request("malformed", "draft.get", {"draftId": draft["draftId"]}))
            self.assertFalse(response["ok"])
            self.assertEqual(response["error"]["code"], "draft.file-corrupt")

    def test_old_catalog_draft_remains_loadable_but_not_evaluable(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = Engine(workspace=directory)
            draft = self.create(engine)
            path = Path(directory) / "drafts" / f"{draft['draftId']}.json"
            document = json.loads(path.read_text())
            persisted = document["current"]["draft"]
            persisted["catalogVersion"] = "old-catalog"
            persisted["fingerprint"] = draft_fingerprint(persisted)
            document["current"]["fingerprint"] = persisted["fingerprint"]
            path.write_text(json.dumps(document))

            loaded = Engine(workspace=directory).execute(request("get-old", "draft.get", {"draftId": draft["draftId"]}))
            self.assertTrue(loaded["ok"], loaded)
            self.assertEqual(loaded["result"]["draft"]["catalogVersion"], "old-catalog")
            self.assertIsNone(loaded["result"]["evaluation"])
            self.assertEqual(loaded["result"]["evaluationError"]["code"], "catalog.version-unsupported")

            evaluated = Engine(workspace=directory).execute(request("eval-old", "draft.evaluate", {"draftId": draft["draftId"]}))
            self.assertFalse(evaluated["ok"])
            self.assertEqual(evaluated["error"]["code"], "catalog.version-unsupported")

    def test_tampered_history_fingerprint_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = Engine(workspace=directory)
            draft = self.create(engine)
            payload = self.guard(draft)
            payload["changes"] = [{
                "changeId": "speed",
                "type": "set-selection",
                "field": "speed",
                "value": {"land": 60},
            }]
            current = engine.execute(request("apply", "draft.applyChanges", payload))["result"]["draft"]
            path = Path(directory) / "drafts" / f"{draft['draftId']}.json"
            document = json.loads(path.read_text())
            document["history"][0]["draft"]["concept"]["name"] = "tampered"
            path.write_text(json.dumps(document))

            response = Engine(workspace=directory).execute(request("get", "draft.get", {"draftId": current["draftId"]}))
            self.assertFalse(response["ok"])
            self.assertEqual(response["error"]["code"], "draft.fingerprint-invalid")


if __name__ == "__main__":
    unittest.main()
