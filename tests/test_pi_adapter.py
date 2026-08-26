import unittest

from monster_builder.ai import PiProposalAdapter


class FakeEngine:
    def __init__(self):
        self.calls = []

    def execute(self, request):
        self.calls.append(request)
        if request["operation"] == "draft.get":
            return {"ok": True, "result": {"draft": {
                "draftId": "draft-test", "revision": 3, "fingerprint": "fingerprint-3",
                "catalogVersion": "catalog-1", "concept": {}, "selections": {},
            }}}
        if request["operation"] == "proposal.validate":
            return {"ok": True, "requestId": request["requestId"], "result": {"evaluation": {"status": "valid", "issues": []}}}
        return {"ok": True, "requestId": request["requestId"], "result": {"proposal": request["payload"]}}


class PiProposalAdapterTests(unittest.TestCase):
    def test_generate_binds_untrusted_output_to_the_authoritative_draft(self):
        engine = FakeEngine()
        seen = []
        adapter = PiProposalAdapter(engine, runner=lambda value: seen.append(value) or {
            "proposal": {"changes": [], "rationale": "Needs a CR", "assumptions": [], "nonCanonicalSuggestions": []},
            "model": "test/model",
        })
        response = adapter.execute({
            "protocolVersion": "1", "requestId": "generate-1", "operation": "proposal.generate",
            "payload": {"draftId": "draft-test", "concept": "A cautious goblin druid"},
        })

        self.assertTrue(response["ok"])
        self.assertEqual(seen[0]["draft"]["revision"], 3)
        create = engine.calls[-1]
        self.assertEqual(create["operation"], "proposal.create")
        self.assertEqual(create["requestId"], "generate-1")
        self.assertEqual(create["payload"]["baseFingerprint"], "fingerprint-3")
        self.assertEqual(create["payload"]["model"], "test/model")

    def test_engine_rejection_gets_one_bounded_repair_run(self):
        class RepairEngine(FakeEngine):
            def __init__(self):
                super().__init__()
                self.creates = 0

            def execute(self, request):
                if request["operation"] == "proposal.validate":
                    self.calls.append(request); self.creates += 1
                    if self.creates == 1:
                        return {"ok": False, "requestId": request["requestId"], "error": {"code": "selection.type-invalid", "message": "skills must contain master and good arrays", "path": "/payload/changes/0/value"}}
                    return {"ok": True, "requestId": request["requestId"], "result": {"evaluation": {"status": "valid", "issues": []}}}
                return super().execute(request)

        engine = RepairEngine()
        inputs = []
        adapter = PiProposalAdapter(engine, runner=lambda value: inputs.append(value) or {
            "proposal": {"changes": [], "rationale": "fixed", "assumptions": [], "nonCanonicalSuggestions": []}, "model": "test/model",
        })
        response = adapter.execute({
            "protocolVersion": "1", "requestId": "generate-repair", "operation": "proposal.generate",
            "payload": {"draftId": "draft-test", "concept": "Goblin"},
        })

        self.assertTrue(response["ok"])
        self.assertEqual(len(inputs), 2)
        self.assertEqual(inputs[1]["repair"]["error"]["code"], "selection.type-invalid")
        self.assertEqual(inputs[1]["repair"]["proposal"]["rationale"], "fixed")

    def test_incomplete_candidate_gets_all_findings_and_up_to_three_attempts(self):
        class EvaluationEngine(FakeEngine):
            def __init__(self):
                super().__init__(); self.validations = 0

            def execute(self, request):
                if request["operation"] == "proposal.validate":
                    self.calls.append(request); self.validations += 1
                    status = "valid" if self.validations == 3 else "incomplete"
                    return {"ok": True, "requestId": request["requestId"], "result": {"evaluation": {
                        "status": status,
                        "issues": [] if status == "valid" else [
                            {"code": "draft.missing-selection", "path": "/selections/cr", "message": "required selection is missing"},
                            {"code": "draft.missing-selection", "path": "/selections/speed", "message": "required selection is missing"},
                        ],
                    }}}
                return super().execute(request)

        engine = EvaluationEngine(); inputs = []
        adapter = PiProposalAdapter(engine, runner=lambda value: inputs.append(value) or {
            "proposal": {"changes": [], "rationale": f"attempt {len(inputs)}", "assumptions": [], "nonCanonicalSuggestions": []}, "model": "test/model",
        })
        response = adapter.execute({
            "protocolVersion": "1", "requestId": "generate-valid", "operation": "proposal.generate",
            "payload": {"draftId": "draft-test", "concept": "CR 7 ranger"},
        })

        self.assertTrue(response["ok"])
        self.assertEqual(len(inputs), 3)
        self.assertEqual(len(inputs[1]["repair"]["evaluation"]["issues"]), 2)
        self.assertEqual([call["operation"] for call in engine.calls].count("proposal.create"), 1)

    def test_runner_failure_never_calls_proposal_create(self):
        engine = FakeEngine()
        adapter = PiProposalAdapter(engine, runner=lambda _value: {"error": {"code": "AI_NOT_CONFIGURED", "message": "No model"}})
        response = adapter.execute({
            "protocolVersion": "1", "requestId": "generate-2", "operation": "proposal.generate",
            "payload": {"draftId": "draft-test", "concept": "Goblin"},
        })

        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "AI_NOT_CONFIGURED")
        self.assertEqual([call["operation"] for call in engine.calls], ["draft.get"])


if __name__ == "__main__":
    unittest.main()
