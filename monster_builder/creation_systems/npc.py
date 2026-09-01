"""Core class-based NPC creation-system adapter.

The adapter is deliberately table-driven.  It accepts the public Draft shape,
resolves every selected identifier through ``NpcCatalog``, and never fills an
unresolved catalog value from memory.  The checked-in NPC catalog currently
contains explicit source gaps, so those selections produce deterministic
``catalog-data`` evaluation findings until a hash-anchored rule row replaces
that gap.  Resolved catalogs with the same schema can run the complete
calculation path used by the vertical evaluator tests.
"""

from __future__ import annotations

import copy
import json
import math
import re
from typing import Any

from ..catalog import CatalogError
from ..errors import BoundaryError
from ..npc.prerequisites import evaluate_prerequisite
from .base import NPC


ABILITY_NAMES = (
    "strength",
    "dexterity",
    "constitution",
    "intelligence",
    "wisdom",
    "charisma",
)
ABILITY_SET = frozenset(ABILITY_NAMES)

# These are user-owned inputs.  Calculated values are explicitly rejected
# below, keeping the public draft contract free of hand-entered derived stats.
NPC_SELECTION_FIELDS = frozenset(
    {
        "statblockUse",
        "raceId",
        "racialChoices",
        "classProgression",
        "abilityGeneration",
        "levelIncreases",
        "skillGeneration",
        "feats",
        "classFeatureChoices",
        "spellLoadout",
        "gearProfile",
        "gear",
        "details",
    }
)
NPC_COMPUTED_SELECTION_FIELDS = frozenset(
    {
        "totalLevel",
        "level",
        "npcCategory",
        "recommendedCR",
        "cr",
        "abilityScores",
        "abilityModifiers",
        "hitDice",
        "hitDiceExpression",
        "hp",
        "bab",
        "saves",
        "defenses",
        "ac",
        "touchAC",
        "flatFootedAC",
        "initiative",
        "attacks",
        "damageExpression",
        "averageDamage",
        "cmb",
        "cmd",
        "skills",
        "skillRanks",
        "classFeatures",
        "spellcasting",
        "casterLevel",
        "spellsPerDay",
        "spellDC",
        "spellDCs",
        "gearBudget",
        "priceCp",
        "totalPriceCp",
        "attackBonus",
        "damageExpression",
        "averageDamage",
        "usesPerDay",
        "sizeId",
        "speed",
        "senses",
        "traits",
        "languages",
        "canonical",
        "effective",
        "derivationTrace",
        "evaluation",
    }
)

ABILITY_METHODS = frozenset(
    {
        "assigned",
        "assigned-array",
        "preset",
        "melee",
        "melee-preset",
        "ranged",
        "ranged-preset",
        "divine",
        "divine-preset",
        "arcane",
        "arcane-preset",
        "skill",
        "skill-preset",
        "custom",
    }
)
ABILITY_PRESET_NAMES = frozenset({"melee", "ranged", "divine", "arcane", "skill"})

_INCOMPLETE_CODES = frozenset(
    {
        "npc.selection-required",
        "npc.ability-selection-required",
        "npc.level-increase-required",
        "npc.skill-selection-required",
        "npc.feat-slot-required",
        "npc.class-feature-choice-required",
        "npc.racial-choice-required",
        "npc.custom-ability-rationale-required",
        "npc.gear-profile-required",
        "npc.gear-item-required",
        "npc.weapon-required",
        "npc.spell-choice-required",
    }
)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _canonical_id(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.rsplit(".", 1)[-1].casefold()


def _refs(*values: Any) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for value in values:
        if not value:
            continue
        entries = value if isinstance(value, list) else [value]
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            key = _canonical_json(entry)
            if key not in seen:
                seen.add(key)
                output.append(copy.deepcopy(entry))
    return output


def _label(value: Any) -> str:
    text = str(value).rsplit(".", 1)[-1]
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text).replace("-", " ").replace("_", " ")
    return text[:1].upper() + text[1:]


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _signed(value: int | float) -> str:
    return f"{value:+g}"


def _ability_modifier(score: int) -> int:
    return math.floor((score - 10) / 2)


def _parse_die(value: Any) -> tuple[int, int] | None:
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"(\d*)d(\d+)", value.strip().lower())
    if not match:
        return None
    count, sides = int(match.group(1) or 1), int(match.group(2))
    if count < 1 or sides < 1:
        return None
    return count, sides


def _format_bonus(value: int) -> str:
    return f"+{value}" if value >= 0 else str(value)


def _format_damage(dice: str | None, bonus: int) -> str | None:
    if not dice:
        return None
    return f"{dice}{_format_bonus(bonus)}" if bonus else dice


def _normalize_item_category(category: Any) -> str:
    value = str(category).casefold()
    return {
        "weapons": "weapon",
        "weapon": "weapon",
        "armors": "armor",
        "armor": "armor",
        "protection": "armor",
        "shields": "shield",
        "shield": "shield",
        "goods": "goods",
        "gear": "goods",
        "equipment": "goods",
        "magic": "magic",
        "magical": "magic",
        "limited-use": "limitedUse",
        "limiteduse": "limitedUse",
    }.get(value, str(category))


def _budget_category(category: Any, targets: dict[str, Any]) -> str:
    """Map item categories to the names used by a source budget row."""
    value = str(category)
    candidates = {
        "weapon": ("weapon", "weapons"),
        "armor": ("armor", "armors", "protection"),
        "shield": ("shield", "shields", "protection"),
        "gear": ("gear", "equipment", "goods"),
        "goods": ("goods", "gear", "equipment"),
        "magic": ("magic", "magical", "limitedUse"),
        "limitedUse": ("limitedUse", "limited-use", "magic"),
    }.get(value, (value,))
    for candidate in candidates:
        if candidate in targets:
            return candidate
    return value


