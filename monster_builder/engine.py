"""The first deterministic public execute vertical slice."""

from __future__ import annotations

import copy
import hashlib
import json
import uuid
from pathlib import Path
from typing import Any

from .catalog import Catalog, CatalogError


class BoundaryError(ValueError):
    def __init__(self, code: str, message: str, path: str = "", *, kind: str = "boundary", details: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.path = path
        self.kind = kind
        self.details = details


class Engine:
    """Owns the in-memory draft workspace for the MVP vertical slice."""

    PROTOCOL_VERSION = "1"
    DRAFT_SCHEMA_VERSION = "1"
    _SELECTION_FIELDS = {
        "cr", "arrayId", "creatureTypeGraftId", "classGraftId", "subtypeGraftIds",
        "templateGraftId", "sizeId", "saveSwap", "abilityModifiers", "options",
        "skills", "attacks", "speed", "spells", "spellListId", "spellLevelSource",
        "spellcastingAbility",
    }
    _COMPUTED_SELECTION_FIELDS = {
        "ac", "touchAC", "flatFootedAC", "fortitude", "reflex", "will", "cmd", "cmb",
        "hp", "abilityDC", "spellDC", "canonical", "effective", "derivationTrace",
        "damageExpression", "averageDamage", "attackBonus", "initiative", "hitDice",
        "concentration", "evaluation", "defenses",
    }
    _ABILITY_NAMES = {"strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"}
    _ATTACK_PROFILES = {"weapon.high", "weapon.low", "natural.two", "natural.three"}
    _DAMAGE_DICE = {"d4", "d6", "d8", "d10", "d12", "2d6", "3d6"}

    def __init__(self, catalog: Catalog | None = None):
        self.catalog = catalog or Catalog.load()
        self._drafts: dict[str, dict[str, Any]] = {}
        self._idempotency: dict[str, tuple[str, dict[str, Any]]] = {}

    @classmethod
    def from_catalog(cls, path: str | Path) -> "Engine":
        return cls(Catalog.load(path))

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
            else:
                raise BoundaryError(
                    "operation.unsupported",
                    f"unsupported operation: {operation}",
                    "/operation",
                )
            response = {"ok": True, "requestId": request_id, "result": result}
            if operation in {"draft.create", "draft.applyChanges"}:
                self._idempotency[request_id] = (request_fingerprint, copy.deepcopy(response))
            return response
        except BoundaryError as exc:
            return self._error(request_id, exc)
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
        self._drafts[draft["draftId"]] = draft
        return {"draft": copy.deepcopy(draft), "evaluation": evaluation}

    def _get(self, payload: dict[str, Any]) -> dict[str, Any]:
        draft = self._stored_draft(payload)
        return {"draft": copy.deepcopy(draft), "evaluation": self._evaluate(draft)}

    def _evaluate_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        if "draftId" in payload:
            draft = self._stored_draft(payload)
        elif "draft" in payload:
            draft = self._prepare_external_draft(payload["draft"])
        else:
            raise BoundaryError("draft.required", "draft or draftId is required", "/payload")
        return {"evaluation": self._evaluate(draft)}

    def _apply_changes(self, payload: dict[str, Any]) -> dict[str, Any]:
        draft = self._stored_draft(payload)
        if "baseRevision" not in payload or "baseFingerprint" not in payload:
            raise BoundaryError(
                "draft.base-guard-required",
                "mutations require baseRevision and baseFingerprint",
                "/payload",
            )
        if payload["baseRevision"] != draft["revision"] or payload["baseFingerprint"] != draft["fingerprint"]:
            current_evaluation = self._evaluate(draft)
            raise BoundaryError(
                "draft.revision-conflict",
                "draft revision or fingerprint is stale",
                "/payload/baseRevision",
                kind="conflict",
                details={"currentDraft": copy.deepcopy(draft), "currentEvaluation": current_evaluation},
            )
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
        candidate["fingerprint"] = _draft_fingerprint(candidate)
        # Revalidate all IDs/types before mutating the workspace. Domain-invalid
        # selections are intentionally stored and reported by evaluation.
        self._validate_draft_input(candidate, include_system=True)
        evaluation = self._evaluate(candidate)
        self._drafts[candidate["draftId"]] = candidate
        return {
            "draft": copy.deepcopy(candidate),
            "evaluation": evaluation,
            "appliedChanges": copy.deepcopy(changes),
        }

    def _apply_change(self, draft: dict[str, Any], change: Any, index: int) -> None:
        path = f"/payload/changes/{index}"
        if not isinstance(change, dict):
            raise BoundaryError("change.invalid", "change must be an object", path)
        if change.get("type") not in {"set-selection", "set_selection", "unset-selection", "unset_selection"}:
            raise BoundaryError("change.type-invalid", "only typed selection changes are supported", f"{path}/type")
        field = change.get("field", change.get("key"))
        if isinstance(field, str) and field.startswith("selections."):
            field = field[len("selections."):]
        if isinstance(field, str) and field.startswith("selection."):
            field = field[len("selection."):]
        if field not in self._SELECTION_FIELDS:
            raise BoundaryError("change.field-invalid", "field is not a supported draft selection", f"{path}/field")
        if change["type"] in {"set-selection", "set_selection"}:
            if "value" not in change:
                raise BoundaryError("change.value-required", "set-selection requires value", f"{path}/value")
            draft["selections"][field] = copy.deepcopy(change["value"])
        else:
            draft["selections"].pop(field, None)

    def _new_draft(self, raw: Any) -> dict[str, Any]:
        if not isinstance(raw, dict):
            raise BoundaryError("draft.invalid", "draft must be an object", "/payload/draft")
        if "schemaVersion" in raw and raw["schemaVersion"] != self.DRAFT_SCHEMA_VERSION:
            raise BoundaryError("draft.schema-unsupported", "unsupported draft schemaVersion", "/schemaVersion")
        if "catalogVersion" in raw and raw["catalogVersion"] != self.catalog.version:
            raise BoundaryError("catalog.version-unsupported", "draft uses an unsupported catalog version", "/catalogVersion", kind="catalog-data")
        concept = raw.get("concept", {})
        selections = raw.get("selections", {})
        if not isinstance(concept, dict):
            raise BoundaryError("draft.concept-invalid", "concept must be an object", "/concept")
        if not isinstance(selections, dict):
            raise BoundaryError("draft.selections-invalid", "selections must be an object", "/selections")
        draft = {
            "schemaVersion": self.DRAFT_SCHEMA_VERSION,
            "draftId": f"draft-{uuid.uuid4().hex}",
            "catalogVersion": self.catalog.version,
            "revision": 0,
            "concept": copy.deepcopy(concept),
            "selections": copy.deepcopy(selections),
        }
        self._validate_draft_input(draft)
        draft["fingerprint"] = _draft_fingerprint(draft)
        return draft

    def _prepare_external_draft(self, raw: Any) -> dict[str, Any]:
        if not isinstance(raw, dict):
            raise BoundaryError("draft.invalid", "draft must be an object", "/payload/draft")
        draft = copy.deepcopy(raw)
        self._validate_draft_input(draft, include_system=True)
        if "fingerprint" in draft and draft["fingerprint"] != _draft_fingerprint(draft):
            raise BoundaryError("draft.fingerprint-invalid", "draft fingerprint does not match its contents", "/fingerprint")
        return draft

    def _stored_draft(self, payload: dict[str, Any]) -> dict[str, Any]:
        draft_id = payload.get("draftId")
        if not isinstance(draft_id, str) or not draft_id:
            raise BoundaryError("draft.id-required", "draftId is required", "/payload/draftId")
        try:
            return self._drafts[draft_id]
        except KeyError as exc:
            raise BoundaryError("draft.not-found", f"unknown draft: {draft_id}", "/payload/draftId") from exc

    def _validate_draft_input(self, draft: dict[str, Any], *, include_system: bool = False) -> None:
        selections = draft.get("selections")
        if not isinstance(selections, dict):
            raise BoundaryError("draft.selections-invalid", "selections must be an object", "/selections")
        unknown = set(selections) - self._SELECTION_FIELDS
        computed = unknown & self._COMPUTED_SELECTION_FIELDS
        if computed:
            field = sorted(computed)[0]
            raise BoundaryError("draft.computed-selection", "computed values are not draft selections", f"/selections/{field}")
        if unknown:
            field = sorted(unknown)[0]
            raise BoundaryError("draft.selection-unknown", f"unknown selection field: {field}", f"/selections/{field}")
        if include_system:
            if draft.get("schemaVersion") != self.DRAFT_SCHEMA_VERSION:
                raise BoundaryError("draft.schema-unsupported", "unsupported draft schemaVersion", "/schemaVersion")
            if draft.get("catalogVersion") != self.catalog.version:
                raise BoundaryError("catalog.version-unsupported", "draft uses an unsupported catalog version", "/catalogVersion", kind="catalog-data")
        self._validate_selection_shapes(selections)
        self._validate_selection_ids(selections)

    def _validate_selection_shapes(self, selections: dict[str, Any]) -> None:
        if "cr" in selections and (not isinstance(selections["cr"], (int, float)) or isinstance(selections["cr"], bool)):
            raise BoundaryError("selection.type-invalid", "cr must be numeric", "/selections/cr")
        for field in ("arrayId", "creatureTypeGraftId", "sizeId", "classGraftId", "templateGraftId", "spellListId", "spellLevelSource", "spellcastingAbility"):
            if field in selections and selections[field] is not None and not isinstance(selections[field], str):
                raise BoundaryError("selection.type-invalid", f"{field} must be a string or null", f"/selections/{field}")
        for field in ("subtypeGraftIds", "options", "attacks", "spells"):
            if field in selections and not isinstance(selections[field], list):
                raise BoundaryError("selection.type-invalid", f"{field} must be an array", f"/selections/{field}")
        if "abilityModifiers" in selections:
            values = selections["abilityModifiers"]
            if not isinstance(values, dict):
                raise BoundaryError("selection.type-invalid", "abilityModifiers must be an object", "/selections/abilityModifiers")
            for key, value in values.items():
                if key not in self._ABILITY_NAMES or not isinstance(value, int) or isinstance(value, bool):
                    raise BoundaryError("selection.type-invalid", "ability modifiers must map ability names to integers", f"/selections/abilityModifiers/{key}")
        if "skills" in selections:
            skills = selections["skills"]
            if not isinstance(skills, dict) or any(not isinstance(skills.get(key, []), list) for key in ("master", "good")):
                raise BoundaryError("selection.type-invalid", "skills must contain master and good arrays", "/selections/skills")
            if any(not isinstance(skill, str) for key in ("master", "good") for skill in skills.get(key, [])):
                raise BoundaryError("selection.type-invalid", "skill IDs must be strings", "/selections/skills")
        if "speed" in selections:
            if not isinstance(selections["speed"], dict) or any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in selections["speed"].values()):
                raise BoundaryError("selection.type-invalid", "speed values must be non-negative integers", "/selections/speed")
        if "saveSwap" in selections and selections["saveSwap"] is not None:
            swap = selections["saveSwap"]
            if not isinstance(swap, dict) or not isinstance(swap.get("from"), str) or not isinstance(swap.get("to"), str):
                raise BoundaryError("selection.type-invalid", "saveSwap must contain from and to strings", "/selections/saveSwap")

    def _validate_selection_ids(self, selections: dict[str, Any]) -> None:
        for field, kind in (("arrayId", "array"), ("creatureTypeGraftId", "creatureType"), ("classGraftId", "classGraft"), ("sizeId", "size"), ("templateGraftId", "template"), ("spellListId", "spellList")):
            value = selections.get(field)
            if value is not None:
                self._resolve(kind, value, f"/selections/{field}")
        for index, value in enumerate(selections.get("subtypeGraftIds", [])):
            self._resolve("subtype", value, f"/selections/subtypeGraftIds/{index}")
        for index, option in enumerate(selections.get("options", [])):
            if not isinstance(option, dict) or not isinstance(option.get("optionId"), str):
                raise BoundaryError("selection.type-invalid", "options must contain optionId objects", f"/selections/options/{index}")
            self._resolve("option", option["optionId"], f"/selections/options/{index}/optionId")
            parameters = option.get("parameters", {})
            if not isinstance(parameters, dict):
                raise BoundaryError("selection.type-invalid", "option parameters must be an object", f"/selections/options/{index}/parameters")
            definition = self.catalog.data["options"].get(option["optionId"])
            if definition is None:
                canonical_id, definition = self._resolve("option", option["optionId"], f"/selections/options/{index}/optionId")
            parameter_definitions = definition.get("parameters", {})
            for parameter_name, parameter_value in parameters.items():
                expected = parameter_definitions.get(parameter_name)
                if expected is None:
                    raise BoundaryError("selection.parameter-unknown", "option parameter is not catalogued", f"/selections/options/{index}/parameters/{parameter_name}")
                if expected.get("type") in {"string", "enum"} and not isinstance(parameter_value, str):
                    raise BoundaryError("selection.parameter-type-invalid", "option parameter must be a string", f"/selections/options/{index}/parameters/{parameter_name}")
        for index, skill in enumerate(selections.get("skills", {}).get("master", []) + selections.get("skills", {}).get("good", [])):
            self._resolve("skill", skill, f"/selections/skills/{index}")
        for index, attack in enumerate(selections.get("attacks", [])):
            if not isinstance(attack, dict):
                raise BoundaryError("selection.type-invalid", "attacks must contain objects", f"/selections/attacks/{index}")
            if not isinstance(attack.get("name"), str) or not isinstance(attack.get("attackProfile"), str) or attack.get("attackProfile") not in self._ATTACK_PROFILES:
                raise BoundaryError("selection.type-invalid", "attack requires name and a catalogued attackProfile", f"/selections/attacks/{index}")
            if "profileEntry" in attack and (not isinstance(attack["profileEntry"], int) or isinstance(attack["profileEntry"], bool) or attack["profileEntry"] < 0):
                raise BoundaryError("selection.type-invalid", "profileEntry must be a non-negative integer", f"/selections/attacks/{index}/profileEntry")
            natural_id = attack.get("naturalAttackId")
            if natural_id is not None:
                self._resolve("naturalAttack", natural_id, f"/selections/attacks/{index}/naturalAttackId")
            if "damageDie" in attack:
                if not isinstance(attack["damageDie"], str):
                    raise BoundaryError("selection.type-invalid", "damageDie must be a string", f"/selections/attacks/{index}/damageDie")
                if attack["damageDie"] not in self._DAMAGE_DICE:
                    raise BoundaryError("catalog.unknown-id", "unknown damage die", f"/selections/attacks/{index}/damageDie", kind="catalog-data")
        for index, spell in enumerate(selections.get("spells", [])):
            if not isinstance(spell, dict) or not isinstance(spell.get("spellId"), str):
                raise BoundaryError("selection.type-invalid", "spells must contain spellId objects", f"/selections/spells/{index}")
            self._resolve("spell", spell["spellId"], f"/selections/spells/{index}/spellId")
            if "spellLevelSource" in spell and not isinstance(spell["spellLevelSource"], str):
                raise BoundaryError("selection.type-invalid", "spellLevelSource must be a string", f"/selections/spells/{index}/spellLevelSource")
            if "metamagic" in spell:
                if not isinstance(spell["metamagic"], list) or any(not isinstance(value, str) for value in spell["metamagic"]):
                    raise BoundaryError("selection.type-invalid", "metamagic must be an array of rule IDs", f"/selections/spells/{index}/metamagic")
                for metamagic in spell["metamagic"]:
                    if metamagic not in self.catalog.data["metamagic"]:
                        raise BoundaryError("catalog.unknown-id", f"unknown metamagic rule: {metamagic}", f"/selections/spells/{index}/metamagic", kind="catalog-data")

    def _resolve(self, kind: str, value: str, path: str) -> tuple[str, dict[str, Any]]:
        try:
            return self.catalog.resolve_id(kind, value)
        except CatalogError as exc:
            if "must be" in str(exc):
                raise BoundaryError("selection.type-invalid", str(exc), path) from exc
            raise BoundaryError("catalog.unknown-id", str(exc), path, kind="catalog-data") from exc

    def _evaluate(self, draft: dict[str, Any]) -> dict[str, Any]:
        issues: list[dict[str, Any]] = []
        selections = draft.get("selections", {})
        default_source_ref = self.catalog.data["arrays"]["combatant"]["mainStatistics"]["2"]["sourceRef"]
        required = ("cr", "arrayId", "creatureTypeGraftId", "sizeId", "abilityModifiers", "options", "skills", "attacks", "speed")
        for field in required:
            if field not in selections or selections[field] is None:
                issues.append(self._issue("draft.missing-selection", f"/selections/{field}", "required selection is missing", "source-rule", "error", default_source_ref))
        if issues:
            return self._evaluation("incomplete", issues)

        cr = selections["cr"]
        array_id, array = self._resolve("array", selections["arrayId"], "/selections/arrayId")
        cr_key = _cr_key(cr)
        if cr_key not in array["mainStatistics"]:
            raise BoundaryError("catalog.cr-unsupported", f"catalog has no CR row: {cr}", "/selections/cr", kind="catalog-data")
        main = array["mainStatistics"][cr_key]
        attack_table = array["attackStatistics"][cr_key]
        type_id, creature_type = self._resolve("creatureType", selections["creatureTypeGraftId"], "/selections/creatureTypeGraftId")
        size_id, size = self._resolve("size", selections["sizeId"], "/selections/sizeId")

        if selections.get("classGraftId") is not None:
            # Class graft data is deliberately not silently approximated in this slice.
            issues.append(self._issue("class-graft.unsupported", "/selections/classGraftId", "class grafts are not in the first catalog slice", "product-constraint", "error"))
        if size.get("minCR") is not None and cr < size["minCR"]:
            issues.append(self._issue("size.cr-too-low", "/selections/sizeId", "size graft is below its minimum CR", "source-rule", "error", size.get("sourceRef")))
        if size.get("maxCR") is not None and cr > size["maxCR"]:
            issues.append(self._issue("size.cr-too-high", "/selections/sizeId", "size graft is above its maximum CR", "source-rule", "error", size.get("sourceRef")))
        target_cr = draft.get("concept", {}).get("targetCR")
        if target_cr is not None and target_cr != cr:
            issues.append(self._issue("concept.target-cr-mismatch", "/concept/targetCR", "concept target CR differs from the selected CR", "product-constraint", "warning"))

        abilities = selections["abilityModifiers"]
        if len(abilities) < 3:
            issues.append(self._issue("ability-modifiers.incomplete", "/selections/abilityModifiers", "three important ability modifiers are required", "source-rule", "error", main.get("sourceRef")))
        if len(abilities) > 6:
            issues.append(self._issue("ability-modifiers.too-many", "/selections/abilityModifiers", "there are only six ability modifiers", "product-constraint", "error", main.get("sourceRef")))

        adjustments = {} if selections.get("classGraftId") else creature_type.get("statisticAdjustments", {})
        fortitude = main["fortitude"] + adjustments.get("fortitude", 0)
        reflex = main["reflex"] + adjustments.get("reflex", 0)
        will = main["will"] + adjustments.get("will", 0)
        attack_adjustment = adjustments.get("attackBonus", 0)
        saves = {"fortitude": fortitude, "reflex": reflex, "will": will}
        swap = selections.get("saveSwap")
        if swap:
            if swap.get("from") not in saves or swap.get("to") not in saves or swap["from"] == swap["to"]:
                issues.append(self._issue("save-swap.invalid", "/selections/saveSwap", "save swap must name two different saves", "source-rule", "error", main.get("sourceRef")))
            else:
                saves[swap["from"]], saves[swap["to"]] = saves[swap["to"]], saves[swap["from"]]

        size_adjustments = size.get("adjustments", {})
        ac = main["ac"]
        touch_ac = min(ac, max(1, main["touchAC"] + size_adjustments.get("touchAC", 0)))
        flat_footed_ac = max(1, main["flatFootedAC"] + size_adjustments.get("flatFootedAC", 0))
        cmb = main["attackStatisticsHigh"] if "attackStatisticsHigh" in main else attack_table["weapon"]["high"]["attackBonuses"][0]
        cmb += size_adjustments.get("cmb", 0)
        cmd = main["cmd"] + size_adjustments.get("cmd", 0)

        options = selections["options"]
        slot_counts = {slot["category"]: slot["count"] for slot in main["options"]}
        remaining_slots = dict(slot_counts)
        selected_options = []
        maneuver_bonuses = {}
        for index, selected in enumerate(options):
            option_id, option = self._resolve("option", selected["optionId"], f"/selections/options/{index}/optionId")
            category = option.get("category")
            parameters = selected.get("parameters", {})
            if category not in {"combat", "magic", "social", "universal"}:
                issues.append(self._issue("option.category-invalid", f"/selections/options/{index}", "option category is not supported", "catalog-data", "error", option.get("sourceRef")))
                continue
            choices = ("universal", "combat", "magic", "social", "any") if category == "universal" else (category, "any")
            assigned_slot = next((slot for slot in choices if remaining_slots.get(slot, 0) > 0), None)
            if assigned_slot is None:
                issues.append(self._issue("option-slot.invalid", f"/selections/options/{index}", "option category exceeds its budget", "source-rule", "error", main.get("sourceRef")))
            else:
                remaining_slots[assigned_slot] -= 1
            selected_options.append({"optionId": option_id, "parameters": copy.deepcopy(parameters)})
            if option_id == "option.improved-combat-maneuver":
                maneuver = parameters.get("maneuver")
                if not isinstance(maneuver, str) or maneuver not in option["parameters"]["maneuver"]["values"]:
                    issues.append(self._issue("option.parameter-invalid", f"/selections/options/{index}/parameters/maneuver", "unknown combat maneuver", "source-rule", "error", option.get("sourceRef")))
                else:
                    attack_type = parameters.get("attackType")
                    if attack_type is not None and attack_type not in {attack.get("name") for attack in selections["attacks"]}:
                        issues.append(self._issue("option.parameter-invalid", f"/selections/options/{index}/parameters/attackType", "option attackType must name a selected attack", "source-rule", "error", option.get("sourceRef")))
                    maneuver_bonuses[maneuver] = {"cmb": cmb + option["effects"]["cmb"], "cmd": cmd + option["effects"]["cmd"]}
        expected_slots = sum(slot_counts.values())
        if len(options) != expected_slots:
            issues.append(self._issue("option-budget.mismatch", "/selections/options", f"array grants {expected_slots} option slot(s), received {len(options)}", "source-rule", "error", main.get("sourceRef")))

        skills_selection = selections["skills"]
        master = list(skills_selection.get("master", []))
        good = list(skills_selection.get("good", []))
        if len(set(master)) != len(master) or len(set(good)) != len(good) or set(master) & set(good):
            issues.append(self._issue("skills.duplicate", "/selections/skills", "a skill cannot occupy more than one slot", "source-rule", "error", main.get("sourceRef")))
        extra_master = size.get("additionalMasterSkills", [])
        extra_good = size.get("additionalGoodSkills", [])
        effective_master = list(master)
        effective_good = list(good)
        for skill in extra_master:
            if skill not in effective_master:
                effective_master.append(skill)
        for skill in extra_good:
            if skill not in effective_master and skill not in effective_good:
                effective_good.append(skill)
        if len(master) != main["masterCount"]:
            issues.append(self._issue("skills.master-budget", "/selections/skills/master", "master skill count does not match the array", "source-rule", "error", main.get("sourceRef")))
        if len(good) != main["goodCount"]:
            issues.append(self._issue("skills.good-budget", "/selections/skills/good", "good skill count does not match the array", "source-rule", "error", main.get("sourceRef")))
        restrictions = size.get("restrictions", {})
        if restrictions.get("stealthMasterForbidden") and "stealth" in master:
            issues.append(self._issue("size.skill-forbidden", "/selections/skills/master", "Stealth cannot be a master skill at this size", "source-rule", "error", size.get("sourceRef")))
        if restrictions.get("flyMasterForbidden") and "fly" in master:
            issues.append(self._issue("size.skill-forbidden", "/selections/skills/master", "Fly cannot be a master skill at this size", "source-rule", "error", size.get("sourceRef")))
        if restrictions.get("stealthGoodMasterForbidden") and ("stealth" in master or "stealth" in good):
            issues.append(self._issue("size.skill-forbidden", "/selections/skills", "Stealth cannot be a good or master skill at this size", "source-rule", "error", size.get("sourceRef")))
        if restrictions.get("flyGoodMasterForbidden") and ("fly" in master or "fly" in good):
            issues.append(self._issue("size.skill-forbidden", "/selections/skills", "Fly cannot be a good or master skill at this size", "source-rule", "error", size.get("sourceRef")))
        skill_values = {}
        for skill in effective_master:
            skill_values[skill] = main["masterBonus"]
        for skill in effective_good:
            skill_values[skill] = main["goodBonus"]
        if "perception" not in skill_values:
            skill_values["perception"] = main["goodBonus"]
        else:
            # Perception is automatically good, but an explicit master choice wins.
            pass

        attacks = self._evaluate_attacks(selections["attacks"], attack_table, size_id, attack_adjustment, issues)
        spells = self._evaluate_spells(selections, array_id, cr, main, issues)
        if array_id != "array.spellcaster" and selections.get("spells"):
            issues.append(self._issue("spells.array-required", "/selections/spells", "Step 6 spells require the spellcaster array", "source-rule", "error"))

        errors = [issue for issue in issues if issue["severity"] == "error"]
        if errors:
            return self._evaluation("invalid", issues)

        concentration = None
        if array_id == "array.spellcaster":
            spellcasting_ability = selections.get("spellcastingAbility")
            if spellcasting_ability is None:
                candidates = [ability for ability in ("intelligence", "wisdom", "charisma") if ability in abilities]
                spellcasting_ability = max(candidates, key=lambda ability: abilities[ability]) if candidates else "charisma"
            concentration = cr + abilities.get(spellcasting_ability, 0)

        canonical = {
            "cr": cr,
            "arrayId": array_id,
            "creatureTypeGraftId": type_id,
            "sizeId": size_id,
            "defenses": {"ac": ac, "touchAC": touch_ac, "flatFootedAC": flat_footed_ac, **saves, "cmd": cmd, "hp": main["hp"]},
            "abilityDC": main["abilityDC"],
            "spellDC": main["spellDC"],
            "abilityModifiers": copy.deepcopy(abilities),
            "skills": skill_values,
            "initiative": abilities.get("dexterity", 0),
            "hitDice": int(max(1, cr)),
            "concentration": concentration,
            "cmb": cmb,
            "maneuverBonuses": maneuver_bonuses,
            "attacks": attacks,
            "options": selected_options,
            "senses": list(dict.fromkeys(creature_type.get("automaticTraits", []))),
            "speed": copy.deepcopy(selections["speed"]),
            "spells": spells,
        }
        trace = self._trace(draft, main, attack_table, creature_type, size, canonical)
        return {
            "status": "valid",
            "mode": "strict",
            "canonical": canonical,
            "effective": copy.deepcopy(canonical),
            "issues": sorted(issues, key=lambda issue: (issue["path"], issue["code"])),
            "derivationTrace": trace,
        }

    def _evaluate_attacks(self, selections, attack_table, size_id, attack_adjustment, issues):
        attacks = []
        size_name = size_id.rsplit(".", 1)[-1]
        for index, selected in enumerate(selections):
            profile_name = selected["attackProfile"]
            family, profile_key = profile_name.split(".")
            profile = attack_table["weapon" if family == "weapon" else "natural"][profile_key]
            profile_entry_index = selected.get("profileEntry", 0)
            if profile_entry_index >= len(profile.get("entries", [])):
                issues.append(self._issue("attack.profile-entry-invalid", f"/selections/attacks/{index}/profileEntry", "attack profile entry is not present in the catalog", "catalog-data", "error", attack_table.get("sourceRef")))
                continue
            profile_entry = profile["entries"][profile_entry_index]
            bonuses = [bonus + attack_adjustment for bonus in profile_entry["attackBonuses"]]
            attack_count = profile_entry["count"]
            natural = None
            if selected.get("naturalAttackId"):
                _, natural = self._resolve("naturalAttack", selected["naturalAttackId"], f"/selections/attacks/{index}/naturalAttackId")
            die = selected.get("damageDie")
            natural_die = natural["bySize"].get(size_name) if natural else None
            if die is None:
                die = natural_die or "d6"
            if natural and selected.get("damageDie") is None and natural_die in {"1", "—"}:
                code = "damage.fixed-natural-unsupported" if natural_die == "1" else "damage.natural-attack-unavailable"
                message = (
                    "source natural-attack damage is fixed at 1; Table 5-9 has no fixed-damage column"
                    if natural_die == "1" else
                    "source natural-attack profile has no damage die at this size"
                )
                issues.append(self._issue(code, f"/selections/attacks/{index}", message, "catalog-data", "error", natural.get("sourceRef")))
            die = _damage_die_name(die)
            average_damage = profile_entry["averageDamage"]
            expression = self._damage_expression(average_damage, die)
            if expression is None and not (natural and selected.get("damageDie") is None and natural_die in {"1", "—"}):
                source_refs = []
                if natural and natural.get("sourceRef"):
                    source_refs.append(natural["sourceRef"])
                damage_rows = self.catalog.data.get("damage", {})
                damage_row = next((row for row in damage_rows.values() if row["min"] <= average_damage <= row["max"]), None)
                if damage_row is None and damage_rows:
                    # Table-level fallback when the average is below/above the source table.
                    damage_row = next(iter(damage_rows.values()))
                if damage_row and damage_row.get("sourceRef"):
                    source_refs.append(damage_row["sourceRef"])
                if not source_refs:
                    source_refs.append(attack_table.get("sourceRef"))
                issues.append(self._issue("damage.unresolved", f"/selections/attacks/{index}", f"no source damage expression for average damage {average_damage} and damage die {die}", "catalog-data", "error", source_refs))
                expression = None
            attack = {
                "name": selected["name"],
                "count": attack_count,
                "attackBonus": bonuses,
                "attackBonusText": "/".join(_signed(value) for value in bonuses),
                "averageDamage": average_damage,
                "damageDie": die,
                "damageExpression": expression,
            }
            if natural:
                attack["naturalAttackId"] = natural["id"]
                attack["damageType"] = natural["damageType"]
                attack["classification"] = natural["classification"]
            attacks.append(attack)
        return attacks

    def _damage_expression(self, average_damage, die):
        row = next((row for row in self.catalog.data["damage"].values() if row["min"] <= average_damage <= row["max"]), None)
        return row["expressions"].get(die) if row else None

    def _evaluate_spells(self, selections, array_id, cr, main, issues):
        if not selections.get("spells"):
            return []
        if array_id != "array.spellcaster":
            return []
        output = []
        for index, selected in enumerate(selections["spells"]):
            spell_id, spell = self._resolve("spell", selected["spellId"], f"/selections/spells/{index}/spellId")
            metamagic = selected.get("metamagic", [])
            if not isinstance(metamagic, list):
                issues.append(self._issue("spell.metamagic-invalid", f"/selections/spells/{index}/metamagic", "metamagic must be an array", "catalog-data", "error"))
                continue
            level_source = selected.get("spellLevelSource", selections.get("spellLevelSource"))
            if level_source is None:
                if "cleric" in spell["levelsByClass"]:
                    level_source = "cleric"
                elif "sorcerer" in spell["levelsByClass"]:
                    level_source = "sorcerer"
                elif "wizard" in spell["levelsByClass"]:
                    level_source = "wizard"
                else:
                    level_source = max(spell["levelsByClass"], key=spell["levelsByClass"].get)
            if level_source not in spell["levelsByClass"]:
                issues.append(self._issue("spell.level-source-invalid", f"/selections/spells/{index}", "requested spell level source is not present", "source-rule", "error", spell.get("sourceRef")))
                continue
            base_level = spell["levelsByClass"][level_source]
            metamagic_increase = sum(self.catalog.data["metamagic"][value] for value in metamagic)
            effective_level = base_level + metamagic_increase
            output.append({"spellId": spell_id, "name": spell["name"], "spellLevelSource": level_source, "baseLevel": base_level, "metamagic": list(metamagic), "effectiveLevel": effective_level, "spellDC": main["spellDC"] + effective_level})
        return output

    def _trace(self, draft, main, attack_table, creature_type, size, canonical):
        trace = []
        def add(path, rule, value, refs):
            trace.append({"path": path, "rule": rule, "value": copy.deepcopy(value), "sourceRefs": copy.deepcopy(refs if isinstance(refs, list) else [refs])})
        main_ref = main["sourceRef"]
        add("/canonical/defenses", "array.mainStatistics", canonical["defenses"], [main_ref])
        add("/canonical/abilityDC", "array.abilityDC", canonical["abilityDC"], [main_ref])
        add("/canonical/spellDC", "array.spellDC", canonical["spellDC"], [main_ref])
        add("/canonical/abilityModifiers", "draft.abilityModifierAssignments", canonical["abilityModifiers"], [main_ref])
        add("/canonical/attacks", "array.attackStatistics + graft adjustments + damage table", canonical["attacks"], [attack_table["sourceRef"]])
        add("/canonical/senses", "creatureTypeGraft.automaticTraits", canonical["senses"], [creature_type["sourceRef"]])
        add("/canonical/skills", "array.skillBonuses + skill selections", canonical["skills"], [main_ref])
        add("/canonical/initiative", "otherCalculations.initiative", canonical["initiative"], [main_ref])
        add("/canonical/hitDice", "otherCalculations.hitDice", canonical["hitDice"], [main_ref])
        add("/canonical/speed", "draft.speed", canonical["speed"], [])
        if canonical.get("concentration") is not None:
            add("/canonical/concentration", "otherCalculations.concentration", canonical["concentration"], [main_ref])
        option_refs = []
        for option in canonical.get("options", []):
            definition = self.catalog.data["options"].get(option["optionId"])
            if definition and definition.get("sourceRef"):
                option_refs.append(definition["sourceRef"])
        add("/canonical/options", "array.optionSlots + option selections", canonical["options"], option_refs)
        if canonical.get("spells"):
            spell_refs = []
            for spell in canonical["spells"]:
                spell_refs.extend(self.catalog.data["spells"][spell["spellId"]].get("sourceRef", []))
            add("/canonical/spells", "step6.spellLevel + metamagic + spellDC", canonical["spells"], spell_refs)
        add("/canonical/cmb", "otherCalculations.cmb", canonical["cmb"], [main_ref])
        if canonical.get("maneuverBonuses"):
            add("/canonical/maneuverBonuses", "option.improvedCombatManeuver", canonical["maneuverBonuses"], [self.catalog.data["options"]["option.improved-combat-maneuver"]["sourceRef"]])
        return trace

    def _evaluation(self, status, issues):
        return {
            "status": status,
            "mode": "strict",
            "canonical": None,
            "effective": None,
            "issues": sorted(issues, key=lambda issue: (issue["path"], issue["code"])),
            "derivationTrace": [],
        }

    @staticmethod
    def _issue(code, path, message, kind, severity, source_refs=None):
        issue = {"code": code, "path": path, "message": message, "kind": kind, "severity": severity}
        if source_refs:
            issue["sourceRefs"] = copy.deepcopy(source_refs if isinstance(source_refs, list) else [source_refs])
        return issue

    @staticmethod
    def _error(request_id, error: BoundaryError) -> dict[str, Any]:
        value = {"code": error.code, "kind": error.kind, "message": error.message, "path": error.path}
        if error.details is not None:
            value["details"] = error.details
        return {"ok": False, "requestId": request_id, "error": value}


