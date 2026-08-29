import tempfile
import unittest
from pathlib import Path

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
        if request["operation"] == "draft.choiceRequirements":
            return {"ok": True, "requestId": request["requestId"], "result": {"requirements": [{"path": "/selections/cr"}]}}
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
        self.assertEqual(seen[0]["choiceRequirements"]["requirements"][0]["path"], "/selections/cr")
        create = engine.calls[-1]
        self.assertEqual(create["operation"], "proposal.create")
        self.assertEqual(create["requestId"], "generate-1")
        self.assertEqual(create["payload"]["baseFingerprint"], "fingerprint-3")
        self.assertEqual(create["payload"]["model"], "test/model")

    def test_final_authoritative_validation_rejection_is_not_persisted(self):
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

        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "selection.type-invalid")
        self.assertEqual(len(inputs), 1)
        self.assertNotIn("proposal.create", [call["operation"] for call in engine.calls])

    def test_incomplete_candidate_from_runner_is_not_persisted(self):
        class EvaluationEngine(FakeEngine):
            def execute(self, request):
                if request["operation"] == "proposal.validate":
                    self.calls.append(request)
                    return {"ok": True, "requestId": request["requestId"], "result": {"evaluation": {
                        "status": "incomplete", "issues": [
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

        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "PROPOSAL_INVALID")
        self.assertEqual(len(inputs), 1)
        self.assertNotIn("proposal.create", [call["operation"] for call in engine.calls])

    def test_warning_candidate_from_runner_is_not_persisted(self):
        class WarningEngine(FakeEngine):
            def execute(self, request):
                if request["operation"] == "proposal.validate":
                    self.calls.append(request)
                    return {"ok": True, "requestId": request["requestId"], "result": {"evaluation": {
                        "status": "valid", "issues": [{
                            "code": "multiclass.cr-mismatch", "path": "/selections/cr",
                            "message": "class levels typically suggest CR 12, but selected CR is 9",
                            "severity": "warning",
                        }],
                    }}}
                return super().execute(request)

        engine = WarningEngine()
        adapter = PiProposalAdapter(engine, runner=lambda _value: {
            "proposal": {"changes": [], "rationale": "retain warning", "assumptions": [], "nonCanonicalSuggestions": []},
            "model": "test/model",
        })
        response = adapter.execute({
            "protocolVersion": "1", "requestId": "generate-warning", "operation": "proposal.generate",
            "payload": {"draftId": "draft-test", "concept": "CR 9 druid with three bard levels"},
        })

        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "PROPOSAL_INVALID")
        self.assertNotIn("proposal.create", [call["operation"] for call in engine.calls])

    def test_stdio_bridge_validates_inside_one_ephemeral_process(self):
        script_text = '''
import readline from "node:readline";
const lines = readline.createInterface({ input: process.stdin });
let started = false;
lines.on("line", (line) => {
  const message = JSON.parse(line);
  if (message.type === "start" && !started) {
    started = true;
    process.stdout.write(JSON.stringify({ type: "request", id: 1, method: "proposal_validate", payload: { proposal: { changes: [], rationale: "valid", assumptions: [], nonCanonicalSuggestions: [] } } }) + "\\n");
  } else if (message.type === "response" && message.id === 1) {
    if (message.value.result.evaluation.status !== "valid") process.exit(2);
    process.stdout.write(JSON.stringify({ type: "result", value: { ok: true, proposal: { changes: [], rationale: "valid", assumptions: [], nonCanonicalSuggestions: [] }, model: "test/model" } }) + "\\n");
  }
});
'''
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "fake-adapter.mjs"
            script.write_text(script_text, encoding="utf-8")
            engine = FakeEngine()
            response = PiProposalAdapter(engine, script=script, timeout=5).execute({
                "protocolVersion": "1", "requestId": "bridge", "operation": "proposal.generate",
                "payload": {"draftId": "draft-test", "concept": "Goblin"},
            })

        self.assertTrue(response["ok"], response)
        operations = [call["operation"] for call in engine.calls]
        self.assertGreaterEqual(operations.count("proposal.validate"), 2)
        self.assertEqual(operations.count("proposal.create"), 1)

    def test_runner_failure_never_calls_proposal_create(self):
        engine = FakeEngine()
        adapter = PiProposalAdapter(engine, runner=lambda _value: {"error": {"code": "AI_NOT_CONFIGURED", "message": "No model"}})
        response = adapter.execute({
            "protocolVersion": "1", "requestId": "generate-2", "operation": "proposal.generate",
            "payload": {"draftId": "draft-test", "concept": "Goblin"},
        })

        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "AI_NOT_CONFIGURED")
        self.assertEqual([call["operation"] for call in engine.calls], ["draft.get", "draft.choiceRequirements"])


if __name__ == "__main__":
    unittest.main()