class NpcCreation:
    """Creation-system adapter for Core class-based NPCs."""

    key = NPC
    selection_fields = NPC_SELECTION_FIELDS
    computed_selection_fields = NPC_COMPUTED_SELECTION_FIELDS

    def __init__(self, catalog):
        self.catalog = catalog

    # ------------------------------------------------------------------
    # Public adapter contract
    # ------------------------------------------------------------------
    def validate_input(self, draft: dict[str, Any]) -> None:
        selections = draft.get("selections")
        if not isinstance(selections, dict):
            raise BoundaryError("draft.selections-invalid", "selections must be an object", "/selections")
        unknown = set(selections) - self.selection_fields
        computed = unknown & self.computed_selection_fields
        if computed:
            field = sorted(computed)[0]
            raise BoundaryError(
                "draft.computed-selection",
                "computed values are not draft selections",
                f"/selections/{field}",
            )
        if unknown:
            field = sorted(unknown)[0]
            raise BoundaryError(
                "draft.selection-unknown",
                f"unknown selection field: {field}",
                f"/selections/{field}",
            )
        self._validate_selection_shapes(selections)
        self._validate_selection_ids(selections)

    def choice_requirements(self, draft: dict[str, Any]) -> dict[str, Any]:
        selections = draft.get("selections", {})
        requirements: list[dict[str, Any]] = []
        automatic: dict[str, Any] = {
            "racialTraits": [],
            "classFeatures": [],
            "featGrants": [],
            "skills": {"master": [], "good": []},
        }

        self._add_requirement(
            requirements,
            "/selections/statblockUse",
            "Statblock use",
            "enum",
            values=("full", "encounter"),
        )
        self._add_requirement(
            requirements,
            "/selections/raceId",
            "Race",
            "enum",
            values=self._choice_values("race"),
        )
        self._add_requirement(
            requirements,
            "/selections/classProgression",
            "Class progression",
            "enum-array",
            values=self._choice_values("class"),
            min_count=1,
        )

        progression = self._progression_for_requirements(selections)
        race = self._record_for("race", selections.get("raceId"))
        for slot in self._race_choice_slots(race):
            slot_id = self._choice_slot_id(slot)
            if not slot_id:
                continue
            allowed = self._choice_allowed_values(slot)
            values = self._values_for_generic_choices(allowed)
            self._add_requirement(
                requirements,
                f"/selections/racialChoices/{slot_id}",
                str(slot.get("name", slot.get("label", slot_id))),
                "enum" if values is not None else "string",
                values=values,
                source_refs=slot.get("sourceRef", race.get("sourceRef") if race else None),
            )
        for index, item in enumerate(progression):
            class_id = item.get("classId")
            class_record = item.get("record")
            class_ref = class_record.get("sourceRef") if class_record else None
            self._add_requirement(
                requirements,
                f"/selections/classProgression/{index}/classId",
                "Class",
                "enum",
                values=self._choice_values("class"),
                source_refs=class_ref,
            )
            self._add_requirement(
                requirements,
                f"/selections/classProgression/{index}/levels",
                "Class levels",
                "integer",
                source_refs=class_ref,
                minimum=1,
                maximum=self._max_class_level(class_record),
            )
            if class_record:
                for slot in self._choice_slots_for_class(class_record, item.get("levels", 0)):
                    if self._slot_is_feat(slot):
                        continue
                    slot_id = self._choice_slot_id(slot)
                    if not slot_id:
                        continue
                    allowed_feat_ids = slot.get("allowedFeatIds")
                    allowed = slot.get("allowedValues", slot.get("values"))
                    if isinstance(allowed_feat_ids, list):
                        values = self._choice_values_for_ids("feat", allowed_feat_ids)
                    elif self._slot_is_feat(slot):
                        values = self._choice_values("feat", category="general")
                    elif allowed is not None:
                        values = self._values_for_generic_choices(allowed)
                    else:
                        values = self._values_for_generic_choices(self._choice_allowed_values(slot))
                    self._add_requirement(
                        requirements,
                        f"/selections/classFeatureChoices/{slot_id}",
                        str(slot.get("name", slot_id)),
                        "enum" if values is not None else "string",
                        values=values,
                        source_refs=slot.get("sourceRef", class_ref),
                    )

                automatic["classFeatures"].extend(
                    self._automatic_feature_values(class_record, item.get("levels", 0))
                )

        ability_generation = selections.get("abilityGeneration")
        self._add_requirement(
            requirements,
            "/selections/abilityGeneration/method",
            "Ability generation method",
            "enum",
            values=tuple(sorted(ABILITY_METHODS)),
        )
        method = ability_generation.get("method") if isinstance(ability_generation, dict) else None
        if method in {"assigned", "assigned-array"}:
            for ability in ABILITY_NAMES:
                self._add_requirement(
                    requirements,
                    f"/selections/abilityGeneration/scores/{ability}",
                    ability.title(),
                    "integer",
                    source_refs=self._array_source_for_requirements(progression),
                )
        elif method in {"preset", "melee", "melee-preset", "ranged", "ranged-preset", "divine", "divine-preset", "arcane", "arcane-preset", "skill", "skill-preset"}:
            self._add_requirement(
                requirements,
                "/selections/abilityGeneration/preset",
                "Ability preset role",
                "enum",
                values=tuple(sorted(ABILITY_PRESET_NAMES)),
                source_refs=self._array_source_for_requirements(progression),
            )
        elif method == "custom":
            for ability in ABILITY_NAMES:
                self._add_requirement(
                    requirements,
                    f"/selections/abilityGeneration/scores/{ability}",
                    ability.title(),
                    "integer",
                    source_refs=self._array_source_for_requirements(progression),
                )
            self._add_requirement(
                requirements,
                "/selections/abilityGeneration/rationale",
                "Custom ability rationale",
                "string",
                source_refs=self._array_source_for_requirements(progression),
            )

        total_level = sum(item.get("levels", 0) for item in progression)
        increase_levels, increase_rule = self._ability_increase_levels(total_level)
        for level in increase_levels:
            self._add_requirement(
                requirements,
                f"/selections/abilityGeneration/levelIncreases/{level}",
                f"Ability increase at level {level}",
                "enum",
                values=tuple({"value": ability, "label": ability.title()} for ability in ABILITY_NAMES),
                source_refs=increase_rule.get("sourceRef") if increase_rule else None,
            )

        skill_generation = selections.get("skillGeneration")
        self._add_requirement(
            requirements,
            "/selections/skillGeneration/method",
            "Skill generation method",
            "enum",
            values=("simplified", "precise"),
        )
        skill_method = skill_generation.get("method") if isinstance(skill_generation, dict) else None
        if skill_method == "simplified":
            skill_values = self._skill_choice_values(progression)
            self._add_requirement(
                requirements,
                "/selections/skillGeneration/skills",
                "Simplified skills",
                "enum-array",
                values=skill_values,
                source_refs=self._class_source_refs(progression),
            )
        elif skill_method == "precise":
            for skill_id in sorted(self._skill_ids()):
                self._add_requirement(
                    requirements,
                    f"/selections/skillGeneration/ranks/{skill_id}",
                    _label(skill_id),
                    "integer",
                    source_refs=self._skill_record(skill_id).get("sourceRef"),
                    minimum=0,
                )

        spell_specs = self._spellcasting_specs(progression)
        if spell_specs:
            self._add_requirement(
                requirements,
                "/selections/spellLoadout/mode",
                "Spellcasting mode",
                "enum",
                values=("prepared", "spontaneous"),
                source_refs=spell_specs[0].get("sourceRef"),
            )
            self._add_requirement(
                requirements,
                "/selections/spellLoadout/spells",
                "Spell loadout",
                "enum-array",
                values=self._spell_choice_values(spell_specs[0]),
                min_count=1,
                source_refs=spell_specs[0].get("sourceRef"),
            )

        feat_slots = self._all_feat_slots(total_level, progression)
        feat_budget_status = None
        if total_level > 0 and not feat_slots:
            feat_budget_status = "gap"
            self._add_requirement(
                requirements,
                "/selections/feats",
                "General feats",
                "enum-array",
                values=self._choice_values("feat", category="general"),
                min_count=0,
            )
        for slot in feat_slots:
            slot_id = slot["slotId"]
            allowed_feat_ids = slot.get("allowedFeatIds")
            allowed_categories = slot.get("allowedCategories")
            if isinstance(allowed_feat_ids, list) and allowed_feat_ids:
                values = self._choice_values_for_ids("feat", allowed_feat_ids)
            elif isinstance(allowed_categories, list) and allowed_categories:
                values = self._choice_values("feat", category=allowed_categories[0]) if len(allowed_categories) == 1 else self._choice_values("feat")
            elif self._slot_is_general(slot):
                values = self._choice_values("feat", category="general")
            else:
                values = self._choice_values("feat")
            label = "General feat" if self._slot_is_general(slot) else str(slot.get("name", "Class feat"))
            self._add_requirement(
                requirements,
                f"/selections/feats/{slot_id}/featId",
                f"{label} at level {slot['grantedAtLevel']}",
                "enum",
                values=values,
                source_refs=slot.get("sourceRef"),
            )

        gear_profile = selections.get("gearProfile")
        self._add_requirement(
            requirements,
            "/selections/gearProfile/experienceProgression",
            "Experience progression",
            "enum",
            values=("slow", "medium", "fast"),
        )
        self._add_requirement(
            requirements,
            "/selections/gearProfile/fantasyLevel",
            "Fantasy level",
            "enum",
            values=("low", "normal", "high"),
        )
        budget = self._gear_budget_for(gear_profile, total_level=total_level)
        gear_budget = {
            "budgetCp": budget.get("budgetCp") if budget else None,
            "spentCp": 0,
            "deltaCp": None,
            "categories": copy.deepcopy(budget.get("categories")) if budget and isinstance(budget.get("categories"), dict) else {},
            "categorySpentCp": {},
            "categoryDeltasCp": {},
            "profileId": budget.get("id") if budget else None,
            "effectiveLevel": budget.get("effectiveLevel") if budget else None,
        }
        gear = selections.get("gear", [])
        self._add_requirement(
            requirements,
            "/selections/gear",
            "Gear",
            "enum-array",
            values=self._choice_values("item"),
            min_count=0,
        )
        for index, item in enumerate(gear if isinstance(gear, list) else []):
            item_id = item.get("itemId") if isinstance(item, dict) else None
            record = self._record_for("item", item_id) if isinstance(item_id, str) else None
            self._add_requirement(
                requirements,
                f"/selections/gear/{index}/itemId",
                "Gear item",
                "enum",
                values=self._choice_values("item"),
                source_refs=record.get("sourceRef") if record else None,
            )
            self._add_requirement(
                requirements,
                f"/selections/gear/{index}/quantity",
                "Quantity",
                "integer",
                minimum=1,
                source_refs=record.get("sourceRef") if record else None,
            )

        race = self._record_for("race", selections.get("raceId"))
        if race:
            # Requirements are a projection, so apply already supplied racial
            # choices to the automatic trait list without emitting duplicate
            # evaluation findings here.
            self._issue_keys = set()
            automatic_race = self._apply_racial_choices(race, selections, [])
            automatic["racialTraits"] = [
                {"value": value, "label": _label(value), "sourceRefs": _refs(automatic_race.get("sourceRef"), automatic_race.get("_npcChoiceRefs"))}
                for value in (automatic_race.get("traits") or [])
                if isinstance(value, str)
            ]

        # A class feature may itself grant a feat. Keep it visible without
        # turning automatic grants into user selections.
        automatic["featGrants"] = self._automatic_feat_values(progression)
        gear_budget.update(self._gear_totals(gear, budget))
        total_ranks = self._precise_skill_budget(progression, selections, None)
        skill_budget = {
            "method": skill_method,
            "master": None,
            "good": None,
            "totalRanks": total_ranks,
            "selected": len(skill_generation.get("skills", [])) if isinstance(skill_generation, dict) and isinstance(skill_generation.get("skills"), list) else 0,
        }
        if skill_method == "simplified":
            skill_budget["count"] = self._simplified_skill_count(progression, selections)
        elif skill_method == "precise":
            skill_budget["selectedRanks"] = sum(
                value for value in (skill_generation.get("ranks", {}).values() if isinstance(skill_generation, dict) and isinstance(skill_generation.get("ranks"), dict) else [])
                if _is_int(value)
            )

        return {
            "creationSystem": NPC,
            "requirements": self._sorted_requirements(requirements),
            "automaticSelections": automatic,
            "selectionBudgets": {
                "skills": skill_budget,
                "feats": {
                    "slots": feat_slots,
                    "selected": len(selections.get("feats", [])) if isinstance(selections.get("feats"), list) else 0,
                    **({"catalogStatus": feat_budget_status} if feat_budget_status else {}),
                },
                "spells": self._spell_budget(progression),
                "gear": gear_budget,
            },
        }

    @staticmethod
    def fingerprint_selections(selections: dict[str, Any]) -> dict[str, Any]:
        normalized = copy.deepcopy(selections)
        progression = normalized.get("classProgression")
        if isinstance(progression, list):
            # Order is authoritative.  Do not sort classes or feat slots.
            for item in progression:
                if isinstance(item, dict) and isinstance(item.get("classId"), str):
                    item["classId"] = item["classId"].strip()
        feats = normalized.get("feats")
        if isinstance(feats, list):
            for item in feats:
                if isinstance(item, dict) and isinstance(item.get("slotId"), str):
                    item["slotId"] = item["slotId"].strip()
        return normalized

    @staticmethod
    def creation_decisions(selections: dict[str, Any], trace: list[dict[str, Any]]) -> list[dict[str, Any]]:
        fields = (
            (1, ("statblockUse", "raceId", "racialChoices", "classProgression")),
            (2, ("abilityGeneration", "levelIncreases")),
            (3, ("skillGeneration",)),
            (4, ("feats",)),
            (5, ("classFeatureChoices",)),
            (6, ("spellLoadout",)),
            (7, ("gearProfile", "gear")),
            (8, ("details",)),
        )
        decisions: list[dict[str, Any]] = []
        for step, names in fields:
            source_refs: list[dict[str, Any]] = []
            seen: set[str] = set()
            for entry in trace:
                for source in entry.get("sourceRefs", []):
                    key = _canonical_json(source)
                    if key not in seen:
                        seen.add(key)
                        source_refs.append(copy.deepcopy(source))
            decisions.append(
                {
                    "step": step,
                    "selections": {field: copy.deepcopy(selections[field]) for field in names if field in selections},
                    "sourceRefs": source_refs,
                }
            )
        return decisions

    # ------------------------------------------------------------------
    # Input validation
    # ------------------------------------------------------------------
    def _validate_selection_shapes(self, selections: dict[str, Any]) -> None:
        if "statblockUse" in selections and selections["statblockUse"] not in {"full", "encounter"}:
            raise BoundaryError("selection.value-invalid", "statblockUse must be full or encounter", "/selections/statblockUse")
        if "raceId" in selections and not isinstance(selections["raceId"], str):
            raise BoundaryError("selection.type-invalid", "raceId must be a string", "/selections/raceId")
        for field in ("racialChoices", "classFeatureChoices", "spellLoadout", "details"):
            if field in selections and not isinstance(selections[field], dict):
                raise BoundaryError("selection.type-invalid", f"{field} must be an object", f"/selections/{field}")
        for field in ("racialChoices", "classFeatureChoices"):
            values = selections.get(field)
            if isinstance(values, dict):
                for key, value in values.items():
                    if not isinstance(key, str) or not key:
                        raise BoundaryError("selection.type-invalid", f"{field} keys must be non-empty strings", f"/selections/{field}")
                    if isinstance(value, (dict, tuple)):
                        raise BoundaryError("selection.type-invalid", f"{field} values must be scalar or arrays", f"/selections/{field}/{key}")
                    if isinstance(value, list) and any(not isinstance(item, (str, int, float, bool)) or isinstance(item, (dict, list)) for item in value):
                        raise BoundaryError("selection.type-invalid", f"{field} array values must contain scalars", f"/selections/{field}/{key}")
        progression = selections.get("classProgression")
        if progression is not None:
            if not isinstance(progression, list):
                raise BoundaryError("selection.type-invalid", "classProgression must be an array", "/selections/classProgression")
            for index, item in enumerate(progression):
                path = f"/selections/classProgression/{index}"
                if not isinstance(item, dict) or not isinstance(item.get("classId"), str) or not _is_int(item.get("levels")):
                    raise BoundaryError("selection.type-invalid", "each class progression entry requires classId and integer levels", path)
                self._reject_nested_fields(item, {"classId", "levels"}, path)
                if item["levels"] < 1:
                    raise BoundaryError("selection.value-invalid", "class levels must be positive", f"{path}/levels")
        ability = selections.get("abilityGeneration")
        if ability is not None:
            if not isinstance(ability, dict):
                raise BoundaryError("selection.type-invalid", "abilityGeneration must be an object", "/selections/abilityGeneration")
            self._reject_nested_fields(
                ability,
                {"method", "arrayId", "scores", "assignments", "levelIncreases", "preset", "role", "rationale"},
                "/selections/abilityGeneration",
            )
            if "arrayId" in ability and not isinstance(ability["arrayId"], str):
                raise BoundaryError("selection.type-invalid", "abilityGeneration.arrayId must be a string", "/selections/abilityGeneration/arrayId")
            self._reject_alias_conflict(ability, ("scores", "assignments"), "/selections/abilityGeneration")
            self._reject_alias_conflict(ability, ("preset", "role"), "/selections/abilityGeneration")
            method = ability.get("method")
            if method is not None and method not in ABILITY_METHODS:
                raise BoundaryError("selection.value-invalid", "abilityGeneration.method is not supported", "/selections/abilityGeneration/method")
            for field in ("preset", "role"):
                if field in ability and (not isinstance(ability[field], str) or ability[field].casefold() not in ABILITY_PRESET_NAMES):
                    raise BoundaryError("selection.value-invalid", f"abilityGeneration.{field} is not a supported preset", f"/selections/abilityGeneration/{field}")
            if "rationale" in ability and not isinstance(ability["rationale"], str):
                raise BoundaryError("selection.type-invalid", "abilityGeneration.rationale must be a string", "/selections/abilityGeneration/rationale")
            for score_field in ("scores", "assignments"):
                if score_field not in ability:
                    continue
                scores = ability[score_field]
                score_path = f"/selections/abilityGeneration/{score_field}"
                if not isinstance(scores, (dict, list)):
                    raise BoundaryError("selection.type-invalid", f"abilityGeneration.{score_field} must be an object or six-value array", score_path)
                if isinstance(scores, list) and (len(scores) != 6 or any(not _is_int(value) for value in scores)):
                    raise BoundaryError("selection.type-invalid", f"abilityGeneration.{score_field} must contain six integers", score_path)
                if isinstance(scores, dict) and any(ability_name not in ABILITY_SET or not _is_int(value) for ability_name, value in scores.items()):
                    raise BoundaryError("selection.type-invalid", f"abilityGeneration.{score_field} must map abilities to integers", score_path)
            if "levelIncreases" in ability:
                self._validate_level_increase_shape(ability["levelIncreases"], "/selections/abilityGeneration/levelIncreases")
        if "levelIncreases" in selections:
            self._validate_level_increase_shape(selections["levelIncreases"], "/selections/levelIncreases")
        skills = selections.get("skillGeneration")
        if skills is not None:
            if not isinstance(skills, dict):
                raise BoundaryError("selection.type-invalid", "skillGeneration must be an object", "/selections/skillGeneration")
            self._reject_nested_fields(
                skills,
                {"method", "skills", "selectedSkills", "ranks"},
                "/selections/skillGeneration",
            )
            self._reject_alias_conflict(skills, ("skills", "selectedSkills"), "/selections/skillGeneration")
            if skills.get("method") is not None and skills.get("method") not in {"simplified", "precise"}:
                raise BoundaryError("selection.value-invalid", "skillGeneration.method must be simplified or precise", "/selections/skillGeneration/method")
            if skills.get("method") == "simplified":
                values = skills.get("skills", skills.get("selectedSkills", []))
                if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
                    raise BoundaryError("selection.type-invalid", "simplified skills must be an array of IDs", "/selections/skillGeneration/skills")
            else:
                ranks = skills.get("ranks", {})
                if not isinstance(ranks, dict) or any(not isinstance(key, str) or not _is_int(value) or value < 0 for key, value in ranks.items()):
                    raise BoundaryError("selection.type-invalid", "precise skill ranks must map IDs to non-negative integers", "/selections/skillGeneration/ranks")
        feats = selections.get("feats")
        if feats is not None:
            if not isinstance(feats, list):
                raise BoundaryError("selection.type-invalid", "feats must be an array", "/selections/feats")
            for index, item in enumerate(feats):
                path = f"/selections/feats/{index}"
                if not isinstance(item, dict) or not isinstance(item.get("slotId"), str) or not isinstance(item.get("featId"), str):
                    raise BoundaryError("selection.type-invalid", "each feat selection requires slotId and featId", path)
                self._reject_nested_fields(item, {"slotId", "featId"}, path)
        details = selections.get("details")
        if isinstance(details, dict):
            computed_details = (set(details) & self.computed_selection_fields) - {"languages"}
            if computed_details:
                field = sorted(computed_details)[0]
                raise BoundaryError("draft.computed-selection", "computed values are not draft selections", f"/selections/details/{field}")

        loadout = selections.get("spellLoadout")
        if isinstance(loadout, dict):
            for field in ("spells", "preparedSpells", "knownSpells", "omittedLevels"):
                if field in loadout and not isinstance(loadout[field], (list, dict)):
                    raise BoundaryError("selection.type-invalid", f"spellLoadout.{field} must be an array or object", f"/selections/spellLoadout/{field}")
            if "mode" in loadout and loadout["mode"] not in {"prepared", "spontaneous"}:
                raise BoundaryError("selection.value-invalid", "spellLoadout.mode must be prepared or spontaneous", "/selections/spellLoadout/mode")
            for field in ("classId", "casterClassId"):
                if field in loadout and not isinstance(loadout[field], str):
                    raise BoundaryError("selection.type-invalid", f"spellLoadout.{field} must be a string", f"/selections/spellLoadout/{field}")
            self._reject_alias_conflict(loadout, ("classId", "casterClassId"), "/selections/spellLoadout")
            if "complete" in loadout and not isinstance(loadout["complete"], bool):
                raise BoundaryError("selection.type-invalid", "spellLoadout.complete must be a boolean", "/selections/spellLoadout/complete")
            if isinstance(loadout.get("omittedLevels"), dict):
                for level, enabled in loadout["omittedLevels"].items():
                    if not str(level).isdigit() or not isinstance(enabled, bool):
                        raise BoundaryError("selection.type-invalid", "omittedLevels map values must be booleans keyed by non-negative levels", "/selections/spellLoadout/omittedLevels")
            elif isinstance(loadout.get("omittedLevels"), list) and any(not _is_int(level) or level < 0 for level in loadout["omittedLevels"]):
                raise BoundaryError("selection.value-invalid", "omittedLevels must contain non-negative integers", "/selections/spellLoadout/omittedLevels")
            self._reject_nested_fields(
                loadout,
                {"spells", "preparedSpells", "knownSpells", "omittedLevels", "mode", "classId", "casterClassId", "complete", "spellsByLevel", "spellLevels"},
                "/selections/spellLoadout",
            )
            for field in ("spells", "preparedSpells", "knownSpells", "spellsByLevel", "spellLevels"):
                values = loadout.get(field)
                entries = []
                if isinstance(values, list):
                    entries = values
                elif isinstance(values, dict):
                    for level, group in values.items():
                        if not str(level).isdigit() or not isinstance(group, list):
                            raise BoundaryError("selection.type-invalid", f"spellLoadout.{field} must map non-negative levels to arrays", f"/selections/spellLoadout/{field}")
                        for entry in group:
                            if isinstance(entry, dict):
                                value_copy = copy.deepcopy(entry)
                                value_copy.setdefault("level", int(level))
                                entries.append(value_copy)
                            else:
                                entries.append({"spellId": entry, "level": int(level)})
                for index, item in enumerate(entries):
                    if isinstance(item, str):
                        continue
                    if not isinstance(item, dict) or not isinstance(item.get("spellId"), str):
                        raise BoundaryError("selection.type-invalid", "spell selections require spellId", f"/selections/spellLoadout/{field}/{index}")
                    self._reject_nested_fields(
                        item,
                        {"spellId", "level", "spellLevel", "prepared", "count"},
                        f"/selections/spellLoadout/{field}/{index}",
                    )
                    self._reject_alias_conflict(item, ("level", "spellLevel"), f"/selections/spellLoadout/{field}/{index}")
                    if "level" in item and (not _is_int(item["level"]) or item["level"] < 0):
                        raise BoundaryError("selection.value-invalid", "spell selection level must be a non-negative integer", f"/selections/spellLoadout/{field}/{index}/level")
                    if "spellLevel" in item and (not _is_int(item["spellLevel"]) or item["spellLevel"] < 0):
                        raise BoundaryError("selection.value-invalid", "spell selection spellLevel must be a non-negative integer", f"/selections/spellLoadout/{field}/{index}/spellLevel")
                    if "prepared" in item and not isinstance(item["prepared"], bool):
                        raise BoundaryError("selection.type-invalid", "spell selection prepared must be a boolean", f"/selections/spellLoadout/{field}/{index}/prepared")
                    if "count" in item and (not _is_int(item["count"]) or item["count"] < 1):
                        raise BoundaryError("selection.value-invalid", "spell selection count must be a positive integer", f"/selections/spellLoadout/{field}/{index}/count")
        profile = selections.get("gearProfile")
        if profile is not None:
            if not isinstance(profile, dict):
                raise BoundaryError("selection.type-invalid", "gearProfile must be an object", "/selections/gearProfile")
            self._reject_nested_fields(
                profile,
                {"experienceProgression", "progression", "fantasyLevel", "gearBudgetId"},
                "/selections/gearProfile",
            )
            if "gearBudgetId" in profile and not isinstance(profile["gearBudgetId"], str):
                raise BoundaryError("selection.type-invalid", "gearProfile.gearBudgetId must be a string", "/selections/gearProfile/gearBudgetId")
            self._reject_alias_conflict(profile, ("experienceProgression", "progression"), "/selections/gearProfile")
            progression = profile.get("experienceProgression", profile.get("progression"))
            if progression is not None and progression not in {"slow", "medium", "fast"}:
                raise BoundaryError("selection.value-invalid", "gearProfile experienceProgression must be slow, medium, or fast", "/selections/gearProfile/experienceProgression")
            if profile.get("fantasyLevel") is not None and profile.get("fantasyLevel") not in {"low", "normal", "high"}:
                raise BoundaryError("selection.value-invalid", "gearProfile fantasyLevel must be low, normal, or high", "/selections/gearProfile/fantasyLevel")
        gear = selections.get("gear")
        if gear is not None:
            if not isinstance(gear, list):
                raise BoundaryError("selection.type-invalid", "gear must be an array", "/selections/gear")
            for index, item in enumerate(gear):
                path = f"/selections/gear/{index}"
                if not isinstance(item, dict) or not isinstance(item.get("itemId"), str):
                    raise BoundaryError("selection.type-invalid", "each gear entry requires itemId", path)
                unknown_gear_fields = set(item) - {"itemId", "quantity", "equipped", "masterwork", "enhancementBonus", "properties", "propertyIds", "charges"}
                if unknown_gear_fields:
                    field = sorted(unknown_gear_fields)[0]
                    code = "draft.computed-selection" if field in self.computed_selection_fields else "draft.selection-unknown"
                    message = "computed values are not draft selections" if code == "draft.computed-selection" else f"unknown gear selection field: {field}"
                    raise BoundaryError(code, message, f"{path}/{field}")
                if "quantity" in item and (not _is_int(item["quantity"]) or item["quantity"] < 1):
                    raise BoundaryError("selection.value-invalid", "gear quantity must be a positive integer", f"{path}/quantity")
                if "equipped" in item and not isinstance(item["equipped"], bool):
                    raise BoundaryError("selection.type-invalid", "gear equipped must be a boolean", f"{path}/equipped")
                if "masterwork" in item and not isinstance(item["masterwork"], bool):
                    raise BoundaryError("selection.type-invalid", "gear masterwork must be a boolean", f"{path}/masterwork")
                if "enhancementBonus" in item and (not _is_int(item["enhancementBonus"]) or item["enhancementBonus"] < 0):
                    raise BoundaryError("selection.value-invalid", "gear enhancementBonus must be a non-negative integer", f"{path}/enhancementBonus")
                self._reject_alias_conflict(item, ("properties", "propertyIds"), path)
                for field in ("properties", "propertyIds"):
                    if field in item and (not isinstance(item[field], list) or any(not isinstance(value, str) or not value for value in item[field])):
                        raise BoundaryError("selection.type-invalid", f"gear {field} must be an array of non-empty IDs", f"{path}/{field}")
                    if field in item and len(item[field]) != len({_canonical_id(value) for value in item[field]}):
                        raise BoundaryError("selection.value-invalid", f"gear {field} must not contain duplicate properties", f"{path}/{field}")
                if "charges" in item and (not _is_int(item["charges"]) or item["charges"] < 1):
                    raise BoundaryError("selection.value-invalid", "gear charges must be a positive integer", f"{path}/charges")

    @classmethod
    def _alias_value(cls, value: Any) -> Any:
        if isinstance(value, str):
            return _canonical_id(value)
        if isinstance(value, list):
            return [cls._alias_value(item) for item in value]
        if isinstance(value, dict):
            return {
                _canonical_id(key) if isinstance(key, str) else key: cls._alias_value(child)
                for key, child in value.items()
            }
        return value

    @classmethod
    def _reject_alias_conflict(cls, value: dict[str, Any], fields: tuple[str, ...], path: str) -> None:
        present = [field for field in fields if field in value]
        if len(present) > 1 and any(cls._alias_value(value[field]) != cls._alias_value(value[present[0]]) for field in present[1:]):
            raise BoundaryError("selection.ambiguous", f"selection aliases must not disagree: {', '.join(present)}", path)

    def _reject_nested_fields(self, value: dict[str, Any], allowed: set[str], path: str) -> None:
        unknown = set(value) - allowed
        if not unknown:
            return
        field = sorted(unknown)[0]
        code = "draft.computed-selection" if field in self.computed_selection_fields else "draft.selection-unknown"
        message = "computed values are not draft selections" if code == "draft.computed-selection" else f"unknown selection field: {field}"
        raise BoundaryError(code, message, f"{path}/{field}")

    def _validate_level_increase_shape(self, value: Any, path: str) -> None:
        if isinstance(value, dict):
            seen: set[int] = set()
            for level, ability in value.items():
                if not str(level).isdigit() or int(level) < 1 or int(level) in seen or not isinstance(ability, str) or ability not in ABILITY_SET:
                    raise BoundaryError("selection.type-invalid", "level increases must map each positive integer level to one ability", path)
                seen.add(int(level))
        elif isinstance(value, list):
            seen: set[int] = set()
            previous = 0
            for index, item in enumerate(value):
                level = item.get("level") if isinstance(item, dict) else None
                if not isinstance(item, dict) or not _is_int(level) or level < 1 or level in seen or level <= previous or item.get("ability") not in ABILITY_SET:
                    raise BoundaryError("selection.type-invalid", "level increase entries must use unique levels in ascending order", f"{path}/{index}")
                seen.add(level)
                previous = level
        else:
            raise BoundaryError("selection.type-invalid", "level increases must be an object or array", path)

    def _validate_selection_ids(self, selections: dict[str, Any]) -> None:
        if isinstance(selections.get("raceId"), str):
            self._resolve("race", selections["raceId"], "/selections/raceId")
        ability = selections.get("abilityGeneration")
        if isinstance(ability, dict) and isinstance(ability.get("arrayId"), str):
            self._resolve("abilityArray", ability["arrayId"], "/selections/abilityGeneration/arrayId")
        profile = selections.get("gearProfile")
        if isinstance(profile, dict) and isinstance(profile.get("gearBudgetId"), str):
            self._resolve("gearBudget", profile["gearBudgetId"], "/selections/gearProfile/gearBudgetId")
        progression = selections.get("classProgression", [])
        if isinstance(progression, list):
            for index, item in enumerate(progression):
                self._resolve("class", item["classId"], f"/selections/classProgression/{index}/classId")
        skills = selections.get("skillGeneration", {})
        if isinstance(skills, dict):
            values = skills.get("skills", skills.get("selectedSkills", []))
            if isinstance(values, list):
                for index, value in enumerate(values):
                    self._resolve("skill", value, f"/selections/skillGeneration/skills/{index}")
            ranks = skills.get("ranks", {})
            if isinstance(ranks, dict):
                for value in ranks:
                    self._resolve("skill", value, f"/selections/skillGeneration/ranks/{value}")
        feats = selections.get("feats", [])
        if isinstance(feats, list):
            for index, item in enumerate(feats):
                self._resolve("feat", item["featId"], f"/selections/feats/{index}/featId")
        gear = selections.get("gear", [])
        if isinstance(gear, list):
            for index, item in enumerate(gear):
                self._resolve("item", item["itemId"], f"/selections/gear/{index}/itemId")
        loadout = selections.get("spellLoadout")
        if isinstance(loadout, dict):
            requested_class = loadout.get("classId", loadout.get("casterClassId"))
            if isinstance(requested_class, str):
                self._resolve("class", requested_class, "/selections/spellLoadout/classId")
            spell_entries = self._spell_entries(loadout)
            for index, item in enumerate(spell_entries):
                spell_id = item if isinstance(item, str) else item.get("spellId") if isinstance(item, dict) else None
                if isinstance(spell_id, str):
                    self._resolve("spell", spell_id, f"/selections/spellLoadout/spells/{index}/spellId")

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------
    def evaluate(self, draft: dict[str, Any]) -> dict[str, Any]:
        selections = draft.get("selections", {})
        issues: list[dict[str, Any]] = []
        self._issue_keys: set[tuple[str, str, str]] = set()
        self._required_selections(selections, issues)
        if issues and all(issue["code"] in _INCOMPLETE_CODES for issue in issues):
            return self._evaluation("incomplete", issues, [])

        progression = self._progression(selections, issues)
        total_level = sum(item["levels"] for item in progression)
        npc_category = self._npc_category(progression)
        race_id, race = self._selected_record("race", selections.get("raceId"), "/selections/raceId", issues)
        if race is not None:
            race = self._apply_racial_choices(race, selections, issues)
            for field in ("sizeId", "speed", "senses", "traits", "languages"):
                value = race.get(field)
                if value is None or value == {} or value == [] or value == "":
                    nested_value = self._race_effect_value(race, field)
                    if nested_value is not None:
                        value = nested_value
                valid = (
                    isinstance(value, str) and bool(value) if field == "sizeId" else
                    isinstance(value, dict) and bool(value) if field == "speed" else
                    isinstance(value, list)
                )
                if not valid:
                    self._append_issue(
                        issues,
                        self._issue(
                            "npc.race-derived-value-gap",
                            f"/selections/raceId/{field}",
                            f"race has no source-backed {field}",
                            "catalog-data",
                            "error",
                            race.get("sourceRef"),
                        ),
                    )
        ability_data = self._evaluate_abilities(
            selections,
            progression,
            race_id,
            race,
            npc_category,
            total_level,
            issues,
        )
        gear_data = self._evaluate_gear(selections, issues, total_level=total_level)
        # Permanent item ability effects are applied before ability modifiers.
        if ability_data.get("scores") is not None:
            for ability, value in gear_data.get("abilityBonuses", {}).items():
                ability_data["scores"][ability] = ability_data["scores"].get(ability, 0) + value
            ability_data["modifiers"] = {
                ability: _ability_modifier(score) for ability, score in ability_data["scores"].items()
            }
            if gear_data.get("abilityBonuses"):
                ability_data.setdefault("traceInputs", []).append({
                    "source": "permanent item ability bonuses",
                    "value": copy.deepcopy(gear_data["abilityBonuses"]),
                    "sourceRefs": gear_data.get("refs", []),
                })
            ability_data["refs"] = _refs(ability_data.get("refs"), gear_data.get("refs"))

        class_data = self._evaluate_classes(progression, total_level, ability_data, issues)
        selected_class_features = self._validate_class_feature_choices(selections, progression, issues)
        if selected_class_features:
            class_data["features"].extend(selected_class_features)
            class_data["refs"] = _refs(class_data.get("refs"), *(feature.get("sourceRefs") for feature in selected_class_features))
        skill_data = self._evaluate_skills(
            selections,
            progression,
            total_level,
            ability_data,
            race,
            gear_data,
            class_data,
            issues,
        )
        feat_data = self._evaluate_feats(
            selections,
            progression,
            total_level,
            ability_data,
            skill_data,
            class_data,
            race_id,
            issues,
        )
        # Feat effects can affect every later combat/statistic calculation.
        effects = self._collect_effects(
            [*feat_data.get("selected", []), *class_data.get("features", [])],
            gear_data.get("items", []),
        )
        if _is_int(class_data.get("hp")):
            class_data["hp"] += effects.get("hp", 0)
        self._apply_skill_effects(skill_data, effects, _refs(feat_data.get("refs"), class_data.get("refs")))
        combat_data = self._evaluate_combat(
            selections,
            progression,
            total_level,
            ability_data,
            race,
            gear_data,
            class_data,
            skill_data,
            effects,
            issues,
        )
        spell_data = self._evaluate_spells(
            selections,
            progression,
            total_level,
            ability_data,
            issues,
            classes=class_data,
        )
        languages = self._languages_for(race, selections, issues)
        details = selections.get("details") if isinstance(selections.get("details"), dict) else {}

        canonical = {
            "creationSystem": NPC,
            "statblockUse": selections.get("statblockUse"),
            "level": total_level,
            "totalLevel": total_level,
            "npcCategory": npc_category,
            "raceId": race_id,
            "racialChoices": copy.deepcopy(selections.get("racialChoices", {})),
            "classProgression": [
                {"classId": item["classId"], "levels": item["levels"]} for item in progression
            ],
            "classFeatureChoices": copy.deepcopy(selections.get("classFeatureChoices", {})),
            "abilityScores": copy.deepcopy(ability_data.get("scores")),
            "abilityModifiers": copy.deepcopy(ability_data.get("modifiers")),
            "hitDice": class_data.get("hitDice"),
            "hitDiceExpression": class_data.get("hitDiceExpression"),
            "hp": class_data.get("hp"),
            "bab": class_data.get("bab"),
            "saves": copy.deepcopy(class_data.get("saves")),
            "defenses": copy.deepcopy(combat_data.get("defenses", {})),
            "initiative": combat_data.get("initiative"),
            "attacks": copy.deepcopy(combat_data.get("attacks", [])),
            "cmb": combat_data.get("cmb"),
            "cmd": combat_data.get("cmd"),
            "skills": copy.deepcopy(skill_data.get("totals", {})),
            "skillRanks": copy.deepcopy(skill_data.get("ranks", {})),
            "feats": copy.deepcopy(feat_data.get("selected", [])),
            "featSlots": copy.deepcopy(feat_data.get("slots", [])),
            "classFeatures": copy.deepcopy(class_data.get("features", [])),
            "gear": copy.deepcopy(gear_data.get("items", [])),
            "gearBudget": copy.deepcopy(gear_data.get("budget")),
            "sizeId": self._race_value(race, "sizeId"),
            "speed": copy.deepcopy(self._race_value(race, "speed")),
            "senses": copy.deepcopy(self._race_list_value(race, "senses")),
            "traits": copy.deepcopy(self._race_list_value(race, "traits")),
            "languages": languages,
            "spells": copy.deepcopy(spell_data.get("spells", [])),
            "details": copy.deepcopy(details),
        }
        for field in ("alignment", "religion", "personality", "personalityTraits", "attackOrder", "gearGrouping"):
            if field in details:
                canonical[field] = copy.deepcopy(details[field])
        # Target CR remains concept guidance.  No NPC CR formula is currently
        # source-backed, so it is intentionally not copied into canonical data.
        if spell_data.get("casterLevel") is not None or spell_data.get("spellcastingClassId") is not None:
            for key in (
                "casterLevel", "spellcastingClassId", "spellcastingMode", "spellcastingAbility",
                "spellsPerDay", "baseSpellsPerDay", "bonusSpells", "omittedSpellLevels",
            ):
                if key in spell_data:
                    canonical[key] = copy.deepcopy(spell_data[key])

        trace = self._trace(canonical, ability_data, class_data, race, gear_data, skill_data, feat_data, combat_data, spell_data)
        errors = [issue for issue in issues if issue["severity"] == "error"]
        if errors:
            status = "incomplete" if all(issue["code"] in _INCOMPLETE_CODES for issue in errors) else "invalid"
            return self._evaluation(status, issues, trace)
        return {
            "status": "valid",
            "mode": "strict",
            "canonical": canonical,
            "effective": copy.deepcopy(canonical),
            "issues": self._sorted_issues(issues),
            "derivationTrace": trace,
        }

    # ------------------------------------------------------------------
    # Required selections and records
    # ------------------------------------------------------------------
    def _required_selections(self, selections: dict[str, Any], issues: list[dict[str, Any]]) -> None:
        required = (
            ("statblockUse", "/selections/statblockUse"),
            ("raceId", "/selections/raceId"),
            ("classProgression", "/selections/classProgression"),
            ("abilityGeneration", "/selections/abilityGeneration"),
            ("skillGeneration", "/selections/skillGeneration"),
            ("gearProfile", "/selections/gearProfile"),
        )
        for field, path in required:
            value = selections.get(field)
            if field not in selections or value is None or value == "" or value == []:
                self._append_issue(issues, self._issue("npc.selection-required", path, f"{field} is required", "source-rule", "error"))
        ability = selections.get("abilityGeneration")
        if isinstance(ability, dict) and not ability.get("method"):
            self._append_issue(issues, self._issue("npc.selection-required", "/selections/abilityGeneration/method", "ability generation method is required", "source-rule", "error"))
        skills = selections.get("skillGeneration")
        if isinstance(skills, dict) and not skills.get("method"):
            self._append_issue(issues, self._issue("npc.selection-required", "/selections/skillGeneration/method", "skill generation method is required", "source-rule", "error"))
        profile = selections.get("gearProfile")
        if isinstance(profile, dict):
            if not profile.get("experienceProgression", profile.get("progression")):
                self._append_issue(issues, self._issue("npc.selection-required", "/selections/gearProfile/experienceProgression", "experience progression is required", "source-rule", "error"))
            if not profile.get("fantasyLevel"):
                self._append_issue(issues, self._issue("npc.selection-required", "/selections/gearProfile/fantasyLevel", "fantasy level is required", "source-rule", "error"))

    def _progression(self, selections: dict[str, Any], issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for index, raw in enumerate(selections.get("classProgression", [])):
            if not isinstance(raw, dict) or not isinstance(raw.get("classId"), str) or not _is_int(raw.get("levels")):
                continue
            class_id, record = self._selected_record("class", raw["classId"], f"/selections/classProgression/{index}/classId", issues)
            if record is None:
                continue
            output.append({"classId": class_id, "levels": raw["levels"], "record": record, "index": index})
            maximum = self._max_class_level(record)
            if maximum is not None and raw["levels"] > maximum:
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.class-level-unsupported",
                        f"/selections/classProgression/{index}/levels",
                        f"class level {raw['levels']} is above the catalogued maximum {maximum}",
                        "catalog-data",
                        "error",
                        record.get("sourceRef"),
                    ),
                )
            self._record_gap(record, f"/selections/classProgression/{index}/classId", issues)
        ids = [item["classId"] for item in output]
        if len(ids) != len(set(ids)):
            self._append_issue(
                issues,
                self._issue(
                    "npc.class-duplicate",
                    "/selections/classProgression",
                    "each class may appear only once in the ordered progression",
                    "product-constraint",
                    "error",
                ),
            )
        return output

    def _selected_record(self, kind: str, value: Any, path: str, issues: list[dict[str, Any]]) -> tuple[str | None, dict[str, Any] | None]:
        if not isinstance(value, str) or not value:
            return None, None
        try:
            record_id, record = self._resolve(kind, value, path)
        except BoundaryError:
            raise
        self._record_gap(record, path, issues)
        return record_id, record

    def _record_gap(self, record: dict[str, Any] | None, path: str, issues: list[dict[str, Any]]) -> None:
        if not record:
            return
        status = record.get("catalogStatus")
        if status in {"gap", "partial"}:
            gap_code = record.get("gapCode", "catalog-source-gap")
            self._append_issue(
                issues,
                self._issue(
                    "npc.catalog-gap",
                    path,
                    f"catalog record {record.get('id', record.get('name', 'unknown'))} is unavailable: {gap_code}",
                    "catalog-data",
                    "error",
                    record.get("sourceRef"),
                    details={"gapCode": gap_code, "recordId": record.get("id")},
                ),
            )

    def _resolve(self, kind: str, value: str, path: str) -> tuple[str, dict[str, Any]]:
        try:
            return self.catalog.resolve_id(kind, value)
        except CatalogError as exc:
            if "must be" in str(exc):
                raise BoundaryError("selection.type-invalid", str(exc), path) from exc
            raise BoundaryError("catalog.unknown-id", str(exc), path, kind="catalog-data") from exc

    def _record_for(self, kind: str, value: Any) -> dict[str, Any] | None:
        if not isinstance(value, str) or not value:
            return None
        try:
            return self._resolve(kind, value, "")[1]
        except BoundaryError:
            return None

    def _section(self, kind: str) -> dict[str, Any]:
        try:
            return self.catalog.entries(kind)
        except (AttributeError, CatalogError):
            sections = {
                "abilityArray": "abilityArrays",
                "gearBudget": "gearBudgets",
                "race": "races",
                "class": "classes",
                "classFeature": "classFeatures",
                "skill": "skills",
                "feat": "feats",
                "item": "items",
                "spell": "spells",
                "derivedRule": "derivedRules",
            }
            return self.catalog.data[sections[kind]]

    # ------------------------------------------------------------------
    # Races, choices, and languages
    # ------------------------------------------------------------------
    @staticmethod
    def _choice_slot_id(slot: dict[str, Any]) -> str:
        for key in ("slotId", "choiceId", "id", "key"):
            value = slot.get(key)
            if isinstance(value, str) and value:
                return value
        return ""

    @staticmethod
    def _choice_allowed_values(slot: dict[str, Any] | None) -> Any:
        if not isinstance(slot, dict):
            return None
        for key in ("allowedValues", "values", "allowed", "options"):
            if key in slot:
                value = slot[key]
                if isinstance(value, dict):
                    return list(value)
                if isinstance(value, list):
                    return value
        return None

    @staticmethod
    def _choice_value_id(value: Any) -> Any:
        if isinstance(value, dict):
            for key in ("value", "id", "choiceId", "name"):
                if key in value:
                    return value[key]
        return value

    @classmethod
    def _choice_matches(cls, selected: Any, allowed: Any) -> bool:
        if allowed is None:
            return True
        values = allowed if isinstance(allowed, list) else [allowed]
        if isinstance(selected, list):
            return all(cls._choice_matches(item, values) for item in selected)
        selected_key = _canonical_id(selected) if isinstance(selected, str) else selected
        for value in values:
            candidate = cls._choice_value_id(value)
            candidate_key = _canonical_id(candidate) if isinstance(candidate, str) else candidate
            if candidate == selected or (selected_key and candidate_key == selected_key):
                return True
        return False

    @classmethod
    def _choice_cardinality_matches(cls, selected: Any, slot: dict[str, Any]) -> bool:
        values = selected if isinstance(selected, list) else [selected]
        count = len(values)
        exact = slot.get("count")
        minimum = slot.get("minCount")
        maximum = slot.get("maxCount")
        if _is_int(exact):
            minimum = maximum = exact
        if not values:
            return slot.get("required", True) is False and (minimum is None or minimum == 0)
        if any(value is None or value == "" for value in values):
            return False
        identities = [
            _canonical_id(cls._choice_value_id(value))
            if isinstance(cls._choice_value_id(value), str)
            else _canonical_json(cls._choice_value_id(value))
            for value in values
        ]
        if len(identities) != len(set(identities)):
            return False
        if minimum is not None and (not _is_int(minimum) or count < minimum):
            return False
        if maximum is not None and (not _is_int(maximum) or count > maximum):
            return False
        return True

    @classmethod
    def _values_for_generic_choices(cls, allowed: Any) -> list[dict[str, Any]] | None:
        if allowed is None:
            return None
        values = allowed if isinstance(allowed, list) else [allowed]
        output = []
        for value in values:
            choice = cls._choice_value_id(value)
            if not isinstance(choice, (str, int, float, bool)):
                continue
            output.append({"value": choice, "label": _label(choice) if isinstance(choice, str) else str(choice)})
        return output

    @classmethod
    def _slot_is_feat(cls, slot: dict[str, Any]) -> bool:
        kind = str(slot.get("kind", slot.get("category", ""))).casefold()
        feature = str(slot.get("featureId", "")).casefold()
        return kind in {"feat", "feat-slot", "bonus-feat", "general-feat", "general"} or "feat" in feature

    def _race_choice_slots(self, race: dict[str, Any] | None) -> list[dict[str, Any]]:
        if not isinstance(race, dict):
            return []
        raw = None
        for key in ("choiceSlots", "racialChoiceSlots", "choices", "racialChoices"):
            if isinstance(race.get(key), (list, dict)):
                raw = race[key]
                break
        if raw is None:
            return []
        output: list[dict[str, Any]] = []
        if isinstance(raw, list):
            entries = raw
        else:
            entries = []
            for key, value in raw.items():
                if isinstance(value, dict):
                    entry = copy.deepcopy(value)
                    entry.setdefault("choiceId", key)
                    entries.append(entry)
                else:
                    entries.append({"choiceId": key, "allowedValues": value})
        for entry in entries:
            if isinstance(entry, dict) and self._choice_slot_id(entry):
                output.append(copy.deepcopy(entry))
        return output

    def _apply_racial_choices(
        self,
        race: dict[str, Any],
        selections: dict[str, Any],
        issues: list[dict[str, Any]],
    ) -> dict[str, Any]:
        result = copy.deepcopy(race)
        slots = self._race_choice_slots(race)
        selected = selections.get("racialChoices", {})
        if not isinstance(selected, dict):
            selected = {}
        by_id = {self._choice_slot_id(slot): slot for slot in slots}
        refs: list[dict[str, Any]] = []
        for choice_id, value in selected.items():
            slot = by_id.get(choice_id)
            if slot is None:
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.racial-choice-invalid",
                        f"/selections/racialChoices/{choice_id}",
                        "racial choice does not name an available race choice slot",
                        "product-constraint",
                        "error",
                        race.get("sourceRef"),
                    ),
                )
                continue
            refs.extend(_refs(slot.get("sourceRef")))
            if slot.get("catalogStatus") in {"gap", "partial"}:
                self._record_gap(slot, f"/selections/racialChoices/{choice_id}", issues)
            allowed = self._choice_allowed_values(slot)
            if not self._choice_matches(value, allowed) or not self._choice_cardinality_matches(value, slot):
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.racial-choice-invalid",
                        f"/selections/racialChoices/{choice_id}",
                        "racial choice is not allowed by its source slot",
                        "source-rule",
                        "error",
                        slot.get("sourceRef", race.get("sourceRef")),
                    ),
                )
                continue
            options = slot.get("options", slot.get("choiceEffects"))
            if options is None and isinstance(slot.get("allowedValues"), dict):
                options = slot["allowedValues"]
            option_values = value if isinstance(value, list) else [value]
            for option_value in option_values:
                option = self._find_choice_option(options, option_value)
                if option:
                    self._record_gap(option, f"/selections/racialChoices/{choice_id}", issues)
                    refs.extend(_refs(option.get("sourceRef")))
                    self._apply_racial_effects(result, option.get("effects", option), refs)
                elif options is not None:
                    self._append_issue(
                        issues,
                        self._issue(
                            "npc.racial-choice-gap",
                            f"/selections/racialChoices/{choice_id}",
                            f"racial choice {option_value} has no source-backed option record",
                            "catalog-data",
                            "error",
                            slot.get("sourceRef", race.get("sourceRef")),
                        ),
                    )
            # A slot can put its effects directly on the chosen value.
            if isinstance(slot.get("effects"), dict):
                self._apply_racial_effects(result, slot["effects"], refs)
        for choice_id, slot in by_id.items():
            if slot.get("required", True) is True and choice_id not in selected:
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.racial-choice-required",
                        f"/selections/racialChoices/{choice_id}",
                        "choose a value for this racial choice slot",
                        "source-rule",
                        "error",
                        slot.get("sourceRef", race.get("sourceRef")),
                    ),
                )
        if refs:
            result["_npcChoiceRefs"] = _refs(result.get("_npcChoiceRefs"), refs)
        return result

    @staticmethod
    def _find_choice_option(options: Any, selected: Any) -> dict[str, Any] | None:
        if isinstance(options, dict):
            option = options.get(selected)
            if isinstance(option, dict):
                return option
            for key, value in options.items():
                if _canonical_id(key) == _canonical_id(selected) and isinstance(value, dict):
                    return value
            return None
        if isinstance(options, list):
            for option in options:
                if isinstance(option, dict):
                    candidate = option.get("value", option.get("id", option.get("name")))
                    if candidate == selected or _canonical_id(candidate) == _canonical_id(selected):
                        return option
        return None

    @staticmethod
    def _apply_racial_effects(race: dict[str, Any], effects: Any, refs: list[dict[str, Any]]) -> None:
        if not isinstance(effects, dict):
            return
        adjustments = effects.get("abilityAdjustments", effects.get("abilityBonuses"))
        if isinstance(adjustments, dict):
            current = race.get("abilityAdjustments")
            if not isinstance(current, dict):
                current = {}
                race["abilityAdjustments"] = current
            for ability, value in adjustments.items():
                canonical_ability = ability.rsplit(".", 1)[-1].casefold() if isinstance(ability, str) else ability
                if canonical_ability in ABILITY_SET and _is_int(value):
                    current[canonical_ability] = current.get(canonical_ability, 0) + value
        for key in (
            "sizeId", "speed", "senses", "traits", "languages", "sizeModifiers", "saveBonuses",
            "skillBonuses", "skillSelectionsBonus", "bonusSkillSelections", "skillRanksBonus",
            "naturalArmor", "naturalArmorBonus", "ac", "acBonus", "touchAC",
            "flatFootedAC", "initiative", "attackBonus", "damageBonus", "cmb", "cmd", "effects",
        ):
            if key not in effects:
                continue
            value = effects[key]
            if key in {"traits", "senses", "languages"} and isinstance(value, list):
                current = race.get(key)
                if not isinstance(current, list):
                    current = []
                    race[key] = current
                for entry in value:
                    if entry not in current:
                        current.append(copy.deepcopy(entry))
            elif key in {"skillBonuses", "saveBonuses", "effects", "sizeModifiers"} and isinstance(value, dict):
                current = race.get(key)
                if not isinstance(current, dict):
                    current = {}
                    race[key] = current
                for name, number in value.items():
                    if _is_int(number) and _is_int(current.get(name)):
                        current[name] += number
                    else:
                        current[name] = copy.deepcopy(number)
            elif _is_int(value) and _is_int(race.get(key)):
                race[key] += value
            else:
                race[key] = copy.deepcopy(value)
        refs.extend(_refs(effects.get("sourceRef")))

    @classmethod
    def _race_effect_values(cls, race: dict[str, Any] | None, key: str) -> list[Any]:
        """Return values from the explicit, possibly nested, effect wrappers."""
        if not isinstance(race, dict):
            return []
        values: list[Any] = []
        effects = race.get("effects")
        seen: set[int] = set()
        while isinstance(effects, dict) and id(effects) not in seen:
            seen.add(id(effects))
            if key in effects:
                values.append(effects[key])
            effects = effects.get("effects")
        return values

    @classmethod
    def _race_effect_map(cls, race: dict[str, Any] | None) -> dict[str, Any]:
        """Flatten explicit effect wrappers without interpreting other metadata."""
        if not isinstance(race, dict):
            return {}
        output: dict[str, Any] = {}
        effects = race.get("effects")
        seen: set[int] = set()
        while isinstance(effects, dict) and id(effects) not in seen:
            seen.add(id(effects))
            for key, value in effects.items():
                if key != "effects" and key not in output:
                    output[key] = copy.deepcopy(value)
            effects = effects.get("effects")
        return output

    @classmethod
    def _race_effect_value(cls, race: dict[str, Any] | None, key: str) -> Any:
        values = cls._race_effect_values(race, key)
        return values[0] if values else None

    @classmethod
    def _race_value(cls, race: dict[str, Any] | None, key: str) -> Any:
        if not isinstance(race, dict):
            return None
        value = race.get(key)
        if value not in (None, {}, [], ""):
            return value
        nested = cls._race_effect_value(race, key)
        return nested if nested is not None else value

    @classmethod
    def _race_list_value(cls, race: dict[str, Any] | None, key: str) -> list[Any]:
        output: list[Any] = []
        if not isinstance(race, dict):
            return output
        values = [race.get(key), *cls._race_effect_values(race, key)]
        for value in values:
            if isinstance(value, list):
                for entry in value:
                    if entry not in output:
                        output.append(copy.deepcopy(entry))
        return output

    def _languages_for(self, race: dict[str, Any] | None, selections: dict[str, Any], issues: list[dict[str, Any]]) -> list[str]:
        languages: list[str] = []
        if isinstance(race, dict):
            for race_languages in (race.get("languages"), *self._race_effect_values(race, "languages")):
                if isinstance(race_languages, list):
                    languages.extend(value for value in race_languages if isinstance(value, str))
        details = selections.get("details")
        if isinstance(details, dict):
            for key in ("languages", "additionalLanguages"):
                value = details.get(key)
                if value is None:
                    continue
                values = value if isinstance(value, list) else [value]
                if any(not isinstance(item, str) or not item for item in values):
                    self._append_issue(
                        issues,
                        self._issue(
                            "npc.languages-invalid",
                            f"/selections/details/{key}",
                            "languages must be non-empty strings",
                            "source-rule",
                            "error",
                            race.get("sourceRef") if race else None,
                        ),
                    )
                    continue
                languages.extend(values)
        output: list[str] = []
        for language in languages:
            if language not in output:
                output.append(language)
        return output

    # ------------------------------------------------------------------
    # Ability scores and class progression
    # ------------------------------------------------------------------
    def _npc_category(self, progression: list[dict[str, Any]]) -> str:
        return "heroic" if any(item["record"].get("category") == "pc" for item in progression) else "basic"

    def _evaluate_abilities(
        self,
        selections: dict[str, Any],
        progression: list[dict[str, Any]],
        race_id: str | None,
        race: dict[str, Any] | None,
        category: str,
        total_level: int,
        issues: list[dict[str, Any]],
    ) -> dict[str, Any]:
        generation = selections.get("abilityGeneration")
        if not isinstance(generation, dict):
            return {"scores": None, "modifiers": None, "refs": []}
        method = generation.get("method")
        array_id: str | None = None
        array: dict[str, Any] | None = None
        if method == "custom":
            scores = self._custom_ability_scores(generation, issues)
            refs: list[dict[str, Any]] = []
        else:
            array_id = f"npc-ability-array.{category}"
            explicit_array = generation.get("arrayId")
            if isinstance(explicit_array, str):
                array_id = explicit_array
            array_id, array = self._selected_record("abilityArray", array_id, "/selections/abilityGeneration", issues)
            if array is None:
                return {"scores": None, "modifiers": None, "refs": []}
            scores = self._base_ability_scores(array, method, generation, issues)
            raw_scores = array.get("scores")
            raw_available = isinstance(raw_scores, list) and len(raw_scores) == 6 and all(_is_int(value) for value in raw_scores)
            preset_direct = method not in {"assigned", "assigned-array"} and not raw_available and scores is not None
            if not preset_direct:
                self._record_gap(array, "/selections/abilityGeneration", issues)
            refs = _refs(array.get("sourceRef"))
        if scores is None:
            return {"scores": None, "modifiers": None, "refs": refs}
        base_scores = copy.deepcopy(scores)

        if race is None:
            return {"scores": None, "modifiers": None, "refs": refs}
        adjustments: dict[str, Any] = {}
        direct_adjustments = race.get("abilityAdjustments")
        direct_aliases = race.get("abilityBonuses")
        nested_adjustments = self._race_effect_values(race, "abilityAdjustments")
        nested_aliases = self._race_effect_values(race, "abilityBonuses")
        adjustment_candidates = (direct_adjustments, direct_aliases, *nested_adjustments, *nested_aliases)
        for candidate in adjustment_candidates:
            if isinstance(candidate, dict):
                for ability, value in candidate.items():
                    if ability in adjustments and _is_int(adjustments[ability]) and _is_int(value):
                        adjustments[ability] += value
                    else:
                        adjustments[ability] = copy.deepcopy(value)
        if not adjustments and not any(isinstance(candidate, dict) for candidate in adjustment_candidates):
            self._record_gap(race, "/selections/raceId", issues)
            self._append_issue(
                issues,
                self._issue(
                    "npc.race-ability-adjustments-unavailable",
                    "/selections/raceId",
                    "race ability adjustments are not catalogued",
                    "catalog-data",
                    "error",
                    _refs(race.get("sourceRef"), race.get("_npcChoiceRefs"), self._race_effect_value(race, "sourceRef")),
                ),
            )
            return {"scores": None, "modifiers": None, "refs": refs + _refs(race.get("sourceRef"), race.get("_npcChoiceRefs"), self._race_effect_value(race, "sourceRef"))}
        for ability, value in adjustments.items():
            canonical_ability = ability.rsplit(".", 1)[-1].casefold() if isinstance(ability, str) else ability
            if canonical_ability in ABILITY_SET and _is_int(value):
                scores[canonical_ability] += value
            else:
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.race-ability-adjustments-invalid",
                        "/selections/raceId",
                        "race ability adjustments must map known abilities to integers",
                        "catalog-data",
                        "error",
                        _refs(race.get("sourceRef"), race.get("_npcChoiceRefs")),
                    ),
                )
        refs.extend(_refs(race.get("sourceRef"), race.get("_npcChoiceRefs"), self._race_effect_value(race, "sourceRef")))
        racial_scores = copy.deepcopy(scores)

        increase_levels, increase_rule = self._ability_increase_levels(total_level)
        if increase_rule:
            self._record_gap(increase_rule, "/selections/abilityGeneration/levelIncreases", issues)
        if total_level >= 4 and not increase_levels:
            self._append_issue(
                issues,
                self._issue(
                    "npc.level-increase-rule-gap",
                    "/selections/abilityGeneration/levelIncreases",
                    "the source-defined level-increase schedule is unavailable",
                    "catalog-data",
                    "error",
                    self._class_source_refs(progression),
                ),
            )
        nested_increases = generation.get("levelIncreases")
        top_level_increases = selections.get("levelIncreases")
        if nested_increases is not None and top_level_increases is not None and nested_increases != top_level_increases:
            self._append_issue(
                issues,
                self._issue(
                    "npc.level-increase-ambiguous",
                    "/selections/abilityGeneration/levelIncreases",
                    "level increases must be supplied in only one selection location",
                    "product-constraint",
                    "error",
                    increase_rule.get("sourceRef") if increase_rule else None,
                ),
            )
        increases = self._selected_level_increases(selections, generation)
        unexpected_increases = sorted(set(increases) - set(increase_levels))
        if unexpected_increases:
            self._append_issue(
                issues,
                self._issue(
                    "npc.level-increase-invalid",
                    "/selections/abilityGeneration/levelIncreases",
                    f"no source-defined ability increase slot exists at level {unexpected_increases[0]}",
                    "source-rule",
                    "error",
                    increase_rule.get("sourceRef") if increase_rule else self._class_source_refs(progression),
                ),
            )
        applied_increases: dict[int, tuple[str, int]] = {}
        if increase_levels:
            refs.extend(_refs(increase_rule.get("sourceRef") if increase_rule else None))
        for level in increase_levels:
            ability = increases.get(level)
            if ability is None:
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.level-increase-required",
                        f"/selections/abilityGeneration/levelIncreases/{level}",
                        f"choose one ability for the level {level} increase",
                        "source-rule",
                        "error",
                        increase_rule.get("sourceRef") if increase_rule else None,
                    ),
                )
                continue
            amount = increase_rule.get("amount") if increase_rule else None
            if not _is_int(amount) or amount <= 0:
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.level-increase-amount-gap",
                        "/selections/abilityGeneration/levelIncreases",
                        "the level-increase amount is not a positive source-backed integer",
                        "catalog-data",
                        "error",
                        increase_rule.get("sourceRef") if increase_rule else None,
                    ),
                )
                continue
            scores[ability] += amount
            applied_increases[level] = (ability, amount)

        modifiers = {ability: _ability_modifier(score) for ability, score in scores.items()}
        return {
            "scores": scores,
            "baseScores": base_scores,
            "racialScores": racial_scores,
            "modifiers": modifiers,
            "increases": applied_increases,
            "refs": refs,
            "arrayId": array_id,
            "traceInputs": [
                {"source": "custom ability scores" if method == "custom" else "NPC ability array", "value": copy.deepcopy(base_scores), "sourceRefs": _refs(array.get("sourceRef") if array else None)},
                {"source": "racial adjustments", "value": copy.deepcopy(racial_scores), "sourceRefs": _refs(race.get("sourceRef"), race.get("_npcChoiceRefs"))},
                {"source": "level increases", "value": copy.deepcopy(applied_increases), "sourceRefs": _refs(increase_rule.get("sourceRef") if increase_rule else None)},
            ],
        }

    def _custom_ability_scores(self, generation: dict[str, Any], issues: list[dict[str, Any]]) -> dict[str, int] | None:
        supplied = generation.get("scores", generation.get("assignments"))
        if not isinstance(supplied, dict) or set(supplied) != ABILITY_SET or any(not _is_int(value) for value in supplied.values()):
            self._append_issue(
                issues,
                self._issue(
                    "npc.ability-selection-required",
                    "/selections/abilityGeneration/scores",
                    "custom ability generation requires one integer score for each ability",
                    "source-rule",
                    "error",
                ),
            )
            return None
        if not isinstance(generation.get("rationale"), str) or not generation.get("rationale").strip():
            self._append_issue(
                issues,
                self._issue(
                    "npc.custom-ability-rationale-required",
                    "/selections/abilityGeneration/rationale",
                    "custom ability scores require an explanatory rationale",
                    "source-rule",
                    "error",
                ),
            )
        return {ability: supplied[ability] for ability in ABILITY_NAMES}

    @staticmethod
    def _preset_name(method: Any, generation: dict[str, Any]) -> str | None:
        explicit = generation.get("preset", generation.get("role"))
        if isinstance(explicit, str) and explicit.casefold() in ABILITY_PRESET_NAMES:
            return explicit.casefold()
        if isinstance(method, str):
            lowered = method.casefold()
            if lowered in ABILITY_PRESET_NAMES:
                return lowered
            if lowered.endswith("-preset") and lowered.removesuffix("-preset") in ABILITY_PRESET_NAMES:
                return lowered.removesuffix("-preset")
        return None

    def _base_ability_scores(self, array: dict[str, Any], method: Any, generation: dict[str, Any], issues: list[dict[str, Any]]) -> dict[str, int] | None:
        raw_scores = array.get("scores")
        raw_available = isinstance(raw_scores, list) and len(raw_scores) == 6 and all(_is_int(value) for value in raw_scores)
        preset_name = self._preset_name(method, generation)
        presets = array.get("presets") if isinstance(array.get("presets"), dict) else {}
        preset = presets.get(preset_name) if preset_name else None
        if preset is None and preset_name:
            preset = array.get(f"{preset_name}Preset")
        if isinstance(preset, dict) and isinstance(preset.get("scores"), dict):
            preset = {**preset, **preset["scores"]}
        if not raw_available:
            if preset_name and isinstance(preset, dict) and all(
                ability in preset and _is_int(preset[ability]) for ability in ABILITY_NAMES
            ):
                return {ability: preset[ability] for ability in ABILITY_NAMES}
            self._append_issue(
                issues,
                self._issue(
                    "npc.ability-array-unavailable",
                    "/selections/abilityGeneration",
                    "selected NPC ability array has no source-backed scores",
                    "catalog-data",
                    "error",
                    array.get("sourceRef"),
                ),
            )
            return None
        if "abilityOrder" in array and (not isinstance(array.get("abilityOrder"), list) or len(array["abilityOrder"]) != 6 or set(array["abilityOrder"]) != ABILITY_SET):
            self._append_issue(
                issues,
                self._issue(
                    "npc.ability-array-order-invalid",
                    "/selections/abilityGeneration",
                    "ability array order must name each ability exactly once",
                    "catalog-data",
                    "error",
                    array.get("sourceRef"),
                ),
            )
            return None
        order = array.get("abilityOrder") if isinstance(array.get("abilityOrder"), list) else list(ABILITY_NAMES)
        if method in {"assigned", "assigned-array"}:
            supplied = generation.get("scores", generation.get("assignments"))
            if isinstance(supplied, list):
                supplied = dict(zip(order, supplied))
            if not isinstance(supplied, dict) or set(supplied) != ABILITY_SET or any(not _is_int(value) for value in supplied.values()):
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.ability-selection-required",
                        "/selections/abilityGeneration/scores",
                        "assigned-array requires one integer score for each ability",
                        "source-rule",
                        "error",
                        array.get("sourceRef"),
                    ),
                )
                return None
            if sorted(supplied.values()) != sorted(raw_scores):
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.ability-array-mismatch",
                        "/selections/abilityGeneration/scores",
                        "assigned scores must use every source array value exactly once",
                        "source-rule",
                        "error",
                        array.get("sourceRef"),
                    ),
                )
                return None
            return {ability: supplied[ability] for ability in ABILITY_NAMES}
        if preset_name:
            if isinstance(preset, dict):
                if all(ability in preset and _is_int(preset[ability]) for ability in ABILITY_NAMES):
                    return {ability: preset[ability] for ability in ABILITY_NAMES}
                preset_scores = preset.get("scores")
                if isinstance(preset_scores, list) and len(preset_scores) == 6 and all(_is_int(value) for value in preset_scores):
                    preset_order = preset.get("order", order)
                    if isinstance(preset_order, list) and len(preset_order) == 6 and set(preset_order) == ABILITY_SET:
                        return dict(zip(preset_order, preset_scores))
                preset_order = preset.get("order")
                if isinstance(preset_order, list) and len(preset_order) == 6 and set(preset_order) == ABILITY_SET:
                    return dict(zip(preset_order, raw_scores))
            elif isinstance(preset, list) and len(preset) == 6 and all(_is_int(value) for value in preset):
                return dict(zip(order, preset))
            orders = array.get("presetOrders") if isinstance(array.get("presetOrders"), dict) else {}
            if not orders and isinstance(array.get("abilityOrders"), dict):
                orders = array["abilityOrders"]
            preset_order = orders.get(preset_name) or array.get(f"{preset_name}Order") or array.get("presetOrder")
            if isinstance(preset_order, list) and len(preset_order) == 6 and set(preset_order) == ABILITY_SET:
                return dict(zip(preset_order, raw_scores))
            self._append_issue(
                issues,
                self._issue(
                    "npc.ability-preset-unavailable",
                    "/selections/abilityGeneration/method",
                    f"the selected {preset_name} ability preset has no source-backed assignment",
                    "catalog-data",
                    "error",
                    array.get("sourceRef"),
                ),
            )
            return None
        self._append_issue(
            issues,
            self._issue(
                "npc.ability-method-invalid",
                "/selections/abilityGeneration/method",
                "ability generation method is not source-supported",
                "source-rule",
                "error",
                array.get("sourceRef"),
            ),
        )
        return None

    def _selected_level_increases(self, selections: dict[str, Any], generation: dict[str, Any]) -> dict[int, str]:
        raw = generation.get("levelIncreases", selections.get("levelIncreases"))
        if raw is None:
            raw = selections.get("levelIncreases")
        output: dict[int, str] = {}
        if isinstance(raw, dict):
            for level, ability in raw.items():
                if str(level).isdigit() and ability in ABILITY_SET:
                    output[int(level)] = ability
        elif isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict) and _is_int(item.get("level")) and item.get("ability") in ABILITY_SET:
                    output[item["level"]] = item["ability"]
        return output

    def _ability_increase_levels(self, total_level: int) -> tuple[list[int], dict[str, Any] | None]:
        rule = self._find_rule(("ability-increase", "level-increase", "ability-score-increase"))
        if rule and rule.get("catalogStatus") in {"gap", "partial"}:
            return [], rule
        if rule:
            if isinstance(rule.get("levels"), list):
                levels = rule["levels"]
                if any(not _is_int(level) or level < 1 for level in levels) or levels != sorted(set(levels)):
                    return [], rule
                return [level for level in levels if level <= total_level], rule
            interval = rule.get("interval")
            first = rule.get("firstLevel", rule.get("first", interval))
            if _is_int(interval) and interval > 0 and _is_int(first) and first >= 1:
                return list(range(first, total_level + 1, interval)), rule
        # No level-4 row is exposed by the current source-bounded catalog. Do
        # not synthesize a numeric schedule. For levels below four there is no
        # increase slot to require.
        return [], rule

    def _evaluate_classes(
        self,
        progression: list[dict[str, Any]],
        total_level: int,
        abilities: dict[str, Any],
        issues: list[dict[str, Any]],
    ) -> dict[str, Any]:
        bab = 0
        saves = {"fortitude": 0, "reflex": 0, "will": 0}
        hit_dice = 0
        dice_parts: list[str] = []
        hp_base: float | int | None = 0
        features: list[dict[str, Any]] = []
        rows: list[dict[str, Any]] = []
        level_inputs: list[dict[str, Any]] = []
        bab_inputs: list[dict[str, Any]] = []
        save_inputs: dict[str, list[dict[str, Any]]] = {"fortitude": [], "reflex": [], "will": []}
        hit_die_inputs: list[dict[str, Any]] = []
        hp_inputs: list[dict[str, Any]] = []
        for index, item in enumerate(progression):
            record = item["record"]
            level = item["levels"]
            row = self._class_level(record, level)
            if row is None:
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.class-level-unavailable",
                        f"/selections/classProgression/{index}/levels",
                        f"{record.get('name', 'class')} has no source-backed level {level} row",
                        "catalog-data",
                        "error",
                        record.get("sourceRef"),
                    ),
                )
                continue
            rows.append({"progression": item, "row": row})
            row_refs = _refs(row.get("sourceRef", record.get("sourceRef")))
            level_inputs.append({"source": f"{record.get('name', item['classId'])} {level}", "value": level, "sourceRefs": row_refs})
            self._record_gap(row, f"/selections/classProgression/{index}/levels", issues)
            for field in ("bab", "fortitude", "reflex", "will"): 
                if self._class_numeric(row, field) is None:
                    self._append_issue(
                        issues,
                        self._issue(
                            "npc.class-derived-value-gap",
                            f"/selections/classProgression/{index}/levels",
                            f"{record.get('name', 'class')} level {level} has no source-backed {field}",
                            "catalog-data",
                            "error",
                            row.get("sourceRef", record.get("sourceRef")),
                        ),
                    )
            row_bab = self._class_numeric(row, "bab")
            row_saves = {save: self._class_numeric(row, save) for save in save_inputs}
            if row_bab is not None:
                bab += row_bab
                bab_inputs.append({"source": f"{record.get('name', item['classId'])} {level} BAB", "value": row_bab, "sourceRefs": row_refs})
            for save, value in row_saves.items():
                if value is not None:
                    saves[save] += value
                    save_inputs[save].append({"source": f"{record.get('name', item['classId'])} {level} {save}", "value": value, "sourceRefs": row_refs})
            hit_die = row.get("hitDie") or record.get("hitDie")
            if isinstance(hit_die, str):
                parsed = _parse_die(hit_die)
                if parsed:
                    count, sides = parsed
                    hit_dice += level * count
                    expression = f"{level * count}{'d' + str(sides)}"
                    dice_parts.append(expression)
                    hit_die_inputs.append({"source": f"{record.get('name', item['classId'])} Hit Dice", "value": expression, "sourceRefs": row_refs})
                else:
                    self._append_issue(
                        issues,
                        self._issue(
                            "npc.hit-die-invalid",
                            f"/selections/classProgression/{index}/levels",
                            f"{record.get('name', 'class')} has an invalid hit die expression",
                            "catalog-data",
                            "error",
                            row.get("sourceRef", record.get("sourceRef")),
                        ),
                    )
            else:
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.hit-die-gap",
                        f"/selections/classProgression/{index}/levels",
                        f"{record.get('name', 'class')} has no source-backed hit die",
                        "catalog-data",
                        "error",
                        row.get("sourceRef", record.get("sourceRef")),
                    ),
                )
            if _is_int(row.get("averageHp")) or isinstance(row.get("averageHp"), float):
                if hp_base is not None:
                    hp_base += row["averageHp"]
                hp_inputs.append({"source": f"{record.get('name', item['classId'])} average HP", "value": row["averageHp"], "sourceRefs": row_refs})
            elif _is_int(row.get("hp")) or isinstance(row.get("hp"), float):
                if hp_base is not None:
                    hp_base += row["hp"]
                hp_inputs.append({"source": f"{record.get('name', item['classId'])} HP", "value": row["hp"], "sourceRefs": row_refs})
            elif isinstance(row.get("averageHpPerLevel"), (int, float)) and not isinstance(row.get("averageHpPerLevel"), bool):
                if hp_base is not None:
                    hp_base += row["averageHpPerLevel"] * level
                hp_inputs.append({"source": f"{record.get('name', item['classId'])} average HP/level", "value": row["averageHpPerLevel"] * level, "sourceRefs": row_refs})
            elif isinstance(hit_die, str) and _parse_die(hit_die):
                # This is only used when the source supplies an explicit
                # average policy below.  The default policy itself is never
                # silently assumed.
                hp_base = None
            for feature_level in range(1, level + 1):
                feature_row = self._class_level(record, feature_level)
                if feature_row is None:
                    self._append_issue(
                        issues,
                        self._issue(
                            "npc.class-level-unavailable",
                            f"/selections/classProgression/{index}/levels",
                            f"{record.get('name', 'class')} has no source-backed level {feature_level} row",
                            "catalog-data",
                            "error",
                            record.get("sourceRef"),
                        ),
                    )
                    continue
                feature_row_refs = _refs(feature_row.get("sourceRef", record.get("sourceRef")))
                self._record_gap(feature_row, f"/selections/classProgression/{index}/levels", issues)
                if feature_row.get("featureGrants") is None:
                    self._append_issue(
                        issues,
                        self._issue(
                            "npc.class-feature-gap",
                            f"/selections/classProgression/{index}/levels",
                            f"{record.get('name', 'class')} level {feature_level} has no source-backed feature grants",
                            "catalog-data",
                            "error",
                            feature_row_refs,
                        ),
                    )
                if feature_row.get("choiceSlots") is None:
                    self._append_issue(
                        issues,
                        self._issue(
                            "npc.class-choice-slot-gap",
                            f"/selections/classProgression/{index}/levels",
                            f"{record.get('name', 'class')} level {feature_level} has no source-backed class choice-slot data",
                            "catalog-data",
                            "error",
                            feature_row_refs,
                        ),
                    )
                for feature in feature_row.get("featureGrants") or []:
                    if isinstance(feature, dict):
                        self._record_gap(feature, f"/selections/classProgression/{index}/levels", issues)
                    if isinstance(feature, str):
                        feature_record = self._record_for("classFeature", feature)
                        if feature_record is not None:
                            self._record_gap(feature_record, f"/selections/classProgression/{index}/levels", issues)
                        else:
                            self._append_issue(
                                issues,
                                self._issue(
                                    "npc.class-feature-gap",
                                    f"/selections/classProgression/{index}/levels",
                                    f"class feature {feature} has no source-backed catalog record",
                                    "catalog-data",
                                    "error",
                                    feature_row.get("sourceRef", record.get("sourceRef")),
                                ),
                            )
                    features.append(
                        self._feature_value(
                            feature,
                            feature_row,
                            {
                                **item,
                                "levels": feature_level,
                                "globalLevel": sum(previous["levels"] for previous in progression[:index]) + feature_level,
                            },
                        )
                    )

        hp = self._average_hp(
            hp_base,
            progression,
            total_level,
            rows,
            (abilities.get("modifiers") or {}).get("constitution"),
            issues,
        )
        hit_expression = "+".join(dice_parts) if dice_parts else None
        return {
            "bab": bab if rows else None,
            "saves": saves if rows and all(_is_int(value) for value in saves.values()) else None,
            "hitDice": hit_dice if rows and hit_dice else None,
            "hitDiceExpression": hit_expression,
            "hp": hp,
            "features": features,
            "rows": rows,
            "refs": _refs(
                *(item["record"].get("sourceRef") for item in progression),
                *(row["row"].get("sourceRef") for row in rows),
                *(feature.get("sourceRefs") for feature in features if isinstance(feature, dict)),
                (self._find_rule(("average-hp", "hit-points", "hp-average", "hit-point-policy")) or {}).get("sourceRef"),
            ),
            "traceInputs": {
                "level": level_inputs,
                "bab": bab_inputs,
                "saves": save_inputs,
                "hitDice": hit_die_inputs,
                "hp": hp_inputs,
            },
        }

    def _average_hp(
        self,
        base: float | int | None,
        progression: list[dict[str, Any]],
        total_level: int,
        rows: list[dict[str, Any]],
        constitution_modifier: int | None,
        issues: list[dict[str, Any]],
    ) -> int | None:
        if not rows:
            return None
        rule = self._find_rule(("average-hp", "hit-points", "hp-average", "hit-point-policy"))
        if rule:
            self._record_gap(rule, "/selections/classProgression", issues)
            if rule.get("catalogStatus") in {"gap", "partial"}:
                return None
        if base is None:
            if rule is None:
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.hp-policy-gap",
                        "/selections/classProgression",
                        "average HP requires a source-backed HP policy",
                        "catalog-data",
                        "error",
                        _refs(*(row["row"].get("sourceRef") for row in rows)),
                    ),
                )
                return None
            base = 0
            first_level_max = bool(rule.get("firstLevelMax", rule.get("maximumFirstHitDie", False)))
            first_hit_die = True
            for item in progression:
                die = item["record"].get("hitDie")
                row = self._class_level(item["record"], item["levels"])
                die = (row or {}).get("hitDie") or die
                parsed = _parse_die(die)
                if not parsed:
                    return None
                count, sides = parsed
                average = (sides + 1) / 2
                hit_dice_for_class = item["levels"] * count
                if first_level_max and first_hit_die and hit_dice_for_class:
                    base += count * sides
                    hit_dice_for_class -= count
                    first_hit_die = False
                base += hit_dice_for_class * average
        if rule is None:
            if _is_int(base) and all(
                _is_int(row["row"].get("averageHp")) or _is_int(row["row"].get("hp"))
                for row in rows
            ):
                return int(base)
            self._append_issue(
                issues,
                self._issue(
                    "npc.hp-policy-gap",
                    "/selections/classProgression",
                    "average HP rounding policy is not catalogued",
                    "catalog-data",
                    "error",
                    _refs(*(row["row"].get("sourceRef") for row in rows)),
                ),
            )
            return None
        con_policy = rule.get("constitutionPerLevel", rule.get("conModifierPerLevel"))
        if con_policy is None or not (isinstance(con_policy, bool) or _is_int(con_policy)):
            self._append_issue(
                issues,
                self._issue(
                    "npc.hp-constitution-policy-gap",
                    "/selections/classProgression",
                    "average HP Constitution policy is not source-backed",
                    "catalog-data",
                    "error",
                    rule.get("sourceRef"),
                ),
            )
            return None
        if constitution_modifier is not None:
            if con_policy is True:
                base += constitution_modifier * total_level
            elif _is_int(con_policy):
                base += constitution_modifier * total_level * con_policy
        rounding = rule.get("rounding", rule.get("round"))
        if not isinstance(rounding, str):
            self._append_issue(
                issues,
                self._issue(
                    "npc.hp-rounding-gap",
                    "/selections/classProgression",
                    "average HP rounding policy is not source-backed",
                    "catalog-data",
                    "error",
                    rule.get("sourceRef"),
                ),
            )
            return None
        value = float(base)
        if rounding in {"ceil", "up"}:
            return math.ceil(value)
        if rounding in {"nearest", "half-up"}:
            return math.floor(value + 0.5)
        if rounding in {"exact", "fractional"} and value.is_integer():
            return int(value)
        if rounding in {"floor", "down"}:
            return math.floor(value)
        self._append_issue(
            issues,
            self._issue(
                "npc.hp-rounding-invalid",
                "/selections/classProgression",
                f"unsupported average HP rounding policy: {rounding}",
                "catalog-data",
                "error",
                rule.get("sourceRef"),
            ),
        )
        return None

    @staticmethod
    def _class_numeric(row: dict[str, Any], field: str) -> int | None:
        value = row.get(field)
        if _is_int(value):
            return value
        if field == "bab" and _is_int(row.get("baseAttackBonus")):
            return row["baseAttackBonus"]
        saves = row.get("saves")
        if field in {"fortitude", "reflex", "will"} and isinstance(saves, dict) and _is_int(saves.get(field)):
            return saves[field]
        return None

    def _class_level(self, record: dict[str, Any], level: int) -> dict[str, Any] | None:
        levels = record.get("levels")
        if not isinstance(levels, dict):
            return None
        row = levels.get(str(level), levels.get(level))
        return row if isinstance(row, dict) else None

    def _feature_value(self, feature: Any, row: dict[str, Any], progression: dict[str, Any]) -> dict[str, Any]:
        if isinstance(feature, dict):
            value = copy.deepcopy(feature)
        else:
            feature_record = self._record_for("classFeature", feature)
            if feature_record:
                value = {
                    "featureId": feature_record.get("id", feature),
                    "name": feature_record.get("name", _label(feature)),
                    "effects": copy.deepcopy(feature_record.get("effects")),
                }
                value["sourceRefs"] = _refs(feature_record.get("sourceRef"))
            else:
                value = {"featureId": feature, "name": _label(feature)}
        if isinstance(value, dict):
            value.setdefault("featureId", value.get("id", feature if isinstance(feature, str) else None))
            value.setdefault("name", value.get("label", _label(value.get("featureId", "feature"))))
        value.setdefault("sourceRefs", _refs(value.get("sourceRef"), row.get("sourceRef"), progression["record"].get("sourceRef")))
        value["acquiredAtLevel"] = progression.get("globalLevel", progression["levels"])
        return value

    def _validate_class_feature_choices(
        self,
        selections: dict[str, Any],
        progression: list[dict[str, Any]],
        issues: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        choices = selections.get("classFeatureChoices", {})
        if not isinstance(choices, dict):
            return []
        slots: list[dict[str, Any]] = []
        offset = 0
        for item in progression:
            for raw_slot in self._choice_slots_for_class(item["record"], item["levels"]):
                if self._slot_is_feat(raw_slot):
                    continue
                slot = copy.deepcopy(raw_slot)
                class_level = slot.get("classLevel", slot.get("level"))
                if not _is_int(class_level):
                    class_level = item["levels"]
                slot["globalLevel"] = offset + class_level
                slots.append(slot)
            offset += item["levels"]
        by_id = {
            self._choice_slot_id(slot): slot
            for slot in slots
            if self._choice_slot_id(slot)
        }
        selected_features: list[dict[str, Any]] = []
        for slot in slots:
            if slot.get("catalogStatus") in {"gap", "partial"}:
                self._record_gap(slot, f"/selections/classFeatureChoices/{self._choice_slot_id(slot)}", issues)
        for slot_id, value in choices.items():
            slot = by_id.get(slot_id)
            if slot is None:
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.class-feature-choice-invalid",
                        f"/selections/classFeatureChoices/{slot_id}",
                        "class feature choice does not name an available slot",
                        "product-constraint",
                        "error",
                    ),
                )
                continue
            allowed = self._choice_allowed_values(slot)
            if not self._choice_matches(value, allowed) or not self._choice_cardinality_matches(value, slot):
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.class-feature-choice-invalid",
                        f"/selections/classFeatureChoices/{slot_id}",
                        "class feature choice is not allowed by its source slot",
                        "source-rule",
                        "error",
                        slot.get("sourceRef"),
                    ),
                )
            option_values = value if isinstance(value, list) else [value]
            options = slot.get("options", slot.get("choiceEffects"))
            if options is None and isinstance(slot.get("allowedValues"), dict):
                options = slot["allowedValues"]
            for option_value in option_values:
                option = self._find_choice_option(options, option_value)
                if option is None:
                    option_record = self._record_for("classFeature", option_value)
                    if option_record is not None:
                        self._record_gap(option_record, f"/selections/classFeatureChoices/{slot_id}", issues)
                        option = option_record
                    else:
                        self._append_issue(
                            issues,
                            self._issue(
                                "npc.class-feature-choice-gap",
                                f"/selections/classFeatureChoices/{slot_id}",
                                f"class feature choice {option_value} has no source-backed option record",
                                "catalog-data",
                                "error",
                                slot.get("sourceRef"),
                            ),
                        )
                if option:
                    self._record_gap(option, f"/selections/classFeatureChoices/{slot_id}", issues)
                    feature = copy.deepcopy(option.get("feature", option.get("featureGrant", option)))
                    if isinstance(feature, str):
                        feature_record = self._record_for("classFeature", feature)
                        if feature_record is not None:
                            self._record_gap(feature_record, f"/selections/classFeatureChoices/{slot_id}", issues)
                            feature = copy.deepcopy(feature_record)
                        else:
                            self._append_issue(
                                issues,
                                self._issue(
                                    "npc.class-feature-choice-gap",
                                    f"/selections/classFeatureChoices/{slot_id}",
                                    f"class feature {feature} has no source-backed record",
                                    "catalog-data",
                                    "error",
                                    option.get("sourceRef", slot.get("sourceRef")),
                                ),
                            )
                            feature = {"featureId": feature}
                    if isinstance(feature, dict):
                        self._record_gap(feature, f"/selections/classFeatureChoices/{slot_id}", issues)
                        if "effects" not in feature and "featureId" not in feature and "id" not in feature and any(key in feature for key in ("ac", "acBonus", "attackBonus", "damageBonus", "cmb", "cmd", "initiative", "hp", "hitPoints", "skillBonuses", "saveBonus", "saveBonuses", "abilityBonuses")):
                            feature = {"effects": feature}
                        feature.setdefault("featureId", option.get("id", option_value))
                        feature.setdefault("name", option.get("name", _label(option_value)))
                        feature.setdefault("sourceRefs", _refs(option.get("sourceRef"), slot.get("sourceRef")))
                        if "effects" in option and "effects" not in feature:
                            feature["effects"] = copy.deepcopy(option["effects"])
                        if isinstance(slot.get("effects"), dict):
                            if not isinstance(feature.get("effects"), dict):
                                feature["effects"] = {}
                            for effect_key, effect_value in slot["effects"].items():
                                if _is_int(effect_value) and _is_int(feature["effects"].get(effect_key)):
                                    feature["effects"][effect_key] += effect_value
                                elif effect_key not in feature["effects"]:
                                    feature["effects"][effect_key] = copy.deepcopy(effect_value)
                        feature["choiceSlotId"] = slot_id
                        feature["acquiredAtLevel"] = slot.get("globalLevel", slot.get("classLevel", 0))
                        selected_features.append(feature)
        for slot_id, slot in by_id.items():
            if slot.get("required", True) is True and slot_id not in choices:
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.class-feature-choice-required",
                        f"/selections/classFeatureChoices/{slot_id}",
                        "choose a value for this class feature slot",
                        "source-rule",
                        "error",
                        slot.get("sourceRef"),
                    ),
                )
        return selected_features

    # ------------------------------------------------------------------
    # Skills
    # ------------------------------------------------------------------
    def _evaluate_skills(
        self,
        selections: dict[str, Any],
        progression: list[dict[str, Any]],
        total_level: int,
        abilities: dict[str, Any],
        race: dict[str, Any] | None,
        gear: dict[str, Any],
        classes: dict[str, Any],
        issues: list[dict[str, Any]],
    ) -> dict[str, Any]:
        generation = selections.get("skillGeneration")
        if not isinstance(generation, dict):
            return {"ranks": {}, "totals": {}, "refs": []}
        method = generation.get("method")
        ability_modifiers = abilities.get("modifiers") or {}
        class_skills = self._class_skill_ids(progression)
        human_bonus = self._human_skill_bonus(race)
        ranks: dict[str, int] = {}
        selected_values = generation.get("skills", generation.get("selectedSkills", []))
        if isinstance(selected_values, list):
            selected_values = [self._canonical_skill_id(value) for value in selected_values]
        if any(not isinstance(item["record"].get("classSkills", item["record"].get("classSkillIds")), list) for item in progression):
            self._append_issue(
                issues,
                self._issue(
                    "npc.class-skill-list-gap",
                    "/selections/skillGeneration",
                    "one or more selected classes have no source-backed class-skill list",
                    "catalog-data",
                    "error",
                    self._class_source_refs(progression),
                ),
            )
        if any(
            isinstance(item["record"].get("classSkills", item["record"].get("classSkillIds")), list)
            and any(self._skill_record(value) == {} for value in item["record"].get("classSkills", item["record"].get("classSkillIds")) if isinstance(value, str))
            for item in progression
        ):
            self._append_issue(
                issues,
                self._issue(
                    "npc.class-skill-list-gap",
                    "/selections/skillGeneration",
                    "one or more class skill lists reference skills absent from the catalog",
                    "catalog-data",
                    "error",
                    self._class_source_refs(progression),
                ),
            )
        if method == "simplified":
            if len(progression) >= 3:
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.simplified-skills-multiclass",
                        "/selections/skillGeneration/method",
                        "simplified skills are only supported for one or two classes; use precise ranks",
                        "product-constraint",
                        "error",
                        self._class_source_refs(progression),
                    ),
                )
            expected = self._simplified_skill_count(progression, selections, abilities)
            if expected is None:
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.skill-budget-gap",
                        "/selections/skillGeneration",
                        "simplified skill selections are not source-backed for the selected class progression",
                        "catalog-data",
                        "error",
                        self._class_source_refs(progression),
                    ),
                )
            elif not isinstance(selected_values, list) or len(selected_values) != expected or len(set(selected_values)) != len(selected_values):
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.skill-selection-required",
                        "/selections/skillGeneration/skills",
                        f"simplified skills require exactly {expected} distinct selected skill(s)",
                        "source-rule",
                        "error",
                        self._class_source_refs(progression),
                    ),
                )
            else:
                if len(progression) == 1:
                    rank_value = progression[0]["levels"]
                    for skill_id in selected_values:
                        if class_skills and skill_id not in class_skills:
                            self._append_issue(
                                issues,
                                self._issue(
                                    "npc.non-class-skill",
                                    "/selections/skillGeneration/skills",
                                    f"selected skill {skill_id} is not a class skill",
                                    "source-rule",
                                    "warning",
                                    self._skill_record(skill_id).get("sourceRef"),
                                ),
                            )
                        ranks[skill_id] = rank_value
                elif len(progression) == 2:
                    counts = [self._class_skill_count(item, ability_modifiers, human_bonus) for item in progression]
                    low = min(counts)
                    high_index = 0 if counts[0] >= counts[1] else 1
                    for index, skill_id in enumerate(selected_values):
                        if class_skills and skill_id not in class_skills:
                            self._append_issue(
                                issues,
                                self._issue(
                                    "npc.non-class-skill",
                                    "/selections/skillGeneration/skills",
                                    f"selected skill {skill_id} is not a class skill",
                                    "source-rule",
                                    "warning",
                                    self._skill_record(skill_id).get("sourceRef"),
                                ),
                            )
                        ranks[skill_id] = total_level if index < low else progression[high_index]["levels"]
        elif method == "precise":
            raw_ranks = generation.get("ranks", {})
            ranks = {
                self._canonical_skill_id(skill_id): value
                for skill_id, value in raw_ranks.items()
                if _is_int(value)
            }
            if len(ranks) != len(raw_ranks):
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.skill-rank-duplicate",
                        "/selections/skillGeneration/ranks",
                        "precise skill ranks must not name one skill more than once",
                        "source-rule",
                        "error",
                        self._class_source_refs(progression),
                    ),
                )
            budget = self._precise_skill_budget(progression, selections, abilities, race)
            selected_total = sum(ranks.values())
            if budget is None:
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.skill-budget-gap",
                        "/selections/skillGeneration/ranks",
                        "precise skill ranks are not source-backed for the selected class progression",
                        "catalog-data",
                        "error",
                        self._class_source_refs(progression),
                    ),
                )
            elif selected_total > budget:
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.skill-budget-exceeded",
                        "/selections/skillGeneration/ranks",
                        f"selected skill ranks {selected_total} exceed the source budget {budget}",
                        "source-rule",
                        "error",
                        self._class_source_refs(progression),
                    ),
                )
            if any(value > total_level for value in ranks.values()):
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.skill-rank-limit",
                        "/selections/skillGeneration/ranks",
                        "skill ranks cannot exceed total Hit Dice",
                        "source-rule",
                        "error",
                        self._class_source_refs(progression),
                    ),
                )
        class_skill_bonus = self._class_skill_bonus(progression)
        class_skill_bonus_rule = self._find_rule(("class-skill-bonus", "class skill bonus"))
        if class_skills and class_skill_bonus == 0 and class_skill_bonus_rule is not None:
            self._record_gap(class_skill_bonus_rule, "/selections/skillGeneration", issues)
        if class_skills and class_skill_bonus == 0 and not self._class_skill_bonus_is_backed(progression):
            self._append_issue(
                issues,
                self._issue(
                    "npc.class-skill-bonus-gap",
                    "/selections/skillGeneration",
                    "class-skill bonus is not source-backed",
                    "catalog-data",
                    "error",
                    self._class_source_refs(progression),
                ),
            )
        int_modifier = ability_modifiers.get("intelligence")
        if int_modifier is not None:
            for item in progression:
                count = self._unclamped_class_skill_count(item, int_modifier, human_bonus)
                minimum = item["record"].get("minimumSkillSelections")
                if not _is_int(minimum):
                    minimum = (self._class_level(item["record"], item["levels"]) or {}).get("minimumSkillSelections")
                if count is not None and count < 0 and not _is_int(minimum):
                    self._append_issue(
                        issues,
                        self._issue(
                            "npc.negative-intelligence-policy-gap",
                            "/selections/skillGeneration",
                            "the minimum skill-selection rule for negative Intelligence is not catalogued",
                            "catalog-data",
                            "error",
                            item["record"].get("sourceRef"),
                        ),
                    )
        armor_penalty = gear.get("armorCheckPenalty", 0)
        totals: dict[str, int] = {}
        trace_inputs: list[dict[str, Any]] = []
        refs = self._class_source_refs(progression)
        refs.extend(_refs(*(self._skill_record(skill_id).get("sourceRef") for skill_id in ranks)))
        refs.extend(_refs(gear.get("refs"), race.get("sourceRef") if race else None))
        for skill_id, rank in ranks.items():
            record = self._skill_record(skill_id)
            key_ability = record.get("keyAbility")
            if isinstance(key_ability, str):
                key_ability = key_ability.rsplit(".", 1)[-1].casefold()
            if not isinstance(key_ability, str) or key_ability not in ABILITY_SET:
                self._record_gap(record, f"/selections/skillGeneration/{'ranks' if method == 'precise' else 'skills'}", issues)
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.skill-key-ability-gap",
                        f"/selections/skillGeneration/{'ranks' if method == 'precise' else 'skills'}/{skill_id}",
                        f"skill {record.get('name', skill_id)} has no source-backed key ability",
                        "catalog-data",
                        "error",
                        record.get("sourceRef"),
                    ),
                )
                continue
            components = [{"source": "skill ranks", "value": rank, "sourceRefs": _refs(record.get("sourceRef"))}]
            key_modifier = ability_modifiers.get(key_ability, 0)
            value = rank + key_modifier
            components.append({"source": f"{key_ability} modifier", "value": key_modifier, "sourceRefs": _refs(record.get("sourceRef"), abilities.get("refs"))})
            if skill_id in class_skills and rank > 0:
                value += class_skill_bonus
                components.append({"source": "class skill bonus", "value": class_skill_bonus, "sourceRefs": self._class_source_refs(progression)})
            if record.get("armorCheckPenalty") is True:
                value += armor_penalty
                components.append({"source": "armor check penalty", "value": armor_penalty, "sourceRefs": gear.get("refs", [])})
            item_bonus = gear.get("skillBonuses", {}).get(skill_id, 0)
            value += item_bonus
            if item_bonus:
                components.append({"source": "equipped item skill bonus", "value": item_bonus, "sourceRefs": gear.get("refs", [])})
            race_bonus = self._race_skill_bonus(race, skill_id)
            value += race_bonus
            if race_bonus:
                components.append({"source": "racial skill bonus", "value": race_bonus, "sourceRefs": _refs(race.get("sourceRef"), race.get("_npcChoiceRefs"), self._race_effect_value(race, "sourceRef")) if race else []})
            totals[skill_id.removeprefix("skill.")] = value
            trace_inputs.append({"source": skill_id, "value": value, "components": components, "sourceRefs": _refs(record.get("sourceRef"), gear.get("refs"), race.get("sourceRef") if race else None)})
        return {"ranks": ranks, "totals": totals, "refs": refs, "classSkills": class_skills, "traceInputs": trace_inputs}

    def _simplified_skill_count(
        self,
        progression: list[dict[str, Any]],
        selections: dict[str, Any],
        abilities: dict[str, Any] | None = None,
    ) -> int | None:
        if not progression or len(progression) > 2:
            return None
        int_modifier = 0
        if abilities and isinstance(abilities.get("modifiers"), dict):
            int_modifier = abilities["modifiers"].get("intelligence", 0)
        else:
            generation = selections.get("abilityGeneration", {})
            scores = generation.get("scores") if isinstance(generation, dict) else None
            if isinstance(scores, dict) and _is_int(scores.get("intelligence")):
                int_modifier = _ability_modifier(scores["intelligence"])
        human_bonus = self._human_skill_bonus_for_selection(selections)
        if len(progression) == 1:
            count = self._class_skill_count(progression[0], {"intelligence": int_modifier}, human_bonus)
            return None if count is None else max(0, count)
        counts = [self._class_skill_count(item, {"intelligence": int_modifier}, human_bonus) for item in progression]
        if any(count is None for count in counts):
            return None
        return max(counts)

    def _unclamped_class_skill_count(self, item: dict[str, Any], int_modifier: int, human_bonus: int) -> int | None:
        record = item["record"]
        raw = record.get("skillSelections")
        if raw is None:
            row = self._class_level(record, item["levels"])
            raw = (row or {}).get("skillSelections")
        if not _is_int(raw):
            return None
        return raw + int_modifier + human_bonus

    def _class_skill_count(self, item: dict[str, Any], modifiers: dict[str, int], human_bonus: int) -> int | None:
        count = self._unclamped_class_skill_count(item, modifiers.get("intelligence", 0), human_bonus)
        if count is None:
            return None
        minimum = item["record"].get("minimumSkillSelections")
        if not _is_int(minimum):
            row = self._class_level(item["record"], item["levels"])
            minimum = (row or {}).get("minimumSkillSelections")
        if _is_int(minimum):
            return max(minimum, count)
        return max(0, count)

    def _precise_skill_budget(
        self,
        progression: list[dict[str, Any]],
        selections: dict[str, Any],
        abilities: dict[str, Any] | None,
        race: dict[str, Any] | None = None,
    ) -> int | None:
        if not progression:
            return 0
        if abilities and isinstance(abilities.get("modifiers"), dict):
            int_modifier = abilities["modifiers"].get("intelligence", 0)
        else:
            int_modifier = 0
            generation = selections.get("abilityGeneration")
            scores = generation.get("scores") if isinstance(generation, dict) else None
            if isinstance(scores, dict) and _is_int(scores.get("intelligence")):
                int_modifier = _ability_modifier(scores["intelligence"])
        human_bonus = self._human_skill_bonus(race if race is not None else self._record_for("race", selections.get("raceId")))
        total = 0
        for item in progression:
            count = self._class_skill_count(item, {"intelligence": int_modifier}, human_bonus)
            if count is None:
                return None
            total += count * item["levels"]
        return total

    def _class_skill_ids(self, progression: list[dict[str, Any]]) -> set[str]:
        output: set[str] = set()
        for item in progression:
            values = item["record"].get("classSkills", item["record"].get("classSkillIds"))
            if isinstance(values, list):
                output.update(self._canonical_skill_id(value) for value in values if isinstance(value, str))
        return output

    def _class_skill_bonus(self, progression: list[dict[str, Any]]) -> int:
        values = []
        for item in progression:
            record = item["record"]
            values.append(record.get("classSkillBonus"))
            for level in range(1, item["levels"] + 1):
                row = self._class_level(record, level)
                if isinstance(row, dict):
                    values.append(row.get("classSkillBonus"))
        values = [value for value in values if _is_int(value)]
        if values:
            return max(values)
        rule = self._find_rule(("class-skill-bonus", "class skill bonus"))
        if rule and rule.get("catalogStatus") not in {"gap", "partial"}:
            value = rule.get("value", rule.get("bonus"))
            if _is_int(value):
                return value
        return 0

    def _class_skill_bonus_is_backed(self, progression: list[dict[str, Any]]) -> bool:
        for item in progression:
            record = item["record"]
            if _is_int(record.get("classSkillBonus")):
                return True
            for level in range(1, item["levels"] + 1):
                row = self._class_level(record, level)
                if isinstance(row, dict) and _is_int(row.get("classSkillBonus")):
                    return True
        rule = self._find_rule(("class-skill-bonus", "class skill bonus"))
        return bool(rule and rule.get("catalogStatus") not in {"gap", "partial"} and _is_int(rule.get("value", rule.get("bonus"))))

    @classmethod
    def _race_skill_bonus(cls, race: dict[str, Any] | None, skill_id: str) -> int:
        if not isinstance(race, dict):
            return 0
        target = _canonical_id(skill_id)
        total = 0
        for bonus_map in (race.get("skillBonuses"), *cls._race_effect_values(race, "skillBonuses")):
            if not isinstance(bonus_map, dict):
                continue
            for candidate, value in bonus_map.items():
                if isinstance(candidate, str) and _canonical_id(candidate) == target and _is_int(value):
                    total += value
        return total

    def _human_skill_bonus(self, race: dict[str, Any] | None) -> int:
        if not race:
            return 0
        total = 0
        found = False
        for key in ("skillSelectionsBonus", "bonusSkillSelections", "skillRanksBonus"):
            for value in (race.get(key), *self._race_effect_values(race, key)):
                if _is_int(value):
                    total += value
                    found = True
        return total if found else 0

    def _human_skill_bonus_for_selection(self, selections: dict[str, Any]) -> int:
        race = self._record_for("race", selections.get("raceId"))
        if race is not None and selections.get("racialChoices"):
            previous_keys = getattr(self, "_issue_keys", None)
            self._issue_keys = set()
            try:
                race = self._apply_racial_choices(race, selections, [])
            finally:
                if previous_keys is None:
                    del self._issue_keys
                else:
                    self._issue_keys = previous_keys
        return self._human_skill_bonus(race)

    def _skill_record(self, skill_id: str) -> dict[str, Any]:
        try:
            return self._resolve("skill", skill_id, "")[1]
        except BoundaryError:
            return {}

    def _canonical_skill_id(self, skill_id: Any) -> str:
        if not isinstance(skill_id, str):
            return str(skill_id)
        record = self._skill_record(skill_id)
        if record:
            return str(record.get("id", skill_id))
        return f"skill.{skill_id.rsplit('.', 1)[-1].casefold()}"

    def _skill_ids(self) -> set[str]:
        return {record.get("id", key) for key, record in self._section("skill").items() if isinstance(record, dict)}

    # ------------------------------------------------------------------
    # Feats and typed prerequisites
    # ------------------------------------------------------------------
    def _evaluate_feats(
        self,
        selections: dict[str, Any],
        progression: list[dict[str, Any]],
        total_level: int,
        abilities: dict[str, Any],
        skills: dict[str, Any],
        classes: dict[str, Any],
        race_id: str | None,
        issues: list[dict[str, Any]],
    ) -> dict[str, Any]:
        slots = self._all_feat_slots(total_level, progression)
        general_slots = self._general_feat_slots(total_level, progression)
        feat_rule = self._find_rule(("general-feat", "feat-slots", "general-feat-slots"))
        if feat_rule:
            self._record_gap(feat_rule, "/selections/feats", issues)
        if total_level > 0 and not general_slots and feat_rule is None:
            self._append_issue(
                issues,
                self._issue(
                    "npc.feat-slot-rule-gap",
                    "/selections/feats",
                    "the source-defined general feat slot progression is unavailable",
                    "catalog-data",
                    "error",
                    self._class_source_refs(progression),
                ),
            )
        if feat_rule and total_level > 0 and not general_slots and feat_rule.get("catalogStatus") not in {"gap", "partial"}:
            self._append_issue(
                issues,
                self._issue(
                    "npc.feat-slot-rule-invalid",
                    "/selections/feats",
                    "the source-defined general feat slot progression is malformed",
                    "catalog-data",
                    "error",
                    feat_rule.get("sourceRef"),
                ),
            )
        selected = selections.get("feats", [])
        if not isinstance(selected, list):
            selected = []
        by_slot = {item.get("slotId"): item for item in selected if isinstance(item, dict)}
        slot_ids = [item.get("slotId") for item in selected if isinstance(item, dict)]
        if len(slot_ids) != len(set(slot_ids)):
            self._append_issue(
                issues,
                self._issue(
                    "npc.feat-slot-duplicate",
                    "/selections/feats",
                    "each feat slot may be selected only once",
                    "product-constraint",
                    "error",
                ),
            )
        output: list[dict[str, Any]] = []
        seen_feats: set[str] = set()
        feat_records: dict[str, dict[str, Any]] = {}
        valid_slot_ids = {slot.get("slotId") for slot in slots}
        for slot_id in slot_ids:
            if slot_id not in valid_slot_ids:
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.feat-slot-invalid",
                        f"/selections/feats/{slot_id}",
                        "selected feat slot is not granted by the source-backed progression",
                        "source-rule",
                        "error",
                        self._class_source_refs(progression),
                    ),
                )
        class_feature_values = [
            feature
            for feature in classes.get("features", [])
            if isinstance(feature, dict)
        ]
        for slot in slots:
            slot_id = slot["slotId"]
            if slot.get("catalogStatus") in {"gap", "partial"}:
                self._record_gap(slot, f"/selections/feats/{slot_id}", issues)
            item = by_slot.get(slot_id)
            if item is not None and slot.get("automatic"):
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.feat-slot-automatic",
                        f"/selections/feats/{slot_id}/featId",
                        "an automatic feat slot cannot be replaced by a draft selection",
                        "source-rule",
                        "error",
                        slot.get("sourceRef"),
                    ),
                )
            if item is None:
                if slot.get("automatic"): 
                    automatic_feat_id = slot.get("featId", slot.get("value"))
                    if not isinstance(automatic_feat_id, str) or not automatic_feat_id:
                        self._append_issue(
                            issues,
                            self._issue(
                                "npc.feat-gap",
                                f"/selections/feats/{slot_id}/featId",
                                "automatic feat slot has no source-backed feat ID",
                                "catalog-data",
                                "error",
                                slot.get("sourceRef"),
                            ),
                        )
                        continue
                    feat = self._record_for("feat", automatic_feat_id)
                    if feat is None:
                        self._append_issue(
                            issues,
                            self._issue(
                                "npc.feat-gap",
                                f"/selections/feats/{slot_id}/featId",
                                f"automatic feat {automatic_feat_id} has no source-backed catalog record",
                                "catalog-data",
                                "error",
                                slot.get("sourceRef"),
                            ),
                        )
                    else:
                        feat_id = feat.get("id", automatic_feat_id)
                        self._record_gap(feat, f"/selections/feats/{slot_id}/featId", issues)
                        if feat_id in seen_feats and not feat.get("allowMultiple"):
                            self._append_issue(
                                issues,
                                self._issue(
                                    "npc.feat-duplicate",
                                    f"/selections/feats/{slot_id}/featId",
                                    "the same feat cannot be selected twice",
                                    "source-rule",
                                    "error",
                                    feat.get("sourceRef"),
                                ),
                            )
                        output.append({
                            "slotId": slot_id,
                            "featId": feat_id,
                            "name": feat.get("name", _label(feat_id)),
                            "grantedAtLevel": slot["grantedAtLevel"],
                            "kind": slot.get("kind", "feat"),
                            "automatic": True,
                            "effects": copy.deepcopy(feat.get("effects")),
                            "sourceRefs": _refs(feat.get("sourceRef"), slot.get("sourceRef")),
                        })
                        if feat_id:
                            seen_feats.add(feat_id)
                            feat_records[feat_id] = feat
                    continue
                if slot.get("required", True) is False:
                    continue
                label = "general feat" if self._slot_is_general(slot) else "class feat"
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.feat-slot-required",
                        f"/selections/feats/{slot_id}/featId",
                        f"choose a {label} for the level {slot['grantedAtLevel']} slot",
                        "source-rule",
                        "error",
                        slot.get("sourceRef"),
                    ),
                )
                continue
            feat_id, feat = self._selected_record("feat", item.get("featId"), f"/selections/feats/{slot_id}/featId", issues)
            if feat is None:
                continue
            if feat_id in seen_feats and not feat.get("allowMultiple"):
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.feat-duplicate",
                        f"/selections/feats/{slot_id}/featId",
                        "the same feat cannot be selected twice",
                        "source-rule",
                        "error",
                        feat.get("sourceRef"),
                    ),
                )
            exclusive = feat.get("exclusiveWith", feat.get("mutuallyExclusiveWith", feat.get("mutuallyExclusive")))
            exclusive_ids = exclusive if isinstance(exclusive, list) else [exclusive]
            prior_ids = set(seen_feats)
            for prior_id, prior_record in feat_records.items():
                prior_exclusive = prior_record.get("exclusiveWith", prior_record.get("mutuallyExclusiveWith", prior_record.get("mutuallyExclusive")))
                prior_values = prior_exclusive if isinstance(prior_exclusive, list) else [prior_exclusive]
                if any(_canonical_id(value) == _canonical_id(feat_id) for value in prior_values if isinstance(value, str)):
                    exclusive_ids.append(prior_id)
            if any(isinstance(value, str) and _canonical_id(value) in {_canonical_id(item) for item in prior_ids} for value in exclusive_ids):
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.feat-mutually-exclusive",
                        f"/selections/feats/{slot_id}/featId",
                        "selected feat conflicts with an earlier feat selection",
                        "source-rule",
                        "error",
                        feat.get("sourceRef"),
                    ),
                )
            seen_feats.add(feat_id or "")
            if feat_id:
                feat_records[feat_id] = feat
            allowed_feat_ids = slot.get("allowedFeatIds")
            if not isinstance(allowed_feat_ids, list):
                allowed_feat_ids = self._choice_allowed_values(slot) or []
            allowed_canonical_ids = {
                _canonical_id(self._choice_value_id(value))
                for value in allowed_feat_ids
                if isinstance(self._choice_value_id(value), str)
            }
            if allowed_canonical_ids and _canonical_id(feat_id) not in allowed_canonical_ids:
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.feat-not-allowed",
                        f"/selections/feats/{slot_id}/featId",
                        "selected feat is not allowed in this feat slot",
                        "source-rule",
                        "error",
                        feat.get("sourceRef"),
                    ),
                )
            allowed_categories = slot.get("allowedCategories")
            if not isinstance(allowed_categories, list):
                allowed_categories = ["general"] if self._slot_is_general(slot) else []
            if allowed_categories and feat.get("category") not in {None, *allowed_categories}:
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.feat-category-invalid",
                        f"/selections/feats/{slot_id}/featId",
                        "selected feat category is not allowed in this feat slot",
                        "source-rule",
                        "error",
                        feat.get("sourceRef"),
                    ),
                )
            class_features = {
                feature.get("featureId", feature.get("id"))
                for feature in class_feature_values
                if not _is_int(feature.get("acquiredAtLevel"))
                or feature.get("acquiredAtLevel") <= slot["grantedAtLevel"]
            }
            context = self._prerequisite_context(
                level=slot["grantedAtLevel"],
                progression=progression,
                abilities=abilities,
                skills=skills,
                race_id=race_id,
                alignment=selections.get("details", {}).get("alignment") if isinstance(selections.get("details"), dict) else None,
                previous_feats={entry["featId"] for entry in output},
                class_features=class_features,
                caster_level=self._caster_level_at_level(progression, slot["grantedAtLevel"]),
            )
            prerequisite = feat.get("prerequisites")
            result = evaluate_prerequisite(prerequisite, **context)
            if result is None:
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.feat-prerequisite-unresolved",
                        f"/selections/feats/{slot_id}/featId",
                        "feat prerequisite cannot be evaluated from the available source data",
                        "catalog-data",
                        "error",
                        feat.get("sourceRef"),
                    ),
                )
            elif not result:
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.feat-prerequisite-failed",
                        f"/selections/feats/{slot_id}/featId",
                        "feat prerequisites are not satisfied at acquisition level",
                        "source-rule",
                        "error",
                        feat.get("sourceRef"),
                    ),
                )
            output.append({
                "slotId": slot_id,
                "featId": feat_id,
                "name": feat.get("name", _label(feat_id)),
                "kind": slot.get("kind", "general"),
                "classId": slot.get("classId"),
                "grantedAtLevel": slot["grantedAtLevel"],
                "effects": copy.deepcopy(feat.get("effects")),
                "sourceRefs": _refs(feat.get("sourceRef"), slot.get("sourceRef")),
            })
        expected_slots = {slot["slotId"] for slot in slots if not slot.get("automatic")}
        extras = set(by_slot) - expected_slots
        if extras:
            self._append_issue(
                issues,
                self._issue(
                    "npc.feat-slot-invalid",
                    "/selections/feats",
                    f"feat selections name unknown slot {sorted(extras)[0]}",
                    "product-constraint",
                    "error",
                ),
            )
        return {"slots": slots, "selected": output, "refs": _refs(*(item.get("sourceRefs") for item in output), *(slot.get("sourceRef") for slot in slots))}

    def _general_feat_slots(
        self,
        total_level: int,
        progression: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        rule = self._find_rule(("general-feat", "feat-slots", "general-feat-slots"))
        if not rule and progression:
            slots: list[dict[str, Any]] = []
            for item in progression:
                for slot in self._choice_slots_for_class(item["record"], item["levels"]):
                    if self._slot_is_general(slot):
                        level = slot.get("grantedAtLevel", slot.get("level", item["levels"]))
                        if _is_int(level) and level <= total_level:
                            slots.append({
                                "slotId": str(slot.get("slotId", slot.get("id", f"general-{level}"))),
                                "kind": "general",
                                "grantedAtLevel": level,
                                "allowedFeatIds": copy.deepcopy(slot.get("allowedFeatIds", slot.get("allowedValues", slot.get("values", [])))),
                                "allowedCategories": copy.deepcopy(slot.get("allowedCategories")),
                                "required": slot.get("required", True),
                                "sourceRef": slot.get("sourceRef", item["record"].get("sourceRef")),
                            })
            return sorted(slots, key=lambda value: (value["grantedAtLevel"], value["slotId"]))
        if not rule or rule.get("catalogStatus") in {"gap", "partial"}:
            return []
        values = rule.get("levels")
        if not isinstance(values, list):
            first = rule.get("firstLevel")
            interval = rule.get("interval")
            if _is_int(first) and _is_int(interval) and first >= 1 and interval > 0:
                values = list(range(first, total_level + 1, interval))
        if not isinstance(values, list) or any(not _is_int(level) or level < 1 for level in values) or values != sorted(set(values)):
            return []
        allowed = rule.get("allowedFeatIds", rule.get("allowedValues", rule.get("values", [])))
        return [
            {
                "slotId": f"general-{level}",
                "kind": "general",
                "grantedAtLevel": level,
                "allowedFeatIds": copy.deepcopy(allowed) if isinstance(allowed, list) else [],
                "allowedCategories": copy.deepcopy(rule.get("allowedCategories")),
                "required": rule.get("required", True),
                "sourceRef": rule.get("sourceRef"),
            }
            for level in values
            if _is_int(level) and 1 <= level <= total_level
        ]

    def _prerequisite_context(self, *, level, progression, abilities, skills, race_id, alignment, previous_feats, class_features, caster_level=None):
        class_levels = {}
        remaining = level
        for item in progression:
            taken = min(item["levels"], max(0, remaining))
            class_levels[item["classId"]] = taken
            remaining -= taken
        score_map = self._scores_at_level(abilities, progression, level)
        bab = self._bab_at_level(progression, level)
        return {
            "ability_scores": score_map,
            "ability_modifiers": {ability: _ability_modifier(value) for ability, value in score_map.items()} if score_map else None,
            "bab": bab,
            "character_level": level,
            "class_levels": class_levels,
            "skill_ranks": self._skill_ranks_at_level(skills, level),
            "race_id": race_id,
            "alignment": alignment,
            "feats": previous_feats,
            "class_features": class_features,
            "caster_level": caster_level,
        }

    @staticmethod
    def _skill_ranks_at_level(skills: dict[str, Any], level: int) -> dict[str, int]:
        ranks = skills.get("ranks") or {}
        return {
            skill_id: min(rank, level)
            for skill_id, rank in ranks.items()
            if isinstance(skill_id, str) and _is_int(rank) and rank >= 0
        }

    def _caster_level_at_level(self, progression: list[dict[str, Any]], level: int) -> int | None:
        remaining = level
        values: list[int] = []
        for item in progression:
            taken = min(item["levels"], max(0, remaining))
            if taken <= 0:
                continue
            spec = next((value for value in self._spellcasting_specs([{**item, "levels": taken}]) if value.get("classId") == item["classId"]), None)
            if spec is not None:
                caster_level = self._spell_caster_level(spec)
                if caster_level is not None:
                    values.append(caster_level)
            remaining -= taken
            if remaining <= 0:
                break
        return values[0] if len(values) == 1 else None

    def _scores_at_level(self, abilities: dict[str, Any], progression: list[dict[str, Any]], level: int) -> dict[str, int]:
        scores = copy.deepcopy(abilities.get("scores") or {})
        # The final score map already includes all selected increases. Reverse
        # increases not yet acquired so feat checks observe the acquisition row.
        for increase_level, value in (abilities.get("increases") or {}).items():
            if _is_int(increase_level) and increase_level > level:
                ability, amount = value
                if ability in scores:
                    scores[ability] -= amount
        return scores

    def _bab_at_level(self, progression: list[dict[str, Any]], level: int) -> int | None:
        value = 0
        any_row = False
        remaining = level
        for item in progression:
            take = min(item["levels"], remaining)
            if take <= 0:
                continue
            row = self._class_level(item["record"], take)
            if row is None or self._class_numeric(row, "bab") is None:
                return None
            value += self._class_numeric(row, "bab")
            any_row = True
            remaining -= take
        return value if any_row else None

    # ------------------------------------------------------------------
    # Gear and item effects
    # ------------------------------------------------------------------
    @staticmethod
    def _pricing_record(record: dict[str, Any]) -> dict[str, Any]:
        pricing = record.get("pricing")
        return pricing if isinstance(pricing, dict) else {}

    @staticmethod
    def _pricing_int(records: list[dict[str, Any]], keys: tuple[str, ...]) -> int | None:
        for record in records:
            for key in keys:
                value = record.get(key)
                if _is_int(value) and value >= 0:
                    return value
        return None

    def _property_definition(self, record: dict[str, Any], property_id: str) -> dict[str, Any] | None:
        containers = [record]
        pricing = record.get("pricing")
        if isinstance(pricing, dict):
            containers.append(pricing)
        for container in containers:
            values = container.get("properties")
            if isinstance(values, dict):
                value = values.get(property_id)
                if isinstance(value, dict):
                    return value
                for key, candidate in values.items():
                    if _canonical_id(key) == _canonical_id(property_id) and isinstance(candidate, dict):
                        return candidate
            if isinstance(values, list):
                for value in values:
                    if not isinstance(value, dict):
                        continue
                    candidate = value.get("id", value.get("propertyId", value.get("name")))
                    if _canonical_id(candidate) == _canonical_id(property_id):
                        return value
        return None

    def _item_instance_effects(self, record: dict[str, Any], selected: dict[str, Any], effects: dict[str, Any]) -> list[dict[str, Any]]:
        refs: list[dict[str, Any]] = []
        enhancement = selected.get("enhancementBonus")
        if _is_int(enhancement):
            effects["enhancementBonus"] = enhancement
        if selected.get("masterwork") is True:
            for source in (record, self._pricing_record(record)):
                if not isinstance(source, dict):
                    continue
                masterwork_effects = None
                for key in ("masterworkEffects", "effectsMasterwork", "masterworkEffect"):
                    candidate = source.get(key)
                    if isinstance(candidate, dict):
                        masterwork_effects = candidate
                        break
                if not isinstance(masterwork_effects, dict):
                    continue
                refs.extend(_refs(source.get("sourceRef")))
                for key, value in masterwork_effects.items():
                    if _is_int(value) and _is_int(effects.get(key)):
                        effects[key] += value
                    elif key not in effects:
                        effects[key] = copy.deepcopy(value)
                break
        property_ids = selected.get("properties", selected.get("propertyIds", []))
        if isinstance(property_ids, list):
            for property_id in property_ids:
                definition = self._property_definition(record, property_id)
                if not definition:
                    continue
                refs.extend(_refs(definition.get("sourceRef")))
                property_effects = definition.get("effects", definition.get("effect"))
                if isinstance(property_effects, dict):
                    for key, value in property_effects.items():
                        if _is_int(value) and _is_int(effects.get(key)):
                            effects[key] += value
                        elif isinstance(value, dict) and isinstance(effects.get(key), dict):
                            for nested_key, nested_value in value.items():
                                if _is_int(nested_value) and _is_int(effects[key].get(nested_key)):
                                    effects[key][nested_key] += nested_value
                                elif nested_key not in effects[key]:
                                    effects[key][nested_key] = copy.deepcopy(nested_value)
                        elif key not in effects:
                            effects[key] = copy.deepcopy(value)
        charges = selected.get("charges")
        if _is_int(charges):
            for source in (record, self._pricing_record(record)):
                if not isinstance(source, dict):
                    continue
                source_refs = source.get("sourceRef")
                table_applied = False
                for key in ("effectsByCharges", "effectsByChargeCount", "chargeEffects"):
                    table = source.get(key)
                    if not isinstance(table, dict):
                        continue
                    charge_effects = table.get(str(charges), table.get(charges))
                    if not isinstance(charge_effects, dict):
                        continue
                    refs.extend(_refs(source_refs))
                    for effect_key, value in charge_effects.items():
                        if _is_int(value) and _is_int(effects.get(effect_key)):
                            effects[effect_key] += value
                        elif effect_key not in effects:
                            effects[effect_key] = copy.deepcopy(value)
                    table_applied = True
                    break
                if table_applied:
                    break
                per_charge_applied = False
                for key in ("effectsPerCharge", "chargeEffectsPerUnit"):
                    per_charge = source.get(key)
                    if not isinstance(per_charge, dict):
                        continue
                    refs.extend(_refs(source_refs))
                    for effect_key, value in per_charge.items():
                        if _is_int(value):
                            effects[effect_key] = effects.get(effect_key, 0) + value * charges
                    per_charge_applied = True
                    break
                if per_charge_applied:
                    break
        return refs

    def _item_instance_price(self, record: dict[str, Any], selected: dict[str, Any]) -> tuple[int | None, list[dict[str, Any]]]:
        pricing = self._pricing_record(record)
        pricing_records = [pricing, record]
        refs = _refs(record.get("sourceRef"), pricing.get("sourceRef"))
        base = self._pricing_int(pricing_records, ("basePriceCp", "baseCostCp", "priceCp", "costCp"))
        if base is None:
            base = record.get("priceCp") if _is_int(record.get("priceCp")) and record.get("priceCp") >= 0 else None
        if base is None:
            return None, refs
        total = base
        if selected.get("masterwork") is True:
            masterwork = self._pricing_int(pricing_records, ("masterworkCostCp", "masterworkAdditionCp", "masterworkPriceCp", "masterworkCp"))
            if masterwork is None:
                return None, refs
            total += masterwork
        enhancement = selected.get("enhancementBonus", 0)
        if _is_int(enhancement) and enhancement > 0:
            enhancement_cost = None
            for source in pricing_records:
                for key in ("enhancementCostByBonusCp", "enhancementPriceByBonusCp", "priceByEnhancementBonusCp", "priceByEnhancement"):
                    table = source.get(key)
                    if isinstance(table, dict):
                        value = table.get(str(enhancement), table.get(enhancement))
                        if _is_int(value) and value >= 0:
                            enhancement_cost = value
                            break
                if enhancement_cost is not None:
                    break
            if enhancement_cost is None:
                per_bonus = self._pricing_int(pricing_records, ("enhancementCostCpPerBonus", "enhancementPriceCpPerBonus"))
                if per_bonus is not None:
                    enhancement_cost = per_bonus * enhancement
            if enhancement_cost is None:
                enhancement_cost = self._pricing_int(pricing_records, ("enhancementCostCp", "enhancementPriceCp"))
            if enhancement_cost is None:
                return None, refs
            total += enhancement_cost
        charges = selected.get("charges")
        if charges is not None:
            charge_priced = False
            charge_capacity = None
            for source in pricing_records:
                if not isinstance(source, dict):
                    continue
                for key in ("maxCharges", "chargeCapacity", "chargesCapacity"):
                    if _is_int(source.get(key)) and source[key] >= 0:
                        charge_capacity = source[key]
                        break
                for key in ("priceByChargesCp", "priceByChargeCountCp", "chargePricesCp"):
                    table = source.get(key)
                    if isinstance(table, dict):
                        value = table.get(str(charges), table.get(charges))
                        if _is_int(value) and value >= 0:
                            total = value
                            charge_priced = True
                            break
                if charge_priced:
                    break
                unit = self._pricing_int([source], ("pricePerChargeCp", "costPerChargeCp", "chargePriceCp", "chargeCostCp"))
                if unit is not None:
                    total += unit * charges
                    charge_priced = True
                    break
                if source.get("chargesIncluded") is True or source.get("priceIncludesCharges") is True:
                    charge_priced = True
                    break
            if charge_capacity is not None and charges > charge_capacity:
                return None, refs
            if not charge_priced:
                return None, refs
        property_ids = selected.get("properties", selected.get("propertyIds", []))
        if isinstance(property_ids, list):
            for property_id in property_ids:
                property_cost = None
                for source in pricing_records:
                    for key in ("propertyPricesCp", "propertyCostByIdCp", "propertyPriceByIdCp", "propertyCostsCp"):
                        table = source.get(key)
                        if isinstance(table, dict):
                            value = table.get(property_id)
                            if value is None:
                                for candidate, candidate_value in table.items():
                                    if _canonical_id(candidate) == _canonical_id(property_id):
                                        value = candidate_value
                                        break
                            if _is_int(value) and value >= 0:
                                property_cost = value
                                break
                    if property_cost is not None:
                        break
                definition = self._property_definition(record, property_id)
                if definition:
                    refs.extend(_refs(definition.get("sourceRef")))
                if property_cost is None and definition:
                    property_cost = self._pricing_int([definition], ("priceCp", "costCp", "price", "cost"))
                if property_cost is None:
                    return None, refs
                total += property_cost
        return total, refs

    def _evaluate_gear(
        self,
        selections: dict[str, Any],
        issues: list[dict[str, Any]],
        *,
        total_level: int | None = None,
    ) -> dict[str, Any]:
        profile = selections.get("gearProfile")
        budget_record = self._gear_budget_for(profile, total_level=total_level)
        if budget_record is None:
            candidate_refs = []
            if isinstance(profile, dict):
                requested_id = profile.get("gearBudgetId")
                requested_record = self._record_for("gearBudget", requested_id) if isinstance(requested_id, str) else None
                progression = profile.get("experienceProgression", profile.get("progression"))
                fantasy = profile.get("fantasyLevel")
                candidate_refs = _refs(
                    requested_record.get("sourceRef") if requested_record else None,
                    *(record.get("sourceRef") for record in self._section("gearBudget").values()
                      if isinstance(record, dict) and record.get("progression") == progression and record.get("fantasyLevel") == fantasy)
                )
            self._append_issue(
                issues,
                self._issue(
                    "npc.gear-budget-unavailable",
                    "/selections/gearProfile",
                    "selected gear profile has no source-backed budget row or level boundary",
                    "catalog-data",
                    "error",
                    candidate_refs,
                ),
            )
        elif budget_record.get("catalogStatus") in {"gap", "partial"}:
            self._record_gap(budget_record, "/selections/gearProfile", issues)
        if budget_record is not None:
            if not _is_int(budget_record.get("budgetCp")) or budget_record.get("budgetCp", 0) < 0:
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.gear-budget-gap",
                        "/selections/gearProfile",
                        "selected gear profile has no source-backed non-negative copper budget",
                        "catalog-data",
                        "error",
                        budget_record.get("sourceRef"),
                    ),
                )
            if not isinstance(budget_record.get("categories"), dict):
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.gear-category-gap",
                        "/selections/gearProfile",
                        "selected gear profile has no source-backed category budget map",
                        "catalog-data",
                        "error",
                        budget_record.get("sourceRef"),
                    ),
                )
            elif any(not _is_int(value) or value < 0 for value in budget_record["categories"].values()):
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.gear-category-gap",
                        "/selections/gearProfile",
                        "selected gear profile has incomplete or invalid category budget values",
                        "catalog-data",
                        "error",
                        budget_record.get("sourceRef"),
                    ),
                )
        items: list[dict[str, Any]] = []
        spent = 0
        category_spent: dict[str, int] = {}
        ability_bonuses: dict[str, int] = {}
        skill_bonuses: dict[str, int] = {}
        armor_check_penalty = 0
        armor_count = 0
        shield_count = 0
        weapon_count = 0
        for index, selected in enumerate(selections.get("gear", [])):
            item_id, record = self._selected_record("item", selected.get("itemId"), f"/selections/gear/{index}/itemId", issues)
            if record is None:
                continue
            quantity = selected.get("quantity", 1)
            property_ids = selected.get("properties", selected.get("propertyIds", []))
            if isinstance(property_ids, list):
                for property_id in property_ids:
                    definition = self._property_definition(record, property_id)
                    if definition is not None:
                        self._record_gap(definition, f"/selections/gear/{index}/itemId", issues)
                    else:
                        self._append_issue(
                            issues,
                            self._issue(
                                "npc.item-property-gap",
                                f"/selections/gear/{index}/itemId",
                                f"{record.get('name', item_id)} has no source-backed property {property_id}",
                                "catalog-data",
                                "error",
                                record.get("sourceRef"),
                            ),
                        )
            if selected.get("masterwork") is True and _normalize_item_category(record.get("category")) not in {"weapon", "armor", "shield"}:
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.item-masterwork-invalid",
                        f"/selections/gear/{index}/itemId",
                        "masterwork is only source-supported for weapons, armor, or shields",
                        "source-rule",
                        "error",
                        record.get("sourceRef"),
                    ),
                )
            if _is_int(selected.get("enhancementBonus")) and selected.get("enhancementBonus", 0) > 0 and _normalize_item_category(record.get("category")) not in {"weapon", "armor", "shield"}:
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.item-enhancement-invalid",
                        f"/selections/gear/{index}/itemId",
                        "enhancement bonuses are only source-supported for weapons, armor, or shields",
                        "source-rule",
                        "error",
                        record.get("sourceRef"),
                    ),
                )
            self._record_gap(self._pricing_record(record), f"/selections/gear/{index}/itemId", issues)
            effects = self._item_effects(record, selected)
            instance_refs = self._item_instance_effects(record, selected, effects)
            price, pricing_refs = self._item_instance_price(record, selected)
            item_refs = _refs(record.get("sourceRef"), instance_refs, pricing_refs)
            if price is None:
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.item-price-gap",
                        f"/selections/gear/{index}/itemId",
                        f"{record.get('name', item_id)} has no source-backed integer copper price for the selected item instance",
                        "catalog-data",
                        "error",
                        item_refs,
                    ),
                )
                total_price = None
            elif price < 0:
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.item-price-invalid",
                        f"/selections/gear/{index}/itemId",
                        f"{record.get('name', item_id)} has a negative copper price",
                        "source-rule",
                        "error",
                        item_refs,
                    ),
                )
                total_price = None
            else:
                total_price = price * quantity
                spent += total_price
            category = _normalize_item_category(record.get("category", "gear"))
            if category not in {"weapon", "armor", "shield", "goods", "magic", "limitedUse"}:
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.item-category-invalid",
                        f"/selections/gear/{index}/itemId",
                        f"{record.get('name', item_id)} has an unsupported catalog category",
                        "catalog-data",
                        "error",
                        item_refs,
                    ),
                )
            if _is_int(total_price):
                category_spent[category] = category_spent.get(category, 0) + total_price
            if selected.get("equipped", True) and isinstance(effects.get("abilityBonuses"), dict):
                for ability, value in effects["abilityBonuses"].items():
                    canonical_ability = ability.rsplit(".", 1)[-1].casefold() if isinstance(ability, str) else ability
                    if canonical_ability in ABILITY_SET and _is_int(value):
                        ability_bonuses[canonical_ability] = ability_bonuses.get(canonical_ability, 0) + value
            if selected.get("equipped", True):
                for skill_id, value in (effects.get("skillBonuses", {}) if isinstance(effects.get("skillBonuses"), dict) else {}).items():
                    if _is_int(value) and isinstance(skill_id, str):
                        canonical = self._canonical_skill_id(skill_id)
                        skill_bonuses[canonical] = skill_bonuses.get(canonical, 0) + value
            if category == "armor" and selected.get("equipped", True):
                armor_count += quantity
                penalty = effects.get("armorCheckPenalty", effects.get("acp", 0))
                if _is_int(penalty):
                    armor_check_penalty += penalty
            if category == "shield" and selected.get("equipped", True):
                shield_count += quantity
                penalty = effects.get("shieldCheckPenalty", effects.get("armorCheckPenalty", effects.get("acp", 0)))
                if _is_int(penalty):
                    armor_check_penalty += penalty
            if category == "weapon" and selected.get("equipped", True):
                weapon_count += quantity
            items.append({
                "itemId": item_id,
                "name": record.get("name", item_id),
                "category": category,
                "quantity": quantity,
                "equipped": selected.get("equipped", True),
                "priceCp": price,
                "totalPriceCp": total_price,
                "effects": effects,
                **({"masterwork": True} if selected.get("masterwork") is True else {}),
                **({"enhancementBonus": selected["enhancementBonus"]} if _is_int(selected.get("enhancementBonus")) and selected.get("enhancementBonus", 0) > 0 else {}),
                **({"properties": copy.deepcopy(selected.get("properties", selected.get("propertyIds")))} if isinstance(selected.get("properties", selected.get("propertyIds")), list) and selected.get("properties", selected.get("propertyIds")) else {}),
                **({"charges": selected["charges"]} if _is_int(selected.get("charges")) else {}),
                "sourceRefs": item_refs,
            })
        if armor_count > 1:
            self._append_issue(
                issues,
                self._issue(
                    "npc.multiple-armor",
                    "/selections/gear",
                    "only one equipped armor item may provide armor effects",
                    "product-constraint",
                    "error",
                ),
            )
        if shield_count > 1:
            self._append_issue(
                issues,
                self._issue(
                    "npc.multiple-shield",
                    "/selections/gear",
                    "only one equipped shield item may provide shield effects",
                    "product-constraint",
                    "error",
                ),
            )
        if weapon_count == 0:
            self._append_issue(
                issues,
                self._issue(
                    "npc.weapon-required",
                    "/selections/gear",
                    "select at least one equipped mundane weapon for a combat statblock",
                    "source-rule",
                    "error",
                ),
            )
        budget = None
        if budget_record:
            budget_categories = copy.deepcopy(budget_record.get("categories")) if isinstance(budget_record.get("categories"), dict) else {}
            normalized_category_spent: dict[str, int] = {}
            for category, value in category_spent.items():
                target_category = _budget_category(category, budget_categories)
                normalized_category_spent[target_category] = normalized_category_spent.get(target_category, 0) + value
                if target_category not in budget_categories:
                    self._append_issue(
                        issues,
                        self._issue(
                            "npc.gear-category-unavailable",
                            "/selections/gear",
                            f"gear category {category} is not represented by the selected source budget",
                            "product-constraint",
                            "warning",
                            budget_record.get("sourceRef"),
                        ),
                    )
            budget = {
                "budgetCp": budget_record.get("budgetCp"),
                "spentCp": spent,
                "deltaCp": spent - budget_record["budgetCp"] if _is_int(budget_record.get("budgetCp")) else None,
                "categories": budget_categories,
                "categorySpentCp": normalized_category_spent,
                "categoryDeltasCp": {},
                "profileId": budget_record.get("id"),
                "progression": budget_record.get("progression"),
                "fantasyLevel": budget_record.get("fantasyLevel"),
                "effectiveLevel": budget_record.get("effectiveLevel"),
                "sourceRefs": _refs(budget_record.get("sourceRef")),
            }
            for category, target in budget["categories"].items():
                if _is_int(target):
                    delta = normalized_category_spent.get(category, 0) - target
                    budget["categoryDeltasCp"][category] = delta
                    if delta:
                        self._append_issue(
                            issues,
                            self._issue(
                                "npc.gear-category-delta",
                                "/selections/gear",
                                f"gear category {category} differs from its approximate target by {delta} cp",
                                "product-constraint",
                                "warning",
                                budget_record.get("sourceRef"),
                            ),
                        )
            if budget["deltaCp"]:
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.gear-budget-delta",
                        "/selections/gear",
                        f"selected gear differs from its approximate budget by {budget['deltaCp']} cp",
                        "product-constraint",
                        "warning",
                        budget_record.get("sourceRef"),
                    ),
                )
        return {
            "items": items,
            "budget": budget,
            "abilityBonuses": ability_bonuses,
            "skillBonuses": skill_bonuses,
            "armorCheckPenalty": armor_check_penalty,
            "refs": _refs(*(item.get("sourceRefs") for item in items), budget.get("sourceRefs") if budget else None),
        }

    def _gear_budget_for(self, profile: Any, *, total_level: int | None = None) -> dict[str, Any] | None:
        if not isinstance(profile, dict):
            return None
        progression = profile.get("experienceProgression", profile.get("progression"))
        fantasy = profile.get("fantasyLevel")
        requested_id = profile.get("gearBudgetId")
        records = self._section("gearBudget")
        if isinstance(requested_id, str):
            try:
                record = self._resolve("gearBudget", requested_id, "")[1]
                if progression is not None and record.get("progression") != progression:
                    return None
                if fantasy is not None and record.get("fantasyLevel") != fantasy:
                    return None
                return record if total_level is None or self._level_in_budget_row(record, total_level) else None
            except BoundaryError:
                return None
        candidates = [
            record for record in records.values()
            if isinstance(record, dict)
            and record.get("progression") == progression
            and record.get("fantasyLevel") == fantasy
        ]
        if total_level is None:
            return candidates[0] if candidates else None
        if len(candidates) == 1:
            return candidates[0] if self._level_in_budget_row(candidates[0], total_level) else None
        matching = [record for record in candidates if self._level_in_budget_row(record, total_level)]
        return matching[0] if len(matching) == 1 else None

    def _level_in_budget_row(self, record: dict[str, Any], level: int) -> bool:
        """Return whether an explicitly bounded Table 14-9 row covers level.

        A profile without a declared range is intentionally treated as a
        match.  The evaluator never invents a boundary from the progression
        name or from a neighboring row.
        """
        minimum = record.get("minLevel", record.get("minimumLevel"))
        maximum = record.get("maxLevel", record.get("maximumLevel"))
        bounds = record.get("levelRange", record.get("levelBand", record.get("levels")))
        if isinstance(bounds, dict):
            minimum = bounds.get("min", bounds.get("minimum", minimum))
            maximum = bounds.get("max", bounds.get("maximum", maximum))
        elif isinstance(bounds, list):
            if not all(_is_int(value) for value in bounds):
                return False
            if len(bounds) == 2:
                minimum, maximum = bounds
            elif level not in bounds:
                return False
        elif _is_int(bounds):
            minimum = maximum = bounds
        elif bounds is not None:
            return False
        if minimum is not None and not _is_int(minimum):
            return False
        if maximum is not None and not _is_int(maximum):
            return False
        if _is_int(minimum) and _is_int(maximum) and minimum > maximum:
            return False
        if _is_int(minimum) and level < minimum:
            return False
        if _is_int(maximum) and level > maximum:
            return False
        return True

    def _gear_totals(self, gear: Any, budget: dict[str, Any] | None) -> dict[str, Any]:
        spent = 0
        category_spent: dict[str, int] = {}
        for item in gear if isinstance(gear, list) else []:
            if not isinstance(item, dict):
                continue
            record = self._record_for("item", item.get("itemId"))
            price = self._item_instance_price(record, item)[0] if record else None
            quantity = item.get("quantity", 1)
            if _is_int(price) and _is_int(quantity):
                total = price * quantity
                spent += total
                category = _normalize_item_category(record.get("category", "gear"))
                category_spent[category] = category_spent.get(category, 0) + total
        budget_cp = budget.get("budgetCp") if budget else None
        categories = budget.get("categories", {}) if budget and isinstance(budget.get("categories", {}), dict) else {}
        normalized_category_spent: dict[str, int] = {}
        for category, value in category_spent.items():
            target_category = _budget_category(category, categories)
            normalized_category_spent[target_category] = normalized_category_spent.get(target_category, 0) + value
        deltas = {
            category: normalized_category_spent.get(category, 0) - target
            for category, target in categories.items()
            if _is_int(target)
        }
        return {
            "spentCp": spent,
            "budgetCp": budget_cp,
            "deltaCp": spent - budget_cp if _is_int(budget_cp) else None,
            "categorySpentCp": normalized_category_spent,
            "categoryDeltasCp": deltas,
        }

    def _item_effects(self, record: dict[str, Any], selected: dict[str, Any]) -> dict[str, Any]:
        effects: dict[str, Any] = {}
        if isinstance(record.get("effects"), dict):
            effects.update(copy.deepcopy(record["effects"]))
        elif isinstance(record.get("effect"), dict):
            effects.update(copy.deepcopy(record["effect"]))
        for key in (
            "armorBonus", "shieldBonus", "maxDex", "armorCheckPenalty", "acp", "naturalArmor",
            "attackBonus", "damageBonus", "enhancementBonus", "damageDie", "damageDice", "damage", "damageExpression", "averageDamage", "damageAverage", "damageType",
            "attackAbility", "ability", "damageAbility", "ranged", "iterativeStep", "count", "cmb", "cmd", "classification",
            "initiative", "saveBonus", "saveBonuses", "skillBonuses", "abilityBonuses", "speed", "touchAC", "flatFootedAC",
            "ac", "acBonus", "armorClassBonus", "shieldCheckPenalty", "averageDamage",
        ):
            if key in record and key not in effects:
                effects[key] = copy.deepcopy(record[key])
            if key in selected and key not in effects:
                effects[key] = copy.deepcopy(selected[key])
        return effects

    # ------------------------------------------------------------------
    # Combat calculations
    # ------------------------------------------------------------------
    def _evaluate_combat(
        self,
        selections,
        progression,
        total_level,
        abilities,
        race,
        gear,
        classes,
        skills,
        effects,
        issues,
    ) -> dict[str, Any]:
        modifiers = abilities.get("modifiers") or {}
        if not modifiers or classes.get("bab") is None:
            return {"defenses": {}, "attacks": [], "initiative": None, "cmb": None, "cmd": None, "refs": []}
        dex = modifiers.get("dexterity", 0)
        strength = modifiers.get("strength", 0)
        race_effects = self._race_effect_map(race)
        size = copy.deepcopy(self._size_modifiers(race))
        size_sources = []
        if isinstance(race, dict):
            if isinstance(race.get("sizeModifiers"), dict) or isinstance(race.get("sizeAdjustments"), dict):
                size_sources.append(race.get("sourceRef"))
            if isinstance(race_effects.get("sizeModifiers"), dict) or isinstance(race_effects.get("sizeAdjustments"), dict):
                size_sources.append(race_effects.get("sourceRef", race.get("sourceRef")))
        if not size_sources:
            self._append_issue(
                issues,
                self._issue(
                    "npc.size-modifiers-gap",
                    "/selections/raceId",
                    "race size modifiers are not source-backed",
                    "catalog-data",
                    "error",
                    _refs(race.get("sourceRef") if race else None, race_effects.get("sourceRef")),
                ),
            )
        for size_key in ("sizeModifiers", "sizeAdjustments"):
            if isinstance(race_effects.get(size_key), dict):
                for key, value in race_effects[size_key].items():
                    if _is_int(value):
                        size[key] = size.get(key, 0) + value
        armor_items = [
            item for item in gear.get("items", [])
            if item.get("category") in {"armor", "shield"} and item.get("equipped", True)
        ]
        armor_bonus = 0
        shield_bonus = 0
        max_dex: int | None = None
        natural_armor = self._effect_int(race or {}, "naturalArmor", "naturalArmorBonus", default=0)
        natural_armor += self._effect_int(race_effects, "naturalArmor", "naturalArmorBonus", default=0)
        touch_extra = self._effect_int(race or {}, "touchAC", "touchAcBonus", default=0)
        flat_extra = self._effect_int(race or {}, "flatFootedAC", "flatFootedAcBonus", default=0)
        ac_misc = self._effect_int(race or {}, "ac", "acBonus", default=0)
        save_bonus = {"fortitude": 0, "reflex": 0, "will": 0}
        ac_misc += self._effect_int(race_effects, "ac", "acBonus", default=0)
        touch_extra += self._effect_int(race_effects, "touchAC", "touchAcBonus", default=0)
        flat_extra += self._effect_int(race_effects, "flatFootedAC", "flatFootedAcBonus", default=0)
        for save in save_bonus:
            save_bonus[save] += self._save_effect(race or {}, save) + self._save_effect(race_effects, save)
        for item in armor_items:
            item_effects = item.get("effects", {})
            if item.get("category") == "armor":
                armor_bonus += sum(self._effect_int(item_effects, key, default=0) for key in ("armorBonus", "armorClassBonus", "acBonus", "ac")) + self._effect_int(item_effects, "enhancementBonus", default=0)
                candidate = self._effect_value(item_effects, "maxDex", "dexCap")
                if _is_int(candidate):
                    max_dex = candidate if max_dex is None else min(max_dex, candidate)
                natural_armor += self._effect_int(item_effects, "naturalArmor", default=0)
            elif item.get("category") == "shield":
                shield_bonus += self._effect_int(item_effects, "shieldBonus", default=0) + sum(self._effect_int(item_effects, key, default=0) for key in ("acBonus", "ac")) + self._effect_int(item_effects, "enhancementBonus", default=0)
            touch_extra += self._effect_int(item_effects, "touchAC", default=0)
            flat_extra += self._effect_int(item_effects, "flatFootedAC", default=0)
            for save in save_bonus:
                save_bonus[save] += self._save_effect(item_effects, save)
        if max_dex is None:
            capped_dex = dex
        else:
            capped_dex = min(dex, max_dex)
        size_ac = self._size_int(size, "ac", "armorClass", "acBonus", default=0)
        ac = 10 + armor_bonus + shield_bonus + capped_dex + natural_armor + size_ac + ac_misc + effects.get("ac", 0)
        # Armor limits normal AC Dexterity, but never touch AC Dexterity.
        touch_ac = 10 + dex + size_ac + touch_extra + effects.get("touchAC", 0)
        flat_ac = 10 + armor_bonus + shield_bonus + natural_armor + size_ac + ac_misc + flat_extra + effects.get("ac", 0) + effects.get("flatFootedAC", 0)
        fortitude = (classes.get("saves") or {}).get("fortitude", 0) + modifiers.get("constitution", 0) + save_bonus["fortitude"] + effects.get("fortitude", 0)
        reflex = (classes.get("saves") or {}).get("reflex", 0) + dex + save_bonus["reflex"] + effects.get("reflex", 0)
        will = (classes.get("saves") or {}).get("will", 0) + modifiers.get("wisdom", 0) + save_bonus["will"] + effects.get("will", 0)
        initiative = dex + self._effect_int(race or {}, "initiative", "initiativeBonus", default=0) + self._effect_int(race_effects, "initiative", "initiativeBonus", default=0) + effects.get("initiative", 0)
        cmb = classes["bab"] + strength + self._size_int(size, "cmb", "cmbBonus", default=0) + self._effect_int(race or {}, "cmb", "cmbBonus", default=0) + self._effect_int(race_effects, "cmb", "cmbBonus", default=0) + effects.get("cmb", 0)
        cmd = 10 + classes["bab"] + strength + dex + self._size_int(size, "cmd", "cmdBonus", default=0) + self._effect_int(race or {}, "cmd", "cmdBonus", default=0) + self._effect_int(race_effects, "cmd", "cmdBonus", default=0) + effects.get("cmd", 0)
        attacks = self._evaluate_attacks(
            selections,
            gear,
            classes["bab"],
            modifiers,
            effects,
            issues,
            size_attack=self._size_int(size, "attack", "attackRoll", "attackBonus", default=0),
            racial_attack_bonus=self._effect_int(race or {}, "attackBonus", "attackBonusValue", default=0) + self._effect_int(race_effects, "attackBonus", "attackBonusValue", default=0),
            racial_damage_bonus=self._effect_int(race or {}, "damageBonus", "damageBonusValue", default=0) + self._effect_int(race_effects, "damageBonus", "damageBonusValue", default=0),
        )
        refs = _refs(
            *(item.get("sourceRefs") for item in gear.get("items", [])),
            *(item["record"].get("sourceRef") for item in progression),
            *(row.get("row", {}).get("sourceRef") for row in classes.get("rows", [])),
            *(race.get("sourceRef"),) if race else None,
            *(race.get("_npcChoiceRefs"),) if race else None,
        )
        defense_inputs = [
            {"source": "base AC", "value": 10, "sourceRefs": _refs(*(item["record"].get("sourceRef") for item in progression))},
            {"source": "armor bonus", "value": armor_bonus, "sourceRefs": _refs(*(item.get("sourceRefs") for item in armor_items if item.get("category") == "armor"))},
            {"source": "shield bonus", "value": shield_bonus, "sourceRefs": _refs(*(item.get("sourceRefs") for item in armor_items if item.get("category") == "shield"))},
            {"source": "Dexterity after armor cap", "value": capped_dex, "sourceRefs": abilities.get("refs", [])},
            {"source": "size and natural armor", "value": size_ac + natural_armor, "sourceRefs": _refs(race.get("sourceRef") if race else None, *(item.get("sourceRefs") for item in armor_items))},
            {"source": "miscellaneous AC effects", "value": ac_misc + effects.get("ac", 0), "sourceRefs": _refs(race.get("sourceRef") if race else None, classes.get("refs"), gear.get("refs"))},
            {"source": "touch AC Dexterity", "value": dex, "sourceRefs": abilities.get("refs", [])},
            {"source": "touch AC effects", "value": size_ac + touch_extra + effects.get("touchAC", 0), "sourceRefs": _refs(race.get("sourceRef") if race else None, classes.get("refs"), gear.get("refs"))},
            {"source": "flat-footed AC effects", "value": armor_bonus + shield_bonus + natural_armor + size_ac + ac_misc + flat_extra + effects.get("ac", 0) + effects.get("flatFootedAC", 0), "sourceRefs": _refs(race.get("sourceRef") if race else None, classes.get("refs"), gear.get("refs"))},
            {"source": "saving throw bonuses", "value": save_bonus, "sourceRefs": _refs(race.get("sourceRef") if race else None, *(item.get("sourceRefs") for item in armor_items))},
            {"source": "class save rows and ability modifiers", "value": {"fortitude": fortitude, "reflex": reflex, "will": will}, "sourceRefs": _refs(classes.get("refs"), abilities.get("refs"))},
        ]
        initiative_inputs = [
            {"source": "Dexterity modifier", "value": dex, "sourceRefs": abilities.get("refs", [])},
            {"source": "initiative effects", "value": initiative - dex, "sourceRefs": _refs(race.get("sourceRef") if race else None, classes.get("refs"), gear.get("refs"))},
        ]
        maneuver_refs = _refs(classes.get("refs"), abilities.get("refs"), race.get("sourceRef") if race else None)
        return {
            "defenses": {
                "ac": ac,
                "touchAC": max(1, touch_ac),
                "flatFootedAC": max(1, flat_ac),
                "hp": classes.get("hp"),
                "fortitude": fortitude,
                "reflex": reflex,
                "will": will,
                "cmd": cmd,
            },
            "initiative": initiative,
            "cmb": cmb,
            "cmd": cmd,
            "attacks": attacks,
            "refs": refs,
            "traceInputs": {
                "defenses": defense_inputs,
                "initiative": initiative_inputs,
                "attacks": [
                    {"source": attack.get("name", "weapon"), "value": attack, "sourceRefs": attack.get("sourceRefs", [])}
                    for attack in attacks
                ],
                "cmb": [
                    {"source": "BAB", "value": classes.get("bab"), "sourceRefs": classes.get("refs", [])},
                    {"source": "Strength modifier", "value": strength, "sourceRefs": abilities.get("refs", [])},
                    {"source": "size and maneuver effects", "value": cmb - classes["bab"] - strength, "sourceRefs": maneuver_refs},
                ],
                "cmd": [
                    {"source": "base CMD", "value": 10, "sourceRefs": maneuver_refs},
                    {"source": "BAB + Strength + Dexterity", "value": classes["bab"] + strength + dex, "sourceRefs": _refs(classes.get("refs"), abilities.get("refs"))},
                    {"source": "size and maneuver effects", "value": cmd - 10 - classes["bab"] - strength - dex, "sourceRefs": maneuver_refs},
                ],
            },
        }

    def _evaluate_attacks(
        self,
        selections,
        gear,
        bab,
        modifiers,
        effects,
        issues,
        *,
        size_attack: int = 0,
        racial_attack_bonus: int = 0,
        racial_damage_bonus: int = 0,
    ) -> list[dict[str, Any]]:
        attacks: list[dict[str, Any]] = []
        selected_weapons = [
            item for item in gear.get("items", [])
            if item.get("category") == "weapon" and item.get("equipped", True) and item.get("quantity", 1) > 0
        ]
        for index, item in enumerate(selected_weapons):
            item_effects = item.get("effects", {}) if isinstance(item, dict) else {}
            name = item.get("name", item.get("itemId", "weapon"))
            attack_ability = item_effects.get("attackAbility", item_effects.get("ability", effects.get("attackAbility")))
            ranged = item_effects.get("ranged")
            if ranged is None:
                ranged = effects.get("ranged")
            finesse = item_effects.get("weaponFinesse", item_effects.get("finesse"))
            if finesse is None:
                finesse = effects.get("weaponFinesse", effects.get("finesse"))
            if isinstance(attack_ability, str):
                attack_ability = attack_ability.rsplit(".", 1)[-1].casefold()
            else:
                attack_ability = "dexterity" if ranged or finesse else "strength"
            ability_value = modifiers.get(attack_ability, 0)
            attack_bonus = bab + ability_value + size_attack + racial_attack_bonus + self._effect_int(item_effects, "attackBonus", default=0) + self._effect_int(item_effects, "enhancementBonus", default=0) + effects.get("attackBonus", 0)
            iterative_step = self._effect_value(item_effects, "iterativeStep")
            if not _is_int(iterative_step):
                rule = self._find_rule(("iterative-attack", "iterative step", "multiple attacks")) if bab >= 5 else None
                if rule:
                    self._record_gap(rule, f"/selections/gear/{index}/itemId", issues)
                    for key in ("iterativeStep", "step", "value", "penaltyStep"):
                        if _is_int(rule.get(key)):
                            iterative_step = rule[key]
                            break
                if bab >= 5 and not _is_int(iterative_step):
                    self._append_issue(
                        issues,
                        self._issue(
                            "npc.iterative-step-gap",
                            f"/selections/gear/{index}/itemId",
                            f"weapon {name} has no source-backed iterative attack step",
                            "catalog-data",
                            "error",
                            item.get("sourceRefs"),
                        ),
                    )
            if _is_int(iterative_step) and iterative_step <= 0:
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.iterative-step-invalid",
                        f"/selections/gear/{index}/itemId",
                        f"weapon {name} has an invalid iterative attack step",
                        "catalog-data",
                        "error",
                        item.get("sourceRefs"),
                    ),
                )
                iterative_step = None
            bonuses = [attack_bonus]
            while _is_int(iterative_step) and bab - iterative_step * len(bonuses) >= 1 and len(bonuses) < 4:
                bonuses.append(attack_bonus - iterative_step * len(bonuses))
            die = item_effects.get("damageDie") or item_effects.get("damageDice")
            parsed = _parse_die(die)
            damage_ability_name = item_effects.get("damageAbility", effects.get("damageAbility"))
            damage_bonus = self._effect_int(item_effects, "damageBonus", default=0) + self._effect_int(item_effects, "enhancementBonus", default=0)
            if isinstance(damage_ability_name, str):
                damage_bonus += modifiers.get(damage_ability_name.rsplit(".", 1)[-1].casefold(), 0)
            elif not ranged:
                damage_bonus += modifiers.get("strength", 0)
            damage_bonus += racial_damage_bonus + effects.get("damageBonus", 0)
            expression = item_effects.get("damageExpression") or item_effects.get("damage")
            average = item_effects.get("averageDamage", item_effects.get("damageAverage"))
            if not (_is_int(average) or isinstance(average, float)):
                average = None
            if isinstance(expression, str):
                expression_average = self._average_expression(expression)
                if expression_average is None:
                    self._append_issue(
                        issues,
                        self._issue(
                            "npc.weapon-damage-invalid",
                            f"/selections/gear/{index}/itemId",
                            f"weapon {name} has an invalid source-backed damage expression",
                            "catalog-data",
                            "error",
                            item.get("sourceRefs"),
                        ),
                    )
                if average is None:
                    expression_die = _parse_die(expression)
                    if expression_die:
                        expression_average += damage_bonus
                        expression = _format_damage(f"{expression_die[0]}d{expression_die[1]}", damage_bonus)
                    average = expression_average
            elif parsed:
                count, sides = parsed
                if average is None:
                    average = count * (sides + 1) / 2 + damage_bonus
                    if float(average).is_integer():
                        average = int(average)
                expression = _format_damage(f"{count}d{sides}", damage_bonus)
            else:
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.weapon-damage-gap",
                        f"/selections/gear/{index}/itemId",
                        f"weapon {name} has no source-backed damage die or expression",
                        "catalog-data",
                        "error",
                        item.get("sourceRefs"),
                    ),
                )
            attacks.append({
                "name": name,
                "count": self._effect_int(item_effects, "count", default=1),
                "attackBonus": bonuses,
                "attackBonusText": "/".join(_signed(value) for value in bonuses),
                "damageExpression": expression,
                "averageDamage": average,
                "damageType": item_effects.get("damageType"),
                "classification": item_effects.get("classification", "manufactured"),
                "itemId": item.get("itemId"),
                "sourceRefs": _refs(item.get("sourceRefs")),
            })
        return attacks

    def _average_expression(self, expression: str) -> int | float | None:
        match = re.fullmatch(r"(\d+)d(\d+)([+-]\d+)?", expression.replace(" ", "").lower())
        if not match:
            return None
        count, sides = int(match.group(1)), int(match.group(2))
        if count < 1 or sides < 1:
            return None
        bonus = int(match.group(3) or 0)
        value = count * (sides + 1) / 2 + bonus
        return int(value) if float(value).is_integer() else value

    def _size_modifiers(self, race: dict[str, Any] | None) -> dict[str, Any]:
        if not race:
            return {}
        for key in ("sizeModifiers", "sizeAdjustments"):
            if isinstance(race.get(key), dict):
                return race[key]
        return {}

    @staticmethod
    def _size_int(size: dict[str, Any], *keys: str, default: int = 0) -> int:
        for key in keys:
            if _is_int(size.get(key)):
                return size[key]
        return default

    @staticmethod
    def _effect_value(effects: dict[str, Any], *keys: str) -> Any:
        for key in keys:
            if key in effects:
                return effects[key]
        return None

    @classmethod
    def _effect_int(cls, effects: dict[str, Any], *keys: str, default: int = 0) -> int:
        value = cls._effect_value(effects, *keys)
        return value if _is_int(value) else default

    @classmethod
    def _save_effect(cls, effects: dict[str, Any], save: str) -> int:
        value = effects.get("saveBonus", effects.get("saveBonuses"))
        if _is_int(value):
            return value
        if isinstance(value, dict) and _is_int(value.get(save)):
            return value[save]
        return 0

    def _collect_effects(self, feats: list[dict[str, Any]], gear: list[dict[str, Any]]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        aliases = {
            "initiative": "initiativeBonus",
            "ac": "acBonus",
            "touchAC": "touchAcBonus",
            "flatFootedAC": "flatFootedAcBonus",
            "attackBonus": "attackBonusValue",
            "damageBonus": "damageBonusValue",
            "cmb": "cmbBonus",
            "cmd": "cmdBonus",
            "hp": "hitPoints",
        }
        for item in [*feats, *gear]:
            is_gear = isinstance(item, dict) and bool(item.get("itemId"))
            if is_gear and item.get("equipped", True) is False:
                continue
            effects = item.get("effects", {}) if isinstance(item, dict) else {}
            if not isinstance(effects, dict):
                continue
            category = item.get("category") if is_gear else None
            direct_gear_keys = set()
            if is_gear and category in {"armor", "shield"}:
                direct_gear_keys.update({"ac", "touchAC", "flatFootedAC", "saveBonus", "saveBonuses"})
            if is_gear and category == "weapon":
                direct_gear_keys.update({"attackBonus", "damageBonus", "attackAbility", "damageAbility", "ranged", "weaponFinesse", "finesse"})
            for key in ("initiative", "ac", "touchAC", "flatFootedAC", "attackBonus", "damageBonus", "cmb", "cmd", "fortitude", "reflex", "will", "hp"):
                if key in direct_gear_keys:
                    continue
                value = effects.get(key, effects.get(aliases.get(key, "")))
                if _is_int(value):
                    output[key] = output.get(key, 0) + value
            save_bonus = effects.get("saveBonus", effects.get("saveBonuses"))
            if not (is_gear and category in {"armor", "shield"}) and isinstance(save_bonus, dict):
                for save, value in save_bonus.items():
                    if save in {"fortitude", "reflex", "will"} and _is_int(value):
                        output[save] = output.get(save, 0) + value
            for key in ("weaponFinesse", "finesse", "ranged", "attackAbility", "damageAbility"):
                if is_gear and category == "weapon":
                    continue
                value = effects.get(key)
                if isinstance(value, (bool, str)):
                    output[key] = value
            skill_bonuses = effects.get("skillBonuses")
            if not is_gear and isinstance(skill_bonuses, dict):
                for skill, value in skill_bonuses.items():
                    if _is_int(value):
                        key = self._canonical_skill_id(skill)
                        output[key] = output.get(key, 0) + value
        return output

    def _apply_skill_effects(self, skills: dict[str, Any], effects: dict[str, int], source_refs: Any = None) -> None:
        refs = _refs(source_refs)
        for skill_id, value in effects.items():
            if skill_id.startswith("skill.") and _is_int(value):
                key = skill_id.removeprefix("skill.")
                skills["totals"][key] = skills["totals"].get(key, 0) + value
                for trace_input in skills.get("traceInputs", []):
                    if trace_input.get("source") == skill_id:
                        trace_input["value"] = skills["totals"][key]
                        trace_input.setdefault("components", []).append({"source": "feat or class-feature skill bonus", "value": value, "sourceRefs": refs})
                        break
        skills["refs"] = _refs(skills.get("refs"), refs)

    # ------------------------------------------------------------------
    # Spells and requirements helpers
    # ------------------------------------------------------------------
    def _evaluate_spells(
        self,
        selections: dict[str, Any],
        progression: list[dict[str, Any]],
        total_level: int,
        abilities: dict[str, Any],
        issues: list[dict[str, Any]],
        *,
        classes: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        specs = self._spellcasting_specs(progression)
        loadout = selections.get("spellLoadout")
        if not specs:
            if isinstance(loadout, dict) and self._spell_entries(loadout):
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.spellcasting-unavailable",
                        "/selections/spellLoadout",
                        "the selected class progression has no source-backed spellcasting",
                        "catalog-data",
                        "error",
                        self._class_source_refs(progression),
                    ),
                )
            return {
                "spells": [],
                "refs": self._class_source_refs(progression),
                "traceInputs": [{"source": "no source-backed spellcasting", "value": [], "sourceRefs": self._class_source_refs(progression)}],
            }
        spec = specs[0]
        requested_class = loadout.get("classId", loadout.get("casterClassId")) if isinstance(loadout, dict) else None
        if isinstance(requested_class, str):
            requested_specs = [candidate for candidate in specs if _canonical_id(candidate.get("classId")) == _canonical_id(requested_class)]
            if len(requested_specs) == 1:
                spec = requested_specs[0]
            else:
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.spellcasting-class-invalid",
                        "/selections/spellLoadout/classId",
                        "selected spellcasting class is not one unambiguous source-backed caster class",
                        "source-rule",
                        "error",
                        _refs(*(candidate.get("sourceRef") for candidate in specs)),
                    ),
                )
        class_ref = spec.get("sourceRef")
        self._record_gap(spec, "/selections/classProgression", issues)
        for spellcasting_record in spec.get("spellcastingRecords", []):
            self._record_gap(spellcasting_record, "/selections/classProgression", issues)
        if len(specs) > 1:
            self._append_issue(
                issues,
                self._issue(
                    "npc.multiple-spellcasting-gap",
                    "/selections/classProgression",
                    "multiclass spellcasting aggregation is not source-backed for the selected classes",
                    "catalog-data",
                    "error",
                    _refs(*(item.get("sourceRef") for item in specs)),
                ),
            )
        requested_mode = loadout.get("mode") if isinstance(loadout, dict) else None
        source_mode = spec.get("mode")
        if source_mode in {"prepared", "spontaneous"}:
            if requested_mode is not None and requested_mode != source_mode:
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.spellcasting-mode-invalid",
                        "/selections/spellLoadout/mode",
                        "selected spellcasting mode does not match the source-backed class mode",
                        "source-rule",
                        "error",
                        class_ref,
                    ),
                )
            mode = source_mode
        else:
            self._append_issue(
                issues,
                self._issue(
                    "npc.spellcasting-mode-gap",
                    "/selections/spellLoadout/mode",
                    "spellcasting mode is not source-backed",
                    "catalog-data",
                    "error",
                    class_ref,
                ),
            )
            mode = None
        caster_level = self._spell_caster_level(spec)
        if caster_level is None:
            self._append_issue(
                issues,
                self._issue(
                    "npc.caster-level-gap",
                    "/selections/classProgression",
                    "caster level is not source-backed for the selected class level",
                    "catalog-data",
                    "error",
                    class_ref,
                ),
            )
        elif caster_level < 1:
            self._append_issue(
                issues,
                self._issue(
                    "npc.caster-level-invalid",
                    "/selections/classProgression",
                    "source-backed caster level must be positive",
                    "catalog-data",
                    "error",
                    class_ref,
                ),
            )
            caster_level = None
        casting_ability = spec.get("ability")
        if not isinstance(casting_ability, str) or casting_ability not in ABILITY_SET:
            self._append_issue(
                issues,
                self._issue(
                    "npc.casting-ability-gap",
                    "/selections/classProgression",
                    "spellcasting ability is not source-backed",
                    "catalog-data",
                    "error",
                    class_ref,
                ),
            )
            casting_ability = None
        slots = self._spell_slots(spec)
        base_slots = copy.deepcopy(slots) if isinstance(slots, dict) else None
        if slots is not None:
            for level, value in self._spell_bonus_slots(spec, abilities.get("scores") or {}).items():
                slots[level] = slots.get(level, 0) + value
        if slots is None:
            self._append_issue(
                issues,
                self._issue(
                    "npc.spells-per-day-gap",
                    "/selections/spellLoadout",
                    "spells-per-day data is not source-backed",
                    "catalog-data",
                    "error",
                    class_ref,
                ),
            )
            slots = {}
        selected = self._spell_entries(loadout) if isinstance(loadout, dict) else []
        if not isinstance(loadout, dict) or not selected:
            self._append_issue(
                issues,
                self._issue(
                    "npc.spell-choice-required",
                    "/selections/spellLoadout/spells",
                    "a prepared spellcasting class requires a selected spell loadout",
                    "source-rule",
                    "error",
                    class_ref,
                ),
            )
        omitted = loadout.get("omittedLevels", []) if isinstance(loadout, dict) else []
        omission_shape_valid = True
        if isinstance(omitted, dict):
            omission_shape_valid = all(str(level).isdigit() and isinstance(enabled, bool) for level, enabled in omitted.items())
            omitted = [int(level) for level, enabled in omitted.items() if isinstance(enabled, bool) and enabled]
        if not isinstance(omitted, list) or any(not _is_int(level) or level < 0 for level in omitted):
            omission_shape_valid = False
        if not omission_shape_valid or len(omitted) != len(set(omitted)):
            self._append_issue(
                issues,
                self._issue(
                    "npc.spell-omission-invalid",
                    "/selections/spellLoadout/omittedLevels",
                    "omitted spell levels must be non-negative integers",
                    "source-rule",
                    "error",
                    class_ref,
                ),
            )
            omitted = []
        if omitted and any(level not in slots or not _is_int(slots.get(level)) or slots.get(level, 0) <= 0 for level in omitted):
            self._append_issue(
                issues,
                self._issue(
                    "npc.spell-omission-invalid",
                    "/selections/spellLoadout/omittedLevels",
                    "only source-backed available spell levels may be omitted",
                    "source-rule",
                    "error",
                    class_ref,
                ),
            )
        if omitted and selections.get("statblockUse", "full") != "encounter":
            self._append_issue(
                issues,
                self._issue(
                    "npc.spell-omission-invalid",
                    "/selections/spellLoadout/omittedLevels",
                    "spell omissions are allowed only for encounter statblocks",
                    "source-rule",
                    "error",
                    class_ref,
                ),
            )
        available_spell_levels = sorted(level for level, count in slots.items() if _is_int(count) and count > 0)
        protected_spell_levels = set(available_spell_levels[-2:])
        if any(level in protected_spell_levels for level in omitted):
            self._append_issue(
                issues,
                self._issue(
                    "npc.spell-omission-invalid",
                    "/selections/spellLoadout/omittedLevels",
                    "encounter spell loadouts must include the two highest available spell levels",
                    "source-rule",
                    "error",
                    class_ref,
                ),
            )
        counts: dict[int, int] = {}
        known_ids: dict[int, set[str]] = {}
        spells: list[dict[str, Any]] = []
        spell_refs: list[dict[str, Any]] = []
        trace_inputs: list[dict[str, Any]] = []
        ability_modifiers = abilities.get("modifiers") or {}
        ability_scores = abilities.get("scores") or {}
        for index, raw_item in enumerate(selected):
            if isinstance(raw_item, str):
                item = {"spellId": raw_item}
            elif isinstance(raw_item, dict):
                item = raw_item
            else:
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.spell-choice-required",
                        f"/selections/spellLoadout/spells/{index}",
                        "spell selection requires spellId",
                        "source-rule",
                        "error",
                        class_ref,
                    ),
                )
                continue
            if not isinstance(item.get("spellId"), str):
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.spell-choice-required",
                        f"/selections/spellLoadout/spells/{index}",
                        "spell selection requires spellId",
                        "source-rule",
                        "error",
                        class_ref,
                    ),
                )
                continue
            path = f"/selections/spellLoadout/spells/{index}/spellId"
            spell_id, spell = self._selected_record("spell", item["spellId"], path, issues)
            if spell is None:
                continue
            spell_refs.extend(_refs(spell.get("sourceRef")))
            catalog_level = self._spell_level_for(spell, spec, {})
            selected_level = item.get("spellLevel", item.get("level"))
            if _is_int(selected_level) and catalog_level is not None and selected_level != catalog_level:
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.spell-level-mismatch",
                        path,
                        f"selected spell level {selected_level} does not match the source-backed level {catalog_level}",
                        "source-rule",
                        "error",
                        spell.get("sourceRef"),
                    ),
                )
            level = catalog_level
            if level is None:
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.spell-level-gap",
                        path,
                        f"{spell.get('name', spell_id)} has no source-backed level for the selected class",
                        "catalog-data",
                        "error",
                        _refs(spell.get("sourceRef"), class_ref),
                    ),
                )
                continue
            if level in omitted:
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.spell-omission-invalid",
                        path,
                        "an explicitly selected spell cannot be in an omitted level",
                        "source-rule",
                        "error",
                        class_ref,
                    ),
                )
            if not self._spell_is_on_class_list(spell, spec):
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.spell-not-on-list",
                        path,
                        "selected spell is not on the source-backed class spell list",
                        "source-rule",
                        "error",
                        _refs(spell.get("sourceRef"), class_ref),
                    ),
                )
            count = item.get("count", item.get("usesPerDay", 1))
            if not _is_int(count) or count < 1:
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.spell-count-invalid",
                        f"/selections/spellLoadout/spells/{index}/count",
                        "spell count must be a positive integer",
                        "source-rule",
                        "error",
                        class_ref,
                    ),
                )
                count = 1
            counts[level] = counts.get(level, 0) + count
            known_ids.setdefault(level, set()).add(spell_id)
            minimum = self._spell_minimum_ability(spec, level)
            if minimum is not None and (not _is_int(ability_scores.get(spec.get("ability"))) or ability_scores.get(spec.get("ability")) < minimum):
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.spell-ability-insufficient",
                        path,
                        f"casting ability must be at least {minimum} for level {level} spells",
                        "source-rule",
                        "error",
                        class_ref,
                        details={"ability": spec.get("ability"), "minimum": minimum, "spellLevel": level},
                    ),
                )
            dc = self._spell_dc(spec, level, ability_modifiers, issues, path)
            spell_value = {
                "spellId": spell_id,
                "name": spell.get("name", spell_id),
                "spellLevel": level,
                "baseLevel": level,
                "prepared": mode == "prepared",
                "count": count,
                "usesPerDay": slots.get(level),
                "spellDC": dc,
                "sourceRefs": _refs(spell.get("sourceRef"), class_ref),
            }
            spells.append(spell_value)
            trace_inputs.append({"source": spell_value["name"], "value": {"level": level, "count": count, "dc": dc}, "sourceRefs": spell_value["sourceRefs"]})
        for level, count in sorted(counts.items()):
            available = slots.get(level)
            if available is None:
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.spells-per-day-gap",
                        "/selections/spellLoadout/spells",
                        f"no source-backed spells-per-day value exists for spell level {level}",
                        "catalog-data",
                        "error",
                        class_ref,
                    ),
                )
            elif count > available:
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.spell-slots-exceeded",
                        "/selections/spellLoadout/spells",
                        f"selected level {level} spells use {count} slots but only {available} are available",
                        "source-rule",
                        "error",
                        class_ref,
                    ),
                )
        known_slots = self._spell_known_slots(spec) if mode == "spontaneous" else None
        if mode == "spontaneous":
            if known_slots is None:
                self._append_issue(
                    issues,
                    self._issue(
                        "npc.spells-known-gap",
                        "/selections/classProgression",
                        "spontaneous spellcasting requires source-backed spells-known limits",
                        "catalog-data",
                        "error",
                        class_ref,
                    ),
                )
            else:
                for level, selected_ids in sorted(known_ids.items()):
                    available = known_slots.get(level)
                    if available is None:
                        self._append_issue(
                            issues,
                            self._issue(
                                "npc.spells-known-gap",
                                "/selections/spellLoadout/spells",
                                f"no source-backed spells-known value exists for spell level {level}",
                                "catalog-data",
                                "error",
                                class_ref,
                            ),
                        )
                    elif len(selected_ids) > available:
                        self._append_issue(
                            issues,
                            self._issue(
                                "npc.spells-known-exceeded",
                                "/selections/spellLoadout/spells",
                                f"selected level {level} spells use {len(selected_ids)} known-spell slots but only {available} are available",
                                "source-rule",
                                "error",
                                class_ref,
                            ),
                        )
        result: dict[str, Any] = {
            "spells": spells,
            "casterLevel": caster_level,
            "spellcastingClassId": spec.get("classId"),
            "spellcastingMode": mode,
            "spellcastingAbility": casting_ability,
            "spellsPerDay": slots,
            "baseSpellsPerDay": base_slots,
            "bonusSpells": {level: value for level, value in self._spell_bonus_slots(spec, abilities.get("scores") or {}).items()},
            "omittedSpellLevels": sorted(set(omitted)),
            "refs": _refs(class_ref, *spell_refs),
            "traceInputs": trace_inputs,
        }
        return result

    def _spellcasting_specs(self, progression: list[dict[str, Any]]) -> list[dict[str, Any]]:
        specs: list[dict[str, Any]] = []
        for item in progression:
            record = item["record"]
            row = self._class_level(record, item["levels"]) or {}
            raw = record.get("spellcasting")
            if not isinstance(raw, dict):
                raw = {}
            state = copy.deepcopy(raw)
            row_state = row.get("spellcasting")
            if isinstance(row_state, dict):
                state.update(copy.deepcopy(row_state))
            aliases = {
                "ability": ("spellcastingAbility", "castingAbility", "keyAbility", "castingStat", "ability"),
                "mode": ("spellcastingMode", "castingMode", "mode"),
                "casterLevel": ("casterLevel", "spellcasterLevel"),
                "spellsPerDay": ("spellsPerDay", "spellSlots", "slots"),
                "spellsKnown": ("spellsKnown", "knownSpells", "spellsKnownByClassLevel"),
                "spellList": ("spellList", "spellListId", "spellClassId"),
                "minimumAbility": ("minimumAbility", "minimumCastingAbility", "abilityMinimum"),
                "spellDCBase": ("spellDCBase", "spellSaveDCBase", "dcBase"),
                "bonusSpells": ("bonusSpells",),
            }
            for target, names in aliases.items():
                if target in state:
                    continue
                for name in names:
                    value = state.get(name)
                    if value is None:
                        value = row.get(name, record.get(name))
                    if value is not None:
                        state[target] = copy.deepcopy(value)
                        break
            marker = bool(state) or any(key in record or key in row for key in ("casterLevel", "spellcastingAbility", "castingAbility", "spellsPerDay", "spellSlots", "spellsKnown", "knownSpells", "spellList"))
            if not marker:
                continue
            ability = state.get("ability")
            if isinstance(ability, str):
                ability = ability.rsplit(".", 1)[-1].casefold()
            mode = state.get("mode")
            if mode is None and state.get("prepared") is True:
                mode = "prepared"
            specs.append({
                **state,
                "classId": item["classId"],
                "classLevel": item["levels"],
                "record": record,
                "row": row,
                "ability": ability,
                "mode": mode,
                "spellcastingRecords": [
                    value for value in (raw, row_state) if isinstance(value, dict) and value
                ],
                "sourceRef": _refs(row.get("sourceRef"), record.get("sourceRef")),
            })
        return specs

    @staticmethod
    def _spell_entries(loadout: dict[str, Any]) -> list[Any]:
        output: list[Any] = []
        for key in ("spells", "preparedSpells", "knownSpells", "spellsByLevel", "spellLevels"):
            value = loadout.get(key)
            if isinstance(value, list):
                output.extend(value)
            elif isinstance(value, dict):
                for level, values in value.items():
                    if not isinstance(values, list):
                        continue
                    for entry in values:
                        if isinstance(entry, dict):
                            value_copy = copy.deepcopy(entry)
                            value_copy.setdefault("level", int(level) if str(level).isdigit() else level)
                            output.append(value_copy)
                        else:
                            output.append({"spellId": entry, "level": int(level) if str(level).isdigit() else level})
        return output

    def _spell_caster_level(self, spec: dict[str, Any]) -> int | None:
        for key in ("casterLevel", "spellcasterLevel"):
            value = spec.get(key)
            if _is_int(value):
                return value
        for key in ("casterLevelByClassLevel", "casterLevels"):
            value = spec.get(key)
            if isinstance(value, dict):
                candidate = value.get(str(spec.get("classLevel")), value.get(spec.get("classLevel")))
                if _is_int(candidate):
                    return candidate
        row = spec.get("row") if isinstance(spec.get("row"), dict) else {}
        for key in ("casterLevel", "spellcasterLevel"):
            if _is_int(row.get(key)):
                return row[key]
        return None

    def _spell_slots(self, spec: dict[str, Any]) -> dict[int, int] | None:
        raw = None
        for key in ("spellsPerDay", "spellSlots", "slots"):
            if key in spec:
                raw = spec[key]
                break
        if raw is None and isinstance(spec.get("row"), dict):
            row = spec["row"]
            for key in ("spellsPerDay", "spellSlots", "slots"):
                if key in row:
                    raw = row[key]
                    break
        if raw is None:
            return None
        if isinstance(raw, dict):
            nested = raw.get(str(spec.get("classLevel")), raw.get(spec.get("classLevel")))
            if isinstance(nested, (dict, list)):
                raw = nested
        if isinstance(raw, list):
            return {index: value for index, value in enumerate(raw) if _is_int(value) and value >= 0}
        if not isinstance(raw, dict):
            return None
        output: dict[int, int] = {}
        for level, value in raw.items():
            if str(level).isdigit() and _is_int(value) and value >= 0:
                output[int(level)] = value
        return output

    def _spell_known_slots(self, spec: dict[str, Any]) -> dict[int, int] | None:
        raw = None
        for key in ("spellsKnown", "knownSpells", "spellsKnownByClassLevel"):
            if key in spec:
                raw = spec[key]
                break
        if raw is None and isinstance(spec.get("row"), dict):
            row = spec["row"]
            for key in ("spellsKnown", "knownSpells", "spellsKnownByClassLevel"):
                if key in row:
                    raw = row[key]
                    break
        if raw is None:
            return None
        if isinstance(raw, dict):
            nested = raw.get(str(spec.get("classLevel")), raw.get(spec.get("classLevel")))
            if isinstance(nested, (dict, list)):
                raw = nested
        if isinstance(raw, list):
            return {index: value for index, value in enumerate(raw) if _is_int(value) and value >= 0}
        if not isinstance(raw, dict):
            return None
        return {
            int(level): value
            for level, value in raw.items()
            if str(level).isdigit() and _is_int(value) and value >= 0
        }

    def _spell_bonus_slots(self, spec: dict[str, Any], scores: dict[str, Any]) -> dict[int, int]:
        raw = spec.get("bonusSpells")
        if raw is None:
            return {}
        if isinstance(raw, dict):
            # A source may provide a ready-to-use bonus-spell row, or rows
            # keyed by the casting score.  Only an explicitly matching row is
            # accepted.
            direct = {int(key): value for key, value in raw.items() if str(key).isdigit() and _is_int(value) and value >= 0}
            if direct:
                return direct
            score = scores.get(spec.get("ability"))
            row = raw.get(str(score), raw.get(score))
            if isinstance(row, dict):
                return {int(key): value for key, value in row.items() if str(key).isdigit() and _is_int(value) and value >= 0}
        if isinstance(raw, list):
            return {index: value for index, value in enumerate(raw) if _is_int(value) and value >= 0}
        return {}

    def _spell_list_values(self, spec: dict[str, Any]) -> Any:
        for key in ("spellList", "spellListId", "spellClassId"):
            if key in spec:
                return spec[key]
        record = spec.get("record") if isinstance(spec.get("record"), dict) else {}
        for key in ("spellList", "spellListId", "spellClassId"):
            if key in record:
                return record[key]
        return None

    def _spell_level_for(self, spell: dict[str, Any], spec: dict[str, Any], selected: dict[str, Any]) -> int | None:
        levels = spell.get("levelsByClass", spell.get("levelsByList", spell.get("spellLevelsByList")))
        class_keys = {
            value for value in (
                _canonical_id(spec.get("classId")),
                _canonical_id(spec.get("record", {}).get("name")),
                _canonical_id(self._spell_list_values(spec)),
            ) if value
        }
        if isinstance(levels, dict):
            matching = [value for key, value in levels.items() if _canonical_id(key) in class_keys]
            if matching:
                if any(not _is_int(value) or value < 0 for value in matching):
                    return None
                valid = set(matching)
                return next(iter(valid)) if len(valid) == 1 else None
            return None
        membership = spell.get("listMembership")
        if isinstance(membership, list):
            matching = [
                row.get("level") for row in membership
                if isinstance(row, dict) and _canonical_id(row.get("classId", row.get("listId"))) in class_keys
            ]
            if matching:
                if any(not _is_int(value) or value < 0 for value in matching):
                    return None
                valid = set(matching)
                return next(iter(valid)) if len(valid) == 1 else None
            return None
        for key in ("spellLevel", "level"):
            if _is_int(spell.get(key)) and spell[key] >= 0:
                return spell[key]
        return None

    def _spell_is_on_class_list(self, spell: dict[str, Any], spec: dict[str, Any]) -> bool:
        class_keys = {
            value for value in (
                _canonical_id(spec.get("classId")),
                _canonical_id(spec.get("record", {}).get("name")),
                _canonical_id(self._spell_list_values(spec)),
            ) if value
        }
        levels = spell.get("levelsByClass", spell.get("levelsByList", spell.get("spellLevelsByList")))
        if isinstance(levels, dict) and any(
            _canonical_id(key) in class_keys and _is_int(value) and value >= 0
            for key, value in levels.items()
        ):
            return True
        membership = spell.get("listMembership")
        if isinstance(membership, list) and any(
            _canonical_id(row.get("classId", row.get("listId"))) in class_keys
            and _is_int(row.get("level")) and row.get("level") >= 0
            for row in membership if isinstance(row, dict)
        ):
            return True
        values = spell.get("spellLists", spell.get("lists", spell.get("classLists")))
        if isinstance(values, list):
            return any(_canonical_id(value) in class_keys for value in values)
        if isinstance(values, dict):
            return any(_canonical_id(key) in class_keys for key in values) or any(
                _canonical_id(value) in class_keys
                for value in values.values() if isinstance(value, str)
            )
        return isinstance(values, str) and _canonical_id(values) in class_keys

    def _spell_minimum_ability(self, spec: dict[str, Any], level: int) -> int | None:
        for key in ("minimumAbility", "minimumCastingAbility", "abilityMinimum", "minimumScore"):
            raw = spec.get(key)
            if isinstance(raw, dict):
                value = raw.get(str(level), raw.get(level))
            else:
                value = raw
            if _is_int(value):
                return value
        return None

    def _spell_dc(self, spec: dict[str, Any], level: int, modifiers: dict[str, Any], issues: list[dict[str, Any]], path: str) -> int | None:
        base = None
        for key in ("spellDCBase", "spellSaveDCBase", "dcBase"):
            if _is_int(spec.get(key)):
                base = spec[key]
                break
        rule = None
        if base is None:
            rule = self._find_rule(("spell-save-dc", "spell-dc", "save-dc"))
            if rule:
                self._record_gap(rule, "/selections/spellLoadout", issues)
                if rule.get("catalogStatus") not in {"gap", "partial"}:
                    for key in ("base", "baseValue", "constant"):
                        if _is_int(rule.get(key)):
                            base = rule[key]
                            break
        ability = spec.get("ability")
        modifier = modifiers.get(ability) if isinstance(ability, str) else None
        if base is None or not _is_int(modifier):
            self._append_issue(
                issues,
                self._issue(
                    "npc.spell-dc-gap",
                    path,
                    "spell save DC requires a source-backed DC formula and casting modifier",
                    "catalog-data",
                    "error",
                    _refs(spec.get("sourceRef"), rule.get("sourceRef") if rule else None),
                ),
            )
            return None
        return base + level + modifier

    def _spell_choice_values(self, spec: dict[str, Any]) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for key, spell in sorted(self._section("spell").items(), key=lambda entry: entry[0]):
            if not isinstance(spell, dict) or not self._spell_is_on_class_list(spell, spec):
                continue
            level = self._spell_level_for(spell, spec, {})
            value = spell.get("id", key)
            entry = {"value": value, "label": spell.get("name", _label(value)), "sourceRefs": _refs(spell.get("sourceRef"))}
            if level is not None:
                entry["spellLevel"] = level
            output.append(entry)
        return output

    def _spell_budget(self, progression):
        budget: dict[str, Any] = {
            "classLevels": [{"classId": item["classId"], "levels": item["levels"]} for item in progression],
            "sourceRefs": self._class_source_refs(progression),
        }
        specs = self._spellcasting_specs(progression)
        if specs:
            spec = specs[0]
            budget.update({
                "spellcastingClassId": spec.get("classId"),
                "mode": spec.get("mode"),
                "castingAbility": spec.get("ability"),
                "casterLevel": self._spell_caster_level(spec),
                "spellsPerDay": self._spell_slots(spec),
            })
        return budget

    def _choice_values(self, kind: str, *, category: str | None = None) -> list[dict[str, Any]]:
        output = []
        for key, record in sorted(self._section(kind).items(), key=lambda entry: entry[0]):
            if not isinstance(record, dict):
                continue
            if category is not None and record.get("category") != category:
                continue
            record_id = record.get("id", key)
            output.append({"value": record_id, "label": record.get("name", _label(record_id)), "sourceRefs": _refs(record.get("sourceRef"))})
        return output

    def _choice_values_for_ids(self, kind: str, values: list[Any]) -> list[dict[str, Any]]:
        output = []
        for value in values:
            record = self._record_for(kind, value)
            if record:
                output.append({"value": record.get("id", value), "label": record.get("name", _label(value)), "sourceRefs": _refs(record.get("sourceRef"))})
        return output

    def _skill_choice_values(self, progression: list[dict[str, Any]]) -> list[dict[str, Any]]:
        values = self._class_skill_ids(progression) or self._skill_ids()
        return self._choice_values_for_ids("skill", sorted(values))

    def _progression_for_requirements(self, selections: dict[str, Any]) -> list[dict[str, Any]]:
        output = []
        for raw in selections.get("classProgression", []) if isinstance(selections.get("classProgression"), list) else []:
            if not isinstance(raw, dict):
                continue
            record = self._record_for("class", raw.get("classId"))
            if record:
                output.append({"classId": raw.get("classId"), "levels": raw.get("levels", 0), "record": record})
        return output

    def _max_class_level(self, record: dict[str, Any] | None) -> int | None:
        levels = record.get("levels") if isinstance(record, dict) else None
        if not isinstance(levels, dict):
            return None
        values = [int(key) for key in levels if str(key).isdigit()]
        return max(values) if values else None

    def _array_source_for_requirements(self, progression: list[dict[str, Any]]) -> Any:
        category = self._npc_category(progression)
        record = self._record_for("abilityArray", f"npc-ability-array.{category}")
        return record.get("sourceRef") if record else None

    def _class_source_refs(self, progression: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return _refs(*(item["record"].get("sourceRef") for item in progression))

    @staticmethod
    def _slot_is_general(slot: dict[str, Any]) -> bool:
        kind = str(slot.get("kind", slot.get("category", ""))).casefold()
        slot_id = str(slot.get("slotId", slot.get("id", ""))).casefold()
        feature_id = str(slot.get("featureId", "")).casefold()
        return bool(slot.get("general") is True) or kind in {"general", "general-feat", "general-feat-slot"} or slot_id.startswith("general-") or feature_id.endswith("general-feats")

    def _choice_slots_for_class(self, record: dict[str, Any], levels: int) -> list[dict[str, Any]]:
        slots: list[dict[str, Any]] = []
        for level in range(1, levels + 1):
            row = self._class_level(record, level)
            if not row:
                continue
            raw_slots = row.get("choiceSlots") or []
            if isinstance(raw_slots, dict):
                raw_slots = [dict(value, slotId=key) if isinstance(value, dict) else {"slotId": key, "allowedValues": value} for key, value in raw_slots.items()]
            for raw_slot in raw_slots if isinstance(raw_slots, list) else []:
                if not isinstance(raw_slot, dict):
                    continue
                slot = copy.deepcopy(raw_slot)
                slot.setdefault("classLevel", level)
                slot.setdefault("grantedAtClassLevel", level)
                slot.setdefault("sourceRef", row.get("sourceRef", record.get("sourceRef")))
                if not self._choice_slot_id(slot):
                    kind = str(slot.get("kind", slot.get("category", "choice"))).casefold()
                    prefix = _canonical_id(record.get("id", record.get("name", "class")))
                    slot["slotId"] = f"{prefix}-{kind}-{level}"
                slots.append(slot)
        return slots

    def _class_feat_slots(self, progression: list[dict[str, Any]], total_level: int) -> list[dict[str, Any]]:
        slots: list[dict[str, Any]] = []
        offset = 0
        for item in progression:
            class_id = item["classId"]
            for slot in self._choice_slots_for_class(item["record"], item["levels"]):
                if not self._slot_is_feat(slot) or self._slot_is_general(slot):
                    continue
                class_level = slot.get("classLevel", slot.get("level", 0))
                if not _is_int(class_level):
                    continue
                global_level = slot.get("grantedAtLevel")
                if not _is_int(global_level) or global_level == class_level:
                    global_level = offset + class_level
                if global_level > total_level:
                    continue
                entry = copy.deepcopy(slot)
                entry.update({
                    "slotId": self._choice_slot_id(slot),
                    "kind": slot.get("kind", "feat"),
                    "classId": class_id,
                    "classLevel": class_level,
                    "grantedAtLevel": global_level,
                    "allowedFeatIds": copy.deepcopy(slot.get("allowedFeatIds", slot.get("allowedValues", slot.get("values", [])))),
                    "required": slot.get("required", not slot.get("automatic", False)),
                    "sourceRef": slot.get("sourceRef", item["record"].get("sourceRef")),
                })
                slots.append(entry)
            offset += item["levels"]
        return slots

    def _all_feat_slots(self, total_level: int, progression: list[dict[str, Any]]) -> list[dict[str, Any]]:
        values = self._general_feat_slots(total_level, progression) + self._class_feat_slots(progression, total_level)
        values.sort(key=lambda item: (item.get("grantedAtLevel", 0), item.get("slotId", "")))
        return values

    def _automatic_feature_values(self, record: dict[str, Any], levels: int) -> list[dict[str, Any]]:
        output = []
        for level in range(1, levels + 1):
            row = self._class_level(record, level)
            for feature in (row or {}).get("featureGrants") or []:
                output.append(self._feature_value(feature, row or {}, {"record": record, "levels": level}))
        return output

    def _automatic_feat_values(self, progression: list[dict[str, Any]]) -> list[dict[str, Any]]:
        output = []
        offset = 0
        for item in progression:
            for slot in self._choice_slots_for_class(item["record"], item["levels"]):
                if self._slot_is_feat(slot) and slot.get("automatic"):
                    value = copy.deepcopy(slot)
                    class_level = slot.get("classLevel", slot.get("level", item["levels"]))
                    global_level = slot.get("grantedAtLevel")
                    if not _is_int(global_level) or global_level == class_level:
                        global_level = offset + class_level if _is_int(class_level) else offset + item["levels"]
                    value["grantedAtLevel"] = global_level
                    value.setdefault("classId", item["classId"])
                    output.append(value)
            offset += item["levels"]
        return output

    def _find_rule(self, tokens: tuple[str, ...]) -> dict[str, Any] | None:
        matches: list[dict[str, Any]] = []
        for key, record in sorted(self._section("derivedRule").items(), key=lambda entry: entry[0]):
            if not isinstance(record, dict):
                continue
            haystack = " ".join(str(record.get(field, "")) for field in ("id", "name", "kind", "rule"))
            compact_haystack = re.sub(r"[^a-z0-9]", "", haystack.casefold())
            if any(token.casefold() in haystack.casefold() or re.sub(r"[^a-z0-9]", "", token.casefold()) in compact_haystack for token in tokens):
                matches.append(record)
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            for token in tokens:
                compact_token = re.sub(r"[^a-z0-9]", "", token.casefold())
                exact = [
                    record for record in matches
                    if any(
                        str(record.get(field, "")).casefold() == token.casefold()
                        or re.sub(r"[^a-z0-9]", "", str(record.get(field, "")).casefold()) == compact_token
                        for field in ("id", "name", "kind")
                    )
                ]
                if len(exact) == 1:
                    return exact[0]
        return None

    @staticmethod
    def _rule_amount(rule: dict[str, Any] | None, key: str, default: int) -> int:
        value = rule.get(key) if isinstance(rule, dict) else None
        return value if _is_int(value) else default

    # ------------------------------------------------------------------
    # Trace and response helpers
    # ------------------------------------------------------------------
    def _trace(self, canonical, abilities, classes, race, gear, skills, feats, combat, spells):
        trace: list[dict[str, Any]] = []

        def add(path: str, rule: str, value: Any, refs: Any, inputs: Any = None) -> None:
            source_refs = _refs(refs)
            if isinstance(inputs, list) and inputs:
                trace_inputs = []
                for raw in inputs:
                    if not isinstance(raw, dict):
                        continue
                    entry = copy.deepcopy(raw)
                    entry_refs = _refs(entry.pop("sourceRefs", entry.pop("sourceRef", None)))
                    if entry_refs:
                        entry["sourceRefs"] = entry_refs
                        if len(entry_refs) == 1:
                            entry["sourceRef"] = copy.deepcopy(entry_refs[0])
                    elif source_refs:
                        entry["sourceRefs"] = copy.deepcopy(source_refs)
                    entry.setdefault("source", "derived input")
                    trace_inputs.append(entry)
                if not trace_inputs:
                    trace_inputs = [{"source": source.get("entry", source.get("section", source.get("sourceId", "source"))), "sourceRef": copy.deepcopy(source)} for source in source_refs]
            else:
                trace_inputs = [
                    {
                        "source": source.get("entry", source.get("section", source.get("sourceId", "source"))),
                        "sourceRef": copy.deepcopy(source),
                    }
                    for source in source_refs
                ]
            trace.append({
                "path": path,
                "rule": rule,
                "inputs": trace_inputs,
                "value": copy.deepcopy(value),
                "sourceRefs": source_refs,
            })

        if canonical.get("creationSystem") is not None:
            add("/canonical/creationSystem", "selected creation system", canonical["creationSystem"], classes.get("refs"))
        if canonical.get("statblockUse") is not None:
            add("/canonical/statblockUse", "selected full or encounter statblock use", canonical["statblockUse"], classes.get("refs"))
        if canonical.get("npcCategory") is not None:
            add("/canonical/npcCategory", "NPC category from selected class categories", canonical["npcCategory"], classes.get("refs"), [{"source": "class categories", "value": canonical["npcCategory"], "sourceRefs": classes.get("refs", [])}])
        if canonical.get("raceId") is not None:
            add("/canonical/raceId", "selected source race", canonical["raceId"], race.get("sourceRef") if race else None)
        if canonical.get("racialChoices") is not None:
            add("/canonical/racialChoices", "user racial choices validated against race choice slots", canonical["racialChoices"], race.get("sourceRef") if race else None, [{"source": "racial choice selections", "value": canonical["racialChoices"], "sourceRefs": _refs(race.get("sourceRef"), race.get("_npcChoiceRefs")) if race else []}])
        if canonical.get("classProgression") is not None:
            add("/canonical/classProgression", "ordered source class progression", canonical["classProgression"], classes.get("refs"), classes.get("traceInputs", {}).get("level"))
        if canonical.get("classFeatureChoices") is not None:
            add("/canonical/classFeatureChoices", "user class feature choices validated against class slots", canonical["classFeatureChoices"], classes.get("refs"))
        ability_inputs = abilities.get("traceInputs") or []
        if canonical.get("abilityScores") is not None:
            add("/canonical/abilityScores", "NPC array + racial adjustments + level increases + permanent item bonuses", canonical["abilityScores"], abilities.get("refs"), ability_inputs)
        if canonical.get("abilityModifiers") is not None:
            add("/canonical/abilityModifiers", "floor((ability score − 10) / 2)", canonical["abilityModifiers"], abilities.get("refs"), [{"source": "final ability scores", "value": canonical["abilityScores"], "sourceRefs": abilities.get("refs", [])}])
        if canonical.get("level") is not None:
            add("/canonical/level", "sum of ordered class levels", canonical["level"], classes.get("refs"), classes.get("traceInputs", {}).get("level"))
        if canonical.get("hitDice") is not None:
            add("/canonical/hitDice", "sum of class Hit Dice", canonical["hitDice"], classes.get("refs"), classes.get("traceInputs", {}).get("hitDice"))
        if canonical.get("hp") is not None:
            hp_inputs = list(classes.get("traceInputs", {}).get("hp", []))
            con_modifier = (abilities.get("modifiers") or {}).get("constitution")
            hp_rule = self._find_rule(("average-hp", "hit-points", "hp-average", "hit-point-policy"))
            con_policy = hp_rule.get("constitutionPerLevel", hp_rule.get("conModifierPerLevel")) if hp_rule else None
            con_value = 0
            if _is_int(con_modifier):
                if con_policy is True:
                    con_value = con_modifier * canonical.get("level", 0)
                elif _is_int(con_policy):
                    con_value = con_modifier * canonical.get("level", 0) * con_policy
            hp_inputs.append({
                "source": "Constitution modifier × total level",
                "value": con_value,
                "sourceRefs": _refs(abilities.get("refs"), hp_rule.get("sourceRef") if hp_rule else None),
            })
            effect_entries = [
                *(item for item in feats.get("selected", []) if isinstance(item, dict)),
                *(item for item in classes.get("features", []) if isinstance(item, dict)),
                *(item for item in gear.get("items", []) if isinstance(item, dict)),
            ]
            for entry in effect_entries:
                effect_value = self._effect_int(entry.get("effects", {}) if isinstance(entry.get("effects"), dict) else {}, "hp", "hitPoints", default=0)
                if effect_value:
                    hp_inputs.append({"source": "HP effect", "value": effect_value, "sourceRefs": _refs(entry.get("sourceRefs"))})
            add("/canonical/hp", "source average-HP policy + class Hit Dice + Constitution", canonical["hp"], _refs(classes.get("refs"), abilities.get("refs"), gear.get("refs"), feats.get("refs")), hp_inputs)
        if canonical.get("bab") is not None:
            add("/canonical/bab", "sum of ordered class BAB rows", canonical["bab"], classes.get("refs"), classes.get("traceInputs", {}).get("bab"))
        if canonical.get("saves") is not None:
            add("/canonical/saves", "sum of ordered class save rows", canonical["saves"], classes.get("refs"), [item for values in classes.get("traceInputs", {}).get("saves", {}).values() for item in values])
        if canonical.get("defenses"):
            add("/canonical/defenses", "10 + ability modifiers + armor/shield/size/item effects + class saves", canonical["defenses"], _refs(combat.get("refs"), abilities.get("refs"), classes.get("refs"), feats.get("refs")), combat.get("traceInputs", {}).get("defenses"))
        if canonical.get("initiative") is not None:
            add("/canonical/initiative", "Dexterity modifier + initiative effects", canonical["initiative"], _refs(combat.get("refs"), abilities.get("refs"), feats.get("refs")), combat.get("traceInputs", {}).get("initiative"))
        if canonical.get("attacks"):
            add("/canonical/attacks", "class BAB + weapon ability + weapon/feat effects", canonical["attacks"], _refs(combat.get("refs"), abilities.get("refs"), feats.get("refs")), combat.get("traceInputs", {}).get("attacks"))
        if canonical.get("cmb") is not None:
            add("/canonical/cmb", "BAB + Strength modifier + size/item effects", canonical["cmb"], _refs(combat.get("refs"), abilities.get("refs"), classes.get("refs"), feats.get("refs")), combat.get("traceInputs", {}).get("cmb"))
        if canonical.get("cmd") is not None:
            add("/canonical/cmd", "10 + BAB + Strength + Dexterity + size/item effects", canonical["cmd"], _refs(combat.get("refs"), abilities.get("refs"), classes.get("refs"), feats.get("refs")), combat.get("traceInputs", {}).get("cmd"))
        if canonical.get("skills") is not None:
            add("/canonical/skills", "ranks + key ability + class-skill bonus + armor/item effects", canonical["skills"], _refs(skills.get("refs"), abilities.get("refs"), gear.get("refs")), skills.get("traceInputs"))
        if canonical.get("skillRanks") is not None:
            add("/canonical/skillRanks", "user skill allocations after class and level budgets", canonical["skillRanks"], skills.get("refs"), skills.get("traceInputs"))
        if canonical.get("feats") is not None:
            add("/canonical/feats", "feat slots at acquisition level + typed prerequisites", canonical["feats"], feats.get("refs"), [{"source": "feat slots", "value": feats.get("slots", []), "sourceRefs": feats.get("refs", [])}])
        if canonical.get("featSlots") is not None:
            add("/canonical/featSlots", "source-defined general and class feat slots", canonical["featSlots"], feats.get("refs"), [{"source": "feat slots", "value": canonical["featSlots"], "sourceRefs": feats.get("refs", [])}])
        if canonical.get("classFeatures") is not None:
            add("/canonical/classFeatures", "class level feature grants and selected class choices", canonical["classFeatures"], classes.get("refs"), [{"source": "class level rows", "value": canonical["classFeatures"], "sourceRefs": classes.get("refs", [])}])
        if canonical.get("gear") is not None:
            add("/canonical/gear", "selected catalog items × integer copper prices", canonical["gear"], gear.get("refs"), [{"source": "selected gear", "value": canonical["gear"], "sourceRefs": gear.get("refs", [])}])
        if canonical.get("gearBudget") is not None:
            add("/canonical/gearBudget", "NPC gear budget row and approximate category deltas", canonical["gearBudget"], gear.get("refs"), [{"source": "gear budget row", "value": canonical["gearBudget"], "sourceRefs": gear.get("refs", [])}])
        if canonical.get("sizeId") is not None:
            add("/canonical/sizeId", "selected racial size", canonical["sizeId"], race.get("sourceRef") if race else None)
        if canonical.get("senses") is not None:
            add("/canonical/senses", "racial senses and selected racial choices", canonical["senses"], race.get("sourceRef") if race else None, [{"source": "race", "value": canonical["senses"], "sourceRefs": _refs(race.get("sourceRef"), race.get("_npcChoiceRefs")) if race else []}])
        if canonical.get("speed") is not None:
            add("/canonical/speed", "racial speed and selected racial choices", canonical["speed"], race.get("sourceRef") if race else None, [{"source": "race", "value": canonical["speed"], "sourceRefs": _refs(race.get("sourceRef"), race.get("_npcChoiceRefs")) if race else []}])
        if canonical.get("languages") is not None:
            add("/canonical/languages", "racial languages plus explicitly selected additional languages", canonical["languages"], race.get("sourceRef") if race else None, [{"source": "languages", "value": canonical["languages"], "sourceRefs": _refs(race.get("sourceRef"), race.get("_npcChoiceRefs")) if race else []}])
        if canonical.get("details") is not None:
            add("/canonical/details", "user-owned NPC presentation details", canonical["details"], race.get("sourceRef") if race else None)
        if canonical.get("traits") is not None:
            add("/canonical/traits", "racial traits and selected racial choices", canonical["traits"], race.get("sourceRef") if race else None, [{"source": "traits", "value": canonical["traits"], "sourceRefs": _refs(race.get("sourceRef"), race.get("_npcChoiceRefs")) if race else []}])
        if canonical.get("spells") is not None:
            add("/canonical/spells", "source class spellcasting + selected catalog spell loadout", canonical["spells"], spells.get("refs"), spells.get("traceInputs"))
        return trace

    def _evaluation(self, status: str, issues: list[dict[str, Any]], trace: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "status": status,
            "mode": "strict",
            "canonical": None,
            "effective": None,
            "issues": self._sorted_issues(issues),
            "derivationTrace": trace,
        }

    def _issue(self, code, path, message, kind, severity, source_refs=None, *, details=None):
        value = {"code": code, "path": path, "message": message, "kind": kind, "severity": severity}
        refs = _refs(source_refs)
        if refs:
            value["sourceRefs"] = refs
        if details is not None:
            value["details"] = copy.deepcopy(details)
        return value

    def _append_issue(self, issues: list[dict[str, Any]], issue: dict[str, Any]) -> None:
        key = (issue["code"], issue["path"], issue["message"])
        if key not in self._issue_keys:
            self._issue_keys.add(key)
            issues.append(issue)

    @staticmethod
    def _sorted_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(issues, key=lambda issue: (issue.get("path", ""), issue.get("code", "")))

    @staticmethod
    def _add_requirement(output, path, label, value_type, *, values=None, source_refs=None, minimum=None, maximum=None, min_count=None, max_count=None):
        requirement = {"path": path, "label": label, "type": value_type, "required": True}
        if values is not None:
            if isinstance(values, tuple) and values and all(isinstance(value, str) for value in values):
                requirement["values"] = [{"value": value, "label": _label(value)} for value in values]
            else:
                requirement["values"] = copy.deepcopy(list(values))
        if minimum is not None:
            requirement["minValue"] = minimum
        if maximum is not None:
            requirement["maxValue"] = maximum
        if min_count is not None:
            requirement["minCount"] = min_count
        if max_count is not None:
            requirement["maxCount"] = max_count
        refs = _refs(source_refs)
        if refs:
            requirement["sourceRefs"] = refs
        output.append(requirement)

    @staticmethod
    def _sorted_requirements(requirements: list[dict[str, Any]]) -> list[dict[str, Any]]:
        unique = {item["path"]: item for item in requirements}
        return [unique[path] for path in sorted(unique)]


__all__ = ["NpcCreation"]