def _signed(value: int | float) -> str:
    return f"{value:+g}"


def _damage_die_name(value: str) -> str:
    # Bestiary natural-attack entries use 1d6 notation; Table 5-9 labels
    # the same column d6. Keep one canonical column key in the evaluation.
    if value.startswith("1d"):
        return value[1:]
    return value


def _cr_key(cr: int | float) -> str:
    if cr == 0.5:
        return "1/2"
    if isinstance(cr, float) and cr.is_integer():
        return str(int(cr))
    return str(cr)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _draft_fingerprint(draft: dict[str, Any]) -> str:
    # Identity is semantic draft content, not the process-local opaque ID or
    # revision counter. This makes the same draft reproducible across engines.
    selections = copy.deepcopy(draft.get("selections", {}))
    for field in ("subtypeGraftIds",):
        if isinstance(selections.get(field), list):
            selections[field] = sorted(selections[field])
    if isinstance(selections.get("skills"), dict):
        for field in ("master", "good"):
            if isinstance(selections["skills"].get(field), list):
                selections["skills"][field] = sorted(selections["skills"][field])
    # Options and spells remain ordered: slot assignment, presentation, and
    # traces observe their order. Sorting them would alias distinct drafts.
    value = {
        "schemaVersion": draft.get("schemaVersion"),
        "catalogVersion": draft.get("catalogVersion"),
        "concept": draft.get("concept", {}),
        "selections": selections,
    }
    return _fingerprint(value)
