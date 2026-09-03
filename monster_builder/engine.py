"""Shared public execute lifecycle and creation-system dispatch."""

from __future__ import annotations

import copy
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .catalog import Catalog, CatalogError, CatalogRegistry
from .creation_systems import (
    SIMPLE_MONSTER,
    CreationSystem,
    creation_system_key,
    installed_creation_systems,
    load_optional_creation_system,
)
from .errors import BoundaryError
from .persistence import JSONWorkspace, PersistenceError


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Engine:
    """Own the shared draft workspace and dispatch rules to an adapter."""

    PROTOCOL_VERSION = "1"
    DRAFT_SCHEMA_VERSION = "1"
    _CONCEPT_FIELDS = {"name", "targetCR", "role", "creatureType", "description"}

    def __init__(
        self,
        catalog: Catalog | None = None,
        workspace: str | Path | None = None,
        *,
        catalogs: CatalogRegistry | None = None,
        creation_systems: dict[str, CreationSystem] | None = None,
    ):
        if catalog is not None and catalogs is not None:
            raise ValueError("provide catalog or catalogs, not both")
        self.catalogs = catalogs or CatalogRegistry(catalog)
        # Preserve the original public attribute as the Simple Monster catalog.
        self.catalog = self.catalogs.for_system(SIMPLE_MONSTER)
        self._creation_systems: dict[str, CreationSystem] = installed_creation_systems(self.catalogs)
        if creation_systems:
            self._creation_systems.update(creation_systems)
        self.workspace = JSONWorkspace(workspace) if workspace is not None else None
        self._drafts: dict[str, dict[str, Any]] = {}
        self._histories: dict[str, list[dict[str, Any]]] = {}
        self._previous_status: dict[str, str] = {}
        self._draft_saved_at: dict[str, str] = {}
        self._monsters: dict[str, dict[str, Any]] = {}
        self._proposals: dict[str, dict[str, Any]] = {}
        self._monster_status: dict[str, str] = {}
        self._monster_saved_at: dict[str, str] = {}
        self._idempotency: dict[str, tuple[str, dict[str, Any]]] = {}

    @classmethod
    def from_catalog(cls, path: str | Path, *, workspace: str | Path | None = None) -> "Engine":
        return cls(Catalog.load(path), workspace)

    @staticmethod
    def _creation_system_key(value: dict[str, Any]) -> str:
        if "creationSystem" not in value:
            return SIMPLE_MONSTER
        if value["creationSystem"] is None:
            raise BoundaryError(
                "creation-system.invalid",
                "creationSystem must be simple-monster or npc",
                "/creationSystem",
            )
        return creation_system_key(value["creationSystem"])

    def _catalog_for(self, value: dict[str, Any]):
        return self.catalogs.for_system(self._creation_system_key(value))

    def _creation_system_for(self, value: dict[str, Any]) -> CreationSystem:
        key = self._creation_system_key(value)
        # Resolve the catalog first so catalog availability/version errors stay
        # catalog-data errors rather than being confused with an adapter bug.
        self.catalogs.for_system(key)
        try:
            return self._creation_systems[key]
        except KeyError:
            adapter = load_optional_creation_system(key, self.catalogs)
            self._creation_systems[key] = adapter
            return adapter

    def _evaluate(self, draft: dict[str, Any]) -> dict[str, Any]:
        return self._creation_system_for(draft).evaluate(draft)

    def _draft_fingerprint(self, draft: dict[str, Any]) -> str:
        # Resolve only after validating the creation-system key. Known systems
        # own their selection normalization, including NPC progression order.
        key = self._creation_system_key(draft)
        adapter = self._creation_systems.get(key)
        if adapter is None:
            adapter = self._creation_system_for(draft)
        normalize = getattr(adapter, "fingerprint_selections", copy.deepcopy)
        selections = normalize(draft.get("selections", {}))
        return _fingerprint_draft_content(draft, selections)

    def execute(self, request: dict[str, Any]) -> dict[str, Any]:
        request_id = request.get("requestId") if isinstance(request, dict) else None
        try:
            self._validate_request(request)
            request_id = request["requestId"]
            request_fingerprint = _fingerprint(request)
            cached = self._idempotency.get(request_id)
            if cached:
                previous_fingerprint, previous_response = cached
                if previous_fingerprint != request_fingerprint:
                    raise BoundaryError(
                        "request.idempotency-conflict",
                        "requestId was already used with a different request",
                        "/requestId",
                        kind="conflict",
                    )
                return copy.deepcopy(previous_response)
            operation = request["operation"]
            payload = request.get("payload", {})
            if operation == "draft.create":
                result = self._create(payload)
            elif operation == "draft.get":
                result = self._get(payload)
            elif operation == "draft.applyChanges":
                result = self._apply_changes(payload)
            elif operation == "draft.evaluate":
                result = self._evaluate_request(payload)
            elif operation == "proposal.validate":
                result = self._proposal_validate(payload)
            elif operation == "proposal.create":
                result = self._proposal_create(payload)
            elif operation == "proposal.get":
                result = self._proposal_get(payload)
            elif operation == "proposal.accept":
                result = self._proposal_accept(payload)
            elif operation == "draft.choiceRequirements":
                result = self._choice_requirements(payload)
            elif operation == "draft.history.get":
                result = self._history_get(payload)
            elif operation == "draft.restoreRevision":
                result = self._restore_revision(payload)
            elif operation == "draft.duplicate":
                result = self._duplicate(payload)
            elif operation == "draft.archive":
                result = self._archive(payload)
            elif operation == "draft.delete":
                result = self._delete_draft(payload)
            elif operation == "draft.restore":
                result = self._restore(payload)
            elif operation == "monster.finalize":
                result = self._finalize_monster(payload)
            elif operation == "monster.get":
                result = self._get_monster(payload)
            elif operation == "monster.duplicate":
                result = self._duplicate_monster(payload)
            elif operation == "monster.archive":
                result = self._archive_monster(payload)
            elif operation == "monster.delete":
                result = self._delete_monster(payload)
            elif operation == "monster.restore":
                result = self._restore_monster(payload)
            elif operation == "monster.export":
                result = self._export_monster(payload)
            elif operation == "library.search":
                result = self._search_library(payload)
            else:
                raise BoundaryError(
                    "operation.unsupported",
                    f"unsupported operation: {operation}",
                    "/operation",
                )
            response = {"ok": True, "requestId": request_id, "result": result}
            if operation in {
                "draft.create", "draft.applyChanges", "draft.restoreRevision", "draft.duplicate", "draft.archive", "draft.restore",
                "proposal.create", "proposal.accept",
                "monster.finalize", "monster.duplicate", "monster.archive", "monster.restore",
            }:
                self._idempotency[request_id] = (request_fingerprint, copy.deepcopy(response))
            return response
        except BoundaryError as exc:
            return self._error(request_id, exc)
        except PersistenceError as exc:
            operation_name = str(request.get("operation", "")) if isinstance(request, dict) else ""
            if operation_name.startswith("monster.") and operation_name != "monster.finalize":
                entity = "monster"
            elif operation_name.startswith("proposal."):
                entity = "proposal"
            else:
                entity = "draft"
            code, kind = {
                "persistence.not-found": (f"{entity}.not-found", "boundary"),
                "persistence.invalid-id": (f"{entity}.not-found", "boundary"),
                "persistence.corrupt": (f"{entity}.file-corrupt", "persistence"),
                "persistence.schema-unsupported": (f"{entity}.file-schema-unsupported", "persistence"),
                "persistence.conflict": (f"{entity}.revision-conflict", "conflict"),
            }.get(exc.code, (f"{entity}.write-failed", "persistence"))
            return self._error(request_id, BoundaryError(code, str(exc), f"/payload/{entity}Id", kind=kind))
        except CatalogError as exc:
            return self._error(
                request_id,
                BoundaryError("catalog.invalid", str(exc), "", kind="catalog-data"),
            )

    def _validate_request(self, request: Any) -> None:
        if not isinstance(request, dict):
            raise BoundaryError("request.invalid", "request must be a JSON object")
        if request.get("protocolVersion") != self.PROTOCOL_VERSION:
            raise BoundaryError("protocol.unsupported", "protocolVersion must be '1'", "/protocolVersion")
        if not isinstance(request.get("requestId"), str) or not request["requestId"]:
            raise BoundaryError("request.id-required", "requestId must be a non-empty string", "/requestId")
        if not isinstance(request.get("operation"), str) or not request["operation"]:
            raise BoundaryError("operation.required", "operation must be a non-empty string", "/operation")
        if "payload" in request and not isinstance(request["payload"], dict):
            raise BoundaryError("payload.invalid", "payload must be an object", "/payload")

    def _create(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw = payload.get("draft", payload)
        draft = self._new_draft(raw)
        evaluation = self._evaluate(draft)
        self._store_new(draft)
        return {"draft": copy.deepcopy(draft), "evaluation": evaluation}

    def _get(self, payload: dict[str, Any]) -> dict[str, Any]:
        draft = self._stored_draft(payload, allow_unsupported_catalog=True)
        if draft.get("catalogVersion") != self._catalog_for(draft).version:
            return {
                "draft": copy.deepcopy(draft),
                "evaluation": None,
                "evaluationError": {
                    "code": "catalog.version-unsupported",
                    "kind": "catalog-data",
                    "message": "draft uses an unsupported catalog version",
                    "path": "/catalogVersion",
                },
            }
        return {"draft": copy.deepcopy(draft), "evaluation": self._evaluate(draft)}

    def _search_library(self, payload: dict[str, Any]) -> dict[str, Any]:
        query = payload.get("query", "")
        include_archived = payload.get("includeArchived", False)
        if not isinstance(query, str):
            raise BoundaryError("library.query-invalid", "query must be a string", "/payload/query")
        if not isinstance(include_archived, bool):
            raise BoundaryError("library.include-archived-invalid", "includeArchived must be a boolean", "/payload/includeArchived")
        drafts = self.workspace.list_drafts() if self.workspace else [
            (copy.deepcopy(draft), self._draft_saved_at.get(draft["draftId"]))
            for draft in self._drafts.values()
        ]
        monsters = self.workspace.list_monsters() if self.workspace else [
            (copy.deepcopy(monster), self._monster_status.get(monster_id, "active"), self._monster_saved_at.get(monster_id))
            for monster_id, monster in self._monsters.items()
        ]
        draft_entries = [{
            "kind": "draft",
            "id": draft["draftId"],
            "creationSystem": self._creation_system_key(draft),
            "catalogVersion": draft.get("catalogVersion"),
            "name": str(draft.get("concept", {}).get("name", "")),
            "cr": draft.get("selections", {}).get("cr", draft.get("concept", {}).get("targetCR")),
            "level": self._library_draft_level(draft),
            "role": str(draft.get("concept", {}).get("role", "")),
            "status": draft.get("status", "active"),
            "revision": draft["revision"],
            "savedAt": saved_at,
        } for draft, saved_at in drafts if include_archived or draft.get("status", "active") == "active"]
        monster_entries = [{
            "kind": "monster",
            "id": monster["monsterId"],
            "creationSystem": self._creation_system_key(monster),
            "catalogVersion": monster.get("catalogVersion"),
            "name": str(monster.get("concept", {}).get("name", "")),
            "cr": monster.get("result", {}).get("cr", monster.get("result", {}).get("recommendedCR", monster.get("concept", {}).get("targetCR"))),
            "level": monster.get("result", {}).get("level", monster.get("result", {}).get("totalLevel")),
            "role": str(monster.get("concept", {}).get("role", "")),
            "status": status,
            "revision": monster.get("sourceDraft", {}).get("revision"),
            "savedAt": saved_at,
            "sourceDraftId": monster.get("sourceDraft", {}).get("draftId"),
        } for monster, status, saved_at in monsters if include_archived or status == "active"]
        if query:
            needle = query.casefold()
            draft_entries = [entry for entry in draft_entries if needle in " ".join(map(str, entry.values())).casefold()]
            monster_entries = [entry for entry in monster_entries if needle in " ".join(map(str, entry.values())).casefold()]
        key = lambda entry: (entry["name"].casefold(), entry["id"])
        draft_entries.sort(key=key)
        monster_entries.sort(key=key)
        # Stable secondary sort: newest first, name order within identical timestamps.
        draft_entries.sort(key=lambda entry: entry["savedAt"] or "", reverse=True)
        monster_entries.sort(key=lambda entry: entry["savedAt"] or "", reverse=True)
        return {"drafts": draft_entries, "monsters": monster_entries}

    def _library_draft_level(self, draft: dict[str, Any]) -> Any:
        """Project adapter-owned level data without making search catalog-fragile."""
        if self._creation_system_key(draft) == SIMPLE_MONSTER:
            return None
        try:
            if draft.get("catalogVersion") != self._catalog_for(draft).version:
                return None
            evaluation = self._evaluate(draft)
        except (BoundaryError, CatalogError):
            return None
        result = evaluation.get("effective")
        if not isinstance(result, dict):
            return None
        return result.get("level", result.get("totalLevel"))

    def _choice_requirements(self, payload: dict[str, Any]) -> dict[str, Any]:
        if "draftId" in payload and "draft" in payload:
            raise BoundaryError("draft.ambiguous", "provide draftId or draft, not both", "/payload")
        if "draftId" in payload:
            stored = self._stored_draft(payload)
            overrides = payload.get("selectionOverrides", {})
            if not isinstance(overrides, dict):
                raise BoundaryError("selection-overrides.invalid", "selectionOverrides must be an object", "/payload/selectionOverrides")
            draft = stored if not overrides else self._new_draft({
                "creationSystem": self._creation_system_key(stored),
                "concept": stored["concept"],
                "selections": {**stored["selections"], **overrides},
            })
            basis = {
                "draftId": stored["draftId"], "revision": stored["revision"],
                "fingerprint": stored["fingerprint"], "catalogVersion": stored["catalogVersion"],
                "candidateFingerprint": draft["fingerprint"],
            }
        elif "draft" in payload:
            if "selectionOverrides" in payload:
                raise BoundaryError("draft.ambiguous", "selectionOverrides can be used only with draftId", "/payload/selectionOverrides")
            draft = self._new_draft(payload["draft"])
            basis = {"catalogVersion": draft["catalogVersion"], "candidateFingerprint": draft["fingerprint"]}
        else:
            raise BoundaryError("draft.required", "draft or draftId is required", "/payload")
        requirements = self._creation_system_for(draft).choice_requirements(draft)
        return {"basis": basis, **requirements}

    def _evaluate_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        if "draftId" in payload:
            draft = self._stored_draft(payload)
        elif "draft" in payload:
            draft = self._prepare_external_draft(payload["draft"])
        else:
            raise BoundaryError("draft.required", "draft or draftId is required", "/payload")
        return {"evaluation": self._evaluate(draft)}

    def _proposal_validate(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise BoundaryError("proposal.invalid", "proposal payload must be an object", "/payload")
        raw = payload.get("proposal", payload)
        if not isinstance(raw, dict):
            raise BoundaryError("proposal.invalid", "proposal must be an object", "/payload/proposal")
        draft_id = raw.get("draftId", payload.get("draftId"))
        if not isinstance(draft_id, str) or not draft_id:
            raise BoundaryError("proposal.draft-id-required", "draftId is required", "/payload/draftId")
        draft = copy.deepcopy(self._stored_draft({"draftId": draft_id}))
        if draft.get("status", "active") != "active":
            raise BoundaryError("draft.not-active", "proposals can only be validated for active drafts", "/payload/draftId", kind="conflict")
        merged = {**payload, **raw}
        base_revision, base_fingerprint, _ = self._proposal_base(merged, draft)
        base_draft = self._draft_at_base(draft, base_revision, base_fingerprint)
        changes = self._proposal_changes(raw)
        candidate = self._validate_proposal_changes(base_draft, changes)
        candidate["revision"] = base_revision + 1
        candidate["fingerprint"] = self._draft_fingerprint(candidate)
        return {"candidateDraft": candidate, "evaluation": self._evaluate(candidate)}

    def _proposal_create(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise BoundaryError("proposal.invalid", "proposal payload must be an object", "/payload")
        raw = payload.get("proposal", payload)
        if not isinstance(raw, dict):
            raise BoundaryError("proposal.invalid", "proposal must be an object", "/payload/proposal")
        if raw is not payload:
            raw = copy.deepcopy(raw)
            for field in (
                "draftId", "baseRevision", "baseFingerprint", "catalogVersion", "model",
                "rationale", "assumptions", "nonCanonicalSuggestions",
            ):
                if field not in raw and field in payload:
                    raw[field] = copy.deepcopy(payload[field])
        draft_id = raw.get("draftId")
        if not isinstance(draft_id, str) or not draft_id:
            raise BoundaryError("proposal.draft-id-required", "draftId is required", "/payload/draftId")
        draft = copy.deepcopy(self._stored_draft({"draftId": draft_id}))
        if draft.get("status", "active") != "active":
            raise BoundaryError("draft.not-active", "proposals can only be created for active drafts", "/payload/draftId", kind="conflict")
        base_revision, base_fingerprint, catalog_version = self._proposal_base(raw, draft)
        base_draft = self._draft_at_base(draft, base_revision, base_fingerprint)
        changes = self._proposal_changes(raw)
        self._validate_proposal_changes(base_draft, changes)
        proposal = {
            "schemaVersion": self.DRAFT_SCHEMA_VERSION,
            "kind": "Proposal",
            "proposalId": f"proposal-{uuid.uuid4().hex}",
            "draftId": draft_id,
            "baseRevision": base_revision,
            "baseFingerprint": base_fingerprint,
            "catalogVersion": catalog_version,
            "changes": copy.deepcopy(changes),
            "rationale": self._proposal_text(raw, "rationale", ""),
            "assumptions": self._proposal_strings(raw, "assumptions"),
            "nonCanonicalSuggestions": self._proposal_strings(raw, "nonCanonicalSuggestions"),
        }
        if isinstance(raw.get("model"), str):
            proposal["model"] = raw["model"]
        elif raw.get("model") is not None:
            raise BoundaryError("proposal.metadata-invalid", "model must be a string", "/payload/model")
        self._store_proposal(proposal)
        return {"proposal": copy.deepcopy(proposal)}

    def _proposal_get(self, payload: dict[str, Any]) -> dict[str, Any]:
        proposal = self._stored_proposal(payload)
        return {"proposal": copy.deepcopy(proposal)}

    def _proposal_accept(self, payload: dict[str, Any]) -> dict[str, Any]:
        proposal = self._stored_proposal(payload)
        self._validate_proposal_confirmation(payload)
        selected_ids = self._proposal_change_ids(payload)
        changes_by_id = {change["changeId"]: change for change in proposal["changes"]}
        unknown = [change_id for change_id in selected_ids if change_id not in changes_by_id]
        if unknown:
            raise BoundaryError(
                "proposal.change-id-unknown",
                f"unknown proposal changeId: {unknown[0]}",
                f"/payload/changeIds/{selected_ids.index(unknown[0])}",
            )
        if payload.get("draftId") is not None and payload["draftId"] != proposal["draftId"]:
            raise BoundaryError("proposal.draft-mismatch", "proposal is bound to a different draft", "/payload/draftId", kind="conflict")
        for field in ("baseRevision", "baseFingerprint"):
            if field in payload and payload[field] != proposal[field]:
                raise BoundaryError("proposal.base-mismatch", "acceptance base does not match the proposal base", f"/payload/{field}", kind="conflict")
        if "catalogVersion" in payload and payload["catalogVersion"] != proposal["catalogVersion"]:
            raise BoundaryError("proposal.catalog-mismatch", "acceptance catalogVersion does not match the proposal", "/payload/catalogVersion", kind="catalog-data")
        draft = copy.deepcopy(self._stored_draft({"draftId": proposal["draftId"]}))
        active_catalog = self._catalog_for(draft)
        if draft.get("catalogVersion") != proposal["catalogVersion"] or proposal["catalogVersion"] != active_catalog.version:
            raise BoundaryError("catalog.version-unsupported", "proposal uses an unsupported catalog version", "/payload/catalogVersion", kind="catalog-data")
        self._require_base_guard({
            "baseRevision": proposal["baseRevision"],
            "baseFingerprint": proposal["baseFingerprint"],
        }, draft)
        selected_changes = [copy.deepcopy(changes_by_id[change_id]) for change_id in selected_ids]
        self._validate_proposal_changes(draft, selected_changes)
        applied = self._apply_changes({
            "draftId": proposal["draftId"],
            "baseRevision": proposal["baseRevision"],
            "baseFingerprint": proposal["baseFingerprint"],
            "changes": selected_changes,
        })
        return {
            "proposal": copy.deepcopy(proposal),
            "draft": applied["draft"],
            "evaluation": applied["evaluation"],
            "appliedChanges": applied["appliedChanges"],
            "acceptedChangeIds": list(selected_ids),
        }

    def _proposal_base(self, raw: dict[str, Any], draft: dict[str, Any]) -> tuple[int, str, str]:
        for field in ("baseRevision", "baseFingerprint", "catalogVersion"):
            if field not in raw:
                raise BoundaryError("proposal.base-guard-required", "proposal requires baseRevision, baseFingerprint, and catalogVersion", f"/payload/{field}")
        base_revision = raw["baseRevision"]
        if not isinstance(base_revision, int) or isinstance(base_revision, bool) or base_revision < 0:
            raise BoundaryError("proposal.base-revision-invalid", "baseRevision must be a non-negative integer", "/payload/baseRevision")
        base_fingerprint = raw["baseFingerprint"]
        if not isinstance(base_fingerprint, str) or not base_fingerprint:
            raise BoundaryError("proposal.base-fingerprint-invalid", "baseFingerprint must be a non-empty string", "/payload/baseFingerprint")
        catalog_version = raw["catalogVersion"]
        if not isinstance(catalog_version, str) or not catalog_version:
            raise BoundaryError("proposal.catalog-version-invalid", "catalogVersion must be a non-empty string", "/payload/catalogVersion")
        if catalog_version != self._catalog_for(draft).version:
            raise BoundaryError("catalog.version-unsupported", "proposal uses an unsupported catalog version", "/payload/catalogVersion", kind="catalog-data")
        if catalog_version != draft.get("catalogVersion"):
            raise BoundaryError("proposal.catalog-mismatch", "proposal catalogVersion does not match the draft", "/payload/catalogVersion", kind="catalog-data")
        return base_revision, base_fingerprint, catalog_version

    def _draft_at_base(self, current: dict[str, Any], revision: int, fingerprint: str) -> dict[str, Any]:
        if current.get("revision") == revision and current.get("fingerprint") == fingerprint:
            return copy.deepcopy(current)
        history = self.workspace.history(current["draftId"]) if self.workspace else self._histories.get(current["draftId"], [])
        for snapshot in history:
            if snapshot.get("revision") == revision and snapshot.get("fingerprint") == fingerprint:
                candidate = copy.deepcopy(snapshot["draft"])
                candidate.setdefault("status", current.get("status", "active"))
                return candidate
        raise BoundaryError(
            "draft.revision-conflict",
            "draft revision or fingerprint is stale or unknown",
            "/payload/baseRevision",
            kind="conflict",
            details={"currentDraft": copy.deepcopy(current), "currentEvaluation": self._evaluate(current)},
        )

    def _proposal_changes(self, raw: dict[str, Any]) -> list[dict[str, Any]]:
        if "changes" in raw and "typedChanges" in raw:
            raise BoundaryError("proposal.changes-ambiguous", "provide changes or typedChanges, not both", "/payload")
        changes = raw.get("changes", raw.get("typedChanges", []))
        if not isinstance(changes, list):
            raise BoundaryError("proposal.changes-invalid", "changes must be an array", "/payload/changes")
        return copy.deepcopy(changes)

    @staticmethod
    def _proposal_text(raw: dict[str, Any], field: str, default: str) -> str:
        value = raw.get(field, default)
        if not isinstance(value, str):
            raise BoundaryError("proposal.metadata-invalid", f"{field} must be a string", f"/payload/{field}")
        return value

    @staticmethod
    def _proposal_strings(raw: dict[str, Any], field: str) -> list[str]:
        value = raw.get(field, [])
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise BoundaryError("proposal.metadata-invalid", f"{field} must be an array of strings", f"/payload/{field}")
        return copy.deepcopy(value)

    def _validate_proposal_confirmation(self, payload: dict[str, Any]) -> None:
        confirmation = payload.get("confirmation")
        if not isinstance(confirmation, dict) or confirmation.get("actor") != "user" or confirmation.get("confirmed") is not True:
            raise BoundaryError(
                "proposal.confirmation-required",
                "proposal acceptance requires confirmation.actor='user' and confirmed=true",
                "/payload/confirmation",
            )

    def _proposal_change_ids(self, payload: dict[str, Any]) -> list[str]:
        if "changeIds" in payload and "selectedChangeIds" in payload:
            raise BoundaryError("proposal.change-ids-ambiguous", "provide changeIds or selectedChangeIds, not both", "/payload")
        values = payload.get("changeIds", payload.get("selectedChangeIds"))
        if not isinstance(values, list) or not values:
            raise BoundaryError("proposal.change-ids-required", "acceptance requires one or more explicit change IDs", "/payload/changeIds")
        if any(not isinstance(value, str) or not value for value in values):
            raise BoundaryError("proposal.change-id-invalid", "change IDs must be non-empty strings", "/payload/changeIds")
        if len(values) != len(set(values)):
            raise BoundaryError("proposal.change-id-duplicate", "change IDs must be unique", "/payload/changeIds")
        return list(values)

    def _validate_proposal_changes(self, draft: dict[str, Any], changes: list[dict[str, Any]]) -> dict[str, Any]:
        candidate = copy.deepcopy(draft)
        seen: set[str] = set()
        for index, change in enumerate(changes):
            path = f"/payload/changes/{index}"
            if not isinstance(change, dict):
                raise BoundaryError("change.invalid", "change must be an object", path)
            change_id = change.get("changeId")
            if not isinstance(change_id, str) or not change_id:
                raise BoundaryError("change.id-required", "each change requires a non-empty changeId", f"{path}/changeId")
            if change_id in seen:
                raise BoundaryError("change.id-duplicate", "changeId values must be unique within a proposal", f"{path}/changeId")
            seen.add(change_id)
            if "rationale" in change and not isinstance(change["rationale"], str):
                raise BoundaryError("change.rationale-invalid", "change rationale must be a string", f"{path}/rationale")
            if "sourceRefs" in change and not isinstance(change["sourceRefs"], (dict, list)):
                raise BoundaryError("change.source-refs-invalid", "change sourceRefs must be an object or array", f"{path}/sourceRefs")
            self._apply_change(candidate, change, index)
        self._validate_draft_input(candidate)
        return candidate

    def _store_proposal(self, proposal: dict[str, Any]) -> None:
        if self.workspace:
            self.workspace.create_proposal(proposal)
            return
        proposal_id = proposal["proposalId"]
        existing = self._proposals.get(proposal_id)
        if existing is not None and existing != proposal:
            raise BoundaryError("proposal.id-conflict", "proposalId already exists", "/proposalId", kind="conflict")
        self._proposals[proposal_id] = copy.deepcopy(proposal)

    def _stored_proposal(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise BoundaryError("proposal.invalid", "proposal payload must be an object", "/payload")
        proposal_id = payload.get("proposalId")
        if not isinstance(proposal_id, str) or not proposal_id:
            raise BoundaryError("proposal.id-required", "proposalId is required", "/payload/proposalId")
        if self.workspace:
            proposal = self.workspace.load_proposal(proposal_id)
        else:
            try:
                proposal = copy.deepcopy(self._proposals[proposal_id])
            except KeyError as exc:
                raise BoundaryError("proposal.not-found", f"unknown proposal: {proposal_id}", "/payload/proposalId") from exc
        self._validate_stored_proposal(proposal)
        return proposal

    def _validate_stored_proposal(self, proposal: dict[str, Any]) -> None:
        required = {
            "schemaVersion", "kind", "proposalId", "draftId", "baseRevision", "baseFingerprint",
            "catalogVersion", "changes", "rationale", "assumptions", "nonCanonicalSuggestions",
        }
        if not isinstance(proposal, dict) or not required <= set(proposal):
            raise BoundaryError("proposal.file-corrupt", "proposal is missing required fields", "", kind="persistence")
        if proposal.get("schemaVersion") != self.DRAFT_SCHEMA_VERSION or proposal.get("kind") != "Proposal":
            raise BoundaryError("proposal.file-schema-unsupported", "unsupported proposal snapshot", "/schemaVersion", kind="persistence")
        if not isinstance(proposal.get("proposalId"), str) or not isinstance(proposal.get("draftId"), str):
            raise BoundaryError("proposal.file-corrupt", "proposal identifiers are invalid", "", kind="persistence")
        if not isinstance(proposal.get("baseRevision"), int) or isinstance(proposal.get("baseRevision"), bool) or proposal["baseRevision"] < 0:
            raise BoundaryError("proposal.file-corrupt", "proposal baseRevision is invalid", "/baseRevision", kind="persistence")
        if not isinstance(proposal.get("baseFingerprint"), str) or not isinstance(proposal.get("catalogVersion"), str):
            raise BoundaryError("proposal.file-corrupt", "proposal base metadata is invalid", "", kind="persistence")
        if not isinstance(proposal.get("changes"), list) or not isinstance(proposal.get("rationale"), str):
            raise BoundaryError("proposal.file-corrupt", "proposal content is invalid", "", kind="persistence")
        if "model" in proposal and not isinstance(proposal["model"], str):
            raise BoundaryError("proposal.file-corrupt", "proposal model metadata is invalid", "/model", kind="persistence")
        if not isinstance(proposal.get("assumptions"), list) or any(not isinstance(item, str) for item in proposal["assumptions"]):
            raise BoundaryError("proposal.file-corrupt", "proposal assumptions are invalid", "/assumptions", kind="persistence")
        if not isinstance(proposal.get("nonCanonicalSuggestions"), list) or any(not isinstance(item, str) for item in proposal["nonCanonicalSuggestions"]):
            raise BoundaryError("proposal.file-corrupt", "proposal suggestions are invalid", "/nonCanonicalSuggestions", kind="persistence")
        seen: set[str] = set()
        for change in proposal["changes"]:
            if not isinstance(change, dict) or not isinstance(change.get("changeId"), str) or not change["changeId"] or change["changeId"] in seen:
                raise BoundaryError("proposal.file-corrupt", "proposal changes are invalid", "/changes", kind="persistence")
            seen.add(change["changeId"])

    def _apply_changes(self, payload: dict[str, Any]) -> dict[str, Any]:
        draft = self._stored_draft(payload)
        self._require_base_guard(payload, draft)
        if draft.get("status", "active") != "active":
            raise BoundaryError("draft.not-active", "only active drafts can be edited", "/payload/draftId", kind="conflict")
        changes = payload.get("changes")
        if not isinstance(changes, list) or not changes:
            raise BoundaryError("changes.required", "changes must be a non-empty array", "/payload/changes")
        candidate = copy.deepcopy(draft)
        change_ids = set()
        for index, change in enumerate(changes):
            if not isinstance(change, dict) or not isinstance(change.get("changeId"), str) or not change["changeId"]:
                raise BoundaryError("change.id-required", "each change requires a non-empty changeId", f"/payload/changes/{index}/changeId")
            if change["changeId"] in change_ids:
                raise BoundaryError("change.id-duplicate", "changeId values must be unique within a request", f"/payload/changes/{index}/changeId")
            change_ids.add(change["changeId"])
            self._apply_change(candidate, change, index)
        candidate["revision"] += 1
        candidate["fingerprint"] = self._draft_fingerprint(candidate)
        # Revalidate all IDs/types before mutating the workspace. Domain-invalid
        # selections are intentionally stored and reported by evaluation.
        self._validate_draft_input(candidate, include_system=True)
        evaluation = self._evaluate(candidate)
        self._replace_draft(draft, candidate)
        return {
            "draft": copy.deepcopy(candidate),
            "evaluation": evaluation,
            "appliedChanges": copy.deepcopy(changes),
        }

    def _history_get(self, payload: dict[str, Any]) -> dict[str, Any]:
        draft = self._stored_draft(payload, allow_unsupported_catalog=True)
        history = self.workspace.history(draft["draftId"]) if self.workspace else copy.deepcopy(self._histories.get(draft["draftId"], []))
        allow_unsupported = draft.get("catalogVersion") != self._catalog_for(draft).version
        for snapshot in history:
            self._validate_persisted_draft(snapshot["draft"], allow_unsupported_catalog=allow_unsupported)
        return {"draftId": draft["draftId"], "currentRevision": draft["revision"], "history": history}

    def _restore_revision(self, payload: dict[str, Any]) -> dict[str, Any]:
        draft = self._stored_draft(payload)
        self._require_base_guard(payload, draft)
        if draft.get("status", "active") != "active":
            raise BoundaryError("draft.not-active", "only active drafts can restore a revision", "/payload/draftId", kind="conflict")
        revision = payload.get("revision")
        if not isinstance(revision, int) or isinstance(revision, bool):
            raise BoundaryError("draft.revision-required", "revision must be an integer", "/payload/revision")
        history = self.workspace.history(draft["draftId"]) if self.workspace else self._histories.get(draft["draftId"], [])
        snapshot = next((item for item in history if item["revision"] == revision), None)
        if snapshot is None:
            raise BoundaryError("draft.revision-not-found", f"unknown retained revision: {revision}", "/payload/revision")
        self._validate_persisted_draft(snapshot["draft"])
        candidate = copy.deepcopy(draft)
        candidate["concept"] = copy.deepcopy(snapshot["draft"].get("concept", {}))
        candidate["selections"] = copy.deepcopy(snapshot["draft"].get("selections", {}))
        candidate["revision"] += 1
        candidate["fingerprint"] = self._draft_fingerprint(candidate)
        self._validate_draft_input(candidate, include_system=True)
        evaluation = self._evaluate(candidate)
        self._replace_draft(draft, candidate)
        return {"draft": copy.deepcopy(candidate), "evaluation": evaluation, "restoredRevision": revision}

    def _duplicate(self, payload: dict[str, Any]) -> dict[str, Any]:
        # ponytail: duplicates always evaluate under the current catalog so stale drafts stay rehomable.
        source = self._stored_draft(payload, allow_unsupported_catalog=True)
        duplicate = self._new_draft({
            "creationSystem": self._creation_system_key(source),
            "concept": source.get("concept", {}),
            "selections": source.get("selections", {}),
        })
        duplicate["revision"] = 1
        duplicate["derivedFrom"] = {
            "type": "draft",
            "draftId": source["draftId"],
            "revision": source["revision"],
            "fingerprint": source["fingerprint"],
        }
        duplicate["fingerprint"] = self._draft_fingerprint(duplicate)
        evaluation = self._evaluate(duplicate)
        self._store_new(duplicate)
        return {"draft": copy.deepcopy(duplicate), "evaluation": evaluation}

    def _finalize_monster(self, payload: dict[str, Any]) -> dict[str, Any]:
        draft_id = payload.get("draftId")
        if self.workspace and isinstance(draft_id, str) and draft_id:
            with self.workspace.lock(draft_id):
                return self._finalize_monster_locked(payload)
        return self._finalize_monster_locked(payload)

    def _finalize_monster_locked(self, payload: dict[str, Any]) -> dict[str, Any]:
        draft = self._stored_draft(payload)
        self._require_base_guard(payload, draft)
        if draft.get("status") == "archived":
            raise BoundaryError("draft.not-active", "archived drafts cannot be finalized", "/payload/draftId", kind="conflict")
        evaluation = self._evaluate(draft)
        if evaluation["status"] != "valid":
            raise BoundaryError(
                "monster.finalization-blocked",
                "only a complete valid strict draft can be finalized",
                "/payload/draftId",
                kind="product-constraint",
                details={"evaluation": evaluation},
            )
        found = self._find_finished(draft)
        if found:
            monster, monster_status = found
            self._validate_finished(monster)
        else:
            monster = self._build_finished(draft, evaluation)
            monster_status = "active"
            self._store_finished(monster)
        if draft.get("status") != "finalized" or draft.get("monsterId") != monster["monsterId"]:
            try:
                finalized = self._set_status(draft, "finalized", None, monster["monsterId"])["draft"]
            except PersistenceError:
                current = self._stored_draft({"draftId": draft["draftId"]})
                if current.get("status") != "finalized" or current.get("monsterId") != monster["monsterId"]:
                    raise
                finalized = copy.deepcopy(current)
        else:
            finalized = copy.deepcopy(draft)
        return {"monster": self._finished_view(monster, monster_status), "draft": finalized}

    def _get_monster(self, payload: dict[str, Any]) -> dict[str, Any]:
        monster, status = self._stored_monster(payload)
        return {"monster": self._finished_view(monster, status)}

    def _duplicate_monster(self, payload: dict[str, Any]) -> dict[str, Any]:
        monster, _ = self._stored_monster(payload)
        # ponytail: duplicates always evaluate under the current catalog so stale snapshots stay rehomable.
        duplicate = self._new_draft({
            "creationSystem": self._creation_system_key(monster),
            "concept": monster["concept"],
            "selections": monster["selections"],
        })
        duplicate["revision"] = 1
        duplicate["derivedFrom"] = {"type": "monster", "monsterId": monster["monsterId"]}
        duplicate["fingerprint"] = self._draft_fingerprint(duplicate)
        evaluation = self._evaluate(duplicate)
        self._store_new(duplicate)
        return {"draft": copy.deepcopy(duplicate), "evaluation": evaluation}

    def _archive_monster(self, payload: dict[str, Any]) -> dict[str, Any]:
        monster, status = self._stored_monster(payload)
        if status == "archived":
            raise BoundaryError("monster.already-archived", "monster is already archived", "/payload/monsterId", kind="conflict")
        self._set_finished_status(monster["monsterId"], status, "archived")
        return {"monster": self._finished_view(monster, "archived")}

    def _delete_draft(self, payload: dict[str, Any]) -> None:
        draft_id = payload.get("draftId")
        if not isinstance(draft_id, str) or not draft_id:
            raise BoundaryError("draft.id-required", "draftId is required", "/payload/draftId")
        if self.workspace:
            # ponytail: stale drafts stay deletable because delete never validates the catalog version.
            self.workspace.delete_draft(draft_id)
            self._drafts.pop(draft_id, None)
        else:
            if draft_id not in self._drafts:
                raise BoundaryError("draft.not-found", f"unknown draft: {draft_id}", "/payload/draftId")
            self._drafts.pop(draft_id)
        return None

    def _delete_monster(self, payload: dict[str, Any]) -> None:
        monster_id = payload.get("monsterId")
        if not isinstance(monster_id, str) or not monster_id:
            raise BoundaryError("monster.id-required", "monsterId is required", "/payload/monsterId")
        if self.workspace:
            self.workspace.delete_monster(monster_id)
            self._monsters.pop(monster_id, None)
        else:
            if monster_id not in self._monsters:
                raise BoundaryError("monster.not-found", f"unknown monster: {monster_id}", "/payload/monsterId")
            self._monsters.pop(monster_id)
            self._monster_status.pop(monster_id, None)
        return None

    def _restore_monster(self, payload: dict[str, Any]) -> dict[str, Any]:
        monster, status = self._stored_monster(payload)
        if status != "archived":
            raise BoundaryError("monster.not-archived", "only archived monsters can be restored", "/payload/monsterId", kind="conflict")
        self._set_finished_status(monster["monsterId"], status, "active")
        return {"monster": self._finished_view(monster, "active")}

    def _export_monster(self, payload: dict[str, Any]) -> dict[str, Any]:
        monster, _ = self._stored_monster(payload)
        format_name = payload.get("format", "json")
        profile = payload.get("profile", "sheet")
        if format_name not in {"json", "markdown", "html"}:
            raise BoundaryError("export.format-invalid", "format must be json, markdown, or html", "/payload/format")
        if profile not in {"sheet", "audit"}:
            raise BoundaryError("export.profile-invalid", "profile must be sheet or audit", "/payload/profile")
        if format_name == "json":
            content = copy.deepcopy(monster)
        else:
            from .exports import render_html, render_markdown
            content = render_html(monster, profile) if format_name == "html" else render_markdown(monster, profile)
        return {"monsterId": monster["monsterId"], "format": format_name, "profile": profile, "content": content}

    def _build_finished(self, draft: dict[str, Any], evaluation: dict[str, Any]) -> dict[str, Any]:
        source = {"draftId": draft["draftId"], "revision": draft["revision"], "fingerprint": draft["fingerprint"]}
        monster_id = f"monster-{uuid.uuid5(uuid.NAMESPACE_URL, _canonical_json(source)).hex}"
        trace = copy.deepcopy(evaluation["derivationTrace"])
        monster = {
            "schemaVersion": "1",
            "kind": "FinishedMonster",
            "monsterId": monster_id,
            "sourceDraft": source,
            "creationSystem": self._creation_system_key(draft),
            "catalogVersion": draft["catalogVersion"],
            "mode": "strict",
            "concept": copy.deepcopy(draft.get("concept", {})),
            "selections": copy.deepcopy(draft["selections"]),
            "result": copy.deepcopy(evaluation["effective"]),
            "fieldAnnotations": {},
            "derivationTrace": trace,
            "audit": {
                "acceptedAIRationale": [],
                "creationDecisions": self._creation_system_for(draft).creation_decisions(draft["selections"], trace),
                "validationFindings": copy.deepcopy(evaluation["issues"]),
                "sources": _trace_sources(trace),
            },
        }
        monster["fingerprint"] = _finished_fingerprint(monster)
        return monster

    def _find_finished(self, draft: dict[str, Any]) -> tuple[dict[str, Any], str] | None:
        if self.workspace:
            return self.workspace.find_monster(draft["draftId"], draft["revision"], draft["fingerprint"])
        source = {"draftId": draft["draftId"], "revision": draft["revision"], "fingerprint": draft["fingerprint"]}
        for monster_id, monster in self._monsters.items():
            if monster.get("sourceDraft") == source:
                return copy.deepcopy(monster), self._monster_status[monster_id]
        return None

    def _store_finished(self, monster: dict[str, Any]) -> None:
        if self.workspace:
            self.workspace.create_monster(monster)
        else:
            existing = self._monsters.get(monster["monsterId"])
            if existing is not None and existing != monster:
                raise BoundaryError("monster.id-conflict", "monsterId already exists", "/monsterId", kind="conflict")
            self._monsters[monster["monsterId"]] = copy.deepcopy(monster)
            self._monster_status.setdefault(monster["monsterId"], "active")
            self._monster_saved_at[monster["monsterId"]] = _now()

    def _stored_monster(self, payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
        monster_id = payload.get("monsterId")
        if not isinstance(monster_id, str) or not monster_id:
            raise BoundaryError("monster.id-required", "monsterId is required", "/payload/monsterId")
        if self.workspace:
            monster, status = self.workspace.load_monster(monster_id)
        else:
            try:
                monster, status = copy.deepcopy(self._monsters[monster_id]), self._monster_status[monster_id]
            except KeyError as exc:
                raise BoundaryError("monster.not-found", f"unknown monster: {monster_id}", "/payload/monsterId") from exc
        self._validate_finished(monster)
        return monster, status

    @staticmethod
    def _validate_finished(monster: dict[str, Any]) -> None:
        required = {
            "schemaVersion", "kind", "monsterId", "sourceDraft", "catalogVersion", "mode", "concept", "selections",
            "result", "fieldAnnotations", "derivationTrace", "audit", "fingerprint",
        }
        if not isinstance(monster, dict) or not required <= set(monster):
            raise BoundaryError("monster.file-corrupt", "finished monster is missing required fields", "", kind="persistence")
        if monster.get("schemaVersion") != "1" or monster.get("kind") != "FinishedMonster" or monster.get("mode") != "strict":
            raise BoundaryError("monster.file-schema-unsupported", "unsupported FinishedMonster snapshot", "/schemaVersion", kind="persistence")
        # Resolve the legacy default for validation only. Never inject it into
        # the snapshot before its original fingerprint has been checked.
        if "creationSystem" in monster:
            creation_system_key(monster["creationSystem"])
        object_fields = ("sourceDraft", "concept", "selections", "result", "fieldAnnotations", "audit")
        if (
            not isinstance(monster.get("monsterId"), str)
            or any(not isinstance(monster.get(field), dict) for field in object_fields)
            or not isinstance(monster.get("derivationTrace"), list)
        ):
            raise BoundaryError("monster.file-corrupt", "finished monster content is invalid", "", kind="persistence")
        if monster.get("fingerprint") != _finished_fingerprint(monster):
            raise BoundaryError("monster.fingerprint-invalid", "finished monster fingerprint does not match its contents", "/fingerprint", kind="persistence")

    @staticmethod
    def _finished_view(monster: dict[str, Any], status: str) -> dict[str, Any]:
        value = copy.deepcopy(monster)
        value["status"] = status
        return value

    def _set_finished_status(self, monster_id: str, base_status: str, status: str) -> None:
        if self.workspace:
            self.workspace.set_monster_status(monster_id, base_status, status)
        else:
            if self._monster_status.get(monster_id) != base_status:
                raise BoundaryError("monster.status-conflict", "monster status changed", "/payload/monsterId", kind="conflict")
            self._monster_status[monster_id] = status

    def _archive(self, payload: dict[str, Any]) -> dict[str, Any]:
        draft = self._stored_draft(payload)
        self._require_base_guard(payload, draft)
        status = draft.get("status", "active")
        if status == "archived":
            raise BoundaryError("draft.already-archived", "draft is already archived", "/payload/draftId", kind="conflict")
        return self._set_status(draft, "archived", status)

    def _restore(self, payload: dict[str, Any]) -> dict[str, Any]:
        draft = self._stored_draft(payload)
        self._require_base_guard(payload, draft)
        if draft.get("status") != "archived":
            raise BoundaryError("draft.not-archived", "only archived drafts can be restored", "/payload/draftId", kind="conflict")
        previous = self.workspace.previous_status(draft["draftId"]) if self.workspace else self._previous_status.get(draft["draftId"])
        if previous not in {"active", "finalized"}:
            raise BoundaryError("draft.restore-state-invalid", "draft has no restorable status", "/payload/draftId", kind="persistence")
        return self._set_status(draft, previous, None)

    def _set_status(self, draft: dict[str, Any], status: str, previous_status: str | None, monster_id: str | None = None) -> dict[str, Any]:
        if self.workspace:
            self.workspace.set_status(
                draft["draftId"], draft["revision"], draft["fingerprint"], draft.get("status", "active"), status, previous_status, monster_id,
            )
        else:
            if previous_status is None:
                self._previous_status.pop(draft["draftId"], None)
            else:
                self._previous_status[draft["draftId"]] = previous_status
            self._drafts[draft["draftId"]]["status"] = status
            if monster_id is not None:
                self._drafts[draft["draftId"]]["monsterId"] = monster_id
            self._draft_saved_at[draft["draftId"]] = _now()
        candidate = copy.deepcopy(draft)
        candidate["status"] = status
        if monster_id is not None:
            candidate["monsterId"] = monster_id
        return {"draft": candidate, "evaluation": self._evaluate(candidate)}

    def _require_base_guard(self, payload: dict[str, Any], draft: dict[str, Any]) -> None:
        if "baseRevision" not in payload or "baseFingerprint" not in payload:
            raise BoundaryError("draft.base-guard-required", "mutations require baseRevision and baseFingerprint", "/payload")
        if payload["baseRevision"] != draft["revision"] or payload["baseFingerprint"] != draft["fingerprint"]:
            raise BoundaryError(
                "draft.revision-conflict", "draft revision or fingerprint is stale", "/payload/baseRevision", kind="conflict",
                details={"currentDraft": copy.deepcopy(draft), "currentEvaluation": self._evaluate(draft)},
            )

    def _store_new(self, draft: dict[str, Any]) -> None:
        if self.workspace:
            self.workspace.create(draft)
        else:
            self._drafts[draft["draftId"]] = copy.deepcopy(draft)
            self._histories[draft["draftId"]] = []
            self._draft_saved_at[draft["draftId"]] = _now()

    def _replace_draft(self, previous: dict[str, Any], candidate: dict[str, Any]) -> None:
        if self.workspace:
            self.workspace.replace(candidate, previous["revision"], previous["fingerprint"], previous.get("status", "active"))
        else:
            snapshot = {
                "revision": previous["revision"],
                "fingerprint": previous["fingerprint"],
                "draft": copy.deepcopy(previous),
            }
            self._histories[candidate["draftId"]] = [snapshot, *self._histories.get(candidate["draftId"], [])][:20]
            self._drafts[candidate["draftId"]] = copy.deepcopy(candidate)
            self._draft_saved_at[candidate["draftId"]] = _now()

    def _apply_change(self, draft: dict[str, Any], change: Any, index: int) -> None:
        path = f"/payload/changes/{index}"
        if not isinstance(change, dict):
            raise BoundaryError("change.invalid", "change must be an object", path)
        change_type = change.get("type")
        if change_type not in {
            "set-selection", "set_selection", "unset-selection", "unset_selection",
            "set-concept", "set_concept", "unset-concept", "unset_concept",
        }:
            raise BoundaryError("change.type-invalid", "only typed selection or concept changes are supported", f"{path}/type")
        if "field" in change and "path" in change:
            raise BoundaryError("change.path-ambiguous", "change may provide field or path, not both", f"{path}/path")
        field = change.get("field", change.get("key"))
        concept_change = change_type in {"set-concept", "set_concept", "unset-concept", "unset_concept"}
        if "path" in change:
            raw_path = change["path"]
            if not isinstance(raw_path, str):
                raise BoundaryError("change.path-invalid", "change path must be a string", f"{path}/path")
            segments = raw_path.split("/")
            expected_root = "concept" if concept_change else "selections"
            if len(segments) != 3 or segments[0] != "" or segments[1] != expected_root or not segments[2]:
                raise BoundaryError("change.path-invalid", "change path must identify one concept or selection field", f"{path}/path")
            field = segments[2]
        prefixes = ("concept.",) if concept_change else ("selections.", "selection.")
        for prefix in prefixes:
            if isinstance(field, str) and field.startswith(prefix):
                field = field[len(prefix):]
        allowed = self._CONCEPT_FIELDS if concept_change else self._creation_system_for(draft).selection_fields
        if field not in allowed:
            noun = "concept field" if concept_change else "draft selection"
            raise BoundaryError("change.field-invalid", f"field is not a supported {noun}", f"{path}/field")
        target = draft["concept"] if concept_change else draft["selections"]
        if change_type in {"set-selection", "set_selection", "set-concept", "set_concept"}:
            if "value" not in change:
                raise BoundaryError("change.value-required", "set change requires value", f"{path}/value")
            target[field] = copy.deepcopy(change["value"])
        else:
            target.pop(field, None)

    def _new_draft(self, raw: Any) -> dict[str, Any]:
        if not isinstance(raw, dict):
            raise BoundaryError("draft.invalid", "draft must be an object", "/payload/draft")
        if "schemaVersion" in raw and raw["schemaVersion"] != self.DRAFT_SCHEMA_VERSION:
            raise BoundaryError("draft.schema-unsupported", "unsupported draft schemaVersion", "/schemaVersion")
        system = self._creation_system_key(raw)
        catalog = self.catalogs.for_system(system)
        if "catalogVersion" in raw and raw["catalogVersion"] != catalog.version:
            raise BoundaryError("catalog.version-unsupported", "draft uses an unsupported catalog version", "/catalogVersion", kind="catalog-data")
        concept = raw.get("concept", {})
        selections = raw.get("selections", {})
        if not isinstance(concept, dict):
            raise BoundaryError("draft.concept-invalid", "concept must be an object", "/concept")
        if not isinstance(selections, dict):
            raise BoundaryError("draft.selections-invalid", "selections must be an object", "/selections")
        draft = {
            "schemaVersion": self.DRAFT_SCHEMA_VERSION,
            "creationSystem": system,
            "draftId": f"draft-{uuid.uuid4().hex}",
            "catalogVersion": catalog.version,
            "revision": 0,
            "status": "active",
            "concept": copy.deepcopy(concept),
            "selections": copy.deepcopy(selections),
        }
        self._validate_draft_input(draft)
        draft["fingerprint"] = self._draft_fingerprint(draft)
        return draft

    def _prepare_external_draft(self, raw: Any) -> dict[str, Any]:
        if not isinstance(raw, dict):
            raise BoundaryError("draft.invalid", "draft must be an object", "/payload/draft")
        draft = copy.deepcopy(raw)
        self._validate_draft_input(draft, include_system=True)
        if "fingerprint" in draft and draft["fingerprint"] != self._draft_fingerprint(draft):
            raise BoundaryError("draft.fingerprint-invalid", "draft fingerprint does not match its contents", "/fingerprint")
        return draft

    def _stored_draft(self, payload: dict[str, Any], *, allow_unsupported_catalog: bool = False) -> dict[str, Any]:
        draft_id = payload.get("draftId")
        if not isinstance(draft_id, str) or not draft_id:
            raise BoundaryError("draft.id-required", "draftId is required", "/payload/draftId")
        if self.workspace:
            draft = self._validate_persisted_draft(
                self.workspace.load(draft_id),
                allow_unsupported_catalog=allow_unsupported_catalog,
            )
            allow_history_catalog = allow_unsupported_catalog and draft.get("catalogVersion") != self._catalog_for(draft).version
            for snapshot in self.workspace.history(draft_id):
                self._validate_persisted_draft(snapshot["draft"], allow_unsupported_catalog=allow_history_catalog)
            return draft
        try:
            return self._drafts[draft_id]
        except KeyError as exc:
            raise BoundaryError("draft.not-found", f"unknown draft: {draft_id}", "/payload/draftId") from exc

    def _validate_persisted_draft(self, draft: dict[str, Any], *, allow_unsupported_catalog: bool = False) -> dict[str, Any]:
        if draft.get("schemaVersion") != self.DRAFT_SCHEMA_VERSION:
            raise BoundaryError("draft.schema-unsupported", "unsupported draft schemaVersion", "/schemaVersion")
        if not isinstance(draft.get("concept"), dict) or not isinstance(draft.get("selections"), dict):
            raise BoundaryError("draft.file-corrupt", "persisted draft content is invalid", "", kind="persistence")
        if draft.get("fingerprint") != self._draft_fingerprint(draft):
            raise BoundaryError("draft.fingerprint-invalid", "draft fingerprint does not match its contents", "/fingerprint", kind="persistence")
        if draft.get("catalogVersion") != self._catalog_for(draft).version:
            if allow_unsupported_catalog:
                return draft
            raise BoundaryError("catalog.version-unsupported", "draft uses an unsupported catalog version", "/catalogVersion", kind="catalog-data")
        self._validate_draft_input(draft, include_system=True)
        return draft

    def _validate_draft_input(self, draft: dict[str, Any], *, include_system: bool = False) -> None:
        concept = draft.get("concept")
        if not isinstance(concept, dict):
            raise BoundaryError("draft.concept-invalid", "concept must be an object", "/concept")
        for field in ("name", "role", "creatureType", "description"):
            if field in concept and not isinstance(concept[field], str):
                raise BoundaryError("draft.concept-invalid", f"{field} must be a string", f"/concept/{field}")
        if "targetCR" in concept and (not isinstance(concept["targetCR"], (int, float)) or isinstance(concept["targetCR"], bool)):
            raise BoundaryError("draft.concept-invalid", "targetCR must be numeric", "/concept/targetCR")
        selections = draft.get("selections")
        if not isinstance(selections, dict):
            raise BoundaryError("draft.selections-invalid", "selections must be an object", "/selections")
        system = self._creation_system_key(draft)
        catalog = self.catalogs.for_system(system)
        if include_system:
            if draft.get("schemaVersion") != self.DRAFT_SCHEMA_VERSION:
                raise BoundaryError("draft.schema-unsupported", "unsupported draft schemaVersion", "/schemaVersion")
            if draft.get("catalogVersion") != catalog.version:
                raise BoundaryError("catalog.version-unsupported", "draft uses an unsupported catalog version", "/catalogVersion", kind="catalog-data")
        self._creation_system_for(draft).validate_input(draft)

    @staticmethod
    def _error(request_id, error: BoundaryError) -> dict[str, Any]:
        value = {"code": error.code, "kind": error.kind, "message": error.message, "path": error.path}
        if error.details is not None:
            value["details"] = error.details
        return {"ok": False, "requestId": request_id, "error": value}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _finished_fingerprint(monster: dict[str, Any]) -> str:
    value = copy.deepcopy(monster)
    value.pop("fingerprint", None)
    value.pop("status", None)
    return _fingerprint(value)


def _trace_sources(trace: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sources = []
    seen = set()
    for entry in trace:
        for source in entry.get("sourceRefs", []):
            key = _canonical_json(source)
            if key not in seen:
                seen.add(key)
                sources.append(copy.deepcopy(source))
    return sources


def _fingerprint_draft_content(
    draft: dict[str, Any], selections: dict[str, Any]
) -> str:
    # Identity is semantic content, not the process-local opaque ID or
    # revision counter. Each adapter owns any system-specific normalization.
    value = {
        "schemaVersion": draft.get("schemaVersion"),
        "catalogVersion": draft.get("catalogVersion"),
        "concept": draft.get("concept", {}),
        "selections": selections,
    }
    # Preserve every legacy fingerprint while binding new drafts to their
    # explicitly selected, immutable rules system.
    if "creationSystem" in draft:
        value["creationSystem"] = draft["creationSystem"]
    return _fingerprint(value)
