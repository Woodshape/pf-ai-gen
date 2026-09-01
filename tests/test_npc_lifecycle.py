import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from monster_builder import CatalogRegistry, Engine
from monster_builder.__main__ import validate_file
from tests.test_npc_vertical_slice import ResolvedNpcCatalog, request, valid_test_draft


class NpcLifecycleTests(unittest.TestCase):
    @staticmethod
    def engine(workspace):
        npc_catalog = ResolvedNpcCatalog()
        registry = CatalogRegistry(loaders={"npc": lambda: npc_catalog})
        return Engine(workspace=workspace, catalogs=registry)

    @staticmethod
    def guard(draft):
        return {
            "draftId": draft["draftId"],
            "baseRevision": draft["revision"],
            "baseFingerprint": draft["fingerprint"],
        }

    def test_npc_persistence_history_finalization_library_and_exports(self):
        with tempfile.TemporaryDirectory() as workspace:
            first = self.engine(workspace)
            created = first.execute(request("npc-create", "draft.create", {"draft": valid_test_draft()}))
            self.assertTrue(created["ok"], created)
            draft = created["result"]["draft"]
            self.assertEqual(draft["creationSystem"], "npc")
            self.assertEqual(draft["catalogVersion"], "npc-test-catalog")

            proposal_created = first.execute(request("npc-proposal-create", "proposal.create", {
                **self.guard(draft),
                "catalogVersion": draft["catalogVersion"],
                "changes": [{
                    "changeId": "description",
                    "type": "set-concept",
                    "field": "description",
                    "value": "Changed for history",
                }],
                "rationale": "Exercise shared NPC proposal persistence.",
            }))
            self.assertTrue(proposal_created["ok"], proposal_created)
            proposal = proposal_created["result"]["proposal"]
            self.assertEqual(proposal["catalogVersion"], "npc-test-catalog")
            changed = first.execute(request("npc-proposal-accept", "proposal.accept", {
                "proposalId": proposal["proposalId"],
                "changeIds": ["description"],
                "confirmation": {"actor": "user", "confirmed": True},
            }))
            self.assertTrue(changed["ok"], changed)
            draft = changed["result"]["draft"]
            history = first.execute(request("npc-history", "draft.history.get", {"draftId": draft["draftId"]}))
            self.assertTrue(history["ok"], history)
            self.assertEqual(history["result"]["history"][0]["draft"]["creationSystem"], "npc")
            self.assertEqual(history["result"]["history"][0]["draft"]["catalogVersion"], "npc-test-catalog")

            restored = first.execute(request("npc-restore-revision", "draft.restoreRevision", {
                **self.guard(draft), "revision": 0,
            }))
            self.assertTrue(restored["ok"], restored)
            draft = restored["result"]["draft"]
            self.assertEqual(
                draft["concept"]["description"],
                "A level 3 human warrior built from the class-based NPC workflow.",
            )
            self.assertEqual(restored["result"]["evaluation"]["status"], "valid")

            duplicated = first.execute(request("npc-duplicate", "draft.duplicate", self.guard(draft)))
            self.assertTrue(duplicated["ok"], duplicated)
            duplicate = duplicated["result"]["draft"]
            self.assertEqual(duplicate["creationSystem"], "npc")
            self.assertEqual(duplicate["catalogVersion"], "npc-test-catalog")
            archived = first.execute(request("npc-draft-archive", "draft.archive", self.guard(duplicate)))
            self.assertTrue(archived["ok"], archived)
            duplicate = archived["result"]["draft"]
            restored_duplicate = first.execute(request("npc-draft-restore", "draft.restore", self.guard(duplicate)))
            self.assertTrue(restored_duplicate["ok"], restored_duplicate)

            finalized = first.execute(request("npc-finalize", "monster.finalize", self.guard(draft)))
            self.assertTrue(finalized["ok"], finalized)
            monster = finalized["result"]["monster"]
            self.assertEqual(monster["creationSystem"], "npc")
            self.assertEqual(monster["catalogVersion"], "npc-test-catalog")
            self.assertEqual(monster["result"]["level"], 3)

            repeated = first.execute(request("npc-finalize-again", "monster.finalize", self.guard(draft)))
            self.assertTrue(repeated["ok"], repeated)
            self.assertEqual(repeated["result"]["monster"], monster)

            # Immutable finished snapshots remain readable without their old
            # catalog, while drafts are never silently reinterpreted.
            unsupported = Engine(workspace=workspace)
            unsupported_draft = unsupported.execute(request("npc-old-catalog-draft", "draft.get", {
                "draftId": draft["draftId"],
            }))
            self.assertTrue(unsupported_draft["ok"], unsupported_draft)
            self.assertIsNone(unsupported_draft["result"]["evaluation"])
            self.assertEqual(
                unsupported_draft["result"]["evaluationError"]["code"],
                "catalog.version-unsupported",
            )
            unsupported_monster = unsupported.execute(request("npc-old-catalog-monster", "monster.get", {
                "monsterId": monster["monsterId"],
            }))
            self.assertTrue(unsupported_monster["ok"], unsupported_monster)
            rejected_copy = unsupported.execute(request("npc-old-catalog-copy", "monster.duplicate", {
                "monsterId": monster["monsterId"],
            }))
            self.assertFalse(rejected_copy["ok"])
            self.assertEqual(rejected_copy["error"]["code"], "catalog.version-unsupported")

            second = self.engine(workspace)
            loaded_proposal = second.execute(request("npc-proposal-reload", "proposal.get", {
                "proposalId": proposal["proposalId"],
            }))
            self.assertTrue(loaded_proposal["ok"], loaded_proposal)
            self.assertEqual(loaded_proposal["result"]["proposal"], proposal)
            loaded = second.execute(request("npc-reload", "draft.get", {"draftId": draft["draftId"]}))
            self.assertTrue(loaded["ok"], loaded)
            self.assertEqual(loaded["result"]["draft"]["creationSystem"], "npc")
            self.assertEqual(loaded["result"]["evaluation"]["effective"], finalized["result"]["monster"]["result"])

            found = second.execute(request("npc-library", "library.search", {"query": "Human Warrior"}))
            self.assertTrue(found["ok"], found)
            self.assertTrue(found["result"]["drafts"])
            for draft_row in found["result"]["drafts"]:
                self.assertEqual(draft_row["creationSystem"], "npc")
                self.assertEqual(draft_row["catalogVersion"], "npc-test-catalog")
                self.assertEqual(draft_row["level"], 3)
            monster_row = next(row for row in found["result"]["monsters"] if row["id"] == monster["monsterId"])
            self.assertEqual(monster_row["creationSystem"], "npc")
            self.assertEqual(monster_row["catalogVersion"], "npc-test-catalog")
            self.assertEqual(monster_row["level"], 3)
            self.assertIsNone(monster_row["cr"])

            json_export = second.execute(request("npc-json", "monster.export", {
                "monsterId": monster["monsterId"], "format": "json",
            }))
            self.assertTrue(json_export["ok"], json_export)
            self.assertEqual(json_export["result"]["content"]["creationSystem"], "npc")
            self.assertNotIn("status", json_export["result"]["content"])

            markdown = second.execute(request("npc-markdown", "monster.export", {
                "monsterId": monster["monsterId"], "format": "markdown", "profile": "audit",
            }))
            self.assertTrue(markdown["ok"], markdown)
            text = markdown["result"]["content"]
            for expected in (
                "# Human Warrior 3 Level 3", "Ability Scores Str 13", "BAB +3",
                "Class Progression Warrior 3", "Feats Improved Initiative, Power Attack",
                "Gear Longsword", "Languages Common", "CREATION DECISIONS: STEPS 1–8",
            ):
                self.assertIn(expected, text)
            self.assertNotIn("CR None", text)

            html = second.execute(request("npc-html", "monster.export", {
                "monsterId": monster["monsterId"], "format": "html",
            }))
            self.assertTrue(html["ok"], html)
            self.assertIn("Human Warrior 3 Level 3", html["result"]["content"])
            self.assertIn("Class Progression Warrior 3", html["result"]["content"])

            monster_copy = second.execute(request("npc-monster-duplicate", "monster.duplicate", {
                "monsterId": monster["monsterId"],
            }))
            self.assertTrue(monster_copy["ok"], monster_copy)
            self.assertEqual(monster_copy["result"]["draft"]["creationSystem"], "npc")
            archived_monster = second.execute(request("npc-monster-archive", "monster.archive", {
                "monsterId": monster["monsterId"],
            }))
            self.assertTrue(archived_monster["ok"], archived_monster)
            restored_monster = second.execute(request("npc-monster-restore", "monster.restore", {
                "monsterId": monster["monsterId"],
            }))
            self.assertTrue(restored_monster["ok"], restored_monster)

            monster_path = Path(workspace) / "monsters" / f"{monster['monsterId']}.json"
            document = json.loads(monster_path.read_text(encoding="utf-8"))
            document["monster"]["result"]["hp"] += 1
            monster_path.write_text(json.dumps(document), encoding="utf-8")
            tampered = self.engine(workspace).execute(request("npc-tampered", "monster.get", {
                "monsterId": monster["monsterId"],
            }))
            self.assertFalse(tampered["ok"])
            self.assertEqual(tampered["error"]["code"], "monster.fingerprint-invalid")

    def test_cli_validates_finished_npc_json(self):
        engine = self.engine(None)
        created = engine.execute(request("cli-npc-create", "draft.create", {"draft": valid_test_draft()}))
        self.assertTrue(created["ok"], created)
        draft = created["result"]["draft"]
        finalized = engine.execute(request("cli-npc-finalize", "monster.finalize", self.guard(draft)))
        self.assertTrue(finalized["ok"], finalized)
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "finished-npc.json"
            path.write_text(json.dumps(finalized["result"]["monster"]), encoding="utf-8")
            stdout = io.StringIO()
            with patch("monster_builder.__main__.Engine", lambda: self.engine(None)):
                with contextlib.redirect_stdout(stdout):
                    exit_code = validate_file(str(path))
        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(stdout.getvalue())["status"], "valid")

    def test_cli_validation_preserves_npc_creation_system(self):
        value = valid_test_draft()
        value["selections"] = copy.deepcopy(value["selections"])
        value["selections"]["level"] = 3
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "npc.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exit_code = validate_file(str(path))
        self.assertEqual(exit_code, 4)
        self.assertIn('"code": "draft.computed-selection"', stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
