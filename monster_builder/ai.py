"""Optional Pi SDK concept-to-Proposal adapter."""

from __future__ import annotations

import json
import select
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from .engine import Engine


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = Path(__file__).with_name("pi_adapter.mjs")
CATALOG = ROOT / "catalog" / "catalog.json"


class PiProposalAdapter:
    """Bind untrusted Pi output to an authoritative Draft and proposal.create."""

    def __init__(
        self,
        engine: Engine,
        *,
        runner: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        timeout: float = 360,
        script: str | Path = SCRIPT,
    ) -> None:
        self.engine = engine
        self.timeout = timeout
        self.script = Path(script)
        self.runner = runner or self._run_pi

    def execute(self, request: dict[str, Any]) -> dict[str, Any]:
        request_id = request.get("requestId") if isinstance(request, dict) else None
        if not isinstance(request, dict) or request.get("protocolVersion") != "1" or request.get("operation") != "proposal.generate":
            return self._error(request_id, "request.invalid", "Expected a protocolVersion 1 proposal.generate request.", "/operation")
        payload = request.get("payload")
        if not isinstance(payload, dict):
            return self._error(request_id, "payload.invalid", "payload must be an object", "/payload")
        draft_id, concept = payload.get("draftId"), payload.get("concept")
        if not isinstance(draft_id, str) or not draft_id:
            return self._error(request_id, "draft.id-required", "draftId is required", "/payload/draftId")
        if not isinstance(concept, str) or not concept.strip() or len(concept) > 20_000:
            return self._error(request_id, "concept.invalid", "concept must be a non-empty string of at most 20,000 characters", "/payload/concept")

        loaded = self.engine.execute({
            "protocolVersion": "1", "requestId": f"{request_id}:draft.get",
            "operation": "draft.get", "payload": {"draftId": draft_id},
        })
        if not loaded.get("ok"):
            return {**loaded, "requestId": request_id}
        draft = loaded.get("result", {}).get("draft")
        if not isinstance(draft, dict):
            return self._error(request_id, "DRAFT_CONFLICT", "Draft could not be loaded for proposal generation.", "/payload/draftId", kind="conflict")

        choices = self.engine.execute({
            "protocolVersion": "1", "requestId": f"{request_id}:choice-requirements",
            "operation": "draft.choiceRequirements", "payload": {"draftId": draft_id},
        })
        if not choices.get("ok"):
            return {**choices, "requestId": request_id}
        adapter_input = {
            "draft": draft, "concept": concept.strip(), "choiceRequirements": choices.get("result", {}),
            "catalogPath": str(CATALOG), "cwd": str(ROOT), "requestId": request_id,
        }
        generated, error_response = self._invoke(adapter_input, request_id)
        if error_response:
            return error_response
        proposal = generated["proposal"]
        proposal_payload = {
            "draftId": draft["draftId"], "baseRevision": draft["revision"],
            "baseFingerprint": draft["fingerprint"], "catalogVersion": draft["catalogVersion"],
            "changes": proposal.get("changes"), "rationale": proposal.get("rationale"),
            "assumptions": proposal.get("assumptions", []),
            "nonCanonicalSuggestions": proposal.get("nonCanonicalSuggestions", []),
            "model": generated.get("model"),
        }
        validated = self.engine.execute({
            "protocolVersion": "1", "requestId": f"{request_id}:final-validation",
            "operation": "proposal.validate", "payload": proposal_payload,
        })
        if not validated.get("ok"):
            return validated
        evaluation = validated.get("result", {}).get("evaluation")
        if not isinstance(evaluation, dict) or evaluation.get("status") != "valid" or evaluation.get("issues"):
            return self._error(
                request_id, "PROPOSAL_INVALID", "Pi emitted a Proposal that did not pass final authoritative validation without findings.",
                details={"evaluation": evaluation},
            )
        return self.engine.execute({
            "protocolVersion": "1", "requestId": request_id,
            "operation": "proposal.create", "payload": proposal_payload,
        })

    def _invoke(self, value: dict[str, Any], request_id: Any) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        try:
            generated = self.runner(value)
        except subprocess.TimeoutExpired:
            return None, self._error(request_id, "AI_TIMEOUT", "Pi proposal generation timed out.", retryable=True)
        except FileNotFoundError:
            return None, self._error(request_id, "AI_NOT_CONFIGURED", "Node.js or the Pi SDK adapter is not installed.")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return None, self._error(request_id, "AI_UNAVAILABLE", str(exc), retryable=True)
        if not isinstance(generated, dict):
            return None, self._error(request_id, "AI_OUTPUT_INVALID", "Pi adapter returned no structured output.")
        if isinstance(generated.get("error"), dict):
            error = generated["error"]
            return None, self._error(request_id, str(error.get("code", "AI_UNAVAILABLE")), str(error.get("message", "Pi adapter failed.")), retryable=error.get("code") in {"AI_UNAVAILABLE", "AI_TIMEOUT"})
        if not isinstance(generated.get("proposal"), dict):
            return None, self._error(request_id, "AI_OUTPUT_INVALID", "Pi adapter did not emit a Proposal.")
        return generated, None

    def _run_pi(self, value: dict[str, Any]) -> dict[str, Any]:
        process = subprocess.Popen(
            ["node", str(self.script)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1, cwd=ROOT,
        )
        assert process.stdin and process.stdout and process.stderr
        process.stdin.write(json.dumps({"type": "start", "input": value}) + "\n")
        process.stdin.flush()
        deadline = time.monotonic() + self.timeout
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not select.select([process.stdout], [], [], max(0, remaining))[0]:
                    raise subprocess.TimeoutExpired(["node", str(self.script)], self.timeout)
                line = process.stdout.readline()
                if not line:
                    message = process.stderr.read().strip() or "Pi adapter ended without a result."
                    if "ERR_MODULE_NOT_FOUND" in message or "Cannot find package" in message:
                        raise FileNotFoundError(message)
                    raise ValueError(message)
                try:
                    event = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Pi adapter returned invalid protocol output: {line.strip()}") from exc
                if event.get("type") == "request" and event.get("method") == "proposal_validate":
                    result = self._validate_for_agent(value, event.get("payload", {}), event.get("id"))
                    process.stdin.write(json.dumps({"type": "response", "id": event.get("id"), "value": result}) + "\n")
                    process.stdin.flush()
                elif event.get("type") == "result":
                    process.stdin.close()
                    process.wait(timeout=5)
                    output = event.get("value")
                    if not isinstance(output, dict):
                        raise ValueError("Pi adapter returned invalid result.")
                    return output
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream and not stream.closed:
                    stream.close()

    def _validate_for_agent(self, adapter_input: dict[str, Any], payload: dict[str, Any], bridge_id: Any) -> dict[str, Any]:
        draft = adapter_input["draft"]
        proposal = payload.get("proposal") if isinstance(payload, dict) else None
        if not isinstance(proposal, dict):
            return self._error(bridge_id, "AI_OUTPUT_INVALID", "proposal_validate requires a Proposal object.")
        validated = self.engine.execute({
            "protocolVersion": "1", "requestId": f"{adapter_input.get('requestId')}:agent-validation:{bridge_id}",
            "operation": "proposal.validate", "payload": {
                "draftId": draft["draftId"], "baseRevision": draft["revision"],
                "baseFingerprint": draft["fingerprint"], "catalogVersion": draft["catalogVersion"],
                "changes": proposal.get("changes"), "rationale": proposal.get("rationale"),
                "assumptions": proposal.get("assumptions", []),
                "nonCanonicalSuggestions": proposal.get("nonCanonicalSuggestions", []),
            },
        })
        candidate = validated.get("result", {}).get("candidateDraft") if validated.get("ok") else None
        if isinstance(candidate, dict):
            requirements = self.engine.execute({
                "protocolVersion": "1", "requestId": f"{adapter_input.get('requestId')}:candidate-choices:{bridge_id}",
                "operation": "draft.choiceRequirements", "payload": {
                    "draft": {"concept": candidate.get("concept", {}), "selections": candidate.get("selections", {})},
                },
            })
            if requirements.get("ok"):
                validated["result"]["choiceRequirements"] = requirements.get("result", {})
        return validated

    @staticmethod
    def _error(request_id: Any, code: str, message: str, path: str = "", *, kind: str = "ai", retryable: bool = False, details: Any = None) -> dict[str, Any]:
        error = {"code": code, "kind": kind, "message": message, "path": path, "retryable": retryable}
        if details is not None:
            error["details"] = details
        return {"ok": False, "requestId": request_id, "error": error}
