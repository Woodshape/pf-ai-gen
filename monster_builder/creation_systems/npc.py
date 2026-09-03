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
    "evaluation", "cr", "ac", "fortitude", "reflex", "will", "linkedCreature",
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


def _bonus_spell_count(ability_modifier: int, spell_level: int) -> int:
    if spell_level == 0 or ability_modifier < spell_level:
        return 0
    return 1 + (ability_modifier - spell_level) // 4


class NpcCreation(CreationSystem):
    """Evaluate the bounded, locally sourced Core NPC slice."""

    key = NPC
    selection_fields = frozenset({
        "statblockUse", "raceId", "racialChoices", "classProgression", "abilityGeneration",
        "levelIncreases", "skillGeneration", "feats", "classFeatureChoices", "spellLoadout",
        "gearProfile", "gear", "details", "archetypeId",
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
        class_row = (class_record or {}).get("levels", {}).get(str(level), {})
        spell_counts = copy.deepcopy(class_row.get("spellsKnown", {}))
        druid_slots: dict[str, dict[str, int]] = {}
        archetype_id = selections.get("archetypeId")
        archetype_selected = isinstance(archetype_id, str) and bool(archetype_id)
        if class_record and class_record.get("id") == "npc-class.druid":
            wisdom = self._preview_ability(selections, race, "wisdom", divine_allowed=True)
            fire_domain = None if archetype_selected else self._optional("classFeature", "npc-class-feature.fire-domain")
            if wisdom is not None and (fire_domain or archetype_selected):
                wisdom_modifier = _ability_modifier(wisdom)
                for spell_level, base in class_row.get("spellsPerDay", {}).items():
                    numeric_level = int(spell_level)
                    wisdom_bonus = _bonus_spell_count(wisdom_modifier, numeric_level)
                    if archetype_selected:
                        domain = 0
                    else:
                        domain = fire_domain["slotsPerSpellLevel"] if numeric_level > 0 else 0
                    druid_slots[spell_level] = {
                        "base": base, "wisdomBonus": wisdom_bonus, "domain": domain,
                        "total": base + wisdom_bonus + domain,
                    }
        skill_count = None
        if class_record and class_record.get("catalogStatus") == "resolved":
            intelligence = self._preview_ability(
                selections, race, "intelligence", divine_allowed=class_record.get("id") == "npc-class.druid",
            )
            if intelligence is not None:
                skill_count = max(1, class_record.get("skillSelections", 0) + _ability_modifier(intelligence)) + (race or {}).get("skillSelectionsBonus", 0)

        class_id = (class_record or {}).get("id")
        method_values = ["melee-preset", "arcane-preset", "assigned-array"]
        if class_id == "npc-class.druid":
            method_values.insert(1, "divine-preset")
        requirements = [
            self._requirement("/selections/statblockUse", "Statblock use", "enum", ["full", "encounter"]),
            self._requirement("/selections/raceId", "Race", "catalog-id", self._catalog_values("race")),
            self._requirement("/selections/classProgression/0/classId", "Class", "catalog-id", self._catalog_values("class")),
            self._requirement("/selections/classProgression/0/levels", "Class levels", "integer"),
            self._requirement("/selections/abilityGeneration/method", "Ability method", "enum", method_values),
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
        if class_record and class_record["id"] in {"npc-class.sorcerer", "npc-class.bard"}:
            if class_record["id"] == "npc-class.sorcerer":
                requirements.append(self._requirement(
                    "/selections/classFeatureChoices/bloodline", "Bloodline", "enum", ["elemental-fire"]
                ))
            requirements.append(self._requirement(
                "/selections/spellLoadout/known", "Spells known", "spell-loadout"
            ))
        elif class_record and class_record["id"] == "npc-class.druid":
            requirements.append(self._requirement(
                "/selections/spellLoadout/prepared", "Prepared Druid spells", "spell-loadout"
            ))
            if not archetype_selected:
                requirements.extend((
                    self._requirement(
                        "/selections/classFeatureChoices/natureBond", "Nature Bond", "enum", ["fire-domain"]
                    ),
                    self._requirement(
                        "/selections/spellLoadout/domainPrepared", "Prepared Fire-domain spells", "spell-loadout"
                    ),
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
                "spells": (
                    {"required": True, "mode": "prepared", "levels": druid_slots}
                    if class_record and class_record.get("id") == "npc-class.druid"
                    else {"required": bool(spell_counts), "levels": spell_counts}
                ),
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
            (1, ("statblockUse", "raceId", "racialChoices", "classProgression", "archetypeId")),
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
        ) or (
            slice_id[0] == "npc-race.goblin" and slice_id[1] == "npc-class.sorcerer" and 5 <= total_level <= 6
        ) or slice_id == ("npc-race.goblin", "npc-class.druid", 3) or (
            slice_id[0] == "npc-race.halfling" and slice_id[1] == "npc-class.bard" and 1 <= total_level <= 3
        )
        if not supported:
            issues.append(self._issue(
                "npc.slice-unsupported", "production evaluation supports human warriors 1–5, goblin sorcerers at levels 5–6, goblin druids at level 3, and halfling bards at levels 1–3",
                path="/selections/classProgression", source_refs=_refs(class_records[0]) if class_records else [],
            ))
        if issues:
            return self._evaluation("invalid", mode, issues)

        class_record, row = class_records[0], rows[0]
        archetype_id = selections.get("archetypeId")
        archetype, archetype_issues = self._archetype(selections, race, class_record, total_level)
        issues.extend(archetype_issues)
        scores, ability_refs, ability_issues = self._abilities(selections, race, total_level, class_record)
        issues.extend(ability_issues)
        if not scores:
            return self._evaluation("invalid", mode, issues)
        gear_result, gear_refs, gear_issues, gear_warnings = self._gear(selections, total_level, race.get("sizeId"))
        issues.extend(gear_issues)
        warnings.extend(gear_warnings)
        feats, feat_effects, feat_refs, feat_issues = self._feats(selections, race, total_level, scores)
        issues.extend(feat_issues)
        skills, skill_refs, skill_issues = self._skills(selections, race, class_record, total_level, scores, gear_result)
        issues.extend(skill_issues)
        modifiers = {ability: _ability_modifier(score) for ability, score in scores.items()}
        class_features, feature_refs, feature_issues = self._selected_class_features(selections, race, class_record, total_level, modifiers, archetype)
        issues.extend(feature_issues)
        spells, spell_refs, spell_issues = self._spells(selections, class_record, row, total_level, scores, modifiers, archetype_id=archetype_id, archetype=archetype)
        issues.extend(spell_issues)
        linked_creature, linked_refs, linked_issues = None, [], []
        if archetype is not None:
            linked_creature, linked_refs, linked_issues = self._linked_creature(archetype, total_level)
            issues.extend(linked_issues)
        if issues:
            return self._evaluation("invalid", mode, issues, warnings)

        class_refs = _dedupe_refs(_refs(class_record), _refs(row))
        combat_ref = self._source_ref("source.aon-combat", "Combat Statistics", [24, 58])
        maneuver_ref = self._source_ref("source.aon-combat", "Combat Maneuvers", [536, 544])
        hp_rule = self._record("derivedRule", "npc-rule.average-hp")
        cr_rule = self._record("derivedRule", "npc-rule.classed-npc-cr")
        cr = total_level + cr_rule["pcClassAdjustment"] if class_record["category"] == "pc" else None
        die_size = int(class_record["hitDie"].removeprefix("d"))
        # ponytail: per getting-started.txt line 30, a first Hit Die from a character (PC) class grants
        # maximum hit points; NPC-class or racial first Hit Dice roll normally. Multiclass is out of slice.
        if class_record["category"] == "pc":
            hp = math.floor(die_size + (total_level - 1) * ((die_size + 1) / 2 + modifiers["constitution"]) + total_level * modifiers["constitution"])
        else:
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
        race_saves = race.get("saveBonuses", {}) if isinstance(race.get("saveBonuses"), dict) else {}
        ac_breakdown = {
            key: value for key, value in (
                ("armor", armor_bonus), ("shield", shield_bonus),
                ("dexterity", dex_to_ac), ("size", size_modifiers.get("ac", 0)),
            ) if value
        }
        defenses = {
            "ac": 10 + armor_bonus + shield_bonus + dex_to_ac + size_modifiers.get("ac", 0),
            "touch": 10 + modifiers["dexterity"] + size_modifiers.get("ac", 0),
            "flatFooted": 10 + armor_bonus + shield_bonus + size_modifiers.get("ac", 0),
            "fortitude": row["fortitude"] + modifiers["constitution"] + feat_saves.get("fortitude", 0) + resistance_bonus + race_saves.get("fortitude", 0),
            "reflex": row["reflex"] + modifiers["dexterity"] + feat_saves.get("reflex", 0) + resistance_bonus + race_saves.get("reflex", 0),
            "will": row["will"] + modifiers["wisdom"] + feat_saves.get("will", 0) + resistance_bonus + race_saves.get("will", 0),
            "acBreakdown": ac_breakdown,
        }
        attacks = self._attacks(equipped, bab, modifiers, size_modifiers, race.get("sizeId"), finesse=any(feat.get("featId") == "feat.weapon-finesse" for feat in feats))
        resistances: dict[str, int] = {}
        for feature in class_features:
            for power in feature.get("powers", []):
                if power.get("damageExpression") and power.get("attackBonus") is not None:
                    attacks.append({
                        "name": power["name"], "attackBonuses": [power["attackBonus"]],
                        "attackBonusExpression": _bonus(power["attackBonus"]), "attackType": power.get("attackType", "ranged touch"),
                        "damageExpression": power["damageExpression"], "damageType": power.get("damageType"),
                        "range": power.get("range"), "usesPerDay": power.get("usesPerDay"),
                    })
                resistances.update(power.get("resistance", {}))
        cmb = bab + modifiers["strength"] + size_modifiers.get("cmb", 0)
        cmd = 10 + bab + modifiers["strength"] + modifiers["dexterity"] + size_modifiers.get("cmd", 0)
        source_groups = {
            "abilities": ability_refs,
            "class": class_refs,
            "hp": _dedupe_refs(class_refs, _refs(hp_rule), ability_refs),
            "gear": gear_refs,
            "feats": feat_refs,
            "skills": skill_refs,
            "combat": _dedupe_refs(class_refs, ability_refs, gear_refs, feature_refs, [combat_ref]),
            "maneuvers": _dedupe_refs(class_refs, ability_refs, [maneuver_ref]),
            "features": _dedupe_refs(feature_refs, ability_refs, class_refs, [combat_ref]),
            "spells": _dedupe_refs(spell_refs, ability_refs, class_refs),
            "cr": _refs(cr_rule),
        }
        canonical = {
            "name": draft.get("concept", {}).get("name", "Unnamed NPC"),
            "creationSystem": NPC,
            "statblockUse": selections["statblockUse"],
            "level": total_level,
            "totalLevel": total_level,
            **({"cr": cr} if cr is not None else {}),
            "npcCategory": "heroic" if class_record["category"] == "pc" else "basic",
            "raceId": race["id"],
            "raceName": race["name"],
            "classProgression": [{"classId": class_record["id"], "className": class_record["name"], "levels": total_level}],
            "abilityScores": scores,
            "abilityModifiers": modifiers,
            "hitDiceExpression": f"{total_level}{class_record['hitDie']}{_bonus(total_level * modifiers['constitution']) if modifiers['constitution'] else ''}",
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
            **({"linkedCreature": linked_creature} if linked_creature is not None else {}),
            "spells": spells,
            "gearBudget": gear_result["budget"],
            "gear": gear_result["items"],
            "speed": copy.deepcopy(race.get("speed", {"land": 30})),
            "senses": copy.deepcopy(race.get("senses", [])),
            "languages": copy.deepcopy(race.get("languages", [])) + [
                language
                for feature in class_features
                for language in self._record("classFeature", feature["featureId"]).get("effects", {}).get("languages", [])
            ],
            "size": {"id": race.get("sizeId", "size.medium"), "name": race.get("sizeId", "size.medium").split(".")[-1].title()},
            "creatureType": f"humanoid ({race['subtype']})" if race.get("subtype") else "humanoid",
            "alignment": selections.get("details", {}).get("alignment"),
            "resistances": resistances,
            "details": copy.deepcopy(selections.get("details", {})),
        }
        if class_record["id"] == "npc-class.druid":
            feature_calculation = (
                "apply cumulative Druid features and derive Fire Bolt damage, uses, and attack bonus"
                if archetype is None
                else f"apply Druid features with the {archetype['name']} archetype replacing Nature Bond"
            )
            spell_calculation = (
                "validate prepared and Wisdom-bonus slots; apply caster level, save DCs, and spontaneous conversion"
                if archetype is not None
                else "validate prepared, Wisdom-bonus, and Fire-domain slots; apply caster level, save DCs, and spontaneous conversion"
            )
        else:
            feature_calculation = "apply automatic features and selected class-feature options"
            spell_calculation = "validate spells known, add bloodline spells, and apply Charisma bonus spells"
        trace = [
            self._trace("/canonical/level", total_level, "sum selected class levels", class_refs),
            *([self._trace("/canonical/cr", cr, "PC class levels − 1", source_groups["cr"])] if cr is not None else []),
            self._trace("/canonical/abilityScores", scores, "apply the NPC array, racial adjustments, and level increases", ability_refs),
            self._trace("/canonical/hp", hp, f"floor(level × (average d{die_size} + Constitution modifier))", source_groups["hp"]),
            self._trace("/canonical/bab", bab, "read the selected class level row", class_refs),
            self._trace("/canonical/defenses", defenses, "combine class saves, abilities, armor, shield, and feat bonuses", source_groups["combat"]),
            self._trace("/canonical/initiative", canonical["initiative"], "Dexterity modifier plus feat bonuses", _dedupe_refs(ability_refs, feat_refs, [combat_ref])),
            self._trace("/canonical/attacks", attacks, "BAB plus ability and size modifiers; weapon die plus Strength", source_groups["combat"]),
            self._trace("/canonical/cmb", cmb, "BAB + Strength modifier + size modifier", source_groups["maneuvers"]),
            self._trace("/canonical/cmd", cmd, "10 + BAB + Strength modifier + Dexterity modifier + size modifier", source_groups["maneuvers"]),
            self._trace(
                "/canonical/skills", skills,
                "level ranks plus class-skill bonus, ability modifier, armor check penalty, and Nature Sense"
                if class_record["id"] == "npc-class.druid"
                else "level ranks plus class-skill bonus, ability modifier, and armor check penalty",
                skill_refs,
            ),
            self._trace("/canonical/feats", feats, "fill granted feat slots", feat_refs),
            self._trace(
                "/canonical/classFeatures", class_features,
                feature_calculation,
                source_groups["features"],
            ),
            *([
                self._trace(
                    "/canonical/linkedCreature", linked_creature,
                    f"project the curated {archetype['name']} level-{linked_creature['level']} linked creature row",
                    linked_refs,
                )
            ] if linked_creature is not None else []),
            self._trace(
                "/canonical/spells", spells,
                spell_calculation,
                source_groups["spells"],
            ),
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
        if "archetypeId" in selections and (not isinstance(selections["archetypeId"], str) or not selections["archetypeId"]):
            raise BoundaryError("selection.type-invalid", "archetypeId must be a non-empty string", "/selections/archetypeId")
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
            if "method" in ability and ability["method"] not in {"melee-preset", "divine-preset", "arcane-preset", "skill-preset", "assigned-array", "custom", "rolled", "purchase"}:
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
        if isinstance(spell_loadout, dict):
            for field in ("known", "prepared", "domainPrepared"):
                if field not in spell_loadout:
                    continue
                by_level = spell_loadout[field]
                if not isinstance(by_level, dict) or any(
                    not str(level).isdigit() or not isinstance(spells, list) or any(not isinstance(spell, str) for spell in spells)
                    for level, spells in by_level.items()
                ):
                    raise BoundaryError(
                        "selection.type-invalid", f"spellLoadout.{field} must map spell levels to arrays of IDs",
                        f"/selections/spellLoadout/{field}",
                    )

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
        lookups: list[tuple[str, Any, str]] = [
            ("race", selections.get("raceId"), "/selections/raceId"),
            ("classFeature", selections.get("archetypeId"), "/selections/archetypeId"),
        ]
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
            for field in ("known", "prepared", "domainPrepared"):
                for level, spells in spell_loadout.get(field, {}).items():
                    for index, spell_id in enumerate(spells):
                        lookups.append(("spell", spell_id, f"/selections/spellLoadout/{field}/{level}/{index}"))
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
    def _abilities(self, selections: dict[str, Any], race: dict[str, Any], level: int, class_record: dict[str, Any] | None = None) -> tuple[dict[str, int], list[dict[str, Any]], list[dict[str, Any]]]:
        generation = selections["abilityGeneration"]
        array = self._record("abilityArray", generation.get("arrayId", "npc-ability-array.basic"))
        issues: list[dict[str, Any]] = []
        if array.get("catalogStatus") != "resolved":
            return {}, _refs(array), [self._gap(array, "/selections/abilityGeneration/arrayId")]
        method = generation.get("method")
        if method == "divine-preset" and (not class_record or class_record["id"] != "npc-class.druid"):
            return {}, _refs(array), [self._issue(
                "npc.slice-unsupported", "the divine preset is part of the source-gated Druid slice",
                path="/selections/abilityGeneration/method", source_refs=_refs(array),
            )]
        if method in {"melee-preset", "divine-preset", "arcane-preset"}:
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
        nature_sense = (
            self._optional("classFeature", "npc-class-feature.druid-nature-sense")
            if class_record["id"] == "npc-class.druid" else None
        )
        if nature_sense:
            refs = _dedupe_refs(refs, _refs(nature_sense))
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
            feature_bonus = (nature_sense or {}).get("effects", {}).get("skillBonuses", {}).get(skill_id, 0)
            race_bonus = (race.get("skillBonuses") or {}).get(skill_id, 0) if isinstance(race.get("skillBonuses"), dict) else 0
            total = level + (3 if class_skill else 0) + _ability_modifier(scores[ability]) + acp + feature_bonus + race_bonus
            results.append({
                "skillId": skill_id, "name": record["name"], "ability": ability, "ranks": level,
                "classSkill": class_skill, "armorCheckPenalty": acp,
                **({"classFeatureBonus": feature_bonus} if feature_bonus else {}),
                **({"raceBonus": race_bonus} if race_bonus else {}),
                "total": total, "sourceRefs": _dedupe_refs(_refs(record), _refs(nature_sense) if feature_bonus else [], _refs(race) if race_bonus else []),
            })
        return results, refs, issues

    def _selected_class_features(
        self, selections: dict[str, Any], race: dict[str, Any], class_record: dict[str, Any], level: int, modifiers: dict[str, int],
        archetype: dict[str, Any] | None = None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        features = self._class_features(class_record, level)
        refs = _dedupe_refs(_refs(class_record), *[feature.get("sourceRefs", []) for feature in features])
        choices = selections.get("classFeatureChoices", {})
        if class_record["id"] == "npc-class.sorcerer":
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
                    selected["damageExpression"] = f"{selected['damageDie']}+{level // 2}"
                    selected["usesPerDay"] = 3 + modifiers["charisma"]
                    selected["attackBonus"] = class_record["levels"][str(level)]["bab"] + modifiers["dexterity"] + race.get("sizeModifiers", {}).get("attack", 0)
                powers.append(selected)
            for feature in features:
                if feature["featureId"] == bloodline["id"]:
                    feature.update(choice=choice, name=option["name"], energyType=option["energyType"], arcana=copy.deepcopy(option["arcana"]), powers=powers)
            return features, _dedupe_refs(refs, _refs(bloodline)), []

        if class_record["id"] == "npc-class.druid":
            nature_bond = self._record("classFeature", "npc-class-feature.druid-nature-bond")
            archetype_id = selections.get("archetypeId")
            if archetype_id is not None:
                feature_refs = _dedupe_refs(refs, *([_refs(archetype)] if archetype else []))
                archetype_issues: list[dict[str, Any]] = []
                if choices:
                    conflict_path = (
                        "/selections/classFeatureChoices/natureBond"
                        if "natureBond" in choices else "/selections/classFeatureChoices"
                    )
                    archetype_issues.append(self._issue(
                        "npc.choice-invalid",
                        f"the {archetype['name'] if archetype else 'selected'} archetype replaces the Nature Bond choice; classFeatureChoices must be empty",
                        path=conflict_path,
                        source_refs=_dedupe_refs(*([_refs(archetype)] if archetype else [])),
                    ))
                if archetype is not None:
                    replaces = archetype.get("replaces")
                    if not isinstance(replaces, list) or any(not isinstance(value, str) for value in replaces):
                        archetype_issues.append(self._issue(
                            "npc.catalog-gap", "the archetype replaces field must be an array of feature IDs", kind="catalog-data",
                            path="/selections/archetypeId", details={"recordId": archetype["id"]}, source_refs=_refs(archetype),
                        ))
                    elif "npc-class-feature.druid-nature-bond" not in replaces:
                        archetype_issues.append(self._issue(
                            "npc.catalog-gap", "the archetype must replace the Druid Nature Bond feature", kind="catalog-data",
                            path="/selections/archetypeId", details={"recordId": archetype["id"], "replaces": copy.deepcopy(replaces)},
                            source_refs=_refs(archetype),
                        ))
                bond_index = next(
                    (index for index, feature in enumerate(features) if feature["featureId"] == nature_bond["id"]), None,
                )
                features = [feature for feature in features if feature["featureId"] not in {nature_bond["id"], "npc-class-feature.druid-wild-empathy"}]
                if archetype is not None and not any(
                    issue["code"] == "npc.catalog-gap" for issue in archetype_issues
                ):
                    entry: dict[str, Any] = {
                        "featureId": archetype["id"], "name": archetype["name"], "sourceRefs": _refs(archetype),
                        "elementalEmpathy": {"checkBonus": level + modifiers["charisma"]},
                    }
                    if archetype.get("replaces"):
                        entry["replaces"] = copy.deepcopy(archetype["replaces"])
                    features.insert(bond_index if bond_index is not None else len(features), entry)
                for feature in features:
                    if feature["featureId"] in {"npc-class-feature.druid-proficiencies", "npc-class-feature.druid-orisons"}:
                        feature["effects"] = copy.deepcopy(self._record("classFeature", feature["featureId"]).get("effects", {}))
                    elif feature["featureId"] == "npc-class-feature.druid-nature-sense":
                        feature["skillBonuses"] = copy.deepcopy(
                            self._record("classFeature", feature["featureId"])["effects"]["skillBonuses"]
                        )
                return features, feature_refs, archetype_issues
            fire_domain = self._record("classFeature", "npc-class-feature.fire-domain")
            feature_refs = _dedupe_refs(refs, _refs(nature_bond), _refs(fire_domain))
            choice = choices.get("natureBond")
            if choice != "fire-domain" or set(choices) != {"natureBond"}:
                return features, feature_refs, [self._issue(
                    "npc.choice-invalid", "the source-gated Druid slice requires Nature Bond with the Fire domain",
                    path="/selections/classFeatureChoices/natureBond", source_refs=_dedupe_refs(_refs(nature_bond), _refs(fire_domain)),
                )]
            option = nature_bond.get("options", {}).get(choice, {})
            if option.get("featureId") not in {None, fire_domain["id"]}:
                return features, feature_refs, [self._issue(
                    "npc.choice-invalid", "the selected Nature Bond does not grant the Fire domain",
                    path="/selections/classFeatureChoices/natureBond", source_refs=_refs(nature_bond),
                )]
            for feature in features:
                if feature["featureId"] == nature_bond["id"]:
                    feature.update(choice=choice, name="Nature Bond (Fire domain)")
                elif feature["featureId"] in {"npc-class-feature.druid-proficiencies", "npc-class-feature.druid-orisons"}:
                    feature["effects"] = copy.deepcopy(self._record("classFeature", feature["featureId"]).get("effects", {}))
                elif feature["featureId"] == "npc-class-feature.druid-nature-sense":
                    feature["skillBonuses"] = copy.deepcopy(
                        self._record("classFeature", feature["featureId"])["effects"]["skillBonuses"]
                    )
                elif feature["featureId"] == "npc-class-feature.druid-wild-empathy":
                    feature["checkBonus"] = level + modifiers["charisma"]
            powers = []
            for power in fire_domain.get("powers", []):
                if power.get("level", 1) > level:
                    continue
                selected = copy.deepcopy(power)
                if selected.get("name") == "Fire Bolt":
                    damage_bonus = (level // 2) * selected["damageBonusPerTwoLevels"]
                    selected["damageExpression"] = selected["damageDie"] + (_bonus(damage_bonus) if damage_bonus else "")
                    selected["usesPerDay"] = selected["usesBase"] + modifiers[selected["usesAbility"]]
                    selected["attackBonus"] = class_record["levels"][str(level)]["bab"] + modifiers["dexterity"] + race.get("sizeModifiers", {}).get("attack", 0)
                powers.append(selected)
            features.append({
                "featureId": fire_domain["id"], "name": fire_domain["name"], "powers": powers,
                "sourceRefs": _refs(fire_domain),
            })
            return features, feature_refs, []

        issues = [self._issue(
            "npc.slice-unsupported", "class feature choices are not part of this production slice",
            path="/selections/classFeatureChoices",
        )] if choices else []
        return features, refs, issues

    def _archetype(
        self, selections: dict[str, Any], race: dict[str, Any], class_record: dict[str, Any], level: int,
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        """Resolve an optional NPC archetype selection against its catalog record."""
        archetype_id = selections.get("archetypeId")
        if archetype_id is None:
            return None, []
        path = "/selections/archetypeId"
        if not isinstance(archetype_id, str) or not archetype_id:
            return None, [self._issue(
                "npc.slice-unsupported", "archetypeId must be a non-empty string", path=path,
            )]
        try:
            record = self._record("classFeature", archetype_id)
        except CatalogError:
            return None, [self._issue(
                "npc.catalog-gap", "catalog data required for this selection is not source-resolved", kind="catalog-data",
                path=path, details={"recordId": archetype_id, "catalogStatus": "gap"},
            )]
        refs = _refs(record)
        issues: list[dict[str, Any]] = []
        if record.get("catalogStatus") != "resolved":
            issues.append(self._gap(record, path))
        if record.get("kind") != "archetype":
            issues.append(self._issue(
                "npc.catalog-gap", "the selected class feature is not an archetype record", kind="catalog-data",
                path=path, details={"recordId": record.get("id"), "kind": record.get("kind")}, source_refs=refs,
            ))
        if record.get("classId") != class_record["id"]:
            issues.append(self._issue(
                "npc.catalog-gap", "the archetype does not belong to the selected class", kind="catalog-data",
                path=path, details={"recordId": record.get("id"), "classId": record.get("classId")}, source_refs=refs,
            ))
        if not (race["id"] == "npc-race.goblin" and class_record["id"] == "npc-class.druid" and level == 3):
            issues.append(self._issue(
                "npc.slice-unsupported", "the archetype is part of the source-gated goblin druid level-3 slice",
                path=path, source_refs=refs,
            ))
        if issues:
            return None, issues
        return record, []

    def _linked_creature(
        self, archetype: dict[str, Any], level: int,
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[dict[str, Any]]]:
        """Project the archetype's curated linked creature row into the canonical block."""
        path = "/selections/archetypeId"
        refs = _refs(archetype)
        row = archetype.get("linkedCreatureRow")
        if not isinstance(row, dict) or row.get("catalogStatus") != "resolved":
            return None, refs, [self._issue(
                "npc.catalog-gap", "the linked creature row is not source-resolved", kind="catalog-data",
                path=path, details={"recordId": archetype.get("id"), "catalogStatus": "gap"}, source_refs=refs,
            )]

        def gap(details: dict[str, Any]) -> dict[str, Any]:
            return self._issue(
                "npc.catalog-gap", "the linked creature row is not fully curated", kind="catalog-data",
                path=path, details={"recordId": archetype.get("id"), **details}, source_refs=refs,
            )

        issues: list[dict[str, Any]] = []
        unexpected = set(row) - {"catalogStatus", "level", "element", "name", "fields", "sourceRef"}
        if unexpected:
            issues.append(gap({"unexpectedRowFields": sorted(unexpected)}))
        row_level = row.get("level")
        if not _is_int(row_level) or row_level != level:
            issues.append(gap({"field": "level", "expected": level, "actual": row_level}))
        element = row.get("element")
        if not isinstance(element, str) or not element:
            issues.append(gap({"field": "element", "problem": "missing-element"}))
        name = row.get("name")
        if "name" in row and (not isinstance(name, str) or not name):
            issues.append(gap({"field": "name", "problem": "invalid-name"}))
        fields = row.get("fields")
        resolved: dict[str, Any] = {}
        field_refs: dict[str, list[dict[str, Any]]] = {}
        if isinstance(fields, dict) and fields:
            for key in sorted(fields):
                entry = fields[key]
                if not isinstance(entry, dict) or "value" not in entry:
                    issues.append(gap({"field": key, "problem": "missing-value"}))
                    continue
                raw_refs = entry.get("sourceRef")
                normalized = raw_refs if isinstance(raw_refs, list) else ([raw_refs] if isinstance(raw_refs, dict) else [])
                if not normalized or any(not isinstance(ref, dict) for ref in normalized):
                    issues.append(gap({"field": key, "problem": "missing-sourceRef"}))
                    continue
                resolved[key] = copy.deepcopy(entry["value"])
                field_refs[key] = copy.deepcopy(normalized)
        else:
            issues.append(gap({"problem": "missing-fields"}))
        if issues:
            return None, refs, issues
        block: dict[str, Any] = {
            "archetypeId": archetype["id"],
            "element": element,
            "level": row_level,
        }
        if isinstance(name, str) and name:
            block["name"] = name
        block.update(resolved)
        block["fieldSourceRefs"] = field_refs
        block["sourceRefs"] = _dedupe_refs(refs, _refs(row), *field_refs.values())
        return block, block["sourceRefs"], []

    def _spells(
        self, selections: dict[str, Any], class_record: dict[str, Any], row: dict[str, Any], level: int,
        scores: dict[str, int], modifiers: dict[str, int], *,
        archetype_id: str | None = None, archetype: dict[str, Any] | None = None,
    ) -> tuple[Any, list[dict[str, Any]], list[dict[str, Any]]]:
        loadout = selections.get("spellLoadout", {})
        if class_record["id"] == "npc-class.druid":
            return self._druid_spells(loadout, class_record, row, level, scores, modifiers, archetype_id=archetype_id, archetype=archetype)
        if class_record["id"] not in {"npc-class.sorcerer", "npc-class.bard"}:
            issues = [self._issue("npc.slice-unsupported", "spells are not part of this production slice", path="/selections/spellLoadout")] if loadout else []
            return [], _refs(class_record), issues

        class_key = "sorcerer" if class_record["id"] == "npc-class.sorcerer" else "bard"
        casting_ability = class_record.get("castingAbility", "charisma")
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
                elif record.get("levelsByClass", {}).get(class_key) != int(spell_level):
                    issues.append(self._issue(
                        "npc.spell-level-invalid", f"spell is not a {class_record['name']} spell of the selected level",
                        path=f"/selections/spellLoadout/known/{spell_level}/{index}", source_refs=_refs(record),
                    ))
                if spell_id in selected_ids:
                    issues.append(self._issue("npc.spell-duplicate", "the same spell cannot fill multiple known slots", path=f"/selections/spellLoadout/known/{spell_level}/{index}"))
                selected_ids.add(spell_id)
                resolved[spell_level].append(record["id"])

        bloodline: dict[str, Any] | None = None
        bloodline_spells: list[str] = []
        if class_record["id"] == "npc-class.sorcerer":
            bloodline = self._record("classFeature", "npc-class-feature.sorcerer-bloodlines")
            option = bloodline["options"]["elemental-fire"]
            refs = _dedupe_refs(refs, _refs(bloodline))
            for granted_level, spell_id in option["bonusSpells"].items():
                if int(granted_level) <= level:
                    spell = self._record("spell", spell_id)
                    spell_level = str(spell["levelsByClass"]["sorcerer"])
                    resolved.setdefault(spell_level, []).append(spell["id"])
                    bloodline_spells.append(spell["id"])
                    refs = _dedupe_refs(refs, _refs(spell))

        charisma = modifiers[casting_ability]
        per_day: dict[str, Any] = {"0": "at-will"}
        for spell_level, base in row["spellsPerDay"].items():
            numeric_level = int(spell_level)
            bonus_spells = _bonus_spell_count(charisma, numeric_level)
            per_day[spell_level] = base + bonus_spells
        bonus_ref = self._source_ref("source.aon-getting-started", "Table: Ability Modifiers and Bonus Spells", [89, 101])
        refs = _dedupe_refs(refs, [bonus_ref])
        result = {
            "className": class_record["name"], "casterLevel": level,
            "castingAbility": casting_ability, "castingAbilityModifier": charisma,
            "perDay": per_day, "saveDcByLevel": {spell_level: 10 + int(spell_level) + charisma for spell_level in expected},
            "known": resolved, "bloodlineSpells": bloodline_spells,
        }
        return result, refs, issues

    def _druid_spells(
        self, loadout: Any, class_record: dict[str, Any], row: dict[str, Any], level: int,
        scores: dict[str, int], modifiers: dict[str, int], *,
        archetype_id: str | None = None, archetype: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
        prepared = loadout.get("prepared", {}) if isinstance(loadout, dict) else {}
        domain_prepared = loadout.get("domainPrepared", {}) if isinstance(loadout, dict) else {}
        base_slots = row["spellsPerDay"]
        spellcasting = self._record("classFeature", "npc-class-feature.druid-spellcasting")
        casting_effects = spellcasting.get("effects", {})
        archetype_refs = _refs(archetype) if archetype_id else []
        if archetype_id:
            fire_domain = None
            slots_per_spell_level = None
            domain_spells = {}
        else:
            fire_domain = self._record("classFeature", "npc-class-feature.fire-domain")
            slots_per_spell_level = fire_domain.get("slotsPerSpellLevel")
            domain_spells = fire_domain.get("domainSpells")
        casting_mode = casting_effects.get("castingMode")
        casting_ability = casting_effects.get("castingAbility")
        conversion_catalog = casting_effects.get("spontaneousConversion")
        druid_ref = self._source_ref("source.aon-druid", "Spells; Spontaneous Casting; Nature Bond", [37, 49])
        repeat_ref = self._source_ref("source.aon-creating-npcs", "Step 5: Class Features", [70, 70])
        cleric_ref = self._source_ref("source.aon-cleric", "Domains", [45, 45])
        caster_level_ref = self._source_ref("source.aon-caster-level", "Caster Level", [4, 6])
        bonus_ref = self._source_ref("source.aon-getting-started", "Table: Ability Modifiers and Bonus Spells", [89, 101])
        if archetype_id:
            refs = _dedupe_refs(
                _refs(class_record), _refs(row), _refs(spellcasting), archetype_refs,
                [druid_ref, repeat_ref, caster_level_ref, bonus_ref],
            )
        else:
            refs = _dedupe_refs(
                _refs(class_record), _refs(row), _refs(spellcasting), _refs(fire_domain),
                [druid_ref, repeat_ref, cleric_ref, caster_level_ref, bonus_ref],
            )
        issues: list[dict[str, Any]] = []
        missing_rules = [
            ("npc-class-feature.druid-spellcasting.effects.castingMode", casting_mode),
            ("npc-class-feature.druid-spellcasting.effects.castingAbility", casting_ability),
            ("npc-class-feature.druid-spellcasting.effects.spontaneousConversion", conversion_catalog),
        ]
        if not archetype_id:
            missing_rules.extend([
                ("npc-class-feature.fire-domain.slotsPerSpellLevel", slots_per_spell_level),
                ("npc-class-feature.fire-domain.domainSpells", domain_spells),
            ])
        for rule_id, value in missing_rules:
            if value is None:
                issues.append(self._gap({"id": rule_id}, "/selections/spellLoadout"))
        if isinstance(conversion_catalog, dict):
            for field in ("name", "from", "excludesDomainSlots", "spellIdsBySlotLevel"):
                if conversion_catalog.get(field) is None:
                    issues.append(self._gap({"id": f"npc-class-feature.druid-spellcasting.effects.spontaneousConversion.{field}"}, "/selections/spellLoadout"))
        if any(issue["code"] == "npc.catalog-gap" for issue in issues):
            return {}, refs, issues
        available_domain_spells = {
            spell_level: spell_id for spell_level, spell_id in domain_spells.items()
            if spell_level in base_slots and int(spell_level) > 0
        }

        unexpected_fields = set(loadout) - {"prepared", "domainPrepared"} if isinstance(loadout, dict) else set()
        if unexpected_fields:
            issues.append(self._issue(
                "npc.spell-loadout-invalid", "the Druid spell loadout accepts only prepared and domainPrepared spells",
                path="/selections/spellLoadout", details={"unexpectedFields": sorted(unexpected_fields)}, source_refs=[druid_ref],
            ))
        if archetype_id and isinstance(loadout, dict) and "domainPrepared" in loadout:
            issues.append(self._issue(
                "npc.spell-levels-invalid",
                f"the {archetype['name'] if archetype else 'selected'} archetype replaces the Nature Bond domain slots; domainPrepared must be absent",
                path="/selections/spellLoadout/domainPrepared", details={"expectedLevels": []},
                source_refs=_dedupe_refs(archetype_refs, [druid_ref]),
            ))
        expected_levels = set(base_slots)
        if set(prepared) != expected_levels:
            issues.append(self._issue(
                "npc.spell-levels-invalid", "prepared spells must include exactly the available Druid spell levels",
                path="/selections/spellLoadout/prepared", details={"expectedLevels": sorted(expected_levels, key=int)}, source_refs=_refs(row),
            ))
        if not archetype_id:
            expected_domain_levels = set(available_domain_spells)
            if set(domain_prepared) != expected_domain_levels:
                issues.append(self._issue(
                    "npc.spell-levels-invalid", "domain preparations must include exactly the available Fire-domain spell levels",
                    path="/selections/spellLoadout/domainPrepared", details={"expectedLevels": sorted(expected_domain_levels, key=int)},
                    source_refs=_dedupe_refs(_refs(fire_domain), [cleric_ref]),
                ))

        wisdom = modifiers["wisdom"]
        highest_level = max(map(int, base_slots))
        wisdom_score = scores["wisdom"]
        required_wisdom = 10 + highest_level
        if wisdom_score < required_wisdom:
            issues.append(self._issue(
                "npc.casting-ability-insufficient", "Wisdom is too low to prepare the highest available Druid spell level",
                path="/selections/abilityGeneration", details={"actual": wisdom_score, "required": required_wisdom, "spellLevel": highest_level},
                source_refs=[druid_ref],
            ))

        slots_by_level: dict[str, dict[str, int]] = {}
        resolved_prepared: dict[str, list[str]] = {}
        for spell_level, base in base_slots.items():
            numeric_level = int(spell_level)
            wisdom_bonus = _bonus_spell_count(wisdom, numeric_level)
            domain_count = 0 if archetype_id else (slots_per_spell_level if spell_level in available_domain_spells else 0)
            slots_by_level[spell_level] = {
                "base": base, "wisdomBonus": wisdom_bonus, "domain": domain_count,
                "total": base + wisdom_bonus + domain_count,
            }
            selected = prepared.get(spell_level, [])
            expected_count = base + wisdom_bonus
            if len(selected) != expected_count:
                issues.append(self._issue(
                    "npc.spell-count-invalid", "prepared spells must fill the base and Wisdom-bonus slots exactly",
                    path=f"/selections/spellLoadout/prepared/{spell_level}",
                    details={"expected": expected_count, "selected": len(selected), "base": base, "wisdomBonus": wisdom_bonus},
                    source_refs=_dedupe_refs(_refs(row), [druid_ref, bonus_ref]),
                ))
            resolved_prepared[spell_level] = []
            for index, spell_id in enumerate(selected):
                spell = self._record("spell", spell_id)
                refs = _dedupe_refs(refs, _refs(spell))
                path = f"/selections/spellLoadout/prepared/{spell_level}/{index}"
                if spell.get("catalogStatus") != "resolved":
                    issues.append(self._gap(spell, path))
                elif spell.get("levelsByClass", {}).get("druid") != numeric_level:
                    issues.append(self._issue(
                        "npc.spell-level-invalid", "spell is not a Druid spell of the prepared level",
                        path=path, source_refs=_refs(spell),
                    ))
                resolved_prepared[spell_level].append(spell["id"])

        resolved_domain: dict[str, list[str]] = {}
        for spell_level, expected_spell_id in available_domain_spells.items():
            selected = domain_prepared.get(spell_level, [])
            expected_count = slots_per_spell_level
            if len(selected) != expected_count:
                issues.append(self._issue(
                    "npc.spell-count-invalid", "each available Fire-domain slot requires exactly one preparation",
                    path=f"/selections/spellLoadout/domainPrepared/{spell_level}",
                    details={"expected": expected_count, "selected": len(selected)}, source_refs=_dedupe_refs(_refs(fire_domain), [cleric_ref]),
                ))
            resolved_domain[spell_level] = []
            for index, spell_id in enumerate(selected):
                spell = self._record("spell", spell_id)
                refs = _dedupe_refs(refs, _refs(spell))
                path = f"/selections/spellLoadout/domainPrepared/{spell_level}/{index}"
                if spell.get("catalogStatus") != "resolved":
                    issues.append(self._gap(spell, path))
                elif spell["id"] != expected_spell_id:
                    issues.append(self._issue(
                        "npc.domain-spell-invalid", "spell does not match the Fire-domain spell for this slot level",
                        path=path, details={"expectedSpellId": expected_spell_id}, source_refs=_refs(fire_domain),
                    ))
                resolved_domain[spell_level].append(spell["id"])

        summon_by_level = {
            1: self._record("spell", "spell.summon-nature-s-ally-i"),
            2: self._record("spell", "spell.summon-nature-s-ally-ii"),
        }
        for spell in summon_by_level.values():
            refs = _dedupe_refs(refs, _refs(spell))
            if spell.get("catalogStatus") != "resolved":
                issues.append(self._gap(spell, "/selections/spellLoadout"))
        conversion_ids = conversion_catalog.get("spellIdsBySlotLevel") or {}
        conversion = {
            "name": conversion_catalog["name"], "from": conversion_catalog["from"],
            "excludesDomainSlots": conversion_catalog["excludesDomainSlots"],
            "spellIdsBySlotLevel": copy.deepcopy(conversion_ids),
        }
        if archetype_id:
            result = {
                "className": class_record["name"], "castingMode": casting_effects["castingMode"],
                "casterLevel": level, "castingAbility": casting_effects["castingAbility"],
                "castingAbilityModifier": wisdom,
                "slotsByLevel": slots_by_level, "prepared": resolved_prepared,
                "saveDcByLevel": {spell_level: 10 + int(spell_level) + wisdom for spell_level in base_slots},
                "spontaneousConversion": conversion,
            }
        else:
            result = {
                "className": class_record["name"], "castingMode": casting_effects["castingMode"],
                "casterLevel": level, "castingAbility": casting_effects["castingAbility"],
                "castingAbilityModifier": wisdom,
                "slotsByLevel": slots_by_level, "prepared": resolved_prepared,
                "domainPrepared": resolved_domain,
                "saveDcByLevel": {spell_level: 10 + int(spell_level) + wisdom for spell_level in base_slots},
                "spontaneousConversion": conversion,
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

    def _gear(
        self, selections: dict[str, Any], level: int, size_id: str | None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
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
            effects = copy.deepcopy(record.get("effects", {}))
            size_key = size_id.removeprefix("size.") if size_id else None
            damage_by_size = effects.get("damageDieBySize", {})
            if size_key in damage_by_size:
                effects["damageDie"] = damage_by_size[size_key]
            weight_by_size = record.get("weightLbBySize", {})
            weight = weight_by_size.get(size_key, record.get("weightLb", 0))
            items.append({
                "itemId": record["id"], "name": record["name"], "category": record["category"],
                "npcGearCategory": record.get("npcGearCategory"),
                "quantity": quantity, "equipped": selected.get("equipped", True), "priceCp": cost,
                "weightLb": weight * quantity, "effects": effects,
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
    def _attacks(
        items: list[dict[str, Any]], bab: int, modifiers: dict[str, int], size_modifiers: dict[str, int],
        size_id: str | None, *, finesse: bool = False,
    ) -> list[dict[str, Any]]:
        attacks = []
        for item in items:
            if item["category"] != "weapon":
                continue
            effects = item["effects"]
            damage_die = effects.get("damageDie")
            if damage_die is None and size_id:
                damage_die = effects.get("damageDieBySize", {}).get(size_id.removeprefix("size."))
            if damage_die is None:
                continue
            # ponytail: Weapon Finesse is 'may use Dex instead of Str', applied only when it helps.
            finesse_eligible = finesse and (effects.get("lightWeapon") or effects.get("finesseWeapon"))
            hit_ability = modifiers["dexterity"] if finesse_eligible and modifiers["dexterity"] > modifiers["strength"] else modifiers["strength"]
            attack_bonus = bab + hit_ability + size_modifiers.get("attack", 0)
            damage_bonus = modifiers["strength"]
            attacks.append({
                "name": item["name"], "itemId": item["itemId"], "attackBonuses": [attack_bonus],
                "attackBonusExpression": _bonus(attack_bonus),
                "damageExpression": f"{damage_die}{_bonus(damage_bonus) if damage_bonus else ''}",
                "damageType": effects.get("damageType"),
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

    def _preview_ability(
        self, selections: dict[str, Any], race: dict[str, Any] | None, ability_name: str,
        *, divine_allowed: bool = False,
    ) -> int | None:
        generation = selections.get("abilityGeneration", {})
        if not isinstance(generation, dict):
            return None
        array = self._optional("abilityArray", generation.get("arrayId", "npc-ability-array.basic"))
        if not array or array.get("catalogStatus") != "resolved":
            return None
        method = generation.get("method")
        if method in {"melee-preset", "divine-preset", "arcane-preset"}:
            if method == "divine-preset" and not divine_allowed:
                return None
            score = array.get("presets", {}).get(method.removesuffix("-preset"), {}).get(ability_name)
        else:
            score = generation.get("assignments", generation.get("scores", {})).get(ability_name)
        if not _is_int(score):
            return None
        score += (race or {}).get("abilityAdjustments", {}).get(ability_name, 0)
        if selections.get("racialChoices", {}).get("ability-bonus") == ability_name:
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
