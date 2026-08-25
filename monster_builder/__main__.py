"""JSONL framing for the shared execute interface."""

from __future__ import annotations

import json
import sys

from . import execute


def main() -> int:
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
        elif response.get("result", {}).get("evaluation", {}).get("status") in {"incomplete", "invalid"}:
            exit_code = max(exit_code, 2)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
