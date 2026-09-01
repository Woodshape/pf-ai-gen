"""JSONL framing for the shared execute interface."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from . import Engine, execute


def validate_file(file_name: str) -> int:
    path = Path(file_name)
    if path.suffix.lower() != ".json":
        print("Rendered sheets are lossy; validate a JSON draft or FinishedMonster export.", file=sys.stderr)
        return 4
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(value, dict) and isinstance(value.get("current"), dict):
            value = value["current"].get("draft", value)
        if isinstance(value, dict) and isinstance(value.get("monster"), dict):
            value = value["monster"]
        elif isinstance(value, dict) and isinstance(value.get("draft"), dict):
            value = value["draft"]
        if not isinstance(value, dict) or not isinstance(value.get("concept"), dict) or not isinstance(value.get("selections"), dict):
            raise ValueError("JSON must contain concept and selections")
        draft = {"concept": value["concept"], "selections": value["selections"]}
        # Validate under the snapshot's rules system. Legacy JSON without this
        # field keeps the Simple Monster default.
        if "creationSystem" in value:
            draft["creationSystem"] = value["creationSystem"]
        response = Engine().execute({
            "protocolVersion": "1",
            "requestId": "validate-file",
            "operation": "draft.create",
            "payload": {"draft": draft},
        })
        if not response.get("ok"):
            print(json.dumps(response["error"], ensure_ascii=False, indent=2))
            return 4
        evaluation = response["result"]["evaluation"]
        print(json.dumps(evaluation, ensure_ascii=False, indent=2))
        return 0 if evaluation["status"] == "valid" else 2
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"Cannot validate JSON: {exc}", file=sys.stderr)
        return 4


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "validate":
        return validate_file(sys.argv[2])
    if len(sys.argv) != 1:
        print("Usage: python3 -m monster_builder [validate FILE.json]", file=sys.stderr)
        return 4
    exit_code = 0
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
            response = execute(request)
        except json.JSONDecodeError as exc:
            response = {
                "ok": False,
                "requestId": None,
                "error": {
                    "code": "protocol.invalid-json",
                    "kind": "boundary",
                    "message": str(exc),
                    "path": "",
                },
            }
        print(json.dumps(response, ensure_ascii=False, separators=(",", ":")), flush=True)
        if not response.get("ok"):
            exit_code = max(exit_code, 3 if response.get("error", {}).get("code") == "draft.revision-conflict" else 4)
        elif (response.get("result", {}).get("evaluation") or {}).get("status") in {"incomplete", "invalid"}:
            exit_code = max(exit_code, 2)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
