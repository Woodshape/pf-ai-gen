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
        "cr", "arrayId", "creatureTypeGraftId", "classGraftId", "classGraftChoices", "graftOptionChoices", "subtypeGraftIds", "subtypeGraftChoices",
        "templateGraftId", "templateGraftChoices", "sizeId", "saveSwap", "abilityModifiers", "options",
        "skills", "attacks", "speed", "spells", "spellListId", "spellListBenefitChoices",
        "spellLevelSource", "spellcastingAbility",
    }
    _COMPUTED_SELECTION_FIELDS = {
        "ac", "touchAC", "flatFootedAC", "fortitude", "reflex", "will", "cmd", "cmb",
        "hp", "abilityDC", "spellDC", "canonical", "effective", "derivationTrace",
        "damageExpression", "averageDamage", "attackBonus", "initiative", "hitDice",
        "concentration", "evaluation", "defenses",
    }
    _ABILITY_NAMES = {"strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"}
    _ATTACK_PROFILES = {"weapon.high", "weapon.low", "natural.two", "natural.three"}
    _DAMAGE_DICE = {"d4", "d6", "d8", "d10", "d12", "2d6", "2d8", "3d6"}

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
        if "classGraftChoices" in selections and not isinstance(selections["classGraftChoices"], dict):
            raise BoundaryError("selection.type-invalid", "classGraftChoices must be an object", "/selections/classGraftChoices")
        if "graftOptionChoices" in selections and not isinstance(selections["graftOptionChoices"], dict):
            raise BoundaryError("selection.type-invalid", "graftOptionChoices must be an object", "/selections/graftOptionChoices")
        if "subtypeGraftChoices" in selections and not isinstance(selections["subtypeGraftChoices"], dict):
            raise BoundaryError("selection.type-invalid", "subtypeGraftChoices must be an object", "/selections/subtypeGraftChoices")
        if "templateGraftChoices" in selections and not isinstance(selections["templateGraftChoices"], dict):
            raise BoundaryError("selection.type-invalid", "templateGraftChoices must be an object", "/selections/templateGraftChoices")
        if "spellListBenefitChoices" in selections and not isinstance(selections["spellListBenefitChoices"], dict):
            raise BoundaryError("selection.type-invalid", "spellListBenefitChoices must be an object", "/selections/spellListBenefitChoices")
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
                if expected is None or expected.get("internal"):
                    raise BoundaryError("selection.parameter-unknown", "option parameter is not user-selectable", f"/selections/options/{index}/parameters/{parameter_name}")
                parameter_type = expected.get("type")
                if parameter_type in {"string", "enum", "selected-attack"} and not isinstance(parameter_value, str):
                    raise BoundaryError("selection.parameter-type-invalid", "option parameter must be a string", f"/selections/options/{index}/parameters/{parameter_name}")
                if parameter_type == "integer" and (not isinstance(parameter_value, int) or isinstance(parameter_value, bool)):
                    raise BoundaryError("selection.parameter-type-invalid", "option parameter must be an integer", f"/selections/options/{index}/parameters/{parameter_name}")
                if parameter_type in {"enum-array", "selected-attacks", "string-array"} and (
                    not isinstance(parameter_value, list) or any(not isinstance(value, str) for value in parameter_value)
                ):
                    raise BoundaryError("selection.parameter-type-invalid", "option parameter must be an array of strings", f"/selections/options/{index}/parameters/{parameter_name}")
                if expected.get("catalogKind") and isinstance(parameter_value, str):
                    self._resolve(expected["catalogKind"], parameter_value, f"/selections/options/{index}/parameters/{parameter_name}")
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
        choices = selections.get("spellListBenefitChoices", {})
        if choices:
            if not selections.get("spellListId"):
                raise BoundaryError("selection.parameter-without-parent", "spellListBenefitChoices requires spellListId", "/selections/spellListBenefitChoices")
            _, spell_list = self._resolve("spellList", selections["spellListId"], "/selections/spellListId")
            parameters = spell_list["benefit"].get("parameters", {})
            unknown = set(choices) - set(parameters)
            if unknown:
                name = sorted(unknown)[0]
                raise BoundaryError("selection.parameter-unknown", "spell-list benefit parameter is not catalogued", f"/selections/spellListBenefitChoices/{name}")
            for name, value in choices.items():
                parameter_type = parameters[name]["type"]
                valid_shape = isinstance(value, str) if parameter_type in {"enum", "selected-speed"} else isinstance(value, list) and all(isinstance(item, str) for item in value)
                if not valid_shape:
                    raise BoundaryError("selection.parameter-type-invalid", "spell-list benefit parameter has the wrong type", f"/selections/spellListBenefitChoices/{name}")

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
        class_id = None
        class_graft = None
        cr_entry = None
        class_option_choice_values = {}
        class_ability_choices = []
        class_choice_effect = None
        if selections.get("classGraftId") is not None:
            class_id, class_graft = self._resolve("classGraft", selections["classGraftId"], "/selections/classGraftId")
            cr_entry = max(
                (entry for entry in class_graft.get("crEntries", []) if cr >= entry["minCR"]),
                key=lambda entry: entry["minCR"], default=None,
            )
            if array_id != class_graft["requiredArrayId"]:
                issues.append(self._issue("class-graft.required-array", "/selections/arrayId", f"class graft requires {class_graft['requiredArrayId']}", "source-rule", "error", class_graft.get("sourceRef")))
            if class_graft.get("maxImplementedCR") is not None and cr > class_graft["maxImplementedCR"]:
                issues.append(self._issue("class-graft.cr-unsupported", "/selections/cr", "class graft CR entries above this CR are not catalogued yet", "catalog-data", "error", class_graft.get("sourceRef")))
            if class_graft.get("unresolvedRules"):
                issues.append(self._issue("class-graft.catalog-gap", "/selections/classGraftId", "; ".join(class_graft["unresolvedRules"]), "catalog-data", "error", class_graft.get("sourceRef")))
            required_spell_list = class_graft.get("requiredSpellListId")
            selected_spell_list = selections.get("spellListId")
            resolved_spell_list_id = self._resolve("spellList", selected_spell_list, "/selections/spellListId")[0] if selected_spell_list else None
            if required_spell_list and resolved_spell_list_id is None:
                issues.append(self._issue("class-graft.spell-list-required", "/selections/spellListId", f"class graft requires {required_spell_list}", "source-rule", "error", class_graft.get("sourceRef")))
            elif required_spell_list and resolved_spell_list_id != required_spell_list:
                issues.append(self._issue("class-graft.spell-list-invalid", "/selections/spellListId", f"class graft requires {required_spell_list}", "source-rule", "error", class_graft.get("sourceRef")))
            companion_spec = class_graft.get("companionSpec")
            if companion_spec:
                companion_name = selections.get("classGraftChoices", {}).get(companion_spec["choiceName"])
                if not isinstance(companion_name, str) or not companion_name.strip():
                    issues.append(self._issue("class-graft.choice-required", f"/selections/classGraftChoices/{companion_spec['choiceName']}", "class graft requires a named eidolon companion", "source-rule", "error", class_graft.get("sourceRef")))
            choice_spec = class_graft.get("choiceSpec")
            choice_value = selections.get("classGraftChoices", {}).get(choice_spec["name"]) if choice_spec else None
            if choice_spec and choice_value not in choice_spec["values"]:
                issues.append(self._issue("class-graft.choice-required", f"/selections/classGraftChoices/{choice_spec['name']}", "class graft requires a source-defined choice", "source-rule", "error", class_graft.get("sourceRef")))
            elif choice_value in class_graft.get("choiceEffects", {}):
                class_choice_effect = class_graft["choiceEffects"][choice_value]
                language_values = class_choice_effect.get("languageValues")
                if language_values:
                    languages = selections.get("classGraftChoices", {}).get("languages")
                    expected_languages = 1 + int(cr >= 4)
                    if not isinstance(languages, list) or len(languages) != expected_languages or len(set(languages)) != len(languages) or any(language not in language_values for language in languages):
                        issues.append(self._issue("class-graft.choice-required", "/selections/classGraftChoices/languages", f"oracle curse requires {expected_languages} source-defined language choice(s)", "source-rule", "error", class_graft.get("sourceRef")))
            for ability_choice in class_graft.get("abilityChoiceSpecs", []):
                value = selections.get("classGraftChoices", {}).get(ability_choice["name"])
                if value not in ability_choice["values"]:
                    issues.append(self._issue("class-graft.choice-required", f"/selections/classGraftChoices/{ability_choice['name']}", "class graft requires a source-defined ability choice", "source-rule", "error", class_graft.get("sourceRef")))
                else:
                    class_ability_choices.append({"ability": ability_choice["name"], "value": value, "sourceText": class_graft["ruleText"]})
            for option_choice in class_graft.get("optionChoiceSpecs", []):
                value = selections.get("classGraftChoices", {}).get(option_choice["name"])
                if option_choice.get("type") == "enum-array":
                    expected_count = 1 + sum(cr >= threshold for threshold in option_choice.get("countThresholds", []))
                    valid = (
                        isinstance(value, list) and len(value) == expected_count
                        and len(set(value)) == len(value)
                        and all(item in option_choice["values"] for item in value)
                    )
                else:
                    valid = value in option_choice["values"]
                if not valid:
                    issues.append(self._issue("class-graft.choice-required", f"/selections/classGraftChoices/{option_choice['name']}", "class graft requires a source-defined option choice", "source-rule", "error", class_graft.get("sourceRef")))
                else:
                    class_option_choice_values[option_choice["optionId"]] = {option_choice["parameter"]: copy.deepcopy(value)}
        subtype_grafts = [self._resolve("subtype", value, f"/selections/subtypeGraftIds/{index}") for index, value in enumerate(selections.get("subtypeGraftIds", []))]
        subtype_ids = [entry_id for entry_id, _ in subtype_grafts]
        if len(subtype_ids) != len(set(subtype_ids)):
            issues.append(self._issue("subtype.duplicate", "/selections/subtypeGraftIds", "a subtype graft can be selected only once", "product-constraint", "error"))
        subtype_choice_skill_grants = []
        subtype_choice_spell_grants = []
        for subtype_id, subtype in subtype_grafts:
            if subtype.get("requiredSizeId") not in {None, size_id}:
                issues.append(self._issue("subtype.size-required", "/selections/sizeId", f"{subtype_id} requires {subtype['requiredSizeId']}", "source-rule", "error", subtype.get("sourceRef")))
            choice = subtype.get("skillChoiceGrant")
            if choice:
                value = selections.get("subtypeGraftChoices", {}).get(subtype_id, {}).get(choice["name"])
                if value not in choice["skillIds"]:
                    issues.append(self._issue("subtype-graft.choice-required", f"/selections/subtypeGraftChoices/{subtype_id}/{choice['name']}", "subtype graft requires a source-defined skill choice", "source-rule", "error", subtype.get("sourceRef")))
                else:
                    subtype_choice_skill_grants.append({"skillId": value, "rank": choice["rank"], "additional": True})
            spell_choice = subtype.get("spellChoiceGrant")
            if spell_choice:
                spell_id = selections.get("subtypeGraftChoices", {}).get(subtype_id, {}).get(spell_choice["name"])
                _, spell_list = self._resolve("spellList", spell_choice["spellListId"], f"/selections/subtypeGraftChoices/{subtype_id}/{spell_choice['name']}")
                band = next(band for band in self.catalog.data["spellBands"] if band["minCR"] <= cr and (band["maxCR"] is None or cr <= band["maxCR"]))["id"]
                allowed = {entry["spellId"] for entry in spell_list["bands"][band][spell_choice["role"]]}
                if spell_id not in allowed:
                    issues.append(self._issue("subtype-graft.choice-required", f"/selections/subtypeGraftChoices/{subtype_id}/{spell_choice['name']}", "subtype graft requires a CR-appropriate spell choice", "source-rule", "error", subtype.get("sourceRef")))
                else:
                    subtype_choice_spell_grants.append({"spellId": spell_id, "frequency": spell_choice["frequency"], "sourceBand": band, "role": "subtype-graft", "sourceText": subtype["ruleText"]})
        template_id = None
        template = None
        template_choice_grants = []
        template_linked_option_parameters = {}
        if selections.get("templateGraftId") is not None:
            template_id, template = self._resolve("template", selections["templateGraftId"], "/selections/templateGraftId")
            if template.get("minCR") is not None and cr < template["minCR"]:
                issues.append(self._issue("template.cr-too-low", "/selections/templateGraftId", "template graft is below its minimum CR", "source-rule", "error", template.get("sourceRef")))
            if template.get("maxCR") is not None and cr > template["maxCR"]:
                issues.append(self._issue("template.cr-too-high", "/selections/templateGraftId", "template graft is above its maximum CR", "source-rule", "error", template.get("sourceRef")))
            if template.get("requiredCreatureTypeId") not in {None, type_id}:
                issues.append(self._issue("template.creature-type-required", "/selections/creatureTypeGraftId", "template graft requires a different creature type", "source-rule", "error", template.get("sourceRef")))
            required_subtype = template.get("requiredSubtypeId")
            if required_subtype and required_subtype not in subtype_ids:
                issues.append(self._issue("template.subtype-required", "/selections/subtypeGraftIds", "template graft requires a subtype", "source-rule", "error", template.get("sourceRef")))
            linked_choice = template.get("linkedOptionChoiceSpec")
            if linked_choice:
                choice_values = selections.get("templateGraftChoices", {})
                energy = choice_values.get(linked_choice["energyName"])
                shape = linked_choice.get("fixedShape") or choice_values.get(linked_choice.get("shapeName"))
                if energy not in linked_choice["energyValues"] or shape not in linked_choice.get("shapeValues", [shape]):
                    issues.append(self._issue("template-graft.choice-required", "/selections/templateGraftChoices", "template graft requires source-defined breath shape and energy choices", "source-rule", "error", template.get("sourceRef")))
                else:
                    template_linked_option_parameters = {
                        "option.breath-weapon": {"shape": shape, "damageType": energy},
                    }
                    if template_id == "graft.template.half-dragon":
                        template_linked_option_parameters["option.immunity"] = {"immunities": ["sleep", "paralysis", energy]}
                    elif template_id == "graft.template.graveknight":
                        template_linked_option_parameters["option.channel-destruction"] = {"energyType": energy}
            choice_grant = template.get("optionChoiceGrant")
            if choice_grant and cr >= choice_grant["minCR"]:
                expected_count = 1 + int((cr - choice_grant["minCR"]) / choice_grant["perCR"])
                values = selections.get("templateGraftChoices", {}).get("optionIds")
                if not isinstance(values, list) or len(values) != expected_count:
                    issues.append(self._issue("template-graft.choice-required", "/selections/templateGraftChoices/optionIds", f"template graft requires {expected_count} option choice(s)", "source-rule", "error", template.get("sourceRef")))
                elif len(set(values)) != len(values) or any(value not in choice_grant["optionIds"] for value in values):
                    issues.append(self._issue("template-graft.choice-invalid", "/selections/templateGraftChoices/optionIds", "template option choice is not allowed", "source-rule", "error", template.get("sourceRef")))
                else:
                    parameters_by_option = choice_grant.get("parametersByOption", {})
                    template_choice_grants = [
                        {"optionId": value, "parameters": copy.deepcopy(parameters_by_option.get(value, {})), "sourceText": template["ruleText"]}
                        for value in values
                    ]
        if size.get("minCR") is not None and cr < size["minCR"]:
            issues.append(self._issue("size.cr-too-low", "/selections/sizeId", "size graft is below its minimum CR", "source-rule", "error", size.get("sourceRef")))
        if size.get("maxCR") is not None and cr > size["maxCR"]:
            issues.append(self._issue("size.cr-too-high", "/selections/sizeId", "size graft is above its maximum CR", "source-rule", "error", size.get("sourceRef")))
        target_cr = draft.get("concept", {}).get("targetCR")
        if target_cr is not None and target_cr != cr:
            issues.append(self._issue("concept.target-cr-mismatch", "/concept/targetCR", "concept target CR differs from the selected CR", "product-constraint", "warning"))

        abilities = copy.deepcopy(selections["abilityModifiers"])
        active_grafts = [graft for _, graft in subtype_grafts] + ([template] if template else [])
        for graft in active_grafts:
            abilities.update(graft.get("abilityModifierOverrides", {}))
            for ability, value in graft.get("abilityModifierAdjustments", {}).items():
                if abilities.get(ability) is not None:
                    abilities[ability] = abilities.get(ability, 0) + value
        for ability, value in (class_choice_effect or {}).get("abilityModifierAdjustments", {}).items():
            if abilities.get(ability) is not None:
                abilities[ability] += value
        if len(abilities) < 3:
            issues.append(self._issue("ability-modifiers.incomplete", "/selections/abilityModifiers", "three important ability modifiers are required", "source-rule", "error", main.get("sourceRef")))
        if len(abilities) > 6:
            issues.append(self._issue("ability-modifiers.too-many", "/selections/abilityModifiers", "there are only six ability modifiers", "product-constraint", "error", main.get("sourceRef")))

        adjustments = copy.deepcopy(class_graft.get("statisticAdjustments", {}) if class_graft else creature_type.get("statisticAdjustments", {}))
        for graft in active_grafts:
            for field, value in graft.get("statisticAdjustments", {}).items():
                adjustments[field] = adjustments.get(field, 0) + value
            for field, rule in graft.get("scaledStatisticAdjustments", {}).items():
                if rule["formula"] == "quarterCR":
                    adjustments[field] = adjustments.get(field, 0) + int(cr / 4)
        save_main = main
        if class_graft and class_graft.get("saveSourceArrayId"):
            save_array_id = class_graft["saveSourceArrayId"].removeprefix("array.")
            save_main = self.catalog.data["arrays"][save_array_id]["mainStatistics"][cr_key]
        fortitude = save_main["fortitude"] + adjustments.get("fortitude", 0)
        reflex = save_main["reflex"] + adjustments.get("reflex", 0)
        will = save_main["will"] + adjustments.get("will", 0)
        if class_graft and class_graft.get("saveChoiceBonus"):
            save_choice = selections.get("classGraftChoices", {}).get("save")
            rule = class_graft["saveChoiceBonus"]
            if save_choice not in rule["choices"]:
                issues.append(self._issue("class-graft.choice-required", "/selections/classGraftChoices/save", "class graft requires a save choice", "source-rule", "error", class_graft.get("sourceRef")))
            else:
                if save_choice == "fortitude":
                    fortitude += rule["value"]
                else:
                    reflex += rule["value"]
        attack_adjustment = adjustments.get("attackBonus", 0)
        saves = {"fortitude": fortitude, "reflex": reflex, "will": will}
        swap = selections.get("saveSwap")
        if swap:
            if swap.get("from") not in saves or swap.get("to") not in saves or swap["from"] == swap["to"]:
                issues.append(self._issue("save-swap.invalid", "/selections/saveSwap", "save swap must name two different saves", "source-rule", "error", main.get("sourceRef")))
            else:
                saves[swap["from"]], saves[swap["to"]] = saves[swap["to"]], saves[swap["from"]]

        size_adjustments = size.get("adjustments", {})
        ac = main["ac"] + adjustments.get("ac", 0)
        touch_ac = min(ac, max(1, main["touchAC"] + adjustments.get("touchAC", 0) + size_adjustments.get("touchAC", 0)))
        flat_footed_ac = max(1, main["flatFootedAC"] + adjustments.get("flatFootedAC", 0) + size_adjustments.get("flatFootedAC", 0))
        if any(graft.get("touchACEqualsAC") for graft in active_grafts):
            touch_ac = ac
        cmb = main["attackStatisticsHigh"] if "attackStatisticsHigh" in main else attack_table["weapon"]["high"]["attackBonuses"][0]
        cmb += adjustments.get("cmb", 0) + size_adjustments.get("cmb", 0)
        cmd = main["cmd"] + adjustments.get("cmd", 0) + size_adjustments.get("cmd", 0)

        options = selections["options"]
        option_slots = copy.deepcopy(class_graft.get("optionSlots", []) if class_graft else main["options"])
        if class_graft and cr_entry:
            option_slots.extend(copy.deepcopy(cr_entry.get("optionSlots", [])))
        for _, subtype in subtype_grafts:
            option_slots.extend(copy.deepcopy(subtype.get("optionSlots", [])))
        slot_counts = {}
        for slot in option_slots:
            slot_counts[slot["category"]] = slot_counts.get(slot["category"], 0) + slot["count"]
        remaining_slots = dict(slot_counts)
        granted_options = []
        if class_graft:
            class_options = copy.deepcopy(class_graft.get("optionGrants", []))
            if cr_entry:
                removed = set(cr_entry.get("removeOptionGrantIds", []))
                class_options = [grant for grant in class_options if grant["optionId"] not in removed]
                class_options.extend(copy.deepcopy(cr_entry.get("optionGrants", [])))
            for grant in class_options:
                grant["parameters"].update(copy.deepcopy(class_option_choice_values.get(grant["optionId"], {})))
                grant["graftId"] = class_id
            granted_options.extend(class_options)
        for subtype_id, subtype in subtype_grafts:
            subtype_options = copy.deepcopy(subtype.get("optionGrants", []))
            for grant in subtype_options:
                grant["graftId"] = subtype_id
            granted_options.extend(subtype_options)
        if template:
            template_options = copy.deepcopy(template.get("optionGrants", [])) + copy.deepcopy(template_choice_grants)
            for grant in template_options:
                grant["parameters"].update(copy.deepcopy(template_linked_option_parameters.get(grant["optionId"], {})))
                grant["graftId"] = template_id
            granted_options.extend(template_options)
            # Template grants replace normal slots when possible, but all are
            # retained even when the template exceeds the normal allotment.
            for grant in template_options:
                category = self.catalog.data["options"][grant["optionId"]]["category"]
                choices = ("universal", "combat", "magic", "social", "any") if category == "universal" else (category, "combat/social", "any") if category in {"combat", "social"} else (category, "any")
                assigned_slot = next((slot for slot in choices if remaining_slots.get(slot, 0) > 0), None)
                if assigned_slot:
                    remaining_slots[assigned_slot] -= 1
            for slot in template.get("optionSlots", []):
                slot_counts[slot["category"]] = slot_counts.get(slot["category"], 0) + slot["count"]
                remaining_slots[slot["category"]] = remaining_slots.get(slot["category"], 0) + slot["count"]

        graft_option_choices = selections.get("graftOptionChoices", {})
        active_graft_ids = {value for value in (class_id, template_id, *subtype_ids) if value}
        granted_option_keys = {(grant["graftId"], grant["optionId"]) for grant in granted_options}
        for graft_id, option_choices in graft_option_choices.items():
            if graft_id not in active_graft_ids or not isinstance(option_choices, dict):
                issues.append(self._issue("graft-option.choice-invalid", f"/selections/graftOptionChoices/{graft_id}", "graft option choices must name an active graft", "source-rule", "error"))
                continue
            for option_id in option_choices:
                if (graft_id, option_id) not in granted_option_keys:
                    issues.append(self._issue("graft-option.choice-invalid", f"/selections/graftOptionChoices/{graft_id}/{option_id}", "graft option choice must name an automatic option granted by that graft", "source-rule", "error"))
        selected_attack_names = {attack.get("name") for attack in selections["attacks"]}
        for grant in granted_options:
            graft_id = grant["graftId"]
            option_id = grant["optionId"]
            option = self.catalog.data["options"][option_id]
            choice_parameters = graft_option_choices.get(graft_id, {}).get(option_id, {})
            if not isinstance(choice_parameters, dict):
                issues.append(self._issue("graft-option.choice-invalid", f"/selections/graftOptionChoices/{graft_id}/{option_id}", "graft option parameters must be an object", "source-rule", "error", option.get("sourceRef")))
                choice_parameters = {}
            definitions = option.get("parameters", {})
            if set(choice_parameters) - set(definitions):
                issues.append(self._issue("graft-option.choice-invalid", f"/selections/graftOptionChoices/{graft_id}/{option_id}", "graft option choice contains an unknown parameter", "source-rule", "error", option.get("sourceRef")))
            if any(definitions.get(name, {}).get("internal") for name in choice_parameters):
                issues.append(self._issue("graft-option.choice-invalid", f"/selections/graftOptionChoices/{graft_id}/{option_id}", "internal graft option parameters are not user-selectable", "source-rule", "error", option.get("sourceRef")))
            for name, value in choice_parameters.items():
                if name in grant["parameters"] and grant["parameters"][name] != value:
                    issues.append(self._issue("graft-option.choice-invalid", f"/selections/graftOptionChoices/{graft_id}/{option_id}/{name}", "source-fixed graft option parameters cannot be overridden", "source-rule", "error", option.get("sourceRef")))
                elif name in definitions and not definitions[name].get("internal"):
                    grant["parameters"][name] = copy.deepcopy(value)
            if option_id == "option.secondary-magic" and "spellListId" not in grant["parameters"] and selections.get("spellListId"):
                grant["parameters"]["spellListId"] = self._resolve("spellList", selections["spellListId"], "/selections/spellListId")[0]
            for name, definition in definitions.items():
                if definition.get("internal"):
                    continue
                path = f"/selections/graftOptionChoices/{graft_id}/{option_id}/{name}"
                if name not in grant["parameters"] and not definition.get("optional"):
                    issues.append(self._issue("graft-option.choice-required", path, "automatic graft option requires a source-defined choice", "source-rule", "error", option.get("sourceRef")))
                    continue
                if name not in grant["parameters"]:
                    continue
                value = grant["parameters"][name]
                valid = (
                    definition["type"] == "enum" and value in definition["values"]
                    or definition["type"] == "string" and isinstance(value, str)
                    or definition["type"] == "selected-attack" and value in selected_attack_names
                    or definition["type"] == "selected-attacks" and isinstance(value, list) and value and all(item in selected_attack_names for item in value)
                    or definition["type"] == "enum-array" and isinstance(value, list) and all(item in definition["values"] for item in value) and len(value) >= definition.get("minCount", 0) and (name not in choice_parameters or definition.get("sourceDefaultCount") is None or len(value) == definition["sourceDefaultCount"])
                    or definition["type"] == "string-array" and isinstance(value, list) and all(isinstance(item, str) for item in value) and len(value) >= definition.get("minCount", 0) and (name not in choice_parameters or definition.get("sourceDefaultCount") is None or len(value) == definition["sourceDefaultCount"])
                )
                if not valid:
                    issues.append(self._issue("graft-option.choice-invalid", path, "automatic graft option choice is not allowed", "source-rule", "error", option.get("sourceRef")))
                elif definition.get("catalogKind") and isinstance(value, str):
                    try:
                        self._resolve(definition["catalogKind"], value, path)
                    except BoundaryError:
                        issues.append(self._issue("graft-option.choice-invalid", path, "automatic graft option references an unknown catalog entry", "catalog-data", "error", option.get("sourceRef")))
        selected_slot_budget = sum(remaining_slots.values())
        selected_options = granted_options
        maneuver_bonuses = {}
        for index, selected in enumerate(options):
            option_id, option = self._resolve("option", selected["optionId"], f"/selections/options/{index}/optionId")
            category = option.get("category")
            parameters = selected.get("parameters", {})
            if category not in {"combat", "magic", "social", "universal"}:
                issues.append(self._issue("option.category-invalid", f"/selections/options/{index}", "option category is not supported", "catalog-data", "error", option.get("sourceRef")))
                continue
            choices = ("universal", "combat", "magic", "social", "any") if category == "universal" else (category, "combat/social", "any") if category in {"combat", "social"} else (category, "any")
            assigned_slot = next((slot for slot in choices if remaining_slots.get(slot, 0) > 0), None)
            if assigned_slot is None:
                issues.append(self._issue("option-slot.invalid", f"/selections/options/{index}", "option category exceeds its budget", "source-rule", "error", main.get("sourceRef")))
            else:
                remaining_slots[assigned_slot] -= 1
            parameter_definitions = option.get("parameters", {})
            selected_attack_names = {attack.get("name") for attack in selections["attacks"]}
            for name, definition in parameter_definitions.items():
                path = f"/selections/options/{index}/parameters/{name}"
                if name not in parameters and not definition.get("optional"):
                    issues.append(self._issue("option.parameter-required", path, "option parameter is required", "source-rule", "error", option.get("sourceRef")))
                    continue
                value = parameters.get(name)
                if definition["type"] == "enum" and value not in definition["values"]:
                    issues.append(self._issue("option.parameter-invalid", path, "option parameter is not allowed", "source-rule", "error", option.get("sourceRef")))
                elif definition["type"] == "enum-array" and (
                    any(item not in definition["values"] for item in (value or []))
                    or definition.get("count") is not None and len(value or []) != definition["count"]
                    or len(value or []) < definition.get("minCount", 0)
                ):
                    issues.append(self._issue("option.parameter-invalid", path, "option parameter contains an unallowed number or value", "source-rule", "error", option.get("sourceRef")))
                elif definition["type"] == "string-array" and (
                    definition.get("count") is not None and len(value or []) != definition["count"]
                    or len(value or []) < definition.get("minCount", 0)
                ):
                    issues.append(self._issue("option.parameter-invalid", path, "option parameter has the wrong number of values", "source-rule", "error", option.get("sourceRef")))
                elif definition["type"] == "selected-attack" and value not in selected_attack_names:
                    issues.append(self._issue("option.parameter-invalid", path, "option attack must name a selected attack", "source-rule", "error", option.get("sourceRef")))
                elif definition["type"] == "selected-attacks" and (not value or any(item not in selected_attack_names for item in value)):
                    issues.append(self._issue("option.parameter-invalid", path, "option attacks must name selected attacks", "source-rule", "error", option.get("sourceRef")))

            if option_id == "option.favored-enemy" and "targets" in parameters:
                expected_targets = 1 + sum(cr >= threshold for threshold in (4, 9, 14, 19))
                if len(parameters["targets"]) != expected_targets:
                    issues.append(self._issue("option.parameter-invalid", f"/selections/options/{index}/parameters/targets", f"Favored Enemy requires {expected_targets} target(s) at CR {cr:g}", "source-rule", "error", option.get("sourceRef")))
            elif option_id == "option.immunity" and "immunities" in parameters:
                expected_immunities = 1 + int(cr / 5)
                if len(parameters["immunities"]) != expected_immunities:
                    issues.append(self._issue("option.parameter-invalid", f"/selections/options/{index}/parameters/immunities", f"Immunity requires {expected_immunities} choice(s) at CR {cr:g}", "source-rule", "error", option.get("sourceRef")))
            elif option_id == "option.bypass-dr" and len(parameters.get("bypass", [])) != 2:
                issues.append(self._issue("option.parameter-invalid", f"/selections/options/{index}/parameters/bypass", "Bypass DR requires two bypass materials or alignments", "source-rule", "error", option.get("sourceRef")))
            elif option_id == "option.regeneration" and len(parameters.get("bypass", [])) < 2:
                issues.append(self._issue("option.parameter-invalid", f"/selections/options/{index}/parameters/bypass", "Regeneration requires at least two bypass types", "source-rule", "error", option.get("sourceRef")))
            elif option_id == "option.aura-of-resistance" and len(parameters.get("descriptors", [])) != 2:
                issues.append(self._issue("option.parameter-invalid", f"/selections/options/{index}/parameters/descriptors", "Aura of Resistance requires two descriptors", "source-rule", "error", option.get("sourceRef")))
            elif option_id == "option.energy-resistance":
                energy_count = len(parameters.get("energyTypes", []))
                resistance_value = parameters.get("resistanceValue")
                if resistance_value is None:
                    issues.append(self._issue("option.parameter-required", f"/selections/options/{index}/parameters/resistanceValue", "Energy Resistance requires an explicit amount/count tradeoff", "source-rule", "error", option.get("sourceRef")))
                elif resistance_value not in {10, 15, 20, 25, 30} or energy_count - 2 + int((resistance_value - 10) / 5) > int(cr / 5):
                    issues.append(self._issue("option.parameter-invalid", f"/selections/options/{index}/parameters/resistanceValue", "Energy Resistance amount/count tradeoff exceeds this CR", "source-rule", "error", option.get("sourceRef")))

            selected_option = {"optionId": option_id, "parameters": copy.deepcopy(parameters)}
            if option_id == "option.improved-combat-maneuver":
                maneuver = parameters.get("maneuver")
                if maneuver in option["parameters"]["maneuver"]["values"]:
                    attack_type = parameters.get("attackType")
                    if attack_type is not None and attack_type not in selected_attack_names:
                        issues.append(self._issue("option.parameter-invalid", f"/selections/options/{index}/parameters/attackType", "option attackType must name a selected attack", "source-rule", "error", option.get("sourceRef")))
                    maneuver_bonuses[maneuver] = {"cmb": cmb + option["effects"]["cmb"], "cmd": cmd + option["effects"]["cmd"]}
            elif option_id == "option.gaze":
                selected_option["effect"] = {"type": "gaze", **copy.deepcopy(parameters), "dc": main["abilityDC"]}
            elif option_id == "option.poison":
                advantages = parameters.get("advantages", [])
                advantage_budget = 2 + int(cr / 3)
                if len(advantages) != advantage_budget:
                    issues.append(self._issue("option.poison-advantage-budget", f"/selections/options/{index}/parameters/advantages", f"poison grants {advantage_budget} advantages at CR {cr:g}", "source-rule", "error", option.get("sourceRef")))
                if any(advantages.count(value) > 1 for value in ("no-onset", "round-frequency", "two-consecutive-saves")) or advantages.count("increase-damage") > 4:
                    issues.append(self._issue("option.poison-advantage-invalid", f"/selections/options/{index}/parameters/advantages", "poison advantage cannot be applied that many times", "source-rule", "error", option.get("sourceRef")))
                damage_steps = ["1d2", "1d3", "1d4", "1d6", "1d8"]
                selected_option["effect"] = {
                    "type": "poison",
                    "attackTypes": copy.deepcopy(parameters.get("attackTypes", [])),
                    "save": "fortitude",
                    "dc": main["abilityDC"],
                    "poisonType": "injury",
                    "onset": "—" if "no-onset" in advantages else "1 minute",
                    "frequency": "1/round for 6 rounds" if "round-frequency" in advantages else "1/minute for 6 minutes",
                    "ability": parameters.get("ability"),
                    "damage": damage_steps[min(advantages.count("increase-damage"), 4)],
                    "cure": "2 consecutive saves" if "two-consecutive-saves" in advantages else "1 save",
                }
            elif option.get("effectMode") == "source-rule":
                selected_option["effect"] = {"type": "source-rule", "text": option["ruleText"]}
            selected_options.append(selected_option)
        selected_option_ids = {option["optionId"] for option in selected_options}
        for selected_option in selected_options:
            definition = self.catalog.data["options"][selected_option["optionId"]]
            for prerequisite in definition.get("prerequisites", []):
                satisfied = (
                    prerequisite["type"] == "array" and prerequisite["id"] == array_id
                    or prerequisite["type"] == "subtype" and prerequisite["id"] in subtype_ids
                    or prerequisite["type"] == "option" and prerequisite["id"] in selected_option_ids
                )
                if not satisfied:
                    issues.append(self._issue("option.prerequisite-missing", "/selections/options", f"{selected_option['optionId']} requires {prerequisite['id']}", "source-rule", "error", definition.get("sourceRef")))
        if len(options) != selected_slot_budget:
            refs = [class_graft["sourceRef"] if class_graft else main["sourceRef"]]
            if template:
                refs.append(template["sourceRef"])
            issues.append(self._issue("option-budget.mismatch", "/selections/options", f"active array and grafts leave {selected_slot_budget} selectable option slot(s), received {len(options)}", "source-rule", "error", refs))

        skills_selection = selections["skills"]
        master = list(skills_selection.get("master", []))
        good = list(skills_selection.get("good", []))
        skill_grants = copy.deepcopy(class_graft.get("skillGrants", [])) if class_graft else []
        for graft in active_grafts:
            skill_grants.extend(copy.deepcopy(graft.get("skillGrants", [])))
        skill_grants.extend(subtype_choice_skill_grants)
        if len(set(master)) != len(master) or len(set(good)) != len(good) or set(master) & set(good):
            issues.append(self._issue("skills.duplicate", "/selections/skills", "a skill cannot occupy more than one slot", "source-rule", "error", main.get("sourceRef")))
        extra_master = size.get("additionalMasterSkills", [])
        extra_good = size.get("additionalGoodSkills", [])
        effective_master = list(master)
        effective_good = list(good)
        for grant in skill_grants:
            skill = grant["skillId"].removeprefix("skill.")
            if grant["rank"] == "master" and skill not in effective_master:
                effective_master.append(skill)
                if skill in effective_good:
                    effective_good.remove(skill)
            elif grant["rank"] == "good" and skill not in effective_master and skill not in effective_good:
                effective_good.append(skill)
        for skill in extra_master:
            if skill not in effective_master:
                effective_master.append(skill)
        for skill in extra_good:
            if skill not in effective_master and skill not in effective_good:
                effective_good.append(skill)
        expected_master = main["masterCount"]
        expected_good = main["goodCount"]
        if class_graft:
            for slot in class_graft.get("skillSlots", []):
                if slot["rank"] == "master":
                    expected_master += slot["count"]
                else:
                    expected_good += slot["count"]
        for graft in active_grafts:
            for slot in graft.get("skillSlots", []):
                if slot["rank"] == "master":
                    expected_master += slot["count"]
                else:
                    expected_good += slot["count"]
        for grant in skill_grants:
            if not grant.get("additional"):
                if grant["rank"] == "master":
                    expected_master = max(0, expected_master - 1)
                else:
                    expected_good = max(0, expected_good - 1)
        if template and template.get("skillBudgetOverride"):
            expected_master = template["skillBudgetOverride"]["master"]
            expected_good = template["skillBudgetOverride"]["good"]
        skill_budget_ref = class_graft.get("sourceRef") if class_graft else main.get("sourceRef")
        if len(master) != expected_master:
            issues.append(self._issue("skills.master-budget", "/selections/skills/master", "master skill count does not match the active graft budget", "source-rule", "error", skill_budget_ref))
        if len(good) != expected_good:
            issues.append(self._issue("skills.good-budget", "/selections/skills/good", "good skill count does not match the active graft budget", "source-rule", "error", skill_budget_ref))
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
        if "perception" not in skill_values and not (template and template.get("suppressAutomaticPerception")):
            skill_values["perception"] = main["goodBonus"]

        attack_selections = selections["attacks"]
        class_attack_damage = None
        if class_graft and class_graft.get("unarmedDamage"):
            class_attack_damage = cr_entry.get("unarmedDamage", class_graft["unarmedDamage"]) if cr_entry else class_graft["unarmedDamage"]
            attack_selections = copy.deepcopy(attack_selections)
            unarmed_attack = next((attack for attack in attack_selections if attack["name"].lower().replace("-", " ") == "unarmed strike"), None)
            if unarmed_attack is not None:
                unarmed_attack["damageDie"] = class_attack_damage
        attacks = self._evaluate_attacks(attack_selections, attack_table, size_id, attack_adjustment, issues)
        spell_level_source = (
            None if class_graft and class_graft.get("spellcastingMode") == "supernatural-extracts"
            else class_graft.get("spellcastingClassId") if class_graft else None
        )
        spellcasting_cr = cr if array_id == "array.spellcaster" else cr_entry.get("spellcastingAsCR") if cr_entry else None
        spells, spell_list_benefit = self._evaluate_spells(selections, array_id, spellcasting_cr, main, issues, spell_level_source)
        secondary_lists = []
        for option in selected_options:
            if option["optionId"] == "option.secondary-magic":
                list_id = option.get("parameters", {}).get("spellListId")
                if list_id is None and spellcasting_cr is None:
                    list_id = selections.get("spellListId")
                if list_id and list_id not in secondary_lists and (spellcasting_cr is None or list_id != selections.get("spellListId")):
                    secondary_lists.append(list_id)
        secondary_magic_cr = cr_entry.get("secondaryMagicAsCR", cr) if cr_entry else cr
        for list_id in secondary_lists:
            spells.extend(self._evaluate_secondary_magic(list_id, secondary_magic_cr, main, issues, spell_level_source))
        at_will_option_spells = []
        for option in selected_options:
            if option["optionId"] == "option.at-will-magic" and option.get("parameters", {}).get("spellId"):
                result = self._spell_result(option["parameters"]["spellId"], [], spell_level_source, main, issues, "/selections/options")
                if result and result["baseLevel"] <= option.get("parameters", {}).get("maxSpellLevel", 1):
                    result.update({"frequency": "at will", "role": "option", "sourceText": option.get("sourceText", "At-Will Magic")})
                    at_will_option_spells.append(result)
                elif result:
                    issues.append(self._issue("option.spell-level-invalid", "/selections/options", "At-Will Magic requires a 0- or 1st-level spell", "source-rule", "error", self.catalog.data["options"]["option.at-will-magic"]["sourceRef"]))
        spells.extend(at_will_option_spells)
        class_choice_spells = []
        for spell_id in (class_choice_effect or {}).get("atWillSpellIds", []):
            result = self._spell_result(spell_id, [], spell_level_source, main, issues, "/selections/classGraftChoices")
            if result:
                result.update({"frequency": "at will", "role": "class-graft-choice"})
                class_choice_spells.append(result)
        spells.extend(class_choice_spells)
        subtype_choice_spells = []
        for grant in subtype_choice_spell_grants:
            result = self._spell_result(grant["spellId"], [], None, main, issues, "/selections/subtypeGraftChoices")
            if result:
                result.update(copy.deepcopy({key: value for key, value in grant.items() if key != "spellId"}))
                subtype_choice_spells.append(result)
        spells.extend(subtype_choice_spells)
        if spellcasting_cr is None and not secondary_lists and not at_will_option_spells and not class_choice_spells and not subtype_choice_spells and (selections.get("spells") or selections.get("spellListId")):
            issues.append(self._issue("spells.array-required", "/selections/spells", "spells require the spellcaster array, class-graft spellcasting, or secondary magic", "source-rule", "error"))

        initiative_bonus = sum(
            self.catalog.data["options"][option["optionId"]].get("effects", {}).get("initiative", 0)
            for option in selected_options
        )
        speed = copy.deepcopy(selections["speed"])
        if class_graft:
            speed_bonus = class_graft.get("speedAdjustment", 0) + (cr_entry.get("speedAdjustment", 0) if cr_entry else 0)
            if speed_bonus:
                speed["land"] = speed.get("land", 0) + speed_bonus
        if class_choice_effect and class_choice_effect.get("speedAdjustment"):
            speed["land"] = max(0, speed.get("land", 0) + class_choice_effect["speedAdjustment"])
        for graft in active_grafts:
            speed.update(graft.get("movement", {}))
            multiplier = graft.get("movementMultiplier")
            if multiplier:
                speed[multiplier["to"]] = speed.get(multiplier["from"], 0) * multiplier["value"]
        class_choice_senses = []
        for sense in (class_choice_effect or {}).get("senses", []):
            if cr < sense["minCR"]:
                continue
            if sense.get("replace") in class_choice_senses:
                class_choice_senses.remove(sense["replace"])
            class_choice_senses.append(sense["value"])
        class_choice_immunities = [
            entry["value"] for entry in (class_choice_effect or {}).get("immunities", [])
            if cr >= entry["minCR"]
        ]
        class_choice_stages = [
            entry["value"] for entry in (class_choice_effect or {}).get("stages", [])
            if cr >= entry["minCR"]
        ]
        class_choice_conditional_skills = [
            {key: value for key, value in entry.items() if key != "minCR"}
            for entry in (class_choice_effect or {}).get("conditionalMasterSkills", [])
            if cr >= entry["minCR"]
        ]
        graft_abilities = []
        if class_graft:
            graft_abilities.append({"origin": "class", "graftId": class_id, "name": class_graft["name"], "text": class_graft["ruleText"]})
        graft_abilities.extend(
            {"origin": "subtype", "graftId": graft_id, "name": graft["name"], "text": graft["ruleText"]}
            for graft_id, graft in subtype_grafts
        )
        if template:
            graft_abilities.append({"origin": "template", "graftId": template_id, "name": template["name"], "text": template["ruleText"]})

        companion = None
        if class_graft and class_graft.get("companionSpec"):
            spec = class_graft["companionSpec"]
            companion = {
                "name": selections.get("classGraftChoices", {}).get(spec["choiceName"]),
                "cr": cr + spec["crAdjustment"],
                "arrayId": spec["arrayId"],
                "creatureTypeGraftId": spec["creatureTypeGraftId"],
                "combinedEncounterCR": cr + spec["combinedCRAdjustment"],
                "awardsIndependentXP": spec["awardsIndependentXP"],
            }
        canonical = {
            "cr": cr,
            "arrayId": array_id,
            "creatureTypeGraftId": type_id,
            "classGraftId": class_id,
            "classGraftChoices": copy.deepcopy(selections.get("classGraftChoices", {})),
            "graftOptionChoices": copy.deepcopy(selections.get("graftOptionChoices", {})),
            "subtypeGraftIds": subtype_ids,
            "subtypeGraftChoices": copy.deepcopy(selections.get("subtypeGraftChoices", {})),
            "templateGraftId": template_id,
            "templateGraftChoices": copy.deepcopy(selections.get("templateGraftChoices", {})),
            "sizeId": size_id,
            "defenses": {"ac": ac, "touchAC": touch_ac, "flatFootedAC": flat_footed_ac, **saves, "cmd": cmd, "hp": main["hp"]},
            "abilityDC": main["abilityDC"],
            "spellDC": main["spellDC"],
            "abilityModifiers": copy.deepcopy(abilities),
            "skills": skill_values,
            "initiative": abilities.get("dexterity", 0) + initiative_bonus,
            "hitDice": int(max(1, cr)),
            "concentration": None,
            "cmb": cmb,
            "maneuverBonuses": maneuver_bonuses,
            "attacks": attacks,
            "options": selected_options,
            "senses": list(dict.fromkeys([
                *creature_type.get("automaticTraits", []),
                *(sense for graft in active_grafts for sense in graft.get("senses", [])),
                *class_choice_senses,
            ])),
            "immunities": class_choice_immunities,
            "resistances": {},
            "damageReduction": [],
            "fastHealing": None,
            "regeneration": [],
            "casterLevelCheckBonuses": [],
            "conditions": [
                *(class_choice_effect or {}).get("conditions", []),
                *(condition for graft in active_grafts for condition in graft.get("conditions", [])),
            ],
            "classGraftChoiceEffect": {
                "traits": [*(class_choice_effect or {}).get("traits", []), *class_choice_stages],
                "limitations": copy.deepcopy((class_choice_effect or {}).get("limitations", [])),
                "conditionalMasterSkills": class_choice_conditional_skills,
                "languages": copy.deepcopy(selections.get("classGraftChoices", {}).get("languages", [])),
            } if class_choice_effect else None,
            "conditionalSaveBonuses": [
                copy.deepcopy(bonus)
                for graft in active_grafts
                for bonus in graft.get("conditionalSaveBonuses", [])
            ],
            "graftTraits": [
                trait for graft in active_grafts for trait in graft.get("traits", [])
            ],
            "vulnerabilities": [
                vulnerability for graft in active_grafts for vulnerability in graft.get("vulnerabilities", [])
            ],
            "damageRules": [
                rule for graft in active_grafts for rule in graft.get("damageRules", [])
            ],
            "speed": speed,
            "movementManeuverability": {
                movement: quality
                for graft in active_grafts
                for movement, quality in graft.get("movementManeuverability", {}).items()
            },
            "graftAbilities": graft_abilities,
            "spells": spells,
            "spellListBenefit": None,
            "spellcastingClassId": class_graft.get("spellcastingClassId") if class_graft else None,
            "spellcastingMode": class_graft.get("spellcastingMode") if class_graft else None,
            "classAttackDamage": class_attack_damage,
            "classAbilities": copy.deepcopy(class_ability_choices),
            "companion": companion,
        }
        if spell_list_benefit:
            canonical["spellListBenefit"] = self._apply_spell_list_benefit(
                spell_list_benefit, selections.get("spellListBenefitChoices", {}), cr, main, canonical, issues
            )
        if spellcasting_cr is not None or secondary_lists or at_will_option_spells or class_choice_spells or subtype_choice_spells:
            spellcasting_ability = selections.get("spellcastingAbility")
            if spellcasting_ability is None:
                candidates = [ability for ability in ("intelligence", "wisdom", "charisma") if ability in canonical["abilityModifiers"]]
                spellcasting_ability = max(candidates, key=lambda ability: canonical["abilityModifiers"][ability]) if candidates else "charisma"
            canonical["concentration"] = cr + canonical["abilityModifiers"].get(spellcasting_ability, 0)

        for selected_option in canonical["options"]:
            effect = self.catalog.data["options"][selected_option["optionId"]].get("effects", {})
            effect_type = effect.get("type")
            if effect_type == "attackBonus":
                value = effect["value"]
                canonical["cmb"] += value
                for attack in canonical["attacks"]:
                    attack["attackBonus"] = [bonus + value for bonus in attack["attackBonus"]]
                    attack["attackBonusText"] = "/".join(_signed(bonus) for bonus in attack["attackBonus"])
            elif effect_type == "defenseBonuses":
                for field, value in effect["values"].items():
                    canonical["defenses"][field] += value
                canonical["defenses"]["touchAC"] = min(canonical["defenses"]["ac"], max(1, canonical["defenses"]["touchAC"]))
                canonical["defenses"]["flatFootedAC"] = max(1, canonical["defenses"]["flatFootedAC"])
                if selected_option["optionId"] == "option.extra-armor" and selected_option.get("parameters", {}).get("armorSource") == "manufactured":
                    canonical["speed"]["land"] = max(0, canonical["speed"].get("land", 0) - 10)
            elif effect_type == "concentrationBonus" and canonical["concentration"] is not None:
                canonical["concentration"] += effect["value"]
            elif effect_type == "spellResistance":
                canonical["spellResistance"] = cr + 11
            elif effect_type == "saveChoice" and selected_option.get("parameters", {}).get("save"):
                save = selected_option["parameters"]["save"]
                if save == "all":
                    for field in ("fortitude", "reflex", "will"):
                        canonical["defenses"][field] += 1
                else:
                    canonical["defenses"][save] += 3
            elif effect_type == "additionalMasterSkills":
                for skill_id in effect["skillIds"]:
                    canonical["skills"][skill_id.removeprefix("skill.")] = main["masterBonus"]
            elif effect_type == "casterLevelCheckBonus":
                value = effect["values"][max(
                    (threshold for threshold in effect["values"] if cr >= int(threshold)), key=int,
                )]
                canonical["casterLevelCheckBonuses"].append({"value": value, "against": effect["against"]})
            if selected_option["optionId"] == "option.extra-hit-points":
                increase = int(canonical["defenses"]["hp"] * 0.2)
                canonical["defenses"]["hp"] += increase
                selected_option["effect"] = {"type": "hit-points-percent", "percent": 20, "value": increase}
            elif selected_option["optionId"] == "option.immunity":
                canonical["immunities"] = list(dict.fromkeys([*canonical["immunities"], *selected_option.get("parameters", {}).get("immunities", [])]))
                selected_option["effect"] = {"type": "immunity", "values": copy.deepcopy(selected_option.get("parameters", {}).get("immunities", []))}
            elif selected_option["optionId"] == "option.damage-reduction" and selected_option.get("parameters", {}).get("bypass"):
                bypass = selected_option["parameters"]["bypass"]
                effective_cr = max(0, cr - 5) if "CR 5 lower" in selected_option.get("sourceText", "") else cr
                row = (5, 5, 5, 5, 1) if effective_cr <= 5 else (10, 10, 10, 5, 3) if effective_cr <= 10 else (15, 15, 10, 10, 5) if effective_cr <= 15 else (20, 20, 20, 15, 10) if effective_cr <= 20 else (30, 30, 30, 20, 15)
                categories = {"bludgeoning": 0, "piercing": 0, "slashing": 0, "adamantine": 1, "cold-iron": 1, "silver": 1, "magic": 2, "chaotic": 3, "evil": 3, "good": 3, "lawful": 3, "none": 4}
                value = selected_option.get("value", min(row[categories[item]] for item in bypass) - (5 if len(bypass) > 1 else 0))
                for tier in selected_option.get("valueByCR", []):
                    if cr >= tier["minCR"]:
                        value = tier["value"]
                value = max(0, value)
                reduction = {"value": value, "bypass": copy.deepcopy(bypass)}
                canonical["damageReduction"].append(reduction)
                canonical["damageRules"].append(f"DR {reduction['value']}/{' and '.join(reduction['bypass'])}")
                selected_option["effect"] = {"type": "damage-reduction", **copy.deepcopy(reduction)}
            elif selected_option["optionId"] == "option.energy-resistance" and selected_option.get("parameters", {}).get("energyTypes"):
                energy_types = selected_option["parameters"]["energyTypes"]
                value = selected_option.get("value", selected_option.get("parameters", {}).get("resistanceValue", 10))
                for energy in energy_types:
                    canonical["resistances"][energy] = max(canonical["resistances"].get(energy, 0), value)
                selected_option["effect"] = {"type": "energy-resistance", "value": value, "energyTypes": copy.deepcopy(energy_types)}
            elif selected_option["optionId"] == "option.fast-healing":
                value = selected_option.get("value", 20 if cr >= 21 else 15 if cr >= 16 else 10 if cr >= 11 else 5 if cr >= 4 else 2)
                canonical["fastHealing"] = max(canonical["fastHealing"] or 0, value)
                selected_option["effect"] = {"type": "fast-healing", "value": value}
            elif selected_option["optionId"] == "option.regeneration" and selected_option.get("parameters", {}).get("bypass"):
                value = selected_option.get("value", 20 if cr >= 21 else 15 if cr >= 16 else 10 if cr >= 11 else 5 if cr >= 4 else 2)
                regeneration = {"value": value, "bypass": copy.deepcopy(selected_option["parameters"]["bypass"]), "suppression": "1 round"}
                canonical["regeneration"].append(regeneration)
                selected_option["effect"] = {"type": "regeneration", **copy.deepcopy(regeneration)}
            if effect_type in {"attackBonus", "defenseBonuses", "concentrationBonus", "spellResistance", "saveChoice", "additionalMasterSkills"}:
                selected_option["effect"] = copy.deepcopy(effect)
            elif effect_type == "casterLevelCheckBonus":
                selected_option["effect"] = {"type": effect_type, "value": value, "against": effect["against"]}

        errors = [issue for issue in issues if issue["severity"] == "error"]
        if errors:
            incomplete_codes = {"spell-list-benefit.choice-required", "class-graft.choice-required", "class-graft.spell-list-required", "graft-option.choice-required", "subtype-graft.choice-required", "template-graft.choice-required"}
            status = "incomplete" if all(issue["code"] in incomplete_codes for issue in errors) else "invalid"
            return self._evaluation(status, issues)

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
                code = "damage.natural-die-unsupported" if natural and selected.get("damageDie") is None else "damage.unresolved"
                message = (
                    f"source natural-attack die {natural_die} has no Table 5-9 column or published alternative for average damage {average_damage}"
                    if code == "damage.natural-die-unsupported" else
                    f"no source damage expression for average damage {average_damage} and damage die {die}"
                )
                issues.append(self._issue(code, f"/selections/attacks/{index}", message, "catalog-data", "error", source_refs))
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

    def _evaluate_spells(self, selections, array_id, cr, main, issues, default_level_source=None):
        if cr is None:
            return [], None
        if selections.get("spellListId"):
            spell_list_id, spell_list = self._resolve("spellList", selections["spellListId"], "/selections/spellListId")
            bands = self.catalog.data["spellBands"]
            band_index = next(index for index, band in enumerate(bands) if band["minCR"] <= cr and (band["maxCR"] is None or cr <= band["maxCR"]))
            sets = [(band_index, "primary", "1/day")]
            if band_index >= 1:
                sets.extend(((band_index - 1, "primary", "3/day"), (band_index - 1, "secondary", "3/day")))
            if band_index >= 2:
                sets.append((band_index - 2, "primary", "at will"))
            output = []
            for source_band_index, role, frequency in sets:
                source_band = bands[source_band_index]["id"]
                for entry in spell_list["bands"][source_band][role]:
                    result = self._spell_result(entry["spellId"], entry.get("metamagic", []), default_level_source, main, issues, "/selections/spellListId")
                    if result:
                        result.update({
                            "frequency": frequency,
                            "sourceBand": source_band,
                            "role": role,
                            "sourceText": entry["sourceText"],
                        })
                        output.append(result)
            return output, {
                "spellListId": spell_list_id,
                "name": spell_list["name"],
                "text": spell_list["benefit"]["text"],
                "definition": spell_list["benefit"],
            }
        if not selections.get("spells"):
            return [], None
        output = []
        for index, selected in enumerate(selections["spells"]):
            result = self._spell_result(
                selected["spellId"], selected.get("metamagic", []),
                selected.get("spellLevelSource") or selections.get("spellLevelSource") or default_level_source,
                main, issues, f"/selections/spells/{index}",
            )
            if result:
                output.append(result)
        return output, None

    def _evaluate_secondary_magic(self, selected_list_id, cr, main, issues, default_level_source=None):
        spell_list_id, spell_list = self._resolve("spellList", selected_list_id, "/selections/options")
        band = next(band for band in self.catalog.data["spellBands"] if band["minCR"] <= cr and (band["maxCR"] is None or cr <= band["maxCR"]))
        output = []
        for entry in spell_list["bands"][band["id"]]["primary"]:
            result = self._spell_result(entry["spellId"], entry.get("metamagic", []), default_level_source, main, issues, "/selections/options")
            if result:
                result.update({"frequency": "1/day", "sourceBand": band["id"], "role": "primary", "sourceText": entry["sourceText"], "secondaryMagic": True, "spellListId": spell_list_id})
                output.append(result)
        return output

    def _apply_spell_list_benefit(self, benefit, choices, cr, main, canonical, issues):
        definition = benefit.pop("definition")
        parameters = definition.get("parameters", {})
        invalid = False
        for name, parameter in parameters.items():
            path = f"/selections/spellListBenefitChoices/{name}"
            if name not in choices:
                issues.append(self._issue("spell-list-benefit.choice-required", path, "spell-list benefit choice is required", "source-rule", "error", definition["sourceRef"]))
                invalid = True
                continue
            value = choices[name]
            if parameter["type"] in {"enum", "enum-array"}:
                values = value if isinstance(value, list) else [value]
                if any(item not in parameter["values"] for item in values) or (parameter["type"] == "enum-array" and (len(values) != parameter["count"] or len(set(values)) != len(values))):
                    issues.append(self._issue("spell-list-benefit.choice-invalid", path, "spell-list benefit choice is not allowed", "source-rule", "error", definition["sourceRef"]))
                    invalid = True
            elif parameter["type"] == "selected-speed" and value not in canonical["speed"]:
                issues.append(self._issue("spell-list-benefit.choice-invalid", path, "speed choice must name a selected movement speed", "source-rule", "error", definition["sourceRef"]))
                invalid = True
        if invalid:
            return benefit

        def selected(value):
            return choices[value["parameter"]] if isinstance(value, dict) and "parameter" in value else value

        def scaled(effect):
            values = effect.get("values")
            if values is None:
                return effect.get("value")
            return values[max((threshold for threshold in values if cr >= int(threshold)), key=int)]

        applied = []
        conditional = canonical.setdefault("conditionalModifiers", [])
        for effect in definition.get("effects", []):
            effect_type = effect["type"]
            value = scaled(effect)
            if effect_type == "resistance":
                energy = selected(effect["energyType"])
                if effect.get("immunityAt") is not None and cr >= effect["immunityAt"]:
                    canonical.setdefault("immunities", []).append(energy)
                    result = {"type": "immunity", "energyType": energy}
                else:
                    canonical.setdefault("resistances", {})[energy] = value
                    result = {"type": effect_type, "energyType": energy, "value": value}
            elif effect_type == "abilityModifier":
                ability = selected(effect["ability"])
                canonical["abilityModifiers"][ability] = canonical["abilityModifiers"].get(ability, 0) + value
                result = {"type": effect_type, "ability": ability, "value": value}
            elif effect_type == "speedBonus":
                speed_type = selected(effect["speedType"])
                canonical["speed"][speed_type] += value
                result = {"type": effect_type, "speedType": speed_type, "value": value}
            elif effect_type == "movementChoice":
                speed_type = choices[effect["parameter"]]
                movement = effect["choices"][speed_type]
                if movement["operation"] == "add":
                    canonical["speed"][speed_type] = canonical["speed"].get(speed_type, 0) + movement["value"]
                else:
                    canonical["speed"][speed_type] = movement["value"]
                result = {"type": effect_type, "speedType": speed_type, **movement}
            elif effect_type == "allSavesBonus":
                for save in ("fortitude", "reflex", "will"):
                    canonical["defenses"][save] += value
                result = {"type": effect_type, "value": value}
            elif effect_type == "attackBonus":
                for attack in canonical["attacks"]:
                    attack["attackBonus"] = [bonus + value for bonus in attack["attackBonus"]]
                    attack["attackBonusText"] = "/".join(_signed(bonus) for bonus in attack["attackBonus"])
                result = {"type": effect_type, "value": value}
            elif effect_type == "defenseBonus":
                for field in effect["fields"]:
                    canonical["defenses"][field] += value
                result = {"type": effect_type, "fields": effect["fields"], "value": value}
            elif effect_type in {"masterSkill", "masterSkills"}:
                skill_ids = selected(effect.get("skillIds", effect.get("skillId")))
                skill_ids = skill_ids if isinstance(skill_ids, list) else [skill_ids]
                for skill_id in skill_ids:
                    canonical["skills"][skill_id.removeprefix("skill.")] = main["masterBonus"]
                result = {"type": effect_type, "skillIds": skill_ids}
            elif effect_type == "spellDCBonus" and effect["condition"] in {"metamagic", "from this spell list"}:
                for spell in canonical["spells"]:
                    if effect["condition"] != "metamagic" or spell["metamagic"]:
                        spell["spellDC"] += value
                result = {"type": effect_type, "condition": effect["condition"], "value": value}
            else:
                result = {key: selected(item) for key, item in effect.items() if key != "values"}
                if "valueFormula" in effect:
                    result["value"] = int(cr / 2) if effect["valueFormula"] == "halfCR" else effect["valueFormula"]
                elif value is not None:
                    result["value"] = value
                conditional.append(copy.deepcopy(result))
            applied.append(result)
        if not conditional:
            canonical.pop("conditionalModifiers")
        if choices:
            benefit["choices"] = copy.deepcopy(choices)
        if applied:
            benefit["effects"] = applied
        return benefit

    def _spell_result(self, selected_spell_id, metamagic, level_source, main, issues, path):
        spell_id, spell = self._resolve("spell", selected_spell_id, f"{path}/spellId")
        if level_source is None:
            level_source = next((source for source in ("cleric", "sorcerer", "wizard") if source in spell["levelsByClass"]), None)
            if level_source is None:
                level_source = max(spell["levelsByClass"], key=spell["levelsByClass"].get)
        if level_source not in spell["levelsByClass"]:
            issues.append(self._issue("spell.level-source-invalid", path, "requested spell level source is not present", "source-rule", "error", spell.get("sourceRef")))
            return None
        base_level = spell["levelsByClass"][level_source]
        effective_level = base_level + sum(self.catalog.data["metamagic"][value] for value in metamagic)
        return {
            "spellId": spell_id,
            "name": spell["name"],
            "spellLevelSource": level_source,
            "baseLevel": base_level,
            "metamagic": list(metamagic),
            "effectiveLevel": effective_level,
            "spellDC": main["spellDC"] + effective_level,
        }

    def _trace(self, draft, main, attack_table, creature_type, size, canonical):
        trace = []
        def add(path, rule, value, refs):
            trace.append({"path": path, "rule": rule, "value": copy.deepcopy(value), "sourceRefs": copy.deepcopy(refs if isinstance(refs, list) else [refs])})
        main_ref = main["sourceRef"]
        add("/canonical/defenses", "array.mainStatistics", canonical["defenses"], [main_ref])
        add("/canonical/abilityDC", "array.abilityDC", canonical["abilityDC"], [main_ref])
        add("/canonical/spellDC", "array.spellDC", canonical["spellDC"], [main_ref])
        add("/canonical/abilityModifiers", "draft.abilityModifierAssignments", canonical["abilityModifiers"], [main_ref])
        attack_refs = [attack_table["sourceRef"]]
        for selected, attack in zip(draft["selections"]["attacks"], canonical["attacks"]):
            if selected.get("naturalAttackId"):
                _, natural = self._resolve("naturalAttack", selected["naturalAttackId"], "/selections/attacks")
                if natural["sourceRef"] not in attack_refs:
                    attack_refs.append(natural["sourceRef"])
            row = next((row for row in self.catalog.data["damage"].values() if row["min"] <= attack["averageDamage"] <= row["max"]), None)
            if row:
                ref = row.get("expressionSourceRefs", {}).get(attack["damageDie"], row["sourceRef"])
                if ref not in attack_refs:
                    attack_refs.append(ref)
        add("/canonical/attacks", "array.attackStatistics + graft adjustments + damage table", canonical["attacks"], attack_refs)
        add("/canonical/senses", "creatureTypeGraft.automaticTraits", canonical["senses"], [creature_type["sourceRef"]])
        if canonical.get("classGraftId"):
            _, class_graft = self._resolve("classGraft", canonical["classGraftId"], "/selections/classGraftId")
            refs = [class_graft["sourceRef"]]
            cr_entry = max(
                (entry for entry in class_graft.get("crEntries", []) if canonical["cr"] >= entry["minCR"]),
                key=lambda entry: entry["minCR"], default=None,
            )
            if cr_entry:
                refs.append(cr_entry["sourceRef"])
            add("/canonical/classGraftId", "classGraft.requiredArray + adjustments + highestCREntry", canonical["classGraftId"], refs)
        if canonical.get("subtypeGraftIds"):
            refs = [self._resolve("subtype", subtype_id, "/selections/subtypeGraftIds")[1]["sourceRef"] for subtype_id in canonical["subtypeGraftIds"]]
            add("/canonical/subtypeGraftIds", "subtypeGraft.additionalGrants", canonical["subtypeGraftIds"], refs)
        if canonical.get("templateGraftId"):
            _, template = self._resolve("template", canonical["templateGraftId"], "/selections/templateGraftId")
            add("/canonical/templateGraftId", "templateGraft.automaticTraits", canonical["templateGraftId"], [template["sourceRef"]])
        if canonical.get("graftAbilities"):
            refs = [
                self._resolve({"class": "classGraft", "subtype": "subtype", "template": "template"}[ability["origin"]], ability["graftId"], "/selections")[1]["sourceRef"]
                for ability in canonical["graftAbilities"]
            ]
            add("/canonical/graftAbilities", "graft.sourceRules", canonical["graftAbilities"], refs)
        skill_refs = [main_ref]
        if canonical.get("classGraftId"):
            skill_refs.append(self._resolve("classGraft", canonical["classGraftId"], "/selections/classGraftId")[1]["sourceRef"])
        skill_refs.extend(
            self._resolve("subtype", subtype_id, "/selections/subtypeGraftIds")[1]["sourceRef"]
            for subtype_id in canonical.get("subtypeGraftIds", [])
        )
        for option in canonical.get("options", []):
            definition = self.catalog.data["options"][option["optionId"]]
            if definition.get("effects", {}).get("type") == "additionalMasterSkills":
                refs = definition["sourceRef"]
                skill_refs.extend(refs if isinstance(refs, list) else [refs])
        if size.get("additionalMasterSkills") or size.get("additionalGoodSkills"):
            skill_refs.append(size["sourceRef"])
        add("/canonical/skills", "array.skillBonuses + graft grants + skill selections", canonical["skills"], skill_refs)
        initiative_refs = [main_ref]
        for option in canonical.get("options", []):
            definition = self.catalog.data["options"][option["optionId"]]
            if definition.get("effects", {}).get("initiative"):
                refs = definition["sourceRef"]
                initiative_refs.extend(refs if isinstance(refs, list) else [refs])
        add("/canonical/initiative", "otherCalculations.initiative + option adjustments", canonical["initiative"], initiative_refs)
        add("/canonical/hitDice", "otherCalculations.hitDice", canonical["hitDice"], [main_ref])
        add("/canonical/speed", "draft.speed", canonical["speed"], [])
        if canonical.get("concentration") is not None:
            add("/canonical/concentration", "otherCalculations.concentration", canonical["concentration"], [main_ref])
        option_refs = []
        for option in canonical.get("options", []):
            definition = self.catalog.data["options"].get(option["optionId"])
            if definition and definition.get("sourceRef"):
                refs = definition["sourceRef"]
                option_refs.extend(refs if isinstance(refs, list) else [refs])
        if canonical.get("classGraftId"):
            _, class_graft = self._resolve("classGraft", canonical["classGraftId"], "/selections/classGraftId")
            option_refs.append(class_graft["sourceRef"])
            cr_entry = max(
                (entry for entry in class_graft.get("crEntries", []) if canonical["cr"] >= entry["minCR"]),
                key=lambda entry: entry["minCR"], default=None,
            )
            if cr_entry:
                option_refs.append(cr_entry["sourceRef"])
        for subtype_id in canonical.get("subtypeGraftIds", []):
            refs = self._resolve("subtype", subtype_id, "/selections/subtypeGraftIds")[1]["sourceRef"]
            option_refs.extend(refs if isinstance(refs, list) else [refs])
        if canonical.get("templateGraftId"):
            refs = self._resolve("template", canonical["templateGraftId"], "/selections/templateGraftId")[1]["sourceRef"]
            option_refs.extend(refs if isinstance(refs, list) else [refs])
        add("/canonical/options", "array/graft option slots + automatic grants + option selections", canonical["options"], option_refs)
        if canonical.get("spells"):
            spell_refs = []
            for spell in canonical["spells"]:
                spell_refs.extend(self.catalog.data["spells"][spell["spellId"]].get("sourceRef", []))
            add("/canonical/spells", "step6.crBand + frequency + spellLevel + metamagic + spellDC", canonical["spells"], spell_refs)
        if canonical.get("spellListBenefit"):
            _, spell_list = self._resolve("spellList", draft["selections"]["spellListId"], "/selections/spellListId")
            benefit_ref = spell_list["benefit"]["sourceRef"]
            add("/canonical/spellListBenefit", "step6.spellListBenefit", canonical["spellListBenefit"], [benefit_ref])
            effect_paths = {
                "resistance": "resistances", "immunity": "immunities",
                "abilityModifier": "abilityModifiers", "speedBonus": "speed", "movementChoice": "speed",
                "allSavesBonus": "defenses", "defenseBonus": "defenses", "attackBonus": "attacks",
                "masterSkill": "skills", "masterSkills": "skills", "spellDCBonus": "spells",
            }
            traced = set()
            for effect in canonical["spellListBenefit"].get("effects", []):
                field = effect_paths.get(effect["type"], "conditionalModifiers")
                if effect["type"] == "spellDCBonus" and effect.get("condition") not in {"metamagic", "from this spell list"}:
                    field = "conditionalModifiers"
                if field in canonical and field not in traced:
                    add(f"/canonical/{field}", f"step6.spellListBenefit.{effect['type']}", canonical[field], [benefit_ref])
                    traced.add(field)
        add("/canonical/cmb", "otherCalculations.cmb", canonical["cmb"], [main_ref])
        if canonical.get("maneuverBonuses"):
            add("/canonical/maneuverBonuses", "option.improvedCombatManeuver", canonical["maneuverBonuses"], [self.catalog.data["options"]["option.improved-combat-maneuver"]["sourceRef"]])
        if canonical.get("casterLevelCheckBonuses"):
            refs = [
                self.catalog.data["options"][option["optionId"]]["sourceRef"]
                for option in canonical["options"]
                if self.catalog.data["options"][option["optionId"]].get("effects", {}).get("type") == "casterLevelCheckBonus"
            ]
            add("/canonical/casterLevelCheckBonuses", "option.casterLevelCheckBonus", canonical["casterLevelCheckBonuses"], refs)
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
