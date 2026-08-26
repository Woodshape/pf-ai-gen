"""Optional Pi SDK concept-to-Proposal adapter."""

from __future__ import annotations

import json
import subprocess
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
        timeout: float = 120,
    ) -> None:
        self.engine = engine
        self.timeout = timeout
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

        adapter_input = {"draft": draft, "concept": concept.strip(), "catalogPath": str(CATALOG), "cwd": str(ROOT)}
        generated, error_response = self._invoke(adapter_input, request_id)
        if error_response:
            return error_response
        for attempt in range(3):
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
                "protocolVersion": "1", "requestId": f"{request_id}:validate:{attempt + 1}",
                "operation": "proposal.validate", "payload": proposal_payload,
            })
            evaluation = validated.get("result", {}).get("evaluation") if validated.get("ok") else None
            if validated.get("ok") and isinstance(evaluation, dict) and evaluation.get("status") == "valid":
                return self.engine.execute({
                    "protocolVersion": "1", "requestId": request_id,
                    "operation": "proposal.create", "payload": proposal_payload,
                })
            if attempt == 2:
                if not validated.get("ok"):
                    return validated
                return self._error(
                    request_id, "PROPOSAL_INVALID", "Pi could not produce a complete valid Proposal after three attempts.",
                    details={"evaluation": evaluation},
                )
            if not validated.get("ok") and not self._repairable(validated):
                return validated
            feedback = {"proposal": proposal}
            if validated.get("ok"):
                feedback["evaluation"] = evaluation
            else:
                feedback["error"] = validated.get("error", {})
            generated, error_response = self._invoke({**adapter_input, "repair": feedback}, request_id)
            if error_response:
                return error_response
        raise AssertionError("bounded proposal validation loop did not return")

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

    @staticmethod
    def _repairable(response: dict[str, Any]) -> bool:
        code = str(response.get("error", {}).get("code", ""))
        return code.startswith(("selection.", "change.")) or code == "catalog.unknown-id"

    def _run_pi(self, value: dict[str, Any]) -> dict[str, Any]:
        completed = subprocess.run(
            ["node", str(SCRIPT)], input=json.dumps(value), text=True,
            capture_output=True, cwd=ROOT, timeout=self.timeout, check=False,
        )
        try:
            output = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            message = completed.stderr.strip() or completed.stdout.strip() or "Pi adapter returned invalid JSON."
            if "ERR_MODULE_NOT_FOUND" in message or "Cannot find package" in message:
                raise FileNotFoundError(message) from exc
            raise ValueError(message) from exc
        if not isinstance(output, dict):
            raise ValueError("Pi adapter returned invalid JSON.")
        return output

    @staticmethod
    def _error(request_id: Any, code: str, message: str, path: str = "", *, kind: str = "ai", retryable: bool = False, details: Any = None) -> dict[str, Any]:
        error = {"code": code, "kind": kind, "message": message, "path": path, "retryable": retryable}
        if details is not None:
            error["details"] = details
        return {"ok": False, "requestId": request_id, "error": error}
