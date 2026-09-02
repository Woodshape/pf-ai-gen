"""Source-backed class-based NPC creation for bounded production slices."""

from __future__ import annotations

import copy
import json
import math
from typing import Any

from monster_builder.catalog import CatalogError
from monster_builder.creation_systems.base import NPC, CreationSystem
from monster_builder.errors import BoundaryError
from monster_builder.npc.prerequisites import evaluate_prerequisite
from monster_builder.npc_catalog import NpcCatalog

ABILITIES = ("strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma")
ABILITY_SET = set(ABILITIES)
COMPUTED_FIELDS = {
    "level", "totalLevel", "npcCategory", "abilityScores", "abilityModifiers", "hp", "bab",
    "defenses", "initiative", "attacks", "cmb", "cmd", "skills", "speed", "senses", "languages",
    "size", "classFeatures", "spells", "gearBudget", "canonical", "effective", "derivationTrace",
    "evaluation", "ac", "fortitude", "reflex", "will",
}


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _refs(record: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not record:
        return []
    value = record.get("sourceRef", [])
    if isinstance(value, dict):
        return [copy.deepcopy(value)]
    return copy.deepcopy(value) if isinstance(value, list) else []


def _dedupe_refs(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ref in (item for group in groups for item in group):
        key = _canonical_json(ref)
        if key not in seen:
            seen.add(key)
            result.append(copy.deepcopy(ref))
    return result


def _ability_modifier(score: int) -> int:
    return math.floor((score - 10) / 2)


def _bonus(value: int) -> str:
    return f"+{value}" if value >= 0 else str(value)


class NpcCreation(CreationSystem):
    """Evaluate the bounded, locally sourced Core NPC slice."""

    key = NPC
    selection_fields = frozenset({
        "statblockUse", "raceId", "racialChoices", "classProgression", "abilityGeneration",
        "levelIncreases", "skillGeneration", "feats", "classFeatureChoices", "spellLoadout",
        "gearProfile", "gear", "details",
    })
    computed_selection_fields = frozenset(COMPUTED_FIELDS)

    def __init__(self, catalog: NpcCatalog):
        self.catalog = catalog

    # ------------------------------------------------------------------
    # Public creation-system seam
    # ------------------------------------------------------------------
    def validate_input(self, draft: dict[str, Any]) -> None:
        selections = draft.get("selections", {})
        if not isinstance(selections, dict):
            raise BoundaryError("selection.type-invalid", "selections must be an object", "/selections")
        for field in selections:
            if field in COMPUTED_FIELDS:
                raise BoundaryError("draft.computed-selection", "computed values are not draft selections", f"/selections/{field}")
            if field not in self.selection_fields:
                raise BoundaryError("draft.selection-unknown", f"unknown selection field: {field}", f"/selections/{field}")
        self._validate_shapes(selections)
        self._validate_ids(selections)

    def choice_requirements(self, draft: dict[str, Any]) -> dict[str, Any]:
        selections = draft.get("selections", {})
        progression = selections.get("classProgression", [])
        level = sum(item.get("levels", 0) for item in progression if isinstance(item, dict) and _is_int(item.get("levels")))
        race = self._optional("race", selections.get("raceId"))
        class_record = self._optional("class", progression[0].get("classId")) if progression and isinstance(progression[0], dict) else None
        feat_slots = self._feat_slots(level, race)
        gear_budget = self._gear_budget(selections, level)
        spell_counts = copy.deepcopy((class_record or {}).get("levels", {}).get(str(level), {}).get("spellsKnown", {}))
        skill_count = None
        if class_record and class_record.get("catalogStatus") == "resolved":
            intelligence = self._preview_intelligence(selections, race)
            if intelligence is not None:
                skill_count = max(1, class_record.get("skillSelections", 0) + _ability_modifier(intelligence)) + (race or {}).get("skillSelectionsBonus", 0)

        requirements = [
            self._requirement("/selections/statblockUse", "Statblock use", "enum", ["full", "encounter"]),
            self._requirement("/selections/raceId", "Race", "catalog-id", self._catalog_values("race")),
            self._requirement("/selections/classProgression/0/classId", "Class", "catalog-id", self._catalog_values("class")),
            self._requirement("/selections/classProgression/0/levels", "Class levels", "integer"),
            self._requirement("/selections/abilityGeneration/method", "Ability method", "enum", ["melee-preset", "arcane-preset", "assigned-array"]),
            self._requirement("/selections/skillGeneration/method", "Skill method", "enum", ["simplified"]),
            self._requirement("/selections/skillGeneration/skills", "Skills", "catalog-id-array", self._catalog_values("skill")),
            self._requirement("/selections/gearProfile/experienceProgression", "Experience progression", "enum", ["medium"]),
            self._requirement("/selections/gearProfile/fantasyLevel", "Fantasy level", "enum", ["normal"]),
            self._requirement("/selections/gear", "Gear", "catalog-id-array", self._catalog_values("item")),
        ]
        if race:
            for slot in race.get("choiceSlots", []):
                requirements.append(self._requirement(
                    f"/selections/racialChoices/{slot['choiceId']}", slot.get("name", slot["choiceId"]), "enum", slot.get("allowedValues", [])
                ))
        if class_record and class_record["id"] == "npc-class.sorcerer":
            requirements.append(self._requirement(
                "/selections/classFeatureChoices/bloodline", "Bloodline", "enum", ["elemental-fire"]
            ))
            requirements.append(self._requirement(
                "/selections/spellLoadout/known", "Spells known", "spell-loadout"
            ))

        selected_skills = selections.get("skillGeneration", {}).get("skills", []) if isinstance(selections.get("skillGeneration"), dict) else []
        selected_feats = selections.get("feats", []) if isinstance(selections.get("feats"), list) else []
        gear = selections.get("gear", []) if isinstance(selections.get("gear"), list) else []
        return {
            "creationSystem": NPC,
            "requirements": sorted(requirements, key=lambda value: value["path"]),
            "automaticSelections": {
                "racialTraits": copy.deepcopy((race or {}).get("traits", [])),
                "classFeatures": self._class_features(class_record, level),
                "featGrants": copy.deepcopy(feat_slots),
            },
            "selectionBudgets": {
                "skills": {"method": "simplified", "count": skill_count, "selected": len(selected_skills)},
                "feats": {"slots": feat_slots, "selected": len(selected_feats)},
                "spells": {"required": bool(spell_counts), "levels": spell_counts},
                "gear": {
                    **(gear_budget or {"budgetCp": None, "categories": None}),
                    "spentCp": self._preview_gear_cost(gear),
                },
            },
        }

    @staticmethod
    def fingerprint_selections(selections: dict[str, Any]) -> dict[str, Any]:
        normalized = copy.deepcopy(selections)
        for item in normalized.get("classProgression", []):
            if isinstance(item, dict) and isinstance(item.get("classId"), str):
                item["classId"] = item["classId"].strip()
        for item in normalized.get("feats", []):
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
        source_refs = _dedupe_refs(*[entry.get("sourceRefs", []) for entry in trace])
        return [{
            "step": step,
            "selections": {name: copy.deepcopy(selections[name]) for name in names if name in selections},
            "sourceRefs": copy.deepcopy(source_refs),
        } for step, names in fields]

    def evaluate(self, draft: dict[str, Any]) -> dict[str, Any]:
        mode = draft.get("mode", "strict")
        selections = draft.get("selections", {})
        missing = self._missing_required(selections)
        if missing:
            return self._evaluation("incomplete", mode, [self._issue(
                "npc.selection-required", "required NPC selections are missing", path=missing[0], details={"paths": missing}
            )])

        issues: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        race = self._record("race", selections["raceId"])
        progression = selections["classProgression"]
        total_level = sum(item["levels"] for item in progression)

        if len(progression) != 1:
            issues.append(self._issue(
                "npc.multiclass-unsupported", "the source-backed production slice supports one class", path="/selections/classProgression"
            ))
        if selections["skillGeneration"].get("method") == "simplified" and len(progression) > 1:
            issues.append(self._issue(
                "npc.simplified-skills-multiclass", "simplified skills cannot represent multiclass class-skill changes", path="/selections/skillGeneration/method"
            ))

        class_records: list[dict[str, Any]] = []
        rows: list[dict[str, Any]] = []
        for index, item in enumerate(progression):
            record = self._record("class", item["classId"])
            class_records.append(record)
            if record.get("catalogStatus") != "resolved":
                issues.append(self._gap(record, f"/selections/classProgression/{index}/classId"))
                continue
            row = record.get("levels", {}).get(str(item["levels"]))
            if not row or row.get("catalogStatus") != "resolved":
                issues.append(self._gap(row or record, f"/selections/classProgression/{index}/levels"))
            else:
                rows.append(row)

        if race.get("catalogStatus") != "resolved":
            issues.append(self._gap(race, "/selections/raceId"))
        slice_id = (selections["raceId"], progression[0]["classId"], total_level)
        supported = (
            slice_id[0] == "npc-race.human" and slice_id[1] == "npc-class.warrior" and 1 <= total_level <= 5
        ) or slice_id == ("npc-race.goblin", "npc-class.sorcerer", 5)
        if not supported:
            issues.append(self._issue(
                "npc.slice-unsupported", "production evaluation supports human warriors 1–5 and goblin sorcerers at level 5",
                path="/selections/classProgression", source_refs=_refs(class_records[0]) if class_records else [],
            ))
        if issues:
            return self._evaluation("invalid", mode, issues)

        class_record, row = class_records[0], rows[0]
        scores, ability_refs, ability_issues = self._abilities(selections, race, total_level)
        issues.extend(ability_issues)
        if not scores:
            return self._evaluation("invalid", mode, issues)
        gear_result, gear_refs, gear_issues, gear_warnings = self._gear(selections, total_level)
        issues.extend(gear_issues)
        warnings.extend(gear_warnings)
        feats, feat_effects, feat_refs, feat_issues = self._feats(selections, race, total_level, scores)
        issues.extend(feat_issues)
        skills, skill_refs, skill_issues = self._skills(selections, race, class_record, total_level, scores, gear_result)
        issues.extend(skill_issues)
        modifiers = {ability: _ability_modifier(score) for ability, score in scores.items()}
        class_features, feature_refs, feature_issues = self._selected_class_features(selections, race, class_record, total_level, modifiers)
        issues.extend(feature_issues)
        spells, spell_refs, spell_issues = self._spells(selections, class_record, row, total_level, modifiers)
        issues.extend(spell_issues)
        if issues:
            return self._evaluation("invalid", mode, issues, warnings)

        class_refs = _dedupe_refs(_refs(class_record), _refs(row))
        combat_ref = self._source_ref("source.aon-combat", "Combat Statistics", [24, 58])
        maneuver_ref = self._source_ref("source.aon-combat", "Combat Maneuvers", [536, 544])
        hp_rule = self._record("derivedRule", "npc-rule.average-hp")
        die_size = int(class_record["hitDie"].removeprefix("d"))
        hp = math.floor(total_level * ((die_size + 1) / 2 + modifiers["constitution"]))
        bab = row["bab"]
        size_modifiers = race.get("sizeModifiers", {})
        equipped = [entry for entry in gear_result["items"] if entry["equipped"]]
        armor_bonus = sum(entry["effects"].get("armorBonus", 0) for entry in equipped)
        shield_bonus = sum(entry["effects"].get("shieldBonus", 0) for entry in equipped)
        max_dex_values = [entry["effects"]["maxDex"] for entry in equipped if "maxDex" in entry["effects"]]
        dex_to_ac = min([modifiers["dexterity"], *max_dex_values]) if max_dex_values else modifiers["dexterity"]
        feat_saves = feat_effects.get("saves", {})
        resistance_bonus = max((entry["effects"].get("resistanceBonus", 0) for entry in equipped), default=0)
        defenses = {
            "ac": 10 + armor_bonus + shield_bonus + dex_to_ac + size_modifiers.get("ac", 0),
            "touch": 10 + modifiers["dexterity"] + size_modifiers.get("ac", 0),
            "flatFooted": 10 + armor_bonus + shield_bonus + size_modifiers.get("ac", 0),
            "fortitude": row["fortitude"] + modifiers["constitution"] + feat_saves.get("fortitude", 0) + resistance_bonus,
            "reflex": row["reflex"] + modifiers["dexterity"] + feat_saves.get("reflex", 0) + resistance_bonus,
            "will": row["will"] + modifiers["wisdom"] + feat_saves.get("will", 0) + resistance_bonus,
        }
        attacks = self._attacks(equipped, bab, modifiers, size_modifiers)
        cmb = bab + modifiers["strength"] + size_modifiers.get("cmb", 0)
        cmd = 10 + bab + modifiers["strength"] + modifiers["dexterity"] + size_modifiers.get("cmd", 0)
        source_groups = {
            "abilities": ability_refs,
            "class": class_refs,
            "hp": _dedupe_refs(class_refs, _refs(hp_rule), ability_refs),
            "gear": gear_refs,
            "feats": feat_refs,
            "skills": skill_refs,
            "combat": _dedupe_refs(class_refs, ability_refs, gear_refs, [combat_ref]),
            "maneuvers": _dedupe_refs(class_refs, ability_refs, [maneuver_ref]),
            "features": _dedupe_refs(feature_refs, ability_refs, class_refs, [combat_ref]),
            "spells": _dedupe_refs(spell_refs, ability_refs, class_refs),
        }
        canonical = {
            "name": draft.get("concept", {}).get("name", "Unnamed NPC"),
            "creationSystem": NPC,
            "statblockUse": selections["statblockUse"],
            "level": total_level,
            "totalLevel": total_level,
            "npcCategory": "heroic" if class_record["category"] == "pc" else "basic",
            "raceId": race["id"],
            "raceName": race["name"],
            "classProgression": [{"classId": class_record["id"], "className": class_record["name"], "levels": total_level}],
            "abilityScores": scores,
            "abilityModifiers": modifiers,
            "hp": hp,
            "bab": bab,
            "defenses": defenses,
            "initiative": modifiers["dexterity"] + feat_effects.get("initiative", 0),
            "attacks": attacks,
            "cmb": cmb,
            "cmd": cmd,
            "skills": skills,
            "feats": feats,
            "classFeatures": class_features,
            "spells": spells,
            "gearBudget": gear_result["budget"],
            "gear": gear_result["items"],
            "speed": copy.deepcopy(race.get("speed", {"land": 30})),
            "senses": copy.deepcopy(race.get("senses", [])),
            "languages": copy.deepcopy(race.get("languages", [])),
            "size": {"id": race.get("sizeId", "size.medium"), "name": race.get("sizeId", "size.medium").split(".")[-1].title()},
            "details": copy.deepcopy(selections.get("details", {})),
        }
        trace = [
            self._trace("/canonical/level", total_level, "sum selected class levels", class_refs),
            self._trace("/canonical/abilityScores", scores, "apply the NPC array, racial adjustments, and level increases", ability_refs),
            self._trace("/canonical/hp", hp, f"floor(level × (average d{die_size} + Constitution modifier))", source_groups["hp"]),
            self._trace("/canonical/bab", bab, "read the selected class level row", class_refs),
            self._trace("/canonical/defenses", defenses, "combine class saves, abilities, armor, shield, and feat bonuses", source_groups["combat"]),
            self._trace("/canonical/initiative", canonical["initiative"], "Dexterity modifier plus feat bonuses", _dedupe_refs(ability_refs, feat_refs, [combat_ref])),
            self._trace("/canonical/attacks", attacks, "BAB plus ability and size modifiers; weapon die plus Strength", source_groups["combat"]),
            self._trace("/canonical/cmb", cmb, "BAB + Strength modifier + size modifier", source_groups["maneuvers"]),
            self._trace("/canonical/cmd", cmd, "10 + BAB + Strength modifier + Dexterity modifier + size modifier", source_groups["maneuvers"]),
            self._trace("/canonical/skills", skills, "level ranks plus class-skill bonus, ability modifier, and armor check penalty", skill_refs),
            self._trace("/canonical/feats", feats, "fill granted feat slots", feat_refs),
            self._trace("/canonical/classFeatures", class_features, "apply automatic features and selected class-feature options", source_groups["features"]),
            self._trace("/canonical/spells", spells, "validate spells known, add bloodline spells, and apply Charisma bonus spells", source_groups["spells"]),
            self._trace("/canonical/gearBudget", gear_result["budget"], "read the NPC category and level row from Table 14-9", gear_refs),
        ]
        return self._evaluation("valid", mode, [], warnings, canonical, trace)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def _validate_shapes(self, selections: dict[str, Any]) -> None:
        if "statblockUse" in selections and selections["statblockUse"] not in {"full", "encounter"}:
            raise BoundaryError("selection.value-invalid", "statblockUse must be full or encounter", "/selections/statblockUse")
        if "raceId" in selections and not isinstance(selections["raceId"], str):
            raise BoundaryError("selection.type-invalid", "raceId must be a string", "/selections/raceId")
        for field in ("racialChoices", "classFeatureChoices", "spellLoadout", "details"):
            if field in selections and not isinstance(selections[field], dict):
                raise BoundaryError("selection.type-invalid", f"{field} must be an object", f"/selections/{field}")
        details = selections.get("details", {})
        for field in details:
            if field in COMPUTED_FIELDS - {"languages"}:
                raise BoundaryError("draft.computed-selection", "computed values are not draft selections", f"/selections/details/{field}")

        progression = selections.get("classProgression")
        if progression is not None:
            if not isinstance(progression, list):
                raise BoundaryError("selection.type-invalid", "classProgression must be an array", "/selections/classProgression")
            for index, item in enumerate(progression):
                path = f"/selections/classProgression/{index}"
                if not isinstance(item, dict) or not isinstance(item.get("classId"), str) or not _is_int(item.get("levels")):
                    raise BoundaryError("selection.type-invalid", "each class progression entry requires classId and integer levels", path)
                self._reject_unknown(item, {"classId", "levels"}, path)
                if item["levels"] < 1:
                    raise BoundaryError("selection.value-invalid", "class levels must be positive", f"{path}/levels")

        ability = selections.get("abilityGeneration")
        if ability is not None:
            if not isinstance(ability, dict):
                raise BoundaryError("selection.type-invalid", "abilityGeneration must be an object", "/selections/abilityGeneration")
            self._reject_unknown(ability, {"method", "arrayId", "scores", "assignments", "levelIncreases", "preset", "role", "rationale"}, "/selections/abilityGeneration")
            if "method" in ability and ability["method"] not in {"melee-preset", "arcane-preset", "skill-preset", "assigned-array", "custom", "rolled", "purchase"}:
                raise BoundaryError("selection.value-invalid", "abilityGeneration.method is not supported", "/selections/abilityGeneration/method")
            if "arrayId" in ability and not isinstance(ability["arrayId"], str):
                raise BoundaryError("selection.type-invalid", "abilityGeneration.arrayId must be a string", "/selections/abilityGeneration/arrayId")
            for field in ("scores", "assignments"):
                if field in ability:
                    value = ability[field]
                    if not isinstance(value, dict) or set(value) != ABILITY_SET or any(not _is_int(score) for score in value.values()):
                        raise BoundaryError("selection.type-invalid", f"abilityGeneration.{field} must map all six abilities to integers", f"/selections/abilityGeneration/{field}")
            self._reject_alias_conflict(ability, ("scores", "assignments"), "/selections/abilityGeneration")
            self._reject_alias_conflict(ability, ("preset", "role"), "/selections/abilityGeneration")
            if "levelIncreases" in ability:
                self._validate_increases(ability["levelIncreases"], "/selections/abilityGeneration/levelIncreases")
        if "levelIncreases" in selections:
            self._validate_increases(selections["levelIncreases"], "/selections/levelIncreases")

        skills = selections.get("skillGeneration")
        if skills is not None:
            if not isinstance(skills, dict):
                raise BoundaryError("selection.type-invalid", "skillGeneration must be an object", "/selections/skillGeneration")
            self._reject_unknown(skills, {"method", "skills", "selectedSkills", "ranks"}, "/selections/skillGeneration")
            self._reject_alias_conflict(skills, ("skills", "selectedSkills"), "/selections/skillGeneration")
            if skills.get("method") not in {None, "simplified", "precise"}:
                raise BoundaryError("selection.value-invalid", "skillGeneration.method must be simplified or precise", "/selections/skillGeneration/method")
            values = skills.get("skills", skills.get("selectedSkills", []))
            if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
                raise BoundaryError("selection.type-invalid", "skills must be an array of IDs", "/selections/skillGeneration/skills")
            if "ranks" in skills and (not isinstance(skills["ranks"], dict) or any(not isinstance(key, str) or not _is_int(value) or value < 0 for key, value in skills["ranks"].items())):
                raise BoundaryError("selection.type-invalid", "precise ranks must map skill IDs to non-negative integers", "/selections/skillGeneration/ranks")

        spell_loadout = selections.get("spellLoadout")
        if isinstance(spell_loadout, dict) and "known" in spell_loadout:
            known = spell_loadout["known"]
            if not isinstance(known, dict) or any(
                not str(level).isdigit() or not isinstance(spells, list) or any(not isinstance(spell, str) for spell in spells)
                for level, spells in known.items()
            ):
                raise BoundaryError("selection.type-invalid", "spellLoadout.known must map spell levels to arrays of IDs", "/selections/spellLoadout/known")

        feats = selections.get("feats")
        if feats is not None:
            if not isinstance(feats, list):
                raise BoundaryError("selection.type-invalid", "feats must be an array", "/selections/feats")
            for index, item in enumerate(feats):
                path = f"/selections/feats/{index}"
                if not isinstance(item, dict) or not isinstance(item.get("slotId"), str) or not isinstance(item.get("featId"), str):
                    raise BoundaryError("selection.type-invalid", "each feat requires slotId and featId", path)
                self._reject_unknown(item, {"slotId", "featId"}, path)

        profile = selections.get("gearProfile")
        if profile is not None:
            if not isinstance(profile, dict):
                raise BoundaryError("selection.type-invalid", "gearProfile must be an object", "/selections/gearProfile")
            self._reject_unknown(profile, {"experienceProgression", "progression", "fantasyLevel", "gearBudgetId"}, "/selections/gearProfile")
            self._reject_alias_conflict(profile, ("experienceProgression", "progression"), "/selections/gearProfile")
            progression_name = profile.get("experienceProgression", profile.get("progression"))
            if progression_name not in {None, "slow", "medium", "fast"}:
                raise BoundaryError("selection.value-invalid", "gear progression must be slow, medium, or fast", "/selections/gearProfile/experienceProgression")
            if profile.get("fantasyLevel") not in {None, "low", "normal", "high"}:
                raise BoundaryError("selection.value-invalid", "fantasy level must be low, normal, or high", "/selections/gearProfile/fantasyLevel")

        gear = selections.get("gear")
        if gear is not None:
            if not isinstance(gear, list):
                raise BoundaryError("selection.type-invalid", "gear must be an array", "/selections/gear")
            for index, item in enumerate(gear):
                path = f"/selections/gear/{index}"
                if not isinstance(item, dict) or not isinstance(item.get("itemId"), str):
                    raise BoundaryError("selection.type-invalid", "each gear entry requires itemId", path)
                self._reject_unknown(item, {"itemId", "quantity", "equipped", "masterwork", "enhancementBonus", "properties", "propertyIds", "charges"}, path)
                if "quantity" in item and (not _is_int(item["quantity"]) or item["quantity"] < 1):
                    raise BoundaryError("selection.value-invalid", "gear quantity must be positive", f"{path}/quantity")
                if "equipped" in item and not isinstance(item["equipped"], bool):
                    raise BoundaryError("selection.type-invalid", "equipped must be a boolean", f"{path}/equipped")
                if "masterwork" in item and not isinstance(item["masterwork"], bool):
                    raise BoundaryError("selection.type-invalid", "masterwork must be a boolean", f"{path}/masterwork")
                if "enhancementBonus" in item and (not _is_int(item["enhancementBonus"]) or item["enhancementBonus"] < 0):
                    raise BoundaryError("selection.value-invalid", "enhancementBonus must be non-negative", f"{path}/enhancementBonus")
                for field in ("properties", "propertyIds"):
                    if field in item and (not isinstance(item[field], list) or any(not isinstance(value, str) or not value for value in item[field])):
                        raise BoundaryError("selection.type-invalid", f"{field} must be an array of IDs", f"{path}/{field}")

    def _validate_ids(self, selections: dict[str, Any]) -> None:
        lookups: list[tuple[str, Any, str]] = [("race", selections.get("raceId"), "/selections/raceId")]
        ability = selections.get("abilityGeneration", {})
        lookups.append(("abilityArray", ability.get("arrayId") if isinstance(ability, dict) else None, "/selections/abilityGeneration/arrayId"))
        for index, item in enumerate(selections.get("classProgression", [])):
            lookups.append(("class", item["classId"], f"/selections/classProgression/{index}/classId"))
        skills = selections.get("skillGeneration", {})
        if isinstance(skills, dict):
            for index, skill_id in enumerate(skills.get("skills", skills.get("selectedSkills", []))):
                lookups.append(("skill", skill_id, f"/selections/skillGeneration/skills/{index}"))
            for skill_id in skills.get("ranks", {}):
                lookups.append(("skill", skill_id, f"/selections/skillGeneration/ranks/{skill_id}"))
        for index, item in enumerate(selections.get("feats", [])):
            lookups.append(("feat", item["featId"], f"/selections/feats/{index}/featId"))
        spell_loadout = selections.get("spellLoadout", {})
        if isinstance(spell_loadout, dict):
            for level, spells in spell_loadout.get("known", {}).items():
                for index, spell_id in enumerate(spells):
                    lookups.append(("spell", spell_id, f"/selections/spellLoadout/known/{level}/{index}"))
        for index, item in enumerate(selections.get("gear", [])):
            lookups.append(("item", item["itemId"], f"/selections/gear/{index}/itemId"))
        profile = selections.get("gearProfile", {})
        lookups.append(("gearBudget", profile.get("gearBudgetId") if isinstance(profile, dict) else None, "/selections/gearProfile/gearBudgetId"))
        for record_type, record_id, path in lookups:
            if isinstance(record_id, str):
                try:
                    self.catalog.resolve_id(record_type, record_id)
                except CatalogError as exc:
                    raise BoundaryError("catalog.unknown-id", str(exc), path, kind="catalog-data") from exc

    def _reject_unknown(self, value: dict[str, Any], allowed: set[str], path: str) -> None:
        unknown = set(value) - allowed
        if unknown:
            field = sorted(unknown)[0]
            code = "draft.computed-selection" if field in COMPUTED_FIELDS else "draft.selection-unknown"
            message = "computed values are not draft selections" if code == "draft.computed-selection" else f"unknown selection field: {field}"
            raise BoundaryError(code, message, f"{path}/{field}")

    @staticmethod
    def _reject_alias_conflict(value: dict[str, Any], fields: tuple[str, ...], path: str) -> None:
        present = [field for field in fields if field in value]
        if len(present) > 1 and any(value[field] != value[present[0]] for field in present[1:]):
            raise BoundaryError("selection.ambiguous", f"selection aliases must not disagree: {', '.join(present)}", path)

    @staticmethod
    def _validate_increases(value: Any, path: str) -> None:
        if not isinstance(value, dict) or any(not str(level).isdigit() or int(level) < 1 or ability not in ABILITY_SET for level, ability in value.items()):
            raise BoundaryError("selection.type-invalid", "level increases must map positive integer levels to abilities", path)

    # ------------------------------------------------------------------
    # Slice evaluation helpers
    # ------------------------------------------------------------------
    def _abilities(self, selections: dict[str, Any], race: dict[str, Any], level: int) -> tuple[dict[str, int], list[dict[str, Any]], list[dict[str, Any]]]:
        generation = selections["abilityGeneration"]
        array = self._record("abilityArray", generation.get("arrayId", "npc-ability-array.basic"))
        issues: list[dict[str, Any]] = []
        if array.get("catalogStatus") != "resolved":
            return {}, _refs(array), [self._gap(array, "/selections/abilityGeneration/arrayId")]
        method = generation.get("method")
        if method in {"melee-preset", "arcane-preset"}:
            scores = copy.deepcopy(array["presets"][method.removesuffix("-preset")])
        elif method == "assigned-array":
            scores = copy.deepcopy(generation.get("assignments", generation.get("scores", {})))
            if sorted(scores.values()) != sorted(array["scores"]):
                issues.append(self._issue("npc.ability-array-invalid", "assigned scores must use the selected NPC array exactly", path="/selections/abilityGeneration/assignments", source_refs=_refs(array)))
        else:
            return {}, _refs(array), [self._issue("npc.slice-unsupported", "the production slice supports its catalog presets or assigned-array abilities", path="/selections/abilityGeneration/method", source_refs=_refs(array))]

        refs = _dedupe_refs(_refs(array), _refs(race))
        for ability, adjustment in race.get("abilityAdjustments", {}).items():
            scores[ability] += adjustment
        for slot in race.get("choiceSlots", []):
            choice = selections.get("racialChoices", {}).get(slot["choiceId"])
            if choice is None:
                issues.append(self._issue("npc.selection-required", "racial ability choice is required", path=f"/selections/racialChoices/{slot['choiceId']}", source_refs=_refs(slot)))
            elif choice not in slot.get("allowedValues", []):
                issues.append(self._issue("npc.choice-invalid", "racial ability choice is not allowed", path=f"/selections/racialChoices/{slot['choiceId']}", source_refs=_refs(slot)))
            else:
                scores[choice] += slot["options"][choice]["effects"]["abilityAdjustments"][choice]
                refs = _dedupe_refs(refs, _refs(slot))

        increases = generation.get("levelIncreases", selections.get("levelIncreases", {}))
        increase_rule = self._record("derivedRule", "npc-rule.ability-increase")
        expected = [value for value in increase_rule["levels"] if value <= level]
        selected_levels = sorted(int(value) for value in increases)
        if selected_levels != expected:
            issues.append(self._issue("npc.level-increases-invalid", "ability increases must fill each eligible level", path="/selections/abilityGeneration/levelIncreases", details={"expectedLevels": expected}, source_refs=_refs(increase_rule)))
        else:
            for value, ability in increases.items():
                scores[ability] += increase_rule["amount"]
            refs = _dedupe_refs(refs, _refs(increase_rule))
        return scores, refs, issues

    def _skills(self, selections: dict[str, Any], race: dict[str, Any], class_record: dict[str, Any], level: int, scores: dict[str, int], gear: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        generation = selections["skillGeneration"]
        if generation.get("method") != "simplified":
            return [], [], [self._issue("npc.slice-unsupported", "the production slice supports simplified skills", path="/selections/skillGeneration/method")]
        selected = generation.get("skills", generation.get("selectedSkills", []))
        count = max(1, class_record["skillSelections"] + _ability_modifier(scores["intelligence"])) + race.get("skillSelectionsBonus", 0)
        issues: list[dict[str, Any]] = []
        if len(selected) != count or len(set(selected)) != len(selected):
            issues.append(self._issue("npc.skill-count-invalid", "simplified skills must fill the exact selection budget without duplicates", path="/selections/skillGeneration/skills", details={"expected": count, "selected": len(selected)}, source_refs=_refs(class_record)))
        armor_check_penalty = sum(item["effects"].get("armorCheckPenalty", 0) for item in gear["items"] if item["equipped"])
        results: list[dict[str, Any]] = []
        refs = _refs(class_record)
        for index, skill_id in enumerate(selected):
            record = self._record("skill", skill_id)
            refs = _dedupe_refs(refs, _refs(record))
            if record.get("catalogStatus") != "resolved":
                issues.append(self._gap(record, f"/selections/skillGeneration/skills/{index}"))
                continue
            class_skill = skill_id in class_record.get("classSkills", [])
            if not class_skill:
                issues.append(self._issue("npc.skill-not-class-skill", "simplified selections must be class skills", path=f"/selections/skillGeneration/skills/{index}", source_refs=_refs(record)))
            ability = record["keyAbility"]
            acp = armor_check_penalty if record.get("armorCheckPenalty") else 0
            total = level + (3 if class_skill else 0) + _ability_modifier(scores[ability]) + acp
            results.append({"skillId": skill_id, "name": record["name"], "ability": ability, "ranks": level, "classSkill": class_skill, "armorCheckPenalty": acp, "total": total, "sourceRefs": _refs(record)})
        return results, refs, issues

    def _selected_class_features(
        self, selections: dict[str, Any], race: dict[str, Any], class_record: dict[str, Any], level: int, modifiers: dict[str, int]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        features = self._class_features(class_record, level)
        refs = _dedupe_refs(_refs(class_record), *[feature.get("sourceRefs", []) for feature in features])
        choices = selections.get("classFeatureChoices", {})
        if class_record["id"] != "npc-class.sorcerer":
            issues = [self._issue("npc.slice-unsupported", "class feature choices are not part of this production slice", path="/selections/classFeatureChoices")] if choices else []
            return features, refs, issues

        bloodline = self._record("classFeature", "npc-class-feature.sorcerer-bloodlines")
        choice = choices.get("bloodline")
        if choice != "elemental-fire":
            return features, _dedupe_refs(refs, _refs(bloodline)), [self._issue(
                "npc.choice-invalid", "the source-gated Sorcerer slice requires the elemental fire bloodline",
                path="/selections/classFeatureChoices/bloodline", source_refs=_refs(bloodline),
            )]
        option = bloodline["options"][choice]
        powers = []
        for power in option["powers"]:
            if power["level"] > level:
                continue
            selected = copy.deepcopy(power)
            if selected["name"] == "Elemental Ray":
                selected["usesPerDay"] = 3 + modifiers["charisma"]
                selected["attackBonus"] = class_record["levels"][str(level)]["bab"] + modifiers["dexterity"] + race.get("sizeModifiers", {}).get("attack", 0)
            powers.append(selected)
        for feature in features:
            if feature["featureId"] == bloodline["id"]:
                feature.update(choice=choice, name=option["name"], energyType=option["energyType"], powers=powers)
        return features, _dedupe_refs(refs, _refs(bloodline)), []

    def _spells(
        self, selections: dict[str, Any], class_record: dict[str, Any], row: dict[str, Any], level: int,
        modifiers: dict[str, int],
    ) -> tuple[Any, list[dict[str, Any]], list[dict[str, Any]]]:
        loadout = selections.get("spellLoadout", {})
        if class_record["id"] != "npc-class.sorcerer":
            issues = [self._issue("npc.slice-unsupported", "spells are not part of this production slice", path="/selections/spellLoadout")] if loadout else []
            return [], _refs(class_record), issues

        known = loadout.get("known", {}) if isinstance(loadout, dict) else {}
        expected = row["spellsKnown"]
        issues: list[dict[str, Any]] = []
        refs = _refs(class_record)
        if set(known) != set(expected):
            issues.append(self._issue(
                "npc.spell-levels-invalid", "spell loadout must include exactly the available spell levels",
                path="/selections/spellLoadout/known", details={"expectedLevels": sorted(expected)}, source_refs=_refs(row),
            ))
        selected_ids: set[str] = set()
        resolved: dict[str, list[str]] = {}
        for spell_level, expected_count in expected.items():
            selected = known.get(spell_level, [])
            if len(selected) != expected_count or len(set(selected)) != len(selected):
                issues.append(self._issue(
                    "npc.spell-count-invalid", "spells known must fill each level exactly without duplicates",
                    path=f"/selections/spellLoadout/known/{spell_level}",
                    details={"expected": expected_count, "selected": len(selected)}, source_refs=_refs(row),
                ))
            resolved[spell_level] = []
            for index, spell_id in enumerate(selected):
                record = self._record("spell", spell_id)
                refs = _dedupe_refs(refs, _refs(record))
                if record.get("catalogStatus") != "resolved":
                    issues.append(self._gap(record, f"/selections/spellLoadout/known/{spell_level}/{index}"))
                elif record.get("levelsByClass", {}).get("sorcerer") != int(spell_level):
                    issues.append(self._issue(
                        "npc.spell-level-invalid", "spell is not a Sorcerer spell of the selected level",
                        path=f"/selections/spellLoadout/known/{spell_level}/{index}", source_refs=_refs(record),
                    ))
                if spell_id in selected_ids:
                    issues.append(self._issue("npc.spell-duplicate", "the same spell cannot fill multiple known slots", path=f"/selections/spellLoadout/known/{spell_level}/{index}"))
                selected_ids.add(spell_id)
                resolved[spell_level].append(record["id"])

        bloodline = self._record("classFeature", "npc-class-feature.sorcerer-bloodlines")
        option = bloodline["options"]["elemental-fire"]
        refs = _dedupe_refs(refs, _refs(bloodline))
        for granted_level, spell_id in option["bonusSpells"].items():
            if int(granted_level) <= level:
                spell = self._record("spell", spell_id)
                spell_level = str(spell["levelsByClass"]["sorcerer"])
                resolved.setdefault(spell_level, []).append(spell["id"])
                refs = _dedupe_refs(refs, _refs(spell))

        charisma = modifiers["charisma"]
        per_day: dict[str, Any] = {"0": "at-will"}
        for spell_level, base in row["spellsPerDay"].items():
            numeric_level = int(spell_level)
            bonus_spells = 1 + (charisma - numeric_level) // 4 if charisma >= numeric_level else 0
            per_day[spell_level] = base + bonus_spells
        bonus_ref = self._source_ref("source.aon-getting-started", "Table: Ability Modifiers and Bonus Spells", [89, 101])
        refs = _dedupe_refs(refs, [bonus_ref])
        result = {
            "casterLevel": level, "castingAbility": "charisma", "castingAbilityModifier": charisma,
            "perDay": per_day, "saveDcByLevel": {spell_level: 10 + int(spell_level) + charisma for spell_level in expected},
            "known": resolved,
        }
        return result, refs, issues

    def _feats(self, selections: dict[str, Any], race: dict[str, Any], level: int, scores: dict[str, int]) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
        slots = self._feat_slots(level, race)
        selected = selections["feats"]
        issues: list[dict[str, Any]] = []
        expected_slots = {slot["slotId"] for slot in slots}
        actual_slots = [item["slotId"] for item in selected]
        if set(actual_slots) != expected_slots or len(actual_slots) != len(set(actual_slots)):
            issues.append(self._issue("npc.feat-slots-invalid", "each required feat slot must be filled exactly once", path="/selections/feats", details={"expectedSlots": sorted(expected_slots)}, source_refs=_dedupe_refs(*[_refs(slot) for slot in slots])))
        if len({item["featId"] for item in selected}) != len(selected):
            issues.append(self._issue("npc.feat-duplicate", "the same feat cannot be selected twice", path="/selections/feats"))
        results: list[dict[str, Any]] = []
        effects: dict[str, Any] = {"initiative": 0, "saves": {}}
        refs: list[dict[str, Any]] = []
        for index, item in enumerate(selected):
            record = self._record("feat", item["featId"])
            refs = _dedupe_refs(refs, _refs(record))
            if record.get("catalogStatus") != "resolved":
                issues.append(self._gap(record, f"/selections/feats/{index}/featId"))
                continue
            if record["id"] not in self._record("derivedRule", "npc-rule.general-feat-slots").get("allowedFeatIds", []):
                issues.append(self._issue("npc.feat-unsupported", "feat is outside the production slice", path=f"/selections/feats/{index}/featId", source_refs=_refs(record)))
            prerequisite = evaluate_prerequisite(
                record.get("prerequisites", {"all": []}), ability_scores=scores, bab=level, character_level=level
            )
            if prerequisite is not True:
                issues.append(self._issue("npc.feat-prerequisite", "feat prerequisites are not met", path=f"/selections/feats/{index}/featId", source_refs=_refs(record)))
            feat_effect = record.get("effects", {})
            effects["initiative"] += feat_effect.get("initiative", 0)
            for save in ("fortitude", "reflex", "will"):
                effects["saves"][save] = effects["saves"].get(save, 0) + feat_effect.get(save, 0)
            results.append({"slotId": item["slotId"], "featId": record["id"], "name": record["name"], "sourceRefs": _refs(record)})
        return results, effects, refs, issues

    def _gear(self, selections: dict[str, Any], level: int) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        budget = self._gear_budget(selections, level)
        issues: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        if not budget or budget.get("catalogStatus") != "resolved":
            record = self._gear_profile_record(selections)
            return {"budget": {}, "items": []}, _refs(record), [self._gap(budget or record, "/selections/gearProfile")], []
        items: list[dict[str, Any]] = []
        refs = _refs(budget)
        spent = 0
        for index, selected in enumerate(selections["gear"]):
            record = self._record("item", selected["itemId"])
            refs = _dedupe_refs(refs, _refs(record))
            if record.get("catalogStatus") != "resolved":
                issues.append(self._gap(record, f"/selections/gear/{index}/itemId"))
                continue
            unsupported = set(selected) & {"masterwork", "enhancementBonus", "properties", "propertyIds", "charges"}
            if unsupported:
                issues.append(self._issue("npc.slice-unsupported", "magic and upgraded item options are outside the production slice", path=f"/selections/gear/{index}"))
            quantity = selected.get("quantity", 1)
            cost = record["priceCp"] * quantity
            spent += cost
            items.append({
                "itemId": record["id"], "name": record["name"], "category": record["category"],
                "npcGearCategory": record.get("npcGearCategory"),
                "quantity": quantity, "equipped": selected.get("equipped", True), "priceCp": cost,
                "weightLb": record.get("weightLb", 0) * quantity, "effects": copy.deepcopy(record.get("effects", {})),
                "sourceRefs": _refs(record),
            })
        if spent != budget["budgetCp"]:
            warnings.append(self._issue(
                "npc.gear-budget-approximate", "selected mundane gear does not spend the full NPC gear budget",
                severity="warning", path="/selections/gear", details={"budgetCp": budget["budgetCp"], "spentCp": spent}, source_refs=_refs(budget),
            ))
        result_budget = {
            "gearBudgetId": budget["gearBudgetId"], "level": level, "effectiveLevel": budget["effectiveLevel"],
            "npcCategory": budget["npcCategory"], "budgetCp": budget["budgetCp"],
            "categories": copy.deepcopy(budget["categories"]), "spentCp": spent, "remainingCp": budget["budgetCp"] - spent,
        }
        return {"budget": result_budget, "items": items}, refs, issues, warnings

    @staticmethod
    def _attacks(items: list[dict[str, Any]], bab: int, modifiers: dict[str, int], size_modifiers: dict[str, int]) -> list[dict[str, Any]]:
        attacks = []
        for item in items:
            if item["category"] != "weapon" or "damageDie" not in item["effects"]:
                continue
            attack_bonus = bab + modifiers["strength"] + size_modifiers.get("attack", 0)
            damage_bonus = modifiers["strength"]
            attacks.append({
                "name": item["name"], "itemId": item["itemId"], "attackBonuses": [attack_bonus],
                "attackBonusExpression": _bonus(attack_bonus),
                "damageExpression": f"{item['effects']['damageDie']}{_bonus(damage_bonus) if damage_bonus else ''}",
                "damageType": item["effects"].get("damageType"),
            })
        return attacks

    # ------------------------------------------------------------------
    # Catalog and response helpers
    # ------------------------------------------------------------------
    def _record(self, record_type: str, record_id: str) -> dict[str, Any]:
        return self.catalog.resolve_id(record_type, record_id)[1]

    def _optional(self, record_type: str, record_id: Any) -> dict[str, Any] | None:
        if not isinstance(record_id, str):
            return None
        try:
            return self._record(record_type, record_id)
        except CatalogError:
            return None

    def _catalog_values(self, record_type: str) -> list[dict[str, Any]]:
        return [{"id": record["id"], "name": record["name"], "catalogStatus": record.get("catalogStatus", "gap")} for record in self.catalog.entries(record_type).values()]

    @staticmethod
    def _requirement(path: str, label: str, value_type: str, values: Any = None) -> dict[str, Any]:
        result = {"path": path, "label": label, "valueType": value_type, "required": True}
        if values is not None:
            result["values"] = copy.deepcopy(values)
        return result

    def _class_features(self, class_record: dict[str, Any] | None, level: int) -> list[dict[str, Any]]:
        if not class_record or class_record.get("catalogStatus") != "resolved":
            return []
        feature_ids: list[str] = []
        for current in range(1, level + 1):
            row = class_record.get("levels", {}).get(str(current), {})
            feature_ids.extend(row.get("featureGrants") or [])
        result = []
        for feature_id in dict.fromkeys(feature_ids):
            record = self._record("classFeature", feature_id)
            if record.get("catalogStatus") == "resolved":
                result.append({"featureId": record["id"], "name": record["name"], "sourceRefs": _refs(record)})
        return result

    def _feat_slots(self, level: int, race: dict[str, Any] | None) -> list[dict[str, Any]]:
        rule = self._record("derivedRule", "npc-rule.general-feat-slots")
        slots = [{
            "slotId": f"general-{value}", "kind": "general", "grantedAtLevel": value,
            "required": True, "allowedCategories": copy.deepcopy(rule.get("allowedCategories", ["general"])),
            "allowedFeatIds": copy.deepcopy(rule.get("allowedFeatIds", [])), "sourceRef": copy.deepcopy(rule.get("sourceRef")),
        } for value in rule.get("levels", []) if value <= level]
        slots.extend(copy.deepcopy((race or {}).get("featSlots", [])))
        return slots

    def _gear_profile_record(self, selections: dict[str, Any]) -> dict[str, Any] | None:
        profile = selections.get("gearProfile", {})
        if not isinstance(profile, dict):
            return None
        record_id = profile.get("gearBudgetId")
        if not record_id:
            progression = profile.get("experienceProgression", profile.get("progression"))
            fantasy = profile.get("fantasyLevel")
            if not progression or not fantasy:
                return None
            record_id = f"npc-gear.{progression}.{fantasy}"
        return self._optional("gearBudget", record_id)

    def _gear_budget(self, selections: dict[str, Any], level: int) -> dict[str, Any] | None:
        record = self._gear_profile_record(selections)
        if not record:
            return None
        progression = selections.get("classProgression", [])
        class_record = self._optional("class", progression[0].get("classId")) if progression and isinstance(progression[0], dict) else None
        npc_category = "heroic" if class_record and class_record.get("category") == "pc" else "basic"
        for row in record.get("rows", []):
            if row.get("level") == level and row.get("npcCategory") == npc_category:
                return {"gearBudgetId": record["id"], **copy.deepcopy(row)}
        return record

    def _preview_intelligence(self, selections: dict[str, Any], race: dict[str, Any] | None) -> int | None:
        generation = selections.get("abilityGeneration", {})
        if not isinstance(generation, dict):
            return None
        array = self._optional("abilityArray", generation.get("arrayId", "npc-ability-array.basic"))
        if not array or array.get("catalogStatus") != "resolved":
            return None
        method = generation.get("method")
        if method in {"melee-preset", "arcane-preset"}:
            score = array.get("presets", {}).get(method.removesuffix("-preset"), {}).get("intelligence")
        else:
            score = generation.get("assignments", generation.get("scores", {})).get("intelligence")
        if not _is_int(score):
            return None
        score += (race or {}).get("abilityAdjustments", {}).get("intelligence", 0)
        if selections.get("racialChoices", {}).get("ability-bonus") == "intelligence":
            score += 2
        return score

    def _preview_gear_cost(self, gear: list[Any]) -> int:
        total = 0
        for item in gear:
            if not isinstance(item, dict):
                continue
            record = self._optional("item", item.get("itemId"))
            if record and _is_int(record.get("priceCp")):
                total += record["priceCp"] * item.get("quantity", 1)
        return total

    def _source_ref(self, source_id: str, section: str, lines: list[int]) -> dict[str, Any]:
        source = self.catalog.data["sources"][source_id]
        return {
            "sourceId": source_id, "file": source["file"], "sha256": source["sha256"],
            "section": section, "txtLines": lines, "provenanceStatus": "resolved",
        }

    @staticmethod
    def _missing_required(selections: dict[str, Any]) -> list[str]:
        required = {
            "statblockUse": "/selections/statblockUse", "raceId": "/selections/raceId",
            "classProgression": "/selections/classProgression", "abilityGeneration": "/selections/abilityGeneration",
            "skillGeneration": "/selections/skillGeneration", "feats": "/selections/feats",
            "gearProfile": "/selections/gearProfile", "gear": "/selections/gear",
        }
        missing = [path for field, path in required.items() if field not in selections]
        if not missing and not selections["classProgression"]:
            missing.append("/selections/classProgression/0")
        for field in ("method",):
            if isinstance(selections.get("abilityGeneration"), dict) and field not in selections["abilityGeneration"]:
                missing.append(f"/selections/abilityGeneration/{field}")
            if isinstance(selections.get("skillGeneration"), dict) and field not in selections["skillGeneration"]:
                missing.append(f"/selections/skillGeneration/{field}")
        return sorted(missing)

    @staticmethod
    def _trace(path: str, value: Any, calculation: str, source_refs: list[dict[str, Any]]) -> dict[str, Any]:
        return {"path": path, "value": copy.deepcopy(value), "calculation": calculation, "sourceRefs": copy.deepcopy(source_refs)}

    @staticmethod
    def _issue(code: str, message: str, *, severity: str = "error", kind: str = "validation", path: str | None = None, details: dict[str, Any] | None = None, source_refs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        issue = {"code": code, "severity": severity, "kind": kind, "message": message}
        if path is not None:
            issue["path"] = path
        if details:
            issue["details"] = copy.deepcopy(details)
        if source_refs:
            issue["sourceRefs"] = copy.deepcopy(source_refs)
        return issue

    def _gap(self, record: dict[str, Any], path: str) -> dict[str, Any]:
        return self._issue(
            "npc.catalog-gap", "catalog data required for this selection is not source-resolved", kind="catalog-data",
            path=path, details={"recordId": record.get("id"), "catalogStatus": record.get("catalogStatus", "gap")}, source_refs=_refs(record),
        )

    @staticmethod
    def _evaluation(status: str, mode: str, issues: list[dict[str, Any]], warnings: list[dict[str, Any]] | None = None, canonical: dict[str, Any] | None = None, trace: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        return {
            "status": status, "mode": mode, "canonical": copy.deepcopy(canonical),
            "effective": copy.deepcopy(canonical), "issues": sorted(issues, key=lambda value: (value.get("path", ""), value["code"])),
            "warnings": sorted(warnings or [], key=lambda value: (value.get("path", ""), value["code"])),
            "derivationTrace": copy.deepcopy(trace or []),
        }
