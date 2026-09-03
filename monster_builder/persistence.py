"""Versioned JSON storage for monster drafts."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


class PersistenceError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


_LOCKS: dict[tuple[str, str], threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _mtime(path: Path) -> str | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    except (OSError, OverflowError, ValueError):
        return None


class JSONWorkspace:
    SCHEMA_VERSION = "1"
    HISTORY_LIMIT = 20

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        self.drafts = self.root / "drafts"
        self.proposals = self.root / "proposals"
        self.monsters = self.root / "monsters"

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
                "monsterId": None,
                "savedAt": _now(),
                "current": self._snapshot(draft),
                "history": [],
            })

    def load(self, draft_id: str) -> dict[str, Any]:
        return self._draft_from_document(self._read(draft_id))

    def history(self, draft_id: str) -> list[dict[str, Any]]:
        return copy.deepcopy(self._read(draft_id)["history"])

    def list_drafts(self) -> list[tuple[dict[str, Any], str | None]]:
        entries = []
        for path in sorted(self.drafts.glob("draft-*.json")):
            document = self._read(path.stem)
            entries.append((self._draft_from_document(document), self._saved_at(document, path)))
        return entries

    def create_proposal(self, proposal: dict[str, Any]) -> None:
        proposal_id = proposal["proposalId"]
        with self.lock(proposal_id):
            path = self._proposal_path(proposal_id)
            if path.exists():
                existing = self._read_proposal(proposal_id)["proposal"]
                if existing == proposal:
                    return
                raise PersistenceError("persistence.already-exists", f"proposal already exists: {proposal_id}")
            self._write(path, {
                "schemaVersion": self.SCHEMA_VERSION,
                "savedAt": _now(),
                "fingerprint": self._proposal_fingerprint(proposal),
                "proposal": copy.deepcopy(proposal),
            })

    def load_proposal(self, proposal_id: str) -> dict[str, Any]:
        return copy.deepcopy(self._read_proposal(proposal_id)["proposal"])

    def list_monsters(self) -> list[tuple[dict[str, Any], str, str | None]]:
        entries = []
        for path in sorted(self.monsters.glob("monster-*.json")):
            document = self._read_monster(path.stem)
            entries.append((copy.deepcopy(document["monster"]), document["status"], self._saved_at(document, path)))
        return entries

    def delete_draft(self, draft_id: str) -> None:
        path = self._path(draft_id)
        if not path.exists():
            raise PersistenceError("persistence.not-found", f"unknown draft: {draft_id}")
        path.unlink()

    def delete_monster(self, monster_id: str) -> None:
        path = self._monster_path(monster_id)
        if not path.exists():
            raise PersistenceError("persistence.not-found", f"unknown monster: {monster_id}")
        path.unlink()

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
            document["savedAt"] = _now()
            self._write(self._path(draft["draftId"]), document)

    def set_status(self, draft_id: str, base_revision: int, base_fingerprint: str, base_status: str, status: str, previous_status: str | None, monster_id: str | None = None) -> None:
        with self.lock(draft_id):
            document = self._read(draft_id)
            current = document["current"]
            if current["revision"] != base_revision or current["fingerprint"] != base_fingerprint or document["status"] != base_status:
                raise PersistenceError("persistence.conflict", "stored draft changed during mutation")
            document["status"] = status
            document["previousStatus"] = previous_status
            if monster_id is not None:
                document["monsterId"] = monster_id
            document["savedAt"] = _now()
            self._write(self._path(draft_id), document)

    def create_monster(self, monster: dict[str, Any]) -> None:
        with self.lock(monster["monsterId"]):
            path = self._monster_path(monster["monsterId"])
            if path.exists():
                existing = self._read_monster(monster["monsterId"])["monster"]
                if existing == monster:
                    return
                raise PersistenceError("persistence.already-exists", f"monster already exists: {monster['monsterId']}")
            self._write(path, {"schemaVersion": self.SCHEMA_VERSION, "status": "active", "savedAt": _now(), "monster": copy.deepcopy(monster)})

    def load_monster(self, monster_id: str) -> tuple[dict[str, Any], str]:
        document = self._read_monster(monster_id)
        return copy.deepcopy(document["monster"]), document["status"]

    def find_monster(self, draft_id: str, revision: int, fingerprint: str) -> tuple[dict[str, Any], str] | None:
        if not self.monsters.exists():
            return None
        # ponytail: linear scan; replace with index.json when library search lands.
        for path in self.monsters.glob("monster-*.json"):
            monster_id = path.stem
            monster, status = self.load_monster(monster_id)
            source = monster.get("sourceDraft", {})
            if not isinstance(source, dict):
                raise PersistenceError("persistence.corrupt", f"invalid monster document: {self._monster_path(monster_id)}")
            if source == {"draftId": draft_id, "revision": revision, "fingerprint": fingerprint}:
                return monster, status
        return None

    def set_monster_status(self, monster_id: str, base_status: str, status: str) -> None:
        with self.lock(monster_id):
            document = self._read_monster(monster_id)
            if document["status"] != base_status:
                raise PersistenceError("persistence.conflict", "stored monster changed during mutation")
            document["status"] = status
            self._write(self._monster_path(monster_id), document)

    @staticmethod
    def _draft_from_document(document: dict[str, Any]) -> dict[str, Any]:
        draft = copy.deepcopy(document["current"]["draft"])
        draft["status"] = document["status"]
        if document.get("monsterId"):
            draft["monsterId"] = document["monsterId"]
        return draft

    @staticmethod
    def _saved_at(document: dict[str, Any], path: Path) -> str | None:
        value = document.get("savedAt")
        return value if isinstance(value, str) and value else _mtime(path)

    @staticmethod
    def _snapshot(draft: dict[str, Any]) -> dict[str, Any]:
        stored = copy.deepcopy(draft)
        stored.pop("status", None)
        stored.pop("monsterId", None)
        return {
            "revision": draft["revision"],
            "fingerprint": draft["fingerprint"],
            "draft": stored,
        }

    def _proposal_path(self, proposal_id: str) -> Path:
        if not isinstance(proposal_id, str) or not proposal_id or Path(proposal_id).name != proposal_id:
            raise PersistenceError("persistence.invalid-id", "invalid proposalId")
        return self.proposals / f"{proposal_id}.json"

    def _monster_path(self, monster_id: str) -> Path:
        if not isinstance(monster_id, str) or not monster_id or Path(monster_id).name != monster_id:
            raise PersistenceError("persistence.invalid-id", "invalid monsterId")
        return self.monsters / f"{monster_id}.json"

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

    def _read_proposal(self, proposal_id: str) -> dict[str, Any]:
        path = self._proposal_path(proposal_id)
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise PersistenceError("persistence.not-found", f"unknown proposal: {proposal_id}") from exc
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PersistenceError("persistence.corrupt", f"cannot load {path}: {exc}") from exc
        proposal = document.get("proposal") if isinstance(document, dict) else None
        if (
            not isinstance(document, dict)
            or document.get("schemaVersion") != self.SCHEMA_VERSION
            or not isinstance(proposal, dict)
            or proposal.get("proposalId") != proposal_id
            or document.get("fingerprint") != self._proposal_fingerprint(proposal)
        ):
            raise PersistenceError("persistence.corrupt", f"invalid proposal document: {path}")
        return document

    @staticmethod
    def _proposal_fingerprint(proposal: dict[str, Any]) -> str:
        encoded = json.dumps(proposal, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _read_monster(self, monster_id: str) -> dict[str, Any]:
        path = self._monster_path(monster_id)
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise PersistenceError("persistence.not-found", f"unknown monster: {monster_id}") from exc
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PersistenceError("persistence.corrupt", f"cannot load {path}: {exc}") from exc
        if not isinstance(document, dict) or document.get("schemaVersion") != self.SCHEMA_VERSION:
            raise PersistenceError("persistence.schema-unsupported", f"unsupported workspace document: {path}")
        monster = document.get("monster")
        if document.get("status") not in {"active", "archived"} or not isinstance(monster, dict) or monster.get("monsterId") != monster_id:
            raise PersistenceError("persistence.corrupt", f"invalid monster document: {path}")
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
