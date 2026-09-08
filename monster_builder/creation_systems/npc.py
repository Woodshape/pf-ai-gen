"""Source-backed class-based NPC creation from composable catalog rules."""

from __future__ import annotations

import copy
import json
import math
from typing import Any

from monster_builder.catalog import CatalogError
from monster_builder.creation_systems.base import NPC, CreationSystem
from monster_builder.errors import BoundaryError
from monster_builder.npc.prerequisites import evaluate_prerequisite
from monster_builder.npc.combat import OPTION_FEATS, calculate_routine, combat_routines
from monster_builder.npc.effects import bonus as effect_bonus, conditional_modifiers, resolve as resolve_effects, validate_selections as validate_effects
from monster_builder.npc_catalog import NpcCatalog

ABILITIES = ("strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma")
ABILITY_SET = set(ABILITIES)
COMPUTED_FIELDS = {
    "level", "totalLevel", "npcCategory", "abilityScores", "abilityModifiers", "hp", "bab",
    "defenses", "initiative", "attacks", "cmb", "cmd", "skills", "speed", "senses", "languages",
    "size", "classFeatures", "spells", "gearBudget", "canonical", "effective", "derivationTrace",
    "evaluation", "cr", "ac", "fortitude", "reflex", "will", "linkedCreature", "combatRoutines", "conditionalModifiers",
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
    """Evaluate races and class progressions using their locally sourced rules."""

    key = NPC
    selection_fields = frozenset({
        "statblockUse", "raceId", "racialChoices", "classProgression", "abilityGeneration",
        "levelIncreases", "skillGeneration", "feats", "classFeatureChoices", "spellLoadout",
        "gearProfile", "gear", "details", "archetypeId", "combatOptions", "activeEffects",
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
        if len(progression) > 1:
            return self._multiclass_choice_requirements(draft)
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
            wisdom = self._preview_ability(selections, race, "wisdom")
            fire_domain = None if archetype_selected else self._selected_domain(selections)
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
            intelligence = self._preview_ability(selections, race, "intelligence")
            if intelligence is not None:
                skill_count = max(1, class_record.get("skillSelections", 0) + _ability_modifier(intelligence)) + (race or {}).get("skillSelectionsBonus", 0)

        class_id = (class_record or {}).get("id")
        array = self._optional("abilityArray", selections.get("abilityGeneration", {}).get("arrayId", "npc-ability-array.basic"))
        method_values = [f"{name}-preset" for name in (array or {}).get("presets", {})] + ["assigned-array"]
        requirements = [
            self._requirement("/selections/statblockUse", "Statblock use", "enum", ["full", "encounter"]),
            self._requirement("/selections/raceId", "Race", "catalog-id", self._catalog_values("race")),
            self._requirement("/selections/classProgression/0/classId", "Class", "catalog-id", self._catalog_values("class")),
            self._requirement("/selections/classProgression/0/levels", "Class levels", "integer",
                              [int(value) for value, row in (class_record or {}).get("levels", {}).items() if row.get("catalogStatus") == "resolved"]),
            self._requirement("/selections/abilityGeneration/method", "Ability method", "enum", method_values),
            self._requirement("/selections/skillGeneration/method", "Skill method", "enum", ["simplified", "precise"]),
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
                    "/selections/classFeatureChoices/bloodline", "Bloodline", "enum",
                    list(self._record("classFeature", "npc-class-feature.sorcerer-bloodlines").get("options", {}))
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
                        "/selections/classFeatureChoices/natureBond", "Nature Bond", "enum",
                        list(self._record("classFeature", "npc-class-feature.druid-nature-bond").get("options", {}))
                    ),
                    self._requirement(
                        "/selections/spellLoadout/domainPrepared", "Prepared Fire-domain spells", "spell-loadout"
                    ),
                ))

        existing_paths = {entry["path"] for entry in requirements}
        for feature in self._class_features(class_record, level):
            record = self._record("classFeature", feature["featureId"])
            choice_id = record.get("choiceId")
            path = f"/selections/classFeatureChoices/{choice_id}"
            if choice_id and path not in existing_paths and not (archetype_selected and choice_id == "natureBond"):
                requirements.append(self._requirement(path, record["name"], "enum", record.get("allowedValues", [])))
        if class_id == "npc-class.ranger" and class_row.get("spellsPerDay"):
            wisdom = self._preview_ability(selections, race, "wisdom")
            druid_slots = {key: {"base": base, "wisdomBonus": _bonus_spell_count(_ability_modifier(wisdom), int(key)),
                                 "total": base + _bonus_spell_count(_ability_modifier(wisdom), int(key))}
                           for key, base in class_row["spellsPerDay"].items()} if wisdom is not None else {}
            requirements.append(self._requirement("/selections/spellLoadout/prepared", "Prepared spells", "spell-loadout"))
        generation = selections.get("skillGeneration", {})
        if generation.get("method") == "precise":
            requirements = [entry for entry in requirements if entry["path"] != "/selections/skillGeneration/skills"]
            requirements.append(self._requirement("/selections/skillGeneration/ranks", "Skill ranks", "integer-map"))
        selected_skills = generation.get("skills", generation.get("selectedSkills", []))
        selected_feats = selections.get("feats", []) if isinstance(selections.get("feats"), list) else []
        for index, feat in enumerate(selected_feats):
            record = self._optional("feat", feat.get("featId")) or {}
            category = (record.get("effects") or {}).get("weaponProficiencyCategory")
            if category:
                requirements.append(self._requirement(f"/selections/feats/{index}/weaponId", "Weapon proficiency", "catalog-id",
                    [{"id": item["id"], "name": item["name"], "catalogStatus": item["catalogStatus"]}
                     for item in self.catalog.entries("item").values()
                     if item.get("catalogStatus") == "resolved" and item.get("effects", {}).get("weaponCategory") == category]))
            choice = record.get("choice", {})
            field = choice.get("field")
            if field and not category:
                record_type = {"weaponId": "item", "skillId": "skill", "spellIds": "spell"}.get(field)
                values = self._catalog_values(record_type) if record_type else choice.get("values", [])
                if field == "weaponId":
                    values = [entry for entry in values if self._record("item", entry["id"]).get("category") == "weapon"]
                requirements.append(self._requirement(f"/selections/feats/{index}/{field}", record["name"],
                    "catalog-id-array" if field == "spellIds" else "catalog-id" if record_type else "enum", values))
        requirements.append(self._requirement("/selections/combatOptions", "Optional combat routines", "combat-routine-array",
            [{"value": feat_id, "label": self._record("feat", feat_id)["name"]} for feat_id in sorted(OPTION_FEATS)]))
        requirements[-1]["required"] = False
        requirements.append(self._requirement("/selections/activeEffects", "Active Effects", "active-effect-array", [
            {"id": record["id"], "name": record["name"], "catalogStatus": record["catalogStatus"],
             "parameters": record.get("parameters", []), "minimumSourceLevel": record["tiers"][0]["level"],
             "maximumSourceLevel": 20, "sourceRefs": _refs(record)}
            for record in self.catalog.entries("activeEffect").values() if record.get("catalogStatus") == "resolved"
        ]))
        requirements[-1]["required"] = False
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
                "skills": {"method": generation.get("method", "simplified"), "count": skill_count, "selected": len(selected_skills),
                           "rankBudget": skill_count * level if skill_count is not None else None, "maxRanks": level,
                           "ranksAssigned": sum(generation.get("ranks", {}).values())},
                "feats": {"slots": feat_slots, "selected": len(selected_feats)},
                "spells": (
                    {"required": bool(class_row.get("spellsPerDay")), "classId": class_id, "mode": "prepared", "levels": druid_slots}
                    if class_record and class_record.get("id") in {"npc-class.druid", "npc-class.ranger"}
                    else {"required": bool(spell_counts), "classId": class_id, "levels": spell_counts}
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
            (4, ("feats", "combatOptions")),
            (5, ("classFeatureChoices",)),
            (6, ("spellLoadout",)),
            (7, ("gearProfile", "gear")),
            (8, ("details", "activeEffects")),
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
        if len(progression) >= 3 and selections["skillGeneration"].get("method") == "simplified":
            issues.append(self._issue("npc.simplified-skills-multiclass", "three or more classes require precise skill ranks",
                                      path="/selections/skillGeneration/method",
                                      source_refs=[self._source_ref("source.aon-creating-npcs", "Step 3: Skills", [36, 38])]))
        if len({item["classId"] for item in progression}) != len(progression):
            issues.append(self._issue(
                "npc.class-duplicate", "combine levels of the same class in one progression entry",
                path="/selections/classProgression",
            ))

        class_records: list[dict[str, Any]] = []
        rows: list[dict[str, Any]] = []
        for index, item in enumerate(progression):
            record = self._record("class", item["classId"])
            class_records.append(record)
            if record.get("catalogStatus") != "resolved":
                issues.append(self._gap(record, f"/selections/classProgression/{index}/classId"))
                continue
            for current_level in range(1, item["levels"] + 1):
                row = record.get("levels", {}).get(str(current_level))
                path = f"/selections/classProgression/{index}/levels"
                if not row or row.get("catalogStatus") != "resolved":
                    issues.append(self._gap(row or {**record, "id": f"{record['id']}.level-{current_level}"}, path))
                    break
                for feature_id in row.get("featureGrants") or []:
                    feature = self._record("classFeature", feature_id)
                    if feature.get("catalogStatus") != "resolved":
                        issues.append(self._gap(feature, path))
            else:
                rows.append(row)

        if race.get("catalogStatus") != "resolved":
            issues.append(self._gap(race, "/selections/raceId"))
        if issues:
            return self._evaluation("invalid", mode, issues)

        class_record = class_records[0]
        row = {key: sum(entry[key] for entry in rows) for key in ("bab", "fortitude", "reflex", "will")}
        heroic = any(record["category"] == "pc" for record in class_records)
        archetype_id = selections.get("archetypeId")
        archetype_class = next((record for record in class_records
                                if record["id"] == (self._optional("classFeature", archetype_id) or {}).get("classId")), class_record)
        archetype_level = next(item["levels"] for item in progression if item["classId"] == archetype_class["id"])
        archetype, archetype_issues = self._archetype(selections, archetype_class)
        issues.extend(archetype_issues)
        scores, ability_refs, ability_issues = self._abilities(selections, race, total_level)
        issues.extend(ability_issues)
        if not scores:
            return self._evaluation("invalid", mode, issues)
        gear_result, gear_refs, gear_issues, gear_warnings = self._gear(selections, total_level, race.get("sizeId"))
        issues.extend(gear_issues)
        warnings.extend(gear_warnings)
        modifiers = {ability: _ability_modifier(score) for ability, score in scores.items()}
        class_features, feature_refs, feature_issues, granted_feats = self._progression_features(
            selections, race, progression, class_records, rows, modifiers, archetype,
        )
        issues.extend(feature_issues)
        skills, skill_refs, skill_issues = self._skills(selections, race, progression, class_records, total_level, scores, gear_result, class_features)
        issues.extend(skill_issues)
        languages, language_refs, language_issues = self._languages(selections, race, class_features, skills)
        issues.extend(language_issues)
        spells, spell_refs, spell_issues, spell_warnings = self._progression_spells(
            selections, progression, class_records, rows, scores, modifiers, archetype,
        )
        issues.extend(spell_issues)
        warnings.extend(spell_warnings)
        feats, feat_effects, feat_refs, feat_issues = self._feats(
            selections, race, total_level, scores, bab=row["bab"], skills=skills,
            features=class_features, spells=spells, granted_feats=granted_feats,
        )
        issues.extend(feat_issues)
        feats.extend(granted_feats)
        for feature in class_features:
            feature_effects = self._record("classFeature", feature["featureId"]).get("effects") or {}
            feat_effects.setdefault("conditionalModifiers", []).extend(copy.deepcopy(feature_effects.get("conditionalModifiers", [])))
        for skill in skills:
            if skill["skillId"] in feat_effects.get("skillFocus", []):
                bonus = 6 if skill["ranks"] >= 10 else 3
                skill["total"] += bonus
                skill["featBonus"] = bonus
                skill["sourceRefs"] = _dedupe_refs(skill.get("sourceRefs", []), feat_refs)
        skill_refs = _dedupe_refs(skill_refs, feat_refs) if feat_effects.get("skillFocus") else skill_refs
        if spells:
            spells["concentration"] = spells["casterLevel"] + modifiers[spells["castingAbility"]]
            spell_refs = _dedupe_refs(spell_refs, [self._source_ref("source.aon-concentration", "Concentration", [4, 4])])
            if feat_effects.get("schoolDCBonus"):
                spells["saveDcBySpell"] = {}
                for field in ("known", "prepared", "domainPrepared"):
                    for spell_level, spell_ids in spells.get(field, {}).items():
                        for spell_id in spell_ids:
                            spell = self._record("spell", spell_id)
                            school = (spell.get("school") or "").split(" (")[0].lower()
                            if not school:
                                issues.append(self._gap(spell, "/selections/spellLoadout"))
                            spells["saveDcBySpell"][spell_id] = 10 + int(spell_level) + modifiers[spells["castingAbility"]] + feat_effects["schoolDCBonus"].get(school, 0)
                spell_refs = _dedupe_refs(spell_refs, feat_refs)
        linked_creature, linked_refs, linked_issues = None, [], []
        if archetype is not None:
            linked_creature, linked_refs, linked_issues = self._linked_creature(archetype, archetype_level)
            issues.extend(linked_issues)
        if issues:
            return self._evaluation("invalid", mode, issues, warnings)

        active_effects, active_modifiers, active_refs = resolve_effects(selections.get("activeEffects", []), self.catalog)
        if active_effects:
            old_modifiers = modifiers
            scores = {ability: score + effect_bonus(active_modifiers, ability) for ability, score in scores.items()}
            modifiers = {ability: _ability_modifier(score) for ability, score in scores.items()}
            raging = any(effect["effectId"] == "npc-effect.rage" for effect in active_effects)
            for skill in skills:
                delta = modifiers[skill["ability"]] - old_modifiers[skill["ability"]] + effect_bonus(active_modifiers, skill["skillId"])
                skill["total"] += delta
                if delta:
                    skill["activeEffectBonus"] = delta
                if raging and skill["ability"] in {"charisma", "dexterity", "intelligence"} and skill["skillId"] not in {"skill.acrobatics", "skill.fly", "skill.intimidate", "skill.ride"}:
                    skill.update(usable=False, restriction="unavailable while raging")
                skill["sourceRefs"] = _dedupe_refs(skill.get("sourceRefs", []), active_refs)
            if raging and spells:
                spells["castingRestricted"] = "Cannot cast spells or use abilities requiring patience or concentration while raging."
            ability_refs = _dedupe_refs(ability_refs, active_refs)
            skill_refs = _dedupe_refs(skill_refs, active_refs)

        class_refs = _dedupe_refs(*[_refs(record) for record in class_records], *[_refs(entry) for entry in rows])
        combat_ref = self._source_ref("source.aon-combat", "Combat Statistics", [24, 58])
        maneuver_ref = self._source_ref("source.aon-combat", "Combat Maneuvers", [536, 544])
        hp_rule = self._record("derivedRule", "npc-rule.average-hp")
        cr_rule = self._record("derivedRule", "npc-rule.classed-npc-cr")
        cr = total_level + cr_rule["pcClassAdjustment" if heroic else "npcClassAdjustment"]
        if cr < 1:
            cr = cr_rule["belowOneProgression"][-cr]
        hp_policy = hp_rule["byNpcCategory"]["heroic" if heroic else "basic"]
        round_die = math.ceil if hp_policy["rounding"] == "ceil" else math.floor
        hp = sum(item["levels"] * (round_die((int(record["hitDie"][1:]) + 1) / 2) + modifiers["constitution"])
                 for item, record in zip(progression, class_records))
        first_die = int(class_record["hitDie"][1:])
        if hp_policy["firstLevelMax"]:
            hp += first_die - round_die((first_die + 1) / 2)
        feat_hp = max(feat_effects["hpPerLevelMinimum"], total_level) if feat_effects.get("hpPerLevelMinimum") else 0
        hp += feat_hp
        hp_modifier = total_level * modifiers["constitution"] + feat_hp
        bab = row["bab"]
        size_modifiers = race.get("sizeModifiers", {})
        equipped = [entry for entry in gear_result["items"] if entry["equipped"]]
        armor_bonus = sum(entry["effects"].get("armorBonus", 0) for entry in equipped)
        shield_bonus = sum(entry["effects"].get("shieldBonus", 0) for entry in equipped)
        if shield_bonus:
            shield_bonus += feat_effects.get("shieldAC", 0)
        armor_bonus = effect_bonus(active_modifiers, "ac", "armor", armor_bonus)
        shield_bonus = effect_bonus(active_modifiers, "ac", "shield", shield_bonus)
        dodge_bonus = effect_bonus(active_modifiers, "ac", "dodge", feat_effects.get("dodgeAC", 0))
        extra_ac = effect_bonus(active_modifiers, "ac") - sum(effect_bonus(active_modifiers, "ac", kind) for kind in ("armor", "shield", "dodge"))
        max_dex_values = [entry["effects"]["maxDex"] for entry in equipped if "maxDex" in entry["effects"]]
        dex_to_ac = min([modifiers["dexterity"], *max_dex_values]) if max_dex_values else modifiers["dexterity"]
        feat_saves = feat_effects.get("saves", {})
        resistance_bonus = max((entry["effects"].get("resistanceBonus", 0) for entry in equipped), default=0)
        race_saves = race.get("saveBonuses", {}) if isinstance(race.get("saveBonuses"), dict) else {}
        ac_breakdown = {
            key: value for key, value in (
                ("armor", armor_bonus), ("shield", shield_bonus), ("dodge", dodge_bonus),
                ("dexterity", dex_to_ac), ("size", size_modifiers.get("ac", 0)),
                ("deflection", effect_bonus(active_modifiers, "ac", "deflection")),
                ("active effects", extra_ac - effect_bonus(active_modifiers, "ac", "deflection")),
            ) if value
        }
        defenses = {
            "ac": 10 + armor_bonus + shield_bonus + dex_to_ac + size_modifiers.get("ac", 0) + dodge_bonus + extra_ac,
            "touch": 10 + dex_to_ac + size_modifiers.get("ac", 0) + dodge_bonus + extra_ac,
            "flatFooted": 10 + armor_bonus + shield_bonus + size_modifiers.get("ac", 0) + min(0, dex_to_ac) + extra_ac,
            "fortitude": row["fortitude"] + modifiers["constitution"] + feat_saves.get("fortitude", 0) + resistance_bonus + race_saves.get("fortitude", 0),
            "reflex": row["reflex"] + modifiers["dexterity"] + feat_saves.get("reflex", 0) + resistance_bonus + race_saves.get("reflex", 0),
            "will": row["will"] + modifiers["wisdom"] + feat_saves.get("will", 0) + resistance_bonus + race_saves.get("will", 0),
            "acBreakdown": ac_breakdown,
        }
        for save in ("fortitude", "reflex", "will"):
            defenses[save] += effect_bonus(active_modifiers, save) - effect_bonus(active_modifiers, save, "resistance")
            defenses[save] += effect_bonus(active_modifiers, save, "resistance", resistance_bonus) - resistance_bonus
        proficiencies = self._proficiencies(class_features, feat_effects, race)
        armor_attack_penalty = sum(item["effects"].get("armorCheckPenalty", 0) for item in equipped
                                   if (item["effects"].get("armorCategory") and item["effects"]["armorCategory"] not in proficiencies["armor"])
                                   or (item["effects"].get("shieldCategory") and item["effects"]["shieldCategory"] not in proficiencies["shields"]))
        if any(feat["featId"] == "feat.improved-unarmed-strike" for feat in feats):
            equipped.append({"itemId": "unarmed-strike", "name": "Unarmed strike (lethal or nonlethal)",
                             "category": "weapon", "effects": {"weaponType": "unarmed-strike", "weaponCategory": "simple",
                             "damageDie": "1d2" if race.get("sizeId") == "size.small" else "1d3",
                             "damageType": "B", "lightWeapon": True}})
            proficiencies["weapons"].add("unarmed-strike")
        attacks = self._attacks(equipped, bab, modifiers, size_modifiers, race.get("sizeId"),
                                weapon_proficiencies=proficiencies["weapons"], armor_penalty=armor_attack_penalty,
                                finesse=any(feat.get("featId") == "feat.weapon-finesse" for feat in feats),
                                rapid_shot=any(feat.get("featId") == "feat.rapid-shot" for feat in feats),
                                feat_effects=feat_effects, active_attack_bonus=effect_bonus(active_modifiers, "attack"),
                                active_damage_bonus=effect_bonus(active_modifiers, "weaponDamage"))
        resistances: dict[str, int] = {}
        for feature in class_features:
            for power in feature.get("powers", []):
                if power.get("attackBonus") is not None:
                    power["attackBonus"] += armor_attack_penalty + effect_bonus(active_modifiers, "attack")
                if power.get("damageExpression") and power.get("attackBonus") is not None:
                    attacks.append({
                        "name": power["name"], "attackBonuses": [power["attackBonus"]],
                        "attackBonusExpression": _bonus(power["attackBonus"]), "attackType": power.get("attackType", "ranged touch"),
                        "damageExpression": power["damageExpression"], "damageType": power.get("damageType"),
                        "range": power.get("range"), "usesPerDay": power.get("usesPerDay"),
                    })
                resistances.update(power.get("resistance", {}))
        for effect in active_effects:
            if "energyResistance" in effect:
                energy = effect["energyType"]
                resistances[energy] = max(resistances.get(energy, 0), effect["energyResistance"])
        routine_modifiers = {**modifiers, "characterLevel": total_level,
                             "casterLevel": max((item["levels"] for item in progression
                                 if item["classId"] in {"npc-class.bard", "npc-class.sorcerer", "npc-class.wizard"}), default=0),
                             "monkLevels": next((item["levels"] for item in progression if item["classId"] == "npc-class.monk"), 0)}
        feat_ids = [feat["featId"] for feat in feats]
        routines = combat_routines(equipped, attacks, feat_ids, bab, routine_modifiers)
        for index, request in enumerate(selections.get("combatOptions", [])):
            try:
                routine = calculate_routine(equipped, attacks, feat_ids, bab, routine_modifiers, request)
                routine["selected"] = True
                routines.append(routine)
            except ValueError as error:
                issues.append(self._issue("npc.combat-option-invalid", str(error), path=f"/selections/combatOptions/{index}", source_refs=feat_refs))
        if issues:
            return self._evaluation("invalid", mode, issues, warnings)
        for routine in routines:
            routine["sourceRefs"] = _dedupe_refs(feat_refs, gear_refs,
                [self._source_ref("source.aon-equipment", "Weapon handedness and Strength multipliers", [58, 62]),
                 self._source_ref("source.aon-combat", "Two-Weapon Fighting", [592, 596])])
        cmb = bab + modifiers["strength"] + size_modifiers.get("cmb", 0) + effect_bonus(active_modifiers, "attack")
        cmd = 10 + bab + modifiers["strength"] + modifiers["dexterity"] + size_modifiers.get("cmd", 0) + dodge_bonus + extra_ac
        source_groups = {
            "abilities": ability_refs,
            "class": class_refs,
            "hp": _dedupe_refs(class_refs, _refs(hp_rule), ability_refs, feat_refs),
            "gear": gear_refs,
            "feats": feat_refs,
            "skills": skill_refs,
            "combat": _dedupe_refs(class_refs, ability_refs, gear_refs, feature_refs, feat_refs,
                                  [combat_ref, self._source_ref("source.aon-equipment", "Weapon nonproficiency", [49, 49]),
                                   self._source_ref("source.aon-equipment", "Armor check penalties and nonproficiency", [308, 310]),
                                   self._source_ref("source.aon-equipment", "Unarmed weapon damage and handedness", [58, 62]),
                                   self._source_ref("source.aon-equipment", "Table: Weapons", [108, 112])]),
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
            "cr": cr,
            "npcCategory": "heroic" if heroic else "basic",
            "raceId": race["id"],
            "raceName": race["name"],
            "classProgression": [{"classId": record["id"], "className": record["name"], "levels": item["levels"]}
                                 for item, record in zip(progression, class_records)],
            "abilityScores": scores,
            "abilityModifiers": modifiers,
            "hitDiceExpression": "+".join(f"{item['levels']}{record['hitDie']}" for item, record in zip(progression, class_records))
                                 + (_bonus(hp_modifier) if hp_modifier else ""),
            "hp": hp,
            "bab": bab,
            "defenses": defenses,
            "initiative": modifiers["dexterity"] + feat_effects.get("initiative", 0),
            "attacks": attacks,
            "combatRoutines": routines,
            "cmb": cmb,
            "cmd": cmd,
            "skills": skills,
            "feats": feats,
            "conditionalModifiers": feat_effects.get("conditionalModifiers", []) + conditional_modifiers(active_modifiers, resistance_bonus),
            **({"activeEffects": active_effects,
                "energyProtection": {effect["energyType"]: effect["absorptionPool"] for effect in active_effects if "absorptionPool" in effect}}
               if active_effects else {}),
            "classFeatures": class_features,
            **({"linkedCreature": linked_creature} if linked_creature is not None else {}),
            "spells": spells,
            "gearBudget": gear_result["budget"],
            "gear": gear_result["items"],
            "speed": copy.deepcopy(race.get("speed", {"land": 30})),
            "senses": copy.deepcopy(race.get("senses", [])),
            "languages": languages,
            "size": {"id": race.get("sizeId", "size.medium"), "name": race.get("sizeId", "size.medium").split(".")[-1].title()},
            "creatureType": f"humanoid ({race['subtype']})" if race.get("subtype") else "humanoid",
            "alignment": selections.get("details", {}).get("alignment"),
            "resistances": resistances,
            "immunities": copy.deepcopy((race.get("immunities") or {}).get("values", [])),
            "conditionalSaves": copy.deepcopy(race.get("conditionalSaves")),
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
            feature_calculation = "apply automatic features and selected class-feature options at each class's level"
            spell_calculation = "validate the casting class's loadout, slots, caster level, and casting ability"
        trace = [
            self._trace("/canonical/level", total_level, "sum selected class levels", class_refs),
            self._trace("/canonical/cr", cr, "class levels − 1 for heroic NPCs, − 2 for basic NPCs; step through fractional CRs below 1", source_groups["cr"]),
            self._trace("/canonical/abilityScores", scores, "apply the NPC array, racial adjustments, and level increases", ability_refs),
            self._trace("/canonical/hp", hp,
                        f"house rule: {hp_policy['rounding']} each die average; "
                        + ("maximize first die; " if hp_policy["firstLevelMax"] else "no maximized die; ")
                        + "add Constitution once per level and permanent feat HP bonuses", source_groups["hp"]),
            self._trace("/canonical/bab", bab, "sum the selected class level rows", class_refs),
            self._trace("/canonical/defenses", defenses, "combine class saves, abilities, armor, shield, and feat bonuses", source_groups["combat"]),
            self._trace("/canonical/initiative", canonical["initiative"], "Dexterity modifier plus feat bonuses", _dedupe_refs(ability_refs, feat_refs, [combat_ref])),
            self._trace("/canonical/attacks", attacks, "base attacks: BAB, ability, size, equipment and nonproficiency; bows apply Strength penalties but not bonuses; no temporary buffs", source_groups["combat"]),
            self._trace("/canonical/combatRoutines", routines, "optional feat routines composed from base attacks; conditions and state costs never change base statistics", _dedupe_refs(source_groups["combat"], *[routine["sourceRefs"] for routine in routines])),
            self._trace("/canonical/cmb", cmb, "BAB + Strength modifier + size modifier", source_groups["maneuvers"]),
            self._trace("/canonical/cmd", cmd, "10 + BAB + Strength modifier + Dexterity modifier + size modifier + dodge bonuses", _dedupe_refs(source_groups["maneuvers"], feat_refs)),
            self._trace("/canonical/conditionalModifiers", canonical["conditionalModifiers"], "conditional feat and feature modifiers; never applied to base totals", _dedupe_refs(feat_refs, feature_refs)),
            self._trace(
                "/canonical/skills", skills,
                "simplified or precise ranks plus trained class-skill bonus, ability, armor, size, racial and permanent class-feature and feat modifiers",
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
            self._trace("/canonical/languages", languages, "racial and class languages plus languages selected with Linguistics ranks", language_refs),
            self._trace("/canonical/gearBudget", gear_result["budget"], "read the NPC category and level row from Table 14-9; descriptive gear is unpriced", gear_refs),
        ]
        if active_effects:
            for entry in trace:
                if entry["path"] in {"/canonical/abilityScores", "/canonical/hp", "/canonical/defenses", "/canonical/attacks", "/canonical/combatRoutines", "/canonical/cmb", "/canonical/cmd", "/canonical/skills", "/canonical/classFeatures", "/canonical/spells", "/canonical/conditionalModifiers"}:
                    entry["sourceRefs"] = _dedupe_refs(entry["sourceRefs"], active_refs)
                    entry["calculation"] = "Base rules plus selected active effects; typed bonuses overlap; conditional effects remain conditional."
            trace.append(self._trace("/canonical/activeEffects", active_effects, "source-level active effect snapshot; no automatic duration or resource expenditure", active_refs))
            trace.append(self._trace("/canonical/resistances", resistances, "highest same-energy resistance; Protection from Energy uses a separate finite pool", active_refs))
            trace.append(self._trace("/canonical/energyProtection", canonical["energyProtection"], "12 per source caster level, capped at 120; track damage expenditure in play", active_refs))
        return self._evaluation("valid", mode, [], warnings, canonical, trace)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def _validate_shapes(self, selections: dict[str, Any]) -> None:
        validate_effects(selections.get("activeEffects", []), self.catalog)
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
            if "method" in ability and ability["method"] not in {"melee-preset", "ranged-preset", "divine-preset", "arcane-preset", "skill-preset", "assigned-array", "custom", "rolled", "purchase"}:
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
            self._reject_unknown(skills, {"method", "skills", "selectedSkills", "ranks", "includeUntrained", "specialties", "languages"}, "/selections/skillGeneration")
            self._reject_alias_conflict(skills, ("skills", "selectedSkills"), "/selections/skillGeneration")
            if skills.get("method") not in {None, "simplified", "precise"}:
                raise BoundaryError("selection.value-invalid", "skillGeneration.method must be simplified or precise", "/selections/skillGeneration/method")
            values = skills.get("skills", skills.get("selectedSkills", []))
            if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
                raise BoundaryError("selection.type-invalid", "skills must be an array of IDs", "/selections/skillGeneration/skills")
            if "ranks" in skills and (not isinstance(skills["ranks"], dict) or any(not isinstance(key, str) or not _is_int(value) or value < 0 for key, value in skills["ranks"].items())):
                raise BoundaryError("selection.type-invalid", "precise ranks must map skill IDs to non-negative integers", "/selections/skillGeneration/ranks")

        if isinstance(skills, dict):
            for field in ("includeUntrained", "languages"):
                values = skills.get(field, [])
                if not isinstance(values, list) or any(not isinstance(value, str) or not value.strip() for value in values):
                    raise BoundaryError("selection.type-invalid", f"{field} must be an array of non-empty strings", f"/selections/skillGeneration/{field}")
            specialties = skills.get("specialties", {})
            if not isinstance(specialties, dict) or any(not isinstance(key, str) or not isinstance(value, str) or not value.strip() for key, value in specialties.items()):
                raise BoundaryError("selection.type-invalid", "specialties must map skill IDs to non-empty names", "/selections/skillGeneration/specialties")

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
                self._reject_unknown(item, {"slotId", "featId", "weaponId", "skillId", "school", "subtype", "spellIds"}, path)
                for field in ("weaponId", "skillId", "school", "subtype"):
                    if field in item and (not isinstance(item[field], str) or not item[field]):
                        raise BoundaryError("selection.type-invalid", f"{field} must be a nonempty string", f"{path}/{field}")
                if "spellIds" in item and (not isinstance(item["spellIds"], list) or any(not isinstance(value, str) or not value for value in item["spellIds"])):
                    raise BoundaryError("selection.type-invalid", "spellIds must be an array of IDs", f"{path}/spellIds")

        combat_options = selections.get("combatOptions", [])
        if not isinstance(combat_options, list):
            raise BoundaryError("selection.type-invalid", "combatOptions must be an array", "/selections/combatOptions")
        for index, option in enumerate(combat_options):
            path = f"/selections/combatOptions/{index}"
            if not isinstance(option, dict):
                raise BoundaryError("selection.type-invalid", "combat option must be an object", path)
            self._reject_unknown(option, {"weaponId", "offHandWeaponId", "action", "options"}, path)
            for field in ("weaponId", "offHandWeaponId", "action"):
                if field in option and (not isinstance(option[field], str) or not option[field]):
                    raise BoundaryError("selection.type-invalid", f"{field} must be a nonempty string", f"{path}/{field}")
            if not isinstance(option.get("options"), list) or any(not isinstance(value, str) for value in option["options"]):
                raise BoundaryError("selection.type-invalid", "options must be an array of feat IDs", f"{path}/options")

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
                if isinstance(item, str):
                    if not item.strip():
                        raise BoundaryError("selection.value-invalid", "descriptive equipment must not be empty", path)
                    continue
                if not isinstance(item, dict) or not isinstance(item.get("itemId"), str):
                    raise BoundaryError("selection.type-invalid", "each gear entry requires itemId", path)
                self._reject_unknown(item, {"itemId", "quantity", "equipped", "masterwork", "enhancementBonus", "properties", "propertyIds", "charges"}, path)
                if "quantity" in item and (not _is_int(item["quantity"]) or item["quantity"] < 1):
                    raise BoundaryError("selection.value-invalid", "gear quantity must be positive", f"{path}/quantity")
                if "equipped" in item and not isinstance(item["equipped"], bool):
                    raise BoundaryError("selection.type-invalid", "equipped must be a boolean", f"{path}/equipped")
                if "masterwork" in item and not isinstance(item["masterwork"], bool):
                    raise BoundaryError("selection.type-invalid", "masterwork must be a boolean", f"{path}/masterwork")
                if "enhancementBonus" in item and (not _is_int(item["enhancementBonus"]) or not 0 <= item["enhancementBonus"] <= 5):
                    raise BoundaryError("selection.value-invalid", "enhancementBonus must be an integer from 0 through 5", f"{path}/enhancementBonus")
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
            for field in ("ranks", "specialties"):
                for skill_id in skills.get(field, {}):
                    lookups.append(("skill", skill_id, f"/selections/skillGeneration/{field}/{skill_id}"))
            for index, skill_id in enumerate(skills.get("includeUntrained", [])):
                lookups.append(("skill", skill_id, f"/selections/skillGeneration/includeUntrained/{index}"))
        for index, item in enumerate(selections.get("feats", [])):
            lookups.append(("feat", item["featId"], f"/selections/feats/{index}/featId"))
            lookups.append(("item", item.get("weaponId"), f"/selections/feats/{index}/weaponId"))
            lookups.append(("skill", item.get("skillId"), f"/selections/feats/{index}/skillId"))
            for spell_index, spell_id in enumerate(item.get("spellIds", [])):
                lookups.append(("spell", spell_id, f"/selections/feats/{index}/spellIds/{spell_index}"))
        spell_loadout = selections.get("spellLoadout", {})
        if isinstance(spell_loadout, dict):
            for field in ("known", "prepared", "domainPrepared"):
                for level, spells in spell_loadout.get(field, {}).items():
                    for index, spell_id in enumerate(spells):
                        lookups.append(("spell", spell_id, f"/selections/spellLoadout/{field}/{level}/{index}"))
        for index, item in enumerate(selections.get("gear", [])):
            if isinstance(item, dict):
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
        if method in {"melee-preset", "ranged-preset", "divine-preset", "arcane-preset"}:
            preset = array.get("presets", {}).get(method.removesuffix("-preset"))
            if preset is None:
                return {}, _refs(array), [self._issue("npc.ability-preset-unavailable", "the selected array has no such preset",
                                                     path="/selections/abilityGeneration/method", source_refs=_refs(array))]
            scores = copy.deepcopy(preset)
        elif method == "assigned-array":
            scores = copy.deepcopy(generation.get("assignments", generation.get("scores", {})))
            if sorted(scores.values()) != sorted(array["scores"]):
                issues.append(self._issue("npc.ability-array-invalid", "assigned scores must use the selected NPC array exactly", path="/selections/abilityGeneration/assignments", source_refs=_refs(array)))
        else:
            return {}, _refs(array), [self._issue("npc.ability-method-unimplemented", "only catalog presets and assigned-array ability generation are implemented", path="/selections/abilityGeneration/method", source_refs=_refs(array))]

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

    def _languages(self, selections, race, features, skills):
        languages = list(race.get("languages", []))
        refs = _refs(race)
        for feature in features:
            record = self._record("classFeature", feature["featureId"])
            languages.extend(record.get("effects", {}).get("languages", []))
            if record.get("effects", {}).get("languages"):
                refs = _dedupe_refs(refs, _refs(record))
        chosen = [value.strip() for value in selections["skillGeneration"].get("languages", [])]
        ranks = next((skill["ranks"] for skill in skills if skill["skillId"] == "skill.linguistics"), 0)
        issues = []
        if chosen:
            refs = _dedupe_refs(refs, _refs(self._record("skill", "skill.linguistics")))
            if len(chosen) > ranks or len({value.casefold() for value in languages + chosen}) != len(languages + chosen):
                issues.append(self._issue("npc.language-choice-invalid", "Linguistics grants one new language per rank, without duplicates",
                                          path="/selections/skillGeneration/languages", source_refs=refs, details={"available": ranks}))
            if any(value.casefold() == "druidic" for value in chosen):
                issues.append(self._issue("npc.language-choice-invalid", "Druidic is a restricted class language, not a Linguistics selection",
                                          path="/selections/skillGeneration/languages", source_refs=refs))
        return list(dict.fromkeys(languages + chosen)), refs, issues

    def _skills(self, selections, race, progression, class_records, level, scores, gear, features):
        generation = selections["skillGeneration"]
        method = generation["method"]
        refs = _dedupe_refs(*[_refs(record) for record in class_records],
                           [self._source_ref("source.aon-creating-npcs", "Step 3: Skills", [36, 38]),
                            self._source_ref("source.aon-skills", "Acquiring Skills", [3, 4])])
        issues = []
        budgets = [max(1, record["skillSelections"] + _ability_modifier(scores["intelligence"]))
                   + race.get("skillSelectionsBonus", 0) for record in class_records]
        if method == "precise":
            ranks = {skill_id: rank for skill_id, rank in generation.get("ranks", {}).items() if rank}
            budget = sum(item["levels"] * count for item, count in zip(progression, budgets))
            if sum(ranks.values()) != budget or any(value > level for value in ranks.values()):
                issues.append(self._issue("npc.skill-ranks-invalid", "precise ranks must fill the rank budget and cannot exceed total HD per skill",
                                          path="/selections/skillGeneration/ranks", source_refs=refs,
                                          details={"rankBudget": budget, "assigned": sum(ranks.values()), "maxRanks": level}))
        else:
            selected = generation.get("skills", generation.get("selectedSkills", []))
            if len(selected) != max(budgets) or len(set(selected)) != len(selected):
                issues.append(self._issue("npc.skill-count-invalid", "simplified skills must fill the largest class selection budget without duplicates",
                                          path="/selections/skillGeneration/skills", source_refs=refs,
                                          details={"expected": max(budgets), "selected": len(selected)}))
            ranks = {skill_id: sum(item["levels"] for item, count in zip(progression, budgets) if index < count)
                     for index, skill_id in enumerate(selected)}
        for skill_id in generation.get("includeUntrained", []):
            ranks.setdefault(skill_id, 0)
        for feat in selections.get("feats", []):
            skill_id = feat.get("skillId")
            if skill_id and not self._record("skill", skill_id).get("trainedOnly"):
                ranks.setdefault(skill_id, 0)
        specialties = generation.get("specialties", {})
        if set(specialties) - set(ranks):
            issues.append(self._issue("npc.skill-specialty-invalid", "specialties must refer to displayed skills", path="/selections/skillGeneration/specialties"))
        feature_bonuses = {}
        feature_bonus_refs = {}
        knowledge_bonus = 0
        knowledge_refs = []
        for feature in features:
            record = self._record("classFeature", feature["featureId"])
            effects = record.get("effects", {})
            for skill_id, bonus in effects.get("skillBonuses", {}).items():
                feature_bonuses[skill_id] = feature_bonuses.get(skill_id, 0) + bonus
                feature_bonus_refs.setdefault(skill_id, []).extend(_refs(record))
            if feature.get("knowledgeBonus"):
                knowledge_bonus = max(knowledge_bonus, feature["knowledgeBonus"])
                knowledge_refs = _dedupe_refs(knowledge_refs, _refs(record))
            if effects.get("skillBonuses"):
                refs = _dedupe_refs(refs, _refs(record))
        class_skills = {skill_id for cls in class_records for skill_id in cls.get("classSkills", [])}
        armor_penalty = sum(item["effects"].get("armorCheckPenalty", 0) for item in gear["items"] if item["equipped"])
        results = []
        for skill_id, rank in ranks.items():
            record = self._record("skill", skill_id)
            refs = _dedupe_refs(refs, _refs(record))
            if record.get("keyAbility") not in ABILITY_SET or not isinstance(record.get("armorCheckPenalty"), bool):
                issues.append(self._gap(record, "/selections/skillGeneration"))
                continue
            is_knowledge = record.get("group") == "knowledge"
            if rank == 0 and record.get("trainedOnly") and not (is_knowledge and knowledge_bonus):
                issues.append(self._issue("npc.skill-trained-only", "this skill requires a rank for ordinary use", path="/selections/skillGeneration/includeUntrained", source_refs=_refs(record)))
            specialty = specialties.get(skill_id, "").strip()
            if specialty and not record.get("hasSpecialty"):
                issues.append(self._issue("npc.skill-specialty-invalid", "this skill has no selectable specialty", path=f"/selections/skillGeneration/specialties/{skill_id}"))
            class_skill = skill_id in class_skills
            acp = armor_penalty if record["armorCheckPenalty"] else 0
            race_bonus = (race.get("skillBonuses") or {}).get(skill_id, 0)
            size_bonus = (race.get("sizeSkillBonuses") or {}).get(skill_id, 0)
            feature_bonus = feature_bonuses.get(skill_id, 0) + (knowledge_bonus if is_knowledge else 0)
            total = rank + (3 if class_skill and rank else 0) + _ability_modifier(scores[record["keyAbility"]]) + acp + race_bonus + size_bonus + feature_bonus
            entry_refs = _dedupe_refs(_refs(record), _refs(race) if race_bonus or size_bonus else [],
                                     feature_bonus_refs.get(skill_id, []), knowledge_refs if is_knowledge else [])
            refs = _dedupe_refs(refs, entry_refs)
            results.append({"skillId": skill_id, "name": record["name"] + (f" ({specialty})" if specialty else ""),
                            "ability": record["keyAbility"], "ranks": rank, "classSkill": class_skill,
                            "armorCheckPenalty": acp, **({"raceBonus": race_bonus} if race_bonus else {}),
                            **({"sizeBonus": size_bonus} if size_bonus else {}),
                            **({"classFeatureBonus": feature_bonus} if feature_bonus else {}),
                            "total": total, "sourceRefs": entry_refs})
        return results, refs, issues

    def _multiclass_class_features(
        self,
        selections: dict[str, Any],
        progression: list[dict[str, Any]],
        class_records: list[dict[str, Any]],
        rows: list[dict[str, Any]],
        modifiers: dict[str, int],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        features: list[dict[str, Any]] = []
        feature_context: dict[str, tuple[dict[str, Any], int]] = {}
        refs = _dedupe_refs(*[_refs(record) for record in class_records], *[_refs(row) for row in rows])
        issues: list[dict[str, Any]] = []
        for class_index, (class_record, item) in enumerate(zip(class_records, progression)):
            class_level = item["levels"]
            for current_level in range(1, class_level + 1):
                row = class_record.get("levels", {}).get(str(current_level), {})
                for feature_id in row.get("featureGrants") or []:
                    if feature_id in feature_context:
                        continue
                    record = self._record("classFeature", feature_id)
                    refs = _dedupe_refs(refs, _refs(record))
                    if record.get("catalogStatus") != "resolved":
                        issues.append(self._gap(record, f"/selections/classProgression/{class_index}/levels"))
                        continue
                    entry: dict[str, Any] = {
                        "featureId": record["id"], "name": record["name"], "sourceRefs": _refs(record),
                    }
                    if record.get("statblockRole"):
                        entry["statblockRole"] = record["statblockRole"]
                    if record.get("effects"):
                        entry["effects"] = copy.deepcopy(record["effects"])
                    features.append(entry)
                    feature_context[feature_id] = (record, class_level)

        choices = selections.get("classFeatureChoices", {})
        if not isinstance(choices, dict):
            choices = {}
        choice_features: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
        for entry in features:
            record, class_level = feature_context[entry["featureId"]]
            choice_id = record.get("choiceId")
            if choice_id:
                choice_features[choice_id] = (record, entry)
        for choice_id in sorted(set(choices) - set(choice_features)):
            issues.append(self._issue(
                "npc.choice-invalid", "classFeatureChoices contains a choice not granted by the selected class levels",
                path=f"/selections/classFeatureChoices/{choice_id}",
            ))
        for choice_id, (record, entry) in choice_features.items():
            path = f"/selections/classFeatureChoices/{choice_id}"
            if choice_id not in choices:
                issues.append(self._issue(
                    "npc.selection-required", "the selected class levels require this class-feature choice",
                    path=path, source_refs=_refs(record),
                ))
                continue
            choice = choices[choice_id]
            if choice == "animal-companion" and choice_id == "huntersBond":
                issues.append(self._issue(
                    "npc.catalog-gap", "the animal-companion Hunter's Bond requires an unresolved wolf companion catalog row",
                    kind="catalog-data", path=path,
                    details={"recordId": "npc-animal-companion.wolf", "catalogStatus": "gap"},
                    source_refs=_refs(record),
                ))
                continue
            allowed = record.get("allowedValues", [])
            if choice not in allowed:
                issues.append(self._issue(
                    "npc.catalog-gap", "rules for this class-feature option are not catalogued",
                    path=path, details={"allowedValues": copy.deepcopy(allowed)}, source_refs=_refs(record),
                ))
                continue
            option = record.get("options", {}).get(choice, {})
            entry["choice"] = choice
            if option.get("name"):
                entry["name"] = f"{record['name']} ({option['name']})"
            if option.get("grantsFeat"):
                entry["grantsFeat"] = option["grantsFeat"]
            refs = _dedupe_refs(refs, _refs(option))

        for entry in features:
            feature_id = entry["featureId"]
            _, class_level = feature_context[feature_id]
            if feature_id == "npc-class-feature.ranger-wild-empathy":
                entry["checkBonus"] = class_level + modifiers["charisma"]
            elif feature_id == "npc-class-feature.ranger-track":
                entry["conditionalBonuses"] = {
                    "skillId": "skill.survival", "bonus": max(1, class_level // 2), "condition": "following tracks",
                }
            elif feature_id == "npc-class-feature.ranger-favored-enemy" and entry.get("choice"):
                entry["conditionalBonuses"] = {
                    "attack": 2, "damage": 2,
                    "skills": ["skill.bluff", "skill.knowledge", "skill.perception", "skill.sense-motive", "skill.survival"],
                    "condition": entry["choice"],
                }
            elif feature_id == "npc-class-feature.ranger-favored-terrain" and entry.get("choice"):
                entry["conditionalBonuses"] = {
                    "initiative": 2,
                    "skills": ["skill.knowledge-geography", "skill.perception", "skill.stealth", "skill.survival"],
                    "condition": entry["choice"],
                }
            elif feature_id == "npc-class-feature.rogue-sneak-attack":
                effect = entry.get("effects", {})
                dice = effect.get("sneakAttackDiceByClassLevel", {}).get(str(class_level))
                if dice:
                    entry["sneakAttackDice"] = dice
            elif feature_id == "npc-class-feature.rogue-trapfinding":
                entry["conditionalBonuses"] = {
                    "skills": ["skill.perception", "skill.disable-device"],
                    "bonus": max(1, class_level // 2), "condition": "locate traps",
                }

        granted_feats: list[dict[str, Any]] = []
        granted_by: set[str] = set()
        for feature in features:
            feat_id = feature.get("effects", {}).get("grantsFeat") or feature.get("grantsFeat")
            if not feat_id or feat_id in granted_by:
                continue
            feat = self._record("feat", feat_id)
            refs = _dedupe_refs(refs, _refs(feat), feature.get("sourceRefs", []))
            if feat.get("catalogStatus") != "resolved":
                issues.append(self._gap(feat, "/selections/classFeatureChoices"))
                continue
            granted_by.add(feat_id)
            granted: dict[str, Any] = {
                "featId": feat["id"], "name": feat["name"], "grantedBy": feature["featureId"],
                "sourceRefs": _dedupe_refs(_refs(feat), feature.get("sourceRefs", [])),
            }
            if feat_id == "feat.rapid-shot":
                granted["prerequisitesWaived"] = True
            granted_feats.append(granted)
        return features, refs, issues, granted_feats

    def _ranger_spells(
        self,
        selections: dict[str, Any],
        class_record: dict[str, Any],
        row: dict[str, Any],
        class_level: int,
        scores: dict[str, int],
        modifiers: dict[str, int],
    ) -> tuple[Any, list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        loadout = selections.get("spellLoadout", {})
        if not row.get("spellsPerDay"):
            if isinstance(loadout, dict) and not any(loadout.values()):
                return [], _refs(class_record), [], []
            if loadout:
                return [], _refs(class_record), [self._issue(
                    "npc.spell-levels-invalid", "selected class levels grant no spell slots",
                    path="/selections/spellLoadout",
                )], []
            return [], _refs(class_record), [], []
        spellcasting = self._record("classFeature", "npc-class-feature.ranger-spellcasting")
        refs = _dedupe_refs(
            _refs(class_record), _refs(row), _refs(spellcasting),
            [self._source_ref("source.aon-getting-started", "Table: Ability Modifiers and Bonus Spells", [92, 115])],
        )
        issues: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        if not isinstance(loadout, dict):
            return {}, refs, [self._issue(
                "npc.spell-loadout-invalid", "Ranger spell loadout must be an object",
                path="/selections/spellLoadout", source_refs=_refs(spellcasting),
            )], warnings
        unexpected = set(loadout) - {"prepared"}
        if unexpected:
            issues.append(self._issue(
                "npc.spell-loadout-invalid", "Ranger spell loadout accepts only prepared spells",
                path="/selections/spellLoadout", details={"unexpectedFields": sorted(unexpected)}, source_refs=_refs(spellcasting),
            ))
        prepared = loadout.get("prepared", {})
        if not isinstance(prepared, dict):
            issues.append(self._issue(
                "npc.spell-loadout-invalid", "prepared Ranger spells must map spell levels to arrays of IDs",
                path="/selections/spellLoadout/prepared", source_refs=_refs(spellcasting),
            ))
            prepared = {}

        wisdom = modifiers["wisdom"]
        wisdom_score = scores["wisdom"]
        slots_by_level: dict[str, dict[str, int]] = {}
        accessible_levels: set[str] = set()
        for spell_level, base in row["spellsPerDay"].items():
            numeric_level = int(spell_level)
            wisdom_bonus = _bonus_spell_count(wisdom, numeric_level)
            total = base + wisdom_bonus
            slots_by_level[spell_level] = {"base": base, "wisdomBonus": wisdom_bonus, "total": total}
            required_wisdom = 10 + numeric_level
            if wisdom_score < required_wisdom:
                warnings.append(self._issue(
                    "npc.casting-ability-insufficient", "Wisdom is too low to prepare or cast this Ranger spell level",
                    severity="warning", path="/selections/spellLoadout/prepared",
                    details={"actual": wisdom_score, "required": required_wisdom, "spellLevel": numeric_level},
                    source_refs=_refs(spellcasting),
                ))
            elif total > 0:
                accessible_levels.add(spell_level)

        if set(prepared) != accessible_levels:
            issues.append(self._issue(
                "npc.spell-levels-invalid", "prepared Ranger spells must include exactly the accessible spell levels",
                path="/selections/spellLoadout/prepared",
                details={"expectedLevels": sorted(accessible_levels, key=int), "selectedLevels": sorted(prepared, key=int)},
                source_refs=_refs(row),
            ))
        resolved_prepared: dict[str, list[str]] = {}
        selected_ids: set[str] = set()
        for spell_level, selected in prepared.items():
            numeric_level = int(spell_level) if str(spell_level).isdigit() else -1
            expected_count = slots_by_level.get(spell_level, {}).get("total", 0) if spell_level in accessible_levels else 0
            if len(selected) != expected_count:
                issues.append(self._issue(
                    "npc.spell-count-invalid", "prepared Ranger spells must fill each accessible slot exactly",
                    path=f"/selections/spellLoadout/prepared/{spell_level}",
                    details={"expected": expected_count, "selected": len(selected)}, source_refs=_refs(row),
                ))
            resolved_prepared[spell_level] = []
            for index, spell_id in enumerate(selected):
                spell = self._record("spell", spell_id)
                refs = _dedupe_refs(refs, _refs(spell))
                path = f"/selections/spellLoadout/prepared/{spell_level}/{index}"
                if not spell.get("levelsByClass"):
                    issues.append(self._gap(spell, path))
                elif spell.get("levelsByClass", {}).get("ranger") != numeric_level:
                    issues.append(self._issue(
                        "npc.spell-level-invalid", "spell is not a Ranger spell of the prepared level",
                        path=path, source_refs=_refs(spell),
                    ))
                resolved_prepared[spell_level].append(spell["id"])

        caster_level = max(0, class_level - 3)
        accessible_dc = {
            spell_level: 10 + int(spell_level) + wisdom
            for spell_level in accessible_levels
        }
        result = {
            "className": class_record["name"], "castingMode": "prepared", "casterLevel": caster_level,
            "castingAbility": "wisdom", "castingAbilityModifier": wisdom,
            "slotsByLevel": slots_by_level, "prepared": resolved_prepared,
            "saveDcByLevel": accessible_dc,
        }
        return result, refs, issues, warnings

    def _progression_features(self, selections, race, progression, class_records, rows, modifiers, archetype):
        features, refs, issues, granted = [], [], [], []
        all_choices = selections.get("classFeatureChoices", {})
        consumed = set()
        for item, record, row in zip(progression, class_records, rows):
            choice_ids = {self._record("classFeature", feature["featureId"]).get("choiceId")
                          for feature in self._class_features(record, item["levels"])} - {None}
            consumed.update(choice_ids)
            local = {**selections, "classFeatureChoices": {key: value for key, value in all_choices.items() if key in choice_ids}}
            local_archetype = archetype if archetype and archetype.get("classId") == record["id"] else None
            if not local_archetype:
                local.pop("archetypeId", None)
            if record["id"] in {"npc-class.sorcerer", "npc-class.druid"}:
                entries, entry_refs, entry_issues = self._selected_class_features(
                    local, race, record, item["levels"], modifiers, local_archetype,
                )
                feat_grants = []
            else:
                entries, entry_refs, entry_issues, feat_grants = self._multiclass_class_features(
                    local, [item], [record], [row], modifiers,
                )
            for entry in entries:
                feature_record = self._record("classFeature", entry["featureId"])
                effects = feature_record.get("effects") or {}
                if feature_record.get("rulesText"):
                    entry["rulesText"] = feature_record["rulesText"]
                if effects.get("wildShape"):
                    entry["wildShape"] = copy.deepcopy(effects["wildShape"])
                if effects.get("knowledgeBonus"):
                    entry["knowledgeBonus"] = max(effects["knowledgeBonus"]["minimum"], item["levels"] // effects["knowledgeBonus"]["levelDivisor"])
                    entry["name"] += f" +{entry['knowledgeBonus']}"
                if effects.get("dailyRounds"):
                    rule = effects["dailyRounds"]
                    entry["roundsPerDay"] = rule["base"] + modifiers[rule["ability"]] + (item["levels"] - 1) * rule["perAdditionalLevel"]
                    entry["name"] += f" ({entry['roundsPerDay']} rounds/day)"
                for power in entry.get("powers", []):
                    if power.get("attackBonus") is not None:
                        power["attackBonus"] += sum(class_row["bab"] for class_row in rows) - row["bab"]
            features.extend(entries)
            refs = _dedupe_refs(refs, entry_refs)
            issues.extend(entry_issues)
            granted.extend(feat_grants)
        for key in sorted(set(all_choices) - consumed):
            issues.append(self._issue("npc.choice-invalid", "choice is not granted by the selected class levels",
                                      path=f"/selections/classFeatureChoices/{key}"))
        return features, refs, issues, granted

    def _progression_spells(self, selections, progression, class_records, rows, scores, modifiers, archetype):
        casters = [(item, record, row) for item, record, row in zip(progression, class_records, rows)
                   if row.get("spellsPerDay") or row.get("spellsKnown")]
        if not casters:
            issues = [self._issue("npc.spell-levels-invalid", "selected class levels grant no spell slots",
                                 path="/selections/spellLoadout")] if any(selections.get("spellLoadout", {}).values()) else []
            return [], [], issues, []
        if len(casters) > 1:
            return [], [], [self._issue(
                "npc.spell-loadout-ambiguous", "independent spellcasting classes require class-keyed loadouts, which are not implemented",
                path="/selections/spellLoadout", details={"classIds": [record["id"] for _, record, _ in casters]},
            )], []
        item, record, row = casters[0]
        if record["id"] == "npc-class.ranger":
            return self._ranger_spells(selections, record, row, item["levels"], scores, modifiers)
        result, refs, issues = self._spells(selections, record, row, item["levels"], scores, modifiers,
                                          archetype_id=archetype["id"] if archetype else None, archetype=archetype)
        return result, refs, issues, []

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
            if choice not in bloodline.get("options", {}):
                return features, _dedupe_refs(refs, _refs(bloodline)), [self._issue(
                    "npc.catalog-gap" if choice else "npc.selection-required", "select a bloodline with catalogued rules",
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
            fire_domain = self._selected_domain(selections)
            feature_refs = _dedupe_refs(refs, _refs(nature_bond), _refs(fire_domain))
            choice = choices.get("natureBond")
            if not fire_domain or fire_domain.get("catalogStatus") != "resolved":
                return features, feature_refs, [self._issue(
                    "npc.catalog-gap" if choice else "npc.selection-required", "select a Nature Bond with catalogued domain rules",
                    path="/selections/classFeatureChoices/natureBond", source_refs=_refs(nature_bond),
                )]
            for feature in features:
                if feature["featureId"] == nature_bond["id"]:
                    feature.update(choice=choice, name=f"Nature Bond ({fire_domain['name'].replace('Domain', 'domain')})")
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
            "npc.choice-invalid", "the selected class grants no such feature choice",
            path="/selections/classFeatureChoices",
        )] if choices else []
        return features, refs, issues

    def _archetype(
        self, selections: dict[str, Any], class_record: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        """Resolve an optional NPC archetype selection against its catalog record."""
        archetype_id = selections.get("archetypeId")
        if archetype_id is None:
            return None, []
        path = "/selections/archetypeId"
        if not isinstance(archetype_id, str) or not archetype_id:
            return None, [self._issue(
                "npc.selection-invalid", "archetypeId must be a non-empty string", path=path,
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
            return self._druid_spells(loadout, class_record, row, level, scores, modifiers, archetype_id=archetype_id, archetype=archetype,
                                      domain=self._selected_domain(selections))
        if class_record.get("castingMode") != "spontaneous" or not row.get("spellsKnown"):
            return [], _refs(class_record), [self._issue(
                "npc.casting-rules-unimplemented", "spellcasting rules for this class are not implemented",
                path="/selections/spellLoadout", details={"classId": class_record["id"]},
            )]

        class_key = class_record["id"].removeprefix("npc-class.")
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
                if not record.get("levelsByClass"):
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
            choice = selections.get("classFeatureChoices", {}).get("bloodline")
            option = bloodline.get("options", {}).get(choice, {})
            refs = _dedupe_refs(refs, _refs(bloodline))
            for granted_level, spell_id in option.get("bonusSpells", {}).items():
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

    def _selected_domain(self, selections):
        bond = self._record("classFeature", "npc-class-feature.druid-nature-bond")
        choice = selections.get("classFeatureChoices", {}).get("natureBond")
        return self._optional("classFeature", bond.get("options", {}).get(choice, {}).get("featureId"))

    def _druid_spells(
        self, loadout: Any, class_record: dict[str, Any], row: dict[str, Any], level: int,
        scores: dict[str, int], modifiers: dict[str, int], *,
        archetype_id: str | None = None, archetype: dict[str, Any] | None = None,
        domain: dict[str, Any] | None = None,
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
            fire_domain = domain or {}
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
                if not spell.get("levelsByClass"):
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
                if not spell.get("levelsByClass"):
                    issues.append(self._gap(spell, path))
                elif spell["id"] != expected_spell_id:
                    issues.append(self._issue(
                        "npc.domain-spell-invalid", "spell does not match the Fire-domain spell for this slot level",
                        path=path, details={"expectedSpellId": expected_spell_id}, source_refs=_refs(fire_domain),
                    ))
                resolved_domain[spell_level].append(spell["id"])

        conversion_ids = {key: spell_id for key, spell_id in (conversion_catalog.get("spellIdsBySlotLevel") or {}).items()
                          if key in base_slots and int(key) > 0}
        for spell_id in dict.fromkeys(spell_id for spell_ids in conversion_ids.values() for spell_id in spell_ids):
            spell = self._record("spell", spell_id)
            refs = _dedupe_refs(refs, _refs(spell))
            if not spell.get("levelsByClass"):
                issues.append(self._gap(spell, "/selections/spellLoadout"))
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

    def _feats(
        self, selections: dict[str, Any], race: dict[str, Any], level: int, scores: dict[str, int], *, bab: int,
        skills=(), features=(), spells=None, granted_feats=(),
    ) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
        slots = self._feat_slots(level, race)
        selected = selections["feats"]
        issues: list[dict[str, Any]] = []
        expected_slots = {slot["slotId"] for slot in slots}
        actual_slots = [item["slotId"] for item in selected]
        if set(actual_slots) != expected_slots or len(actual_slots) != len(set(actual_slots)):
            issues.append(self._issue("npc.feat-slots-invalid", "each required feat slot must be filled exactly once", path="/selections/feats", details={"expectedSlots": sorted(expected_slots)}, source_refs=_dedupe_refs(*[_refs(slot) for slot in slots])))
        slot_levels = {slot["slotId"]: slot.get("grantedAtLevel", 1) for slot in slots}
        feat_keys = set()
        results: list[dict[str, Any]] = []
        effects: dict[str, Any] = {"initiative": 0, "saves": {}}
        refs: list[dict[str, Any]] = []
        for index, item in enumerate(selected):
            record = self._record("feat", item["featId"])
            refs = _dedupe_refs(refs, _refs(record))
            if record.get("catalogStatus") != "resolved":
                issues.append(self._gap(record, f"/selections/feats/{index}/featId"))
                continue
            acquired = slot_levels.get(item["slotId"], level)
            remaining = acquired
            class_levels, acquired_features, acquired_bab, caster_level = {}, set(), 0, 0
            for entry in selections["classProgression"]:
                count = min(remaining, entry["levels"])
                remaining -= count
                if not count:
                    break
                cls = self._record("class", entry["classId"])
                class_levels[cls["id"]] = count
                class_row = cls["levels"][str(count)]
                acquired_bab += class_row["bab"]
                acquired_features.update(feature["featureId"] for feature in self._class_features(cls, count))
                class_caster_level = class_row.get("casterLevel")
                if class_caster_level is None:
                    class_caster_level = max(0, count - 3) if cls["id"] == "npc-class.ranger" else (count if class_row.get("spellsPerDay") else 0)
                caster_level = max(caster_level, class_caster_level)
            acquired_scores = scores.copy()
            for increase, ability in selections["abilityGeneration"].get("levelIncreases", selections.get("levelIncreases", {})).items():
                if int(increase) > acquired:
                    acquired_scores[ability] -= 1
            available_feats = {entry["featId"] for entry in selected
                               if entry is not item and slot_levels.get(entry["slotId"], level) <= acquired}
            available_feats.update(entry["featId"] for entry in granted_feats if entry.get("grantedBy") in acquired_features)
            # Class proficiency grants satisfy the equivalent feat prerequisite.
            proficiencies = self._proficiencies(
                [feature for feature in features if feature["featureId"] in acquired_features], {}, race)
            available_feats.update(f"feat.armor-proficiency-{category}" for category in proficiencies["armor"])
            if "shield" in proficiencies["shields"]:
                available_feats.add("feat.shield-proficiency")
            prerequisite = evaluate_prerequisite(
                record.get("prerequisites", {"all": []}), ability_scores=acquired_scores,
                bab=acquired_bab, character_level=acquired, feats=available_feats,
                class_levels=class_levels, skill_ranks={skill["skillId"]: min(acquired, skill["ranks"]) for skill in skills},
                class_features=acquired_features, caster_level=caster_level,
                race_id=race["id"], alignment=selections.get("details", {}).get("alignment"),
            )
            if prerequisite is not True:
                issues.append(self._issue("npc.feat-prerequisite", "feat prerequisites are not met", path=f"/selections/feats/{index}/featId", source_refs=_refs(record)))
            feat_effect = record.get("effects") or {}
            if record.get("supportStatus") == "selection-only":
                issues.append(self._issue("npc.feat-effect-unimplemented", "source and acquisition rules are catalogued, but this feat's calculation is not implemented",
                                          path=f"/selections/feats/{index}/featId", source_refs=_refs(record)))
            choice = record.get("choice", {})
            choice_field = choice.get("field")
            provided = set(item) & {"weaponId", "skillId", "school", "subtype", "spellIds"}
            allowed_fields = {choice_field} if choice_field else ({"weaponId"} if feat_effect.get("weaponProficiencyCategory") else set())
            if provided - allowed_fields or (choice_field and not item.get(choice_field)):
                issues.append(self._issue("npc.feat-choice-invalid", "supply exactly the feat's required choice", path=f"/selections/feats/{index}"))
            if choice.get("values") and item.get(choice_field) not in choice["values"]:
                issues.append(self._issue("npc.feat-choice-invalid", "the selected choice is not allowed", path=f"/selections/feats/{index}/{choice_field}"))
            if choice_field == "spellIds":
                known = {spell for values in selections.get("spellLoadout", {}).get("known", {}).values() for spell in values}
                chosen = item.get("spellIds", [])
                if len(chosen) != len(set(chosen)) or len(chosen) > max(0, _ability_modifier(acquired_scores["intelligence"])) or set(chosen) - known:
                    issues.append(self._issue("npc.feat-choice-invalid", "select distinct known spells up to the Intelligence modifier", path=f"/selections/feats/{index}/spellIds"))
            weapon = self._optional("item", item.get("weaponId"))
            weapon_effects = (weapon or {}).get("effects") or {}
            weapon_type = weapon_effects.get("weaponType")
            category = feat_effect.get("weaponProficiencyCategory")
            if category:
                if weapon and (weapon.get("catalogStatus") != "resolved" or (weapon.get("category") == "weapon" and not weapon_type)):
                    issues.append(self._gap(weapon, f"/selections/feats/{index}/weaponId"))
                    continue
                if not weapon or weapon.get("category") != "weapon" or weapon_effects.get("weaponCategory") != category:
                    issues.append(self._issue("npc.feat-weapon-invalid", "select a weapon of the proficiency feat's category", path=f"/selections/feats/{index}/weaponId"))
                else:
                    effects.setdefault("weaponProficiencies", []).append(weapon_type)
                    refs = _dedupe_refs(refs, _refs(weapon))
            elif choice_field == "weaponId":
                if not weapon or weapon.get("catalogStatus") != "resolved" or weapon.get("category") != "weapon":
                    issues.append(self._issue("npc.feat-weapon-invalid", "select a resolved weapon", path=f"/selections/feats/{index}/weaponId"))
                elif record.get("requiredWeaponProficiency") and not (weapon_type in proficiencies["weapons"] or weapon_effects.get("weaponCategory") in proficiencies["weapons"] or any(
                    entry.get("featId") == "feat.martial-weapon-proficiency" and
                    slot_levels.get(entry["slotId"], level) <= acquired and
                    (self._optional("item", entry.get("weaponId")) or {}).get("effects", {}).get("weaponType") == weapon_type for entry in selected)):
                    issues.append(self._issue("npc.feat-prerequisite", "the chosen weapon requires proficiency", path=f"/selections/feats/{index}/weaponId"))
            for prerequisite_id in {"feat.weapon-focus", "feat.spell-focus"}:
                if record["id"] == "feat.greater-" + prerequisite_id.removeprefix("feat."):
                    candidates = [entry for entry in selected if entry["featId"] == prerequisite_id
                                  and slot_levels.get(entry["slotId"], level) <= acquired]
                    matches = [((self._optional("item", entry.get("weaponId")) or {}).get("effects", {}).get("weaponType") == weapon_type)
                               if choice_field == "weaponId" else entry.get(choice_field) == item.get(choice_field)
                               for entry in candidates]
                    if not any(matches):
                        issues.append(self._issue("npc.feat-prerequisite", "prerequisite feat must have the same target", path=f"/selections/feats/{index}"))
            key = (record["id"], weapon_type if category or choice_field == "weaponId" else _canonical_json(item.get(choice_field)))
            if key in feat_keys and not record.get("repeatable"):
                issues.append(self._issue("npc.feat-duplicate", "the same feat and choice cannot be selected twice", path=f"/selections/feats/{index}"))
            feat_keys.add(key)
            effects["initiative"] += feat_effect.get("initiative", 0)
            for save in ("fortitude", "reflex", "will"):
                effects["saves"][save] = effects["saves"].get(save, 0) + feat_effect.get(save, 0)
            for field in ("dodgeAC", "shieldAC", "hpPerLevelMinimum"):
                effects[field] = effects.get(field, 0) + feat_effect.get(field, 0)
            for field in ("armorProficiencies", "shieldProficiencies", "conditionalModifiers"):
                effects.setdefault(field, []).extend(copy.deepcopy(feat_effect.get(field, [])))
            if feat_effect.get("skillFocus") and item.get("skillId"):
                effects.setdefault("skillFocus", []).append(item["skillId"])
            for field in ("weaponAttackBonus", "doubleThreatRange", "schoolDCBonus"):
                if feat_effect.get(field):
                    target = weapon_type if field != "schoolDCBonus" else item.get("school")
                    effects.setdefault(field, {})[target] = effects.get(field, {}).get(target, 0) + feat_effect[field]
            label = weapon["name"] if weapon else item.get(choice_field)
            if choice_field == "skillId" and label:
                label = self._record("skill", label)["name"]
            if isinstance(label, list):
                label = ", ".join(self._record("spell", value)["name"] for value in label)
            results.append({**copy.deepcopy(item),
                            "name": record["name"] + (f" ({label})" if label else ""),
                            **{field: copy.deepcopy(record[field]) for field in ("treatments", "supportStatus", "supportLimitations", "rulesText") if field in record},
                            **({"skillBonus": 6 if next((skill["ranks"] for skill in skills if skill["skillId"] == item.get("skillId")), 0) >= 10 else 3}
                               if feat_effect.get("skillFocus") else {}),
                            "sourceRefs": _refs(record)})
        return results, effects, refs, issues

    def _apply_item_lenses(self, selected: dict[str, Any], record: dict[str, Any], effects: dict[str, Any]) -> dict[str, Any]:
        """Apply reusable masterwork, enhancement, and weapon-quality lenses."""
        masterwork = selected.get("masterwork", False)
        enhancement = selected.get("enhancementBonus", 0)
        category = record.get("category")
        source_refs: list[dict[str, Any]] = []
        price_cp = 0
        issue = None
        message = ""
        name = record["name"]
        lenses: dict[str, Any] = {}
        raw_properties = list(selected.get("properties", [])) + list(selected.get("propertyIds", []))
        properties = list(dict.fromkeys(
            next((value.lower().removeprefix(prefix) for prefix in ("weapon-quality.", "weapon-property.", "magic-weapon-property.") if value.lower().startswith(prefix)), value.lower())
            for value in raw_properties
        ))
        known_properties = {"flaming", "keen"}
        unknown = [value for value in properties if value not in known_properties]
        if unknown:
            issue = "npc.item-property-invalid"
            message = f"unsupported weapon quality: {unknown[0]}"
        if properties and category != "weapon":
            issue = "npc.item-lens-invalid"
            message = "weapon qualities apply only to weapons"
        if "keen" in properties and (record.get("effects", {}).get("rangeIncrement") is not None or record.get("effects", {}).get("damageType") not in {"P", "S"}):
            issue = "npc.item-lens-invalid"
            message = "keen applies only to piercing or slashing melee weapons"
        if properties and not enhancement:
            enhancement = 1
        if masterwork or enhancement:
            if category not in {"weapon", "armor", "shield"}:
                issue = "npc.item-lens-invalid"
                message = "masterwork and enhancement lenses apply only to weapons, armor, and shields"
            elif category == "weapon":
                if enhancement:
                    masterwork = True
                    effects["attackBonus"] = effects.get("attackBonus", 0) + enhancement
                    effects["damageBonus"] = effects.get("damageBonus", 0) + enhancement
                    if properties:
                        effects["weaponQualities"] = properties
                    labels = " ".join(properties)
                    name = f"+{enhancement} {labels + ' ' if labels else ''}{record['name']}"
                    equivalent = enhancement + sum(1 for value in properties if value in known_properties)
                    price_cp += 30_000 + equivalent * equivalent * 200_000
                    source_refs.extend((
                        self._source_ref("source.aon-magic-weapons", "Magic Weapons", [4, 4]),
                        self._source_ref("source.aon-magic-weapons", "Table 15-8: Weapons", [21, 21]),
                    ))
                elif masterwork:
                    effects["attackBonus"] = effects.get("attackBonus", 0) + 1
                    name = f"mwk {record['name'].lower()}"
                    price_cp += 30_000
                if masterwork:
                    source_refs.append(self._source_ref("source.aon-equipment", "Masterwork Weapons", [294, 295]))
                if "flaming" in properties:
                    effects["additionalDamage"] = [{"expression": "1d6", "damageType": "fire", "multipliedOnCritical": False}]
                    source_refs.append(self._source_ref("source.aon-magic-weapon-flaming", "Flaming", [1, 7]))
                if "keen" in properties:
                    source_refs.append(self._source_ref("source.aon-magic-weapon-keen", "Keen", [1, 7]))
            else:
                if enhancement:
                    masterwork = True
                    bonus_key = "armorBonus" if category == "armor" else "shieldBonus"
                    effects[bonus_key] = effects.get(bonus_key, 0) + enhancement
                    effects["armorCheckPenalty"] = min(0, effects.get("armorCheckPenalty", 0) + 1)
                    name = f"+{enhancement} {record['name']}"
                    price_cp += 15_000 + enhancement * enhancement * 200_000
                    source_refs.extend((
                        self._source_ref("source.aon-magic-armor", "Magic Armor", [3, 3]),
                        self._source_ref("source.aon-magic-armor", "Table 15-3: Armor and Shields", [17, 17]),
                    ))
                elif masterwork:
                    effects["armorCheckPenalty"] = min(0, effects.get("armorCheckPenalty", 0) + 1)
                    name = f"mwk {record['name'].lower()}"
                    price_cp += 15_000
                if masterwork:
                    source_refs.append(self._source_ref("source.aon-equipment", "Masterwork Armor", [381, 383]))
            if masterwork:
                lenses["masterwork"] = True
            if enhancement:
                lenses["enhancementBonus"] = enhancement
        if properties and not unknown and category == "weapon":
            lenses["properties"] = properties
        if "charges" in selected:
            issue = "npc.item-customization-unimplemented"
            message = "item charges are not implemented"
        return {"name": name, "lenses": lenses, "priceCp": price_cp, "sourceRefs": source_refs, "issue": issue, "message": message}

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
            if isinstance(selected, str):
                items.append({"name": selected, "mechanical": False, "category": "gear", "quantity": 1,
                              "equipped": False, "effects": {}, "priceCp": None, "sourceRefs": []})
                continue
            record = self._record("item", selected["itemId"])
            refs = _dedupe_refs(refs, _refs(record))
            if record.get("catalogStatus") != "resolved":
                issues.append(self._gap(record, f"/selections/gear/{index}/itemId"))
                continue
            quantity = selected.get("quantity", 1)
            effects = copy.deepcopy(record.get("effects", {}))
            lens_result = self._apply_item_lenses(selected, record, effects)
            if lens_result["issue"]:
                issues.append(self._issue(
                    lens_result["issue"], lens_result["message"], path=f"/selections/gear/{index}",
                    source_refs=lens_result["sourceRefs"],
                ))
            refs = _dedupe_refs(refs, lens_result["sourceRefs"])
            cost = (record["priceCp"] + lens_result["priceCp"]) * quantity
            spent += cost
            size_key = size_id.removeprefix("size.") if size_id else None
            damage_by_size = effects.get("damageDieBySize", {})
            if size_key in damage_by_size:
                effects["damageDie"] = damage_by_size[size_key]
            weight_by_size = record.get("weightLbBySize", {})
            weight = weight_by_size.get(size_key, record.get("weightLb", 0))
            items.append({
                "itemId": record["id"], "name": lens_result["name"], "category": record["category"], "mechanical": True,
                "npcGearCategory": record.get("npcGearCategory"),
                "quantity": quantity, "equipped": selected.get("equipped", True), "priceCp": cost,
                "weightLb": weight * quantity, "effects": effects,
                **({"lenses": lens_result["lenses"]} if lens_result["lenses"] else {}),
                "sourceRefs": _dedupe_refs(_refs(record), lens_result["sourceRefs"]),
            })
        if spent != budget["budgetCp"]:
            warnings.append(self._issue(
                "npc.gear-budget-approximate", "priced mechanical gear does not spend the full NPC gear budget; descriptive inventory is unpriced",
                severity="warning", path="/selections/gear", details={"budgetCp": budget["budgetCp"], "spentCp": spent}, source_refs=_refs(budget),
            ))
        result_budget = {
            "gearBudgetId": budget["gearBudgetId"], "level": level, "effectiveLevel": budget["effectiveLevel"],
            "npcCategory": budget["npcCategory"], "budgetCp": budget["budgetCp"],
            "categories": copy.deepcopy(budget["categories"]), "spentCp": spent,
            "remainingCp": None if any(isinstance(item, str) for item in selections["gear"]) else budget["budgetCp"] - spent,
            "descriptiveEquipmentUnpriced": any(isinstance(item, str) for item in selections["gear"]),
        }
        return {"budget": result_budget, "items": items}, refs, issues, warnings

    def _proficiencies(self, features, feats, race):
        result = {"weapons": set(race.get("weaponProficiencies", [])) | set(feats.get("weaponProficiencies", [])),
                  "armor": set(feats.get("armorProficiencies", [])), "shields": set(feats.get("shieldProficiencies", []))}
        for feature in features:
            effects = self._record("classFeature", feature["featureId"]).get("effects", {})
            result["weapons"].update(effects.get("weaponProficiencies", []))
            result["armor"].update(effects.get("armorProficiencies", []))
            shields = effects.get("shieldProficiencies", "none")
            if shields != "none":
                result["shields"].add("shield")
            if shields == "all":
                result["shields"].add("tower-shield")
        return result

    @staticmethod
    def _attacks(
        items: list[dict[str, Any]], bab: int, modifiers: dict[str, int], size_modifiers: dict[str, int],
        size_id: str | None, *, weapon_proficiencies: set[str], armor_penalty: int = 0,
        finesse: bool = False, rapid_shot: bool = False, feat_effects=None,
        active_attack_bonus: int = 0, active_damage_bonus: int = 0,
    ) -> list[dict[str, Any]]:
        feat_effects = feat_effects or {}
        attacks = []
        ranged_bases: list[dict[str, Any]] = []
        for item in items:
            if item["category"] != "weapon":
                continue
            effects = item["effects"]
            damage_die = effects.get("damageDie")
            if damage_die is None and size_id:
                damage_die = effects.get("damageDieBySize", {}).get(size_id.removeprefix("size."))
            if damage_die is None:
                continue
            # Ranged weapons use Dexterity for attack rolls. Weapon Finesse is
            # 'may use Dex instead of Str' for eligible melee weapons.
            ranged = effects.get("rangeIncrement") is not None
            finesse_eligible = finesse and not ranged and (effects.get("lightWeapon") or effects.get("finesseWeapon"))
            hit_ability = modifiers["dexterity"] if ranged else modifiers["strength"]
            if finesse_eligible:
                # Finesse is optional; include shield ACP before choosing Dex.
                shield_acp = sum(shield["effects"].get("armorCheckPenalty", 0)
                                 for shield in items if shield["effects"].get("shieldCategory"))
                hit_ability = max(hit_ability, modifiers["dexterity"] + shield_acp)
            proficient = effects.get("weaponType") in weapon_proficiencies or effects.get("weaponCategory") in weapon_proficiencies
            attack_bonus = bab + hit_ability + size_modifiers.get("attack", 0) + effects.get("attackBonus", 0) + armor_penalty + (0 if proficient else -4)
            attack_bonus += feat_effects.get("weaponAttackBonus", {}).get(effects.get("weaponType"), 0) + active_attack_bonus
            bonuses = [attack_bonus - step for step in range(0, min(16, max(1, bab)), 5)]
            if effects.get("reloadAction") in {"move", "full-round"}:
                bonuses = bonuses[:1]
            damage_bonus = 0 if effects.get("noStrengthToDamage") else modifiers["strength"]
            if effects.get("strengthDamage") == "penalty-only":
                damage_bonus = min(0, modifiers["strength"])
            elif not ranged and effects.get("twoHanded") and damage_bonus > 0:
                damage_bonus = damage_bonus * 3 // 2
            damage_bonus += effects.get("damageBonus", 0) + active_damage_bonus
            attack = {
                "name": item["name"], "itemId": item["itemId"], "attackBonuses": bonuses,
                "attackBonusExpression": "/".join(_bonus(value) for value in bonuses),
                "attackType": "ranged" if ranged else "melee", "proficient": proficient,
                **({"nonlethal": True} if effects.get("nonlethal") else {}),
                **({"reach": effects["reach"]} if effects.get("reach") else {}),
                "damageExpression": f"{damage_die}{_bonus(damage_bonus) if damage_bonus else ''}",
                "damageType": effects.get("damageType"),
                **({"additionalDamage": copy.deepcopy(effects["additionalDamage"])} if effects.get("additionalDamage") else {}),
            }
            if effects.get("critRange", 20) < 20:
                attack["critical"] = f"{effects['critRange']}-20/x{effects.get('critMultiplier', 2)}"
                attack["critRange"] = effects["critRange"]
            elif effects.get("critMultiplier", 2) != 2:
                attack["critical"] = f"x{effects['critMultiplier']}"
            if "critical" in attack:
                attack["critMultiplier"] = effects.get("critMultiplier", 2)
            if "keen" in effects.get("weaponQualities", []) or feat_effects.get("doubleThreatRange", {}).get(effects.get("weaponType")):
                threat = 21 - 2 * (21 - effects.get("critRange", 20))
                attack.update(critRange=threat, critical=f"{threat}-20/x{effects.get('critMultiplier', 2)}")
            if effects.get("rangeIncrement") is not None:
                attack["range"] = f"{effects['rangeIncrement']} ft."
                attack["rangeIncrement"] = effects["rangeIncrement"]
                if effects.get("reloadAction") not in {"move", "full-round"}:
                    ranged_bases.append({"item": item, "attack": attack})
            attacks.append(attack)

        if rapid_shot:
            for base in ranged_bases:
                attack = copy.deepcopy(base["attack"])
                penalty_bonuses = [bonus - 2 for bonus in attack["attackBonuses"]]
                attack.update({
                    "name": f"{base['item']['name']} (Rapid Shot)",
                    "attackBonuses": [penalty_bonuses[0], *penalty_bonuses],
                    "attackBonusExpression": "/".join(_bonus(value) for value in [penalty_bonuses[0], *penalty_bonuses]),
                    "rapidShot": True,
                    "fullAttack": True,
                })
                attacks.append(attack)
        return attacks

    # ------------------------------------------------------------------
    # Catalog and response helpers
    # ------------------------------------------------------------------
    def _multiclass_choice_requirements(self, draft: dict[str, Any]) -> dict[str, Any]:
        selections = draft["selections"]
        progression = selections["classProgression"]
        total_level = sum(item["levels"] for item in progression)
        previews = []
        records = []
        for item in progression:
            local = copy.deepcopy(draft)
            local["selections"]["classProgression"] = [item]
            previews.append(self.choice_requirements(local))
            records.append(self._optional("class", item["classId"]) or {})
        result = copy.deepcopy(previews[0])
        requirements = {entry["path"]: entry for entry in result["requirements"]
                        if not entry["path"].startswith(("/selections/classProgression/", "/selections/classFeatureChoices/", "/selections/spellLoadout/"))}
        for index, preview in enumerate(previews):
            for entry in preview["requirements"]:
                path = entry["path"]
                if path.startswith("/selections/classProgression/"):
                    entry = {**entry, "path": path.replace("/classProgression/0/", f"/classProgression/{index}/")}
                if path.startswith(("/selections/classProgression/", "/selections/classFeatureChoices/", "/selections/spellLoadout/")):
                    requirements[entry["path"]] = entry
        if len(progression) >= 3:
            requirements["/selections/skillGeneration/method"]["values"] = ["precise"]
            requirements.pop("/selections/skillGeneration/skills", None)
            requirements["/selections/skillGeneration/ranks"] = self._requirement("/selections/skillGeneration/ranks", "Skill ranks", "integer-map")
        result["requirements"] = sorted(requirements.values(), key=lambda entry: entry["path"])
        race = self._optional("race", selections.get("raceId"))
        slots = self._feat_slots(total_level, race)
        grants = self._granted_feat_requirements(progression, records, selections.get("classFeatureChoices", {}))
        result["automaticSelections"].update(
            classFeatures=self._class_features_for_progression(progression, records), featGrants=slots, grantedFeats=grants,
        )
        budgets = result["selectionBudgets"]
        counts = [preview["selectionBudgets"]["skills"]["count"] for preview in previews]
        groups = []
        if all(count is not None for count in counts):
            covered = 0
            for index in sorted(range(len(counts)), key=lambda index: counts[index]):
                count = counts[index]
                positions = list(range(covered, max(covered, count)))
                if positions:
                    groups.append({"classId": progression[index]["classId"], "classLevel": progression[index]["levels"],
                                   "positions": positions, "count": len(positions),
                                   "ranks": sum(item["levels"] for item, budget in zip(progression, counts) if positions[0] < budget)})
                covered = max(covered, count)
        budgets["skills"].update(count=max(counts) if all(count is not None for count in counts) else None, groups=groups,
                                 rankBudget=sum(count * item["levels"] for count, item in zip(counts, progression)) if all(count is not None for count in counts) else None,
                                 maxRanks=total_level)
        budgets["feats"].update(slots=slots, granted=grants)
        budgets["gear"] = {**(self._gear_budget(selections, total_level) or {}),
                           "spentCp": self._preview_gear_cost(selections.get("gear", []))}
        casting = [preview["selectionBudgets"]["spells"] for preview in previews if preview["selectionBudgets"]["spells"]["required"]]
        budgets["spells"] = casting[0] if len(casting) == 1 else {"required": bool(casting), "levels": {}, "classes": casting}
        return result

    def _class_features_for_progression(
        self, progression: list[dict[str, Any]], class_records: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item, class_record in zip(progression, class_records):
            for feature in self._class_features(class_record, item["levels"]):
                if feature["featureId"] not in seen:
                    seen.add(feature["featureId"])
                    result.append(feature)
        return result

    def _granted_feat_requirements(
        self, progression: list[dict[str, Any]], class_records: list[dict[str, Any]], choices: Any = None,
    ) -> list[dict[str, Any]]:
        granted: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item, class_record in zip(progression, class_records):
            for current_level in range(1, item["levels"] + 1):
                row = class_record.get("levels", {}).get(str(current_level), {})
                for feature_id in row.get("featureGrants") or []:
                    feature = self._optional("classFeature", feature_id)
                    if not feature:
                        continue
                    feat_id = feature.get("effects", {}).get("grantsFeat")
                    if feature.get("choiceId") and isinstance(choices, dict):
                        option = feature.get("options", {}).get(choices.get(feature["choiceId"]), {})
                        feat_id = option.get("grantsFeat", feat_id)
                    if feat_id and feat_id not in seen:
                        feat = self._optional("feat", feat_id)
                        if feat:
                            seen.add(feat_id)
                            entry = {"featId": feat["id"], "name": feat["name"], "grantedBy": feature_id}
                            if feat_id == "feat.rapid-shot":
                                entry["prerequisitesWaived"] = True
                            granted.append(entry)
        return granted

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
            "allowedFeatIds": [record["id"] for record in self.catalog.entries("feat").values() if record.get("catalogStatus") == "resolved" and record.get("supportStatus") != "selection-only"],
            "sourceRef": copy.deepcopy(rule.get("sourceRef")),
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
        npc_category = "heroic" if any((self._optional("class", item.get("classId")) or {}).get("category") == "pc"
                                       for item in progression if isinstance(item, dict)) else "basic"
        rows = [row for row in record.get("rows", []) if row.get("npcCategory") == npc_category]
        for row in rows:
            if row.get("level") == level:
                return {"gearBudgetId": record["id"], **copy.deepcopy(row)}
        # No source-backed row for this level: report an explicit catalog gap.
        # Never approximate from a lower row; _gear turns the gap status into a
        # catalog-gap issue instead of crashing on budget["gearBudgetId"].
        return {**record, "catalogStatus": "gap"}

    def _preview_ability(
        self, selections: dict[str, Any], race: dict[str, Any] | None, ability_name: str,
    ) -> int | None:
        generation = selections.get("abilityGeneration", {})
        if not isinstance(generation, dict):
            return None
        array = self._optional("abilityArray", generation.get("arrayId", "npc-ability-array.basic"))
        if not array or array.get("catalogStatus") != "resolved":
            return None
        method = generation.get("method")
        if method in {"melee-preset", "ranged-preset", "divine-preset", "arcane-preset"}:
            score = array.get("presets", {}).get(method.removesuffix("-preset"), {}).get(ability_name)
        else:
            score = generation.get("assignments", generation.get("scores", {})).get(ability_name)
        if not _is_int(score):
            return None
        score += (race or {}).get("abilityAdjustments", {}).get(ability_name, 0)
        for slot in (race or {}).get("choiceSlots", []):
            choice = selections.get("racialChoices", {}).get(slot["choiceId"])
            score += slot.get("options", {}).get(choice, {}).get("effects", {}).get("abilityAdjustments", {}).get(ability_name, 0)
        increases = generation.get("levelIncreases", selections.get("levelIncreases", {}))
        score += sum(value == ability_name for value in increases.values()) * self._record("derivedRule", "npc-rule.ability-increase")["amount"]
        return score

    def _preview_gear_cost(self, gear: list[Any]) -> int:
        total = 0
        for item in gear:
            if not isinstance(item, dict):
                continue
            record = self._optional("item", item.get("itemId"))
            if record and _is_int(record.get("priceCp")):
                lens = self._apply_item_lenses(item, record, copy.deepcopy(record.get("effects", {})))
                total += (record["priceCp"] + lens["priceCp"]) * item.get("quantity", 1)
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
