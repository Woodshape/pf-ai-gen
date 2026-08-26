"""Versioned JSON storage for monster drafts."""

from __future__ import annotations

import copy
import json
import os
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


class PersistenceError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


_LOCKS: dict[tuple[str, str], threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


class JSONWorkspace:
    SCHEMA_VERSION = "1"
    HISTORY_LIMIT = 20

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        self.drafts = self.root / "drafts"

    @contextmanager
    def lock(self, draft_id: str) -> Iterator[None]:
        # ponytail: process-local locks; add OS file locks if multiple writer
        # processes become a supported deployment mode.
        key = (str(self.root), draft_id)
        with _LOCKS_GUARD:
            lock = _LOCKS.setdefault(key, threading.RLock())
        with lock:
            yield

    def create(self, draft: dict[str, Any]) -> None:
        with self.lock(draft["draftId"]):
            path = self._path(draft["draftId"])
            if path.exists():
                raise PersistenceError("persistence.already-exists", f"draft already exists: {draft['draftId']}")
            self._write(path, {
                "schemaVersion": self.SCHEMA_VERSION,
                "status": draft.get("status", "active"),
                "previousStatus": None,
                "current": self._snapshot(draft),
                "history": [],
            })

    def load(self, draft_id: str) -> dict[str, Any]:
        document = self._read(draft_id)
        draft = copy.deepcopy(document["current"]["draft"])
        draft["status"] = document["status"]
        return draft

    def history(self, draft_id: str) -> list[dict[str, Any]]:
        return copy.deepcopy(self._read(draft_id)["history"])

    def previous_status(self, draft_id: str) -> str | None:
        return self._read(draft_id).get("previousStatus")

    def replace(self, draft: dict[str, Any], base_revision: int, base_fingerprint: str, base_status: str) -> None:
        with self.lock(draft["draftId"]):
            document = self._read(draft["draftId"])
            current = document["current"]
            if current["revision"] != base_revision or current["fingerprint"] != base_fingerprint or document["status"] != base_status:
                raise PersistenceError("persistence.conflict", "stored draft changed during mutation")
            document["history"] = [current, *document["history"]][:self.HISTORY_LIMIT]
            document["current"] = self._snapshot(draft)
            self._write(self._path(draft["draftId"]), document)

    def set_status(self, draft_id: str, base_revision: int, base_fingerprint: str, base_status: str, status: str, previous_status: str | None) -> None:
        with self.lock(draft_id):
            document = self._read(draft_id)
            current = document["current"]
            if current["revision"] != base_revision or current["fingerprint"] != base_fingerprint or document["status"] != base_status:
                raise PersistenceError("persistence.conflict", "stored draft changed during mutation")
            document["status"] = status
            document["previousStatus"] = previous_status
            self._write(self._path(draft_id), document)

    @staticmethod
    def _snapshot(draft: dict[str, Any]) -> dict[str, Any]:
        stored = copy.deepcopy(draft)
        stored.pop("status", None)
        return {
            "revision": draft["revision"],
            "fingerprint": draft["fingerprint"],
            "draft": stored,
        }

    def _path(self, draft_id: str) -> Path:
        if not isinstance(draft_id, str) or not draft_id or Path(draft_id).name != draft_id:
            raise PersistenceError("persistence.invalid-id", "invalid draftId")
        return self.drafts / f"{draft_id}.json"

    def _read(self, draft_id: str) -> dict[str, Any]:
        path = self._path(draft_id)
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise PersistenceError("persistence.not-found", f"unknown draft: {draft_id}") from exc
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PersistenceError("persistence.corrupt", f"cannot load {path}: {exc}") from exc
        if not isinstance(document, dict) or document.get("schemaVersion") != self.SCHEMA_VERSION:
            raise PersistenceError("persistence.schema-unsupported", f"unsupported workspace document: {path}")
        current = document.get("current")
        history = document.get("history")
        status = document.setdefault("status", "active")
        document.setdefault("previousStatus", None)
        if status not in {"active", "finalized", "archived"}:
            raise PersistenceError("persistence.corrupt", f"invalid workspace document: {path}")
        if not self._valid_snapshot(current) or not isinstance(history, list) or len(history) > self.HISTORY_LIMIT or any(not self._valid_snapshot(item) for item in history):
            raise PersistenceError("persistence.corrupt", f"invalid workspace document: {path}")
        for snapshot in [current, *history]:
            draft = snapshot["draft"]
            if draft.get("draftId") != draft_id or draft.get("revision") != snapshot["revision"] or draft.get("fingerprint") != snapshot["fingerprint"]:
                raise PersistenceError("persistence.corrupt", f"inconsistent snapshot: {path}")
        return document

    @staticmethod
    def _valid_snapshot(value: Any) -> bool:
        return (
            isinstance(value, dict)
            and isinstance(value.get("revision"), int)
            and not isinstance(value.get("revision"), bool)
            and value["revision"] >= 0
            and isinstance(value.get("fingerprint"), str)
            and isinstance(value.get("draft"), dict)
        )

    @staticmethod
    def _write(path: Path, document: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
                temporary = Path(handle.name)
                json.dump(document, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        except OSError as exc:
            if temporary:
                temporary.unlink(missing_ok=True)
            raise PersistenceError("persistence.write-failed", f"cannot write {path}: {exc}") from exc
