import copy
import json
import tempfile
import unittest
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


class ProposalTests(unittest.TestCase):
    @staticmethod
    def guard(draft):
        return {
            "draftId": draft["draftId"],
            "baseRevision": draft["revision"],
            "baseFingerprint": draft["fingerprint"],
            "catalogVersion": draft["catalogVersion"],
        }

    def create_draft(self, engine):
        response = engine.execute(request("draft", "draft.create", {"draft": WORG_DRAFT}))
        self.assertTrue(response["ok"], response)
        return response["result"]["draft"]

    def test_accept_applies_only_selected_change_ids_and_keeps_proposal_immutable(self):
        engine = Engine()
        draft = self.create_draft(engine)
        payload = self.guard(draft)
        payload.update({
            "changes": [
                {"changeId": "speed", "type": "set-selection", "field": "speed", "value": {"land": 60}},
                {"changeId": "name", "type": "set-concept", "field": "name", "value": "Swift Worg"},
            ],
            "rationale": "Offer two independent edits.",
        })
        proposal = engine.execute(request("proposal-create", "proposal.create", payload))["result"]["proposal"]

        accepted = engine.execute(request("proposal-accept", "proposal.accept", {
            "proposalId": proposal["proposalId"],
            "changeIds": ["speed"],
            "confirmation": {"actor": "user", "confirmed": True},
        }))
        self.assertTrue(accepted["ok"], accepted)
        changed = accepted["result"]["draft"]
        self.assertEqual(changed["revision"], 1)
        self.assertEqual(changed["selections"]["speed"], {"land": 60})
        self.assertEqual(changed["concept"], draft["concept"])
        self.assertEqual(accepted["result"]["acceptedChangeIds"], ["speed"])
        self.assertEqual(accepted["result"]["proposal"], proposal)

        fetched = engine.execute(request("proposal-get", "proposal.get", {"proposalId": proposal["proposalId"]}))
        self.assertEqual(fetched["result"]["proposal"], proposal)
        stale = engine.execute(request("proposal-stale", "proposal.accept", {
            "proposalId": proposal["proposalId"],
            "changeIds": ["name"],
            "confirmation": {"actor": "user", "confirmed": True},
        }))
        self.assertFalse(stale["ok"])
        self.assertEqual(stale["error"]["code"], "draft.revision-conflict")
        current = engine.execute(request("draft-get", "draft.get", {"draftId": draft["draftId"]}))
        self.assertEqual(current["result"]["draft"]["revision"], 1)
        self.assertNotEqual(current["result"]["draft"]["concept"]["name"], "Swift Worg")

    def test_accept_requires_user_confirmation_and_leaves_draft_unchanged_on_failure(self):
        engine = Engine()
        draft = self.create_draft(engine)
        proposal = engine.execute(request("proposal-create", "proposal.create", {
            **self.guard(draft),
            "changes": [{"changeId": "speed", "type": "set-selection", "field": "speed", "value": {"land": 60}}],
        }))["result"]["proposal"]
        for confirmation in ({}, {"actor": "ai", "confirmed": True}, {"actor": "user", "confirmed": False}):
            response = engine.execute(request(f"reject-{len(confirmation)}", "proposal.accept", {
                "proposalId": proposal["proposalId"],
                "changeIds": ["speed"],
                "confirmation": confirmation,
            }))
            self.assertFalse(response["ok"], response)
            self.assertEqual(response["error"]["code"], "proposal.confirmation-required")
        current = engine.execute(request("draft-get", "draft.get", {"draftId": draft["draftId"]}))
        self.assertEqual(current["result"]["draft"], draft)

    def test_create_rejects_unknown_ids_and_invalid_paths_without_mutating_draft(self):
        engine = Engine()
        draft = self.create_draft(engine)
        before = copy.deepcopy(draft)
        cases = [
            ({"changeId": "unknown", "type": "set-selection", "field": "arrayId", "value": "array.nope"}, "catalog.unknown-id"),
            ({"changeId": "computed", "type": "set-selection", "field": "ac", "value": 99}, "change.field-invalid"),
            ({"changeId": "nested", "type": "set-selection", "path": "/selections/options/0/optionId", "value": "option.blind-fight"}, "change.path-invalid"),
        ]
        for index, (change, code) in enumerate(cases):
            response = engine.execute(request(f"bad-proposal-{index}", "proposal.create", {
                **self.guard(draft), "changes": [change],
            }))
            self.assertFalse(response["ok"], response)
            self.assertEqual(response["error"]["code"], code)
        current = engine.execute(request("draft-get", "draft.get", {"draftId": draft["draftId"]}))
        self.assertEqual(current["result"]["draft"], before)

    def test_create_requires_an_active_draft(self):
        engine = Engine()
        draft = self.create_draft(engine)
        archived = engine.execute(request("archive", "draft.archive", self.guard(draft)))["result"]["draft"]
        response = engine.execute(request("proposal-archived", "proposal.create", {
            **self.guard(archived),
            "changes": [],
        }))
        self.assertFalse(response["ok"], response)
        self.assertEqual(response["error"]["code"], "draft.not-active")

    def test_validate_returns_candidate_evaluation_without_persisting(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = Engine(workspace=directory)
            draft = engine.execute(request("empty-draft", "draft.create", {"draft": {}}))["result"]["draft"]
            validated = engine.execute(request("proposal-validate", "proposal.validate", {
                **self.guard(draft),
                "changes": [{"changeId": "cr", "type": "set-selection", "field": "cr", "value": 7}],
            }))

            self.assertTrue(validated["ok"], validated)
            self.assertEqual(validated["result"]["evaluation"]["status"], "incomplete")
            self.assertIn("draft.missing-selection", {issue["code"] for issue in validated["result"]["evaluation"]["issues"]})
            self.assertEqual(validated["result"]["candidateDraft"]["selections"]["cr"], 7)
            self.assertFalse((Path(directory) / "proposals").exists())

    def test_create_preserves_optional_model_metadata(self):
        engine = Engine()
        draft = self.create_draft(engine)
        created = engine.execute(request("proposal-model", "proposal.create", {
            **self.guard(draft),
            "model": "openai-codex/gpt-5.6-luna",
            "changes": [],
        }))
        self.assertTrue(created["ok"], created)
        self.assertEqual(created["result"]["proposal"]["model"], "openai-codex/gpt-5.6-luna")

    def test_create_and_get_persist_immutable_proposal_without_mutating_draft(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = Engine(workspace=directory)
            draft = self.create_draft(engine)
            before = copy.deepcopy(draft)
            payload = self.guard(draft)
            payload.update({
                "changes": [{
                    "changeId": "speed-change",
                    "type": "set-selection",
                    "field": "speed",
                    "value": {"land": 60},
                    "rationale": "A swift hunter.",
                    "sourceRefs": [{"sourceId": "pathfinder-unchained"}],
                }],
                "rationale": "Suggest a faster worg.",
                "assumptions": ["The concept calls for a mobile hunter."],
                "nonCanonicalSuggestions": ["Optional: add a cinematic howl."],
            })

            created = engine.execute(request("proposal-create", "proposal.create", payload))
            self.assertTrue(created["ok"], created)
            proposal = created["result"]["proposal"]
            self.assertTrue(proposal["proposalId"].startswith("proposal-"))
            self.assertEqual(proposal["draftId"], draft["draftId"])
            self.assertEqual(proposal["baseRevision"], draft["revision"])
            self.assertEqual(proposal["baseFingerprint"], draft["fingerprint"])
            self.assertEqual(proposal["catalogVersion"], draft["catalogVersion"])
            self.assertEqual(proposal["changes"][0]["changeId"], "speed-change")
            self.assertEqual(proposal["changes"][0]["rationale"], "A swift hunter.")

            fetched = Engine(workspace=directory).execute(request(
                "proposal-get", "proposal.get", {"proposalId": proposal["proposalId"]},
            ))
            self.assertTrue(fetched["ok"], fetched)
            self.assertEqual(fetched["result"]["proposal"], proposal)

            current = engine.execute(request("draft-get", "draft.get", {"draftId": draft["draftId"]}))
            self.assertTrue(current["ok"], current)
            self.assertEqual(current["result"]["draft"], before)


if __name__ == "__main__":
    unittest.main()
