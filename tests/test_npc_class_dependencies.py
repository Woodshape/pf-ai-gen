"""Class level/feature data for NPC feats: warrior 6-20, gear rows to 20, channel/wild-shape dependencies.

Covers the class-expansion and gear-budget work recorded in docs/npc-feat-support-audit.md
("Dependencies outside the literal list"): every resolved class level composes, higher-level
gear rows are source-backed instead of approximated, and cleric stays an explicit gap.
"""
import json
import unittest
from pathlib import Path

from monster_builder import Engine

ROOT = Path(__file__).parents[1]
CATALOG = json.loads((ROOT / "catalog/npc.json").read_text())


def evaluate(draft):
    response = Engine().execute({"protocolVersion": "1", "requestId": "class-dependencies",
                                 "operation": "draft.create", "payload": {"draft": draft}})
    assert response["ok"], response
    return response["result"]["evaluation"]


def draft_for(class_progression, *, feats=None, feature_choices=None):
    """Build a single-race draft on the heroic ability array with explicit feats."""
    progression = class_progression if isinstance(class_progression, list) else [class_progression]
    first = CATALOG["classes"][progression[0]["classId"]]
    race = CATALOG["races"]["npc-race.human"]
    total_level = sum(item["levels"] for item in progression)
    ability_scores = {ability: value for ability, value
                      in zip(CATALOG["abilityArrays"]["npc-ability-array.heroic"]["abilityOrder"],
                             CATALOG["abilityArrays"]["npc-ability-array.heroic"]["scores"])}
    ability_scores.update({"strength": 8, "dexterity": 14, "constitution": 12,
                           "intelligence": 13, "wisdom": 10, "charisma": 15})
    final = {key: value + race.get("abilityAdjustments", {}).get(key, 0) for key, value in ability_scores.items()}
    racial_choices = {slot["choiceId"]: "wisdom" for slot in race.get("choiceSlots", [])}
    for slot in race.get("choiceSlots", []):
        choice = racial_choices.get(slot["choiceId"])
        if choice:
            final[choice] += slot["options"][choice]["effects"]["abilityAdjustments"][choice]
    increases = {str(value): "wisdom" for value in range(4, total_level + 1, 4)}
    final["wisdom"] += len(increases)
    skills = [key for key in (first["classSkills"] or []) if CATALOG["skills"][key]["catalogStatus"] == "resolved"]
    count = max(1, (first["skillSelections"] or 0) + (final["intelligence"] - 10) // 2) + race.get("skillSelectionsBonus", 0)
    slots = [f"general-{value}" for value in range(1, total_level + 1, 2)]
    slots += [slot["slotId"] for slot in race.get("featSlots", [])]
    defaults = [
        "feat.improved-initiative", "feat.iron-will", "feat.lightning-reflexes", "feat.weapon-finesse",
        "feat.toughness", "feat.great-fortitude", "feat.combat-reflexes", "feat.combat-casting",
        "feat.endurance", "feat.eschew-materials", "feat.empower-spell",
    ]
    custom = list(feats or [])
    selected_feats = (custom + [feat for feat in defaults if feat not in custom])[:len(slots)]
    loadout = {}
    row = first["levels"][str(progression[0]["levels"])]
    class_key = progression[0]["classId"].removeprefix("npc-class.")
    modifier = (final["wisdom"] - 10) // 2
    if row.get("spellsKnown"):
        loadout["known"] = {
            key: [spell["id"] for spell in CATALOG["spells"].values()
                  if spell["catalogStatus"] == "resolved" and spell.get("levelsByClass", {}).get(class_key) == int(key)][:number]
            for key, number in row["spellsKnown"].items()
        }
    elif row.get("spellsPerDay"):
        loadout["prepared"] = {}
        for spell_level, base in row["spellsPerDay"].items():
            number = int(spell_level)
            bonus = 1 + (modifier - number) // 4 if number and modifier >= number else 0
            spell_id = next(spell["id"] for spell in CATALOG["spells"].values()
                            if spell["catalogStatus"] == "resolved"
                            and spell.get("levelsByClass", {}).get(class_key) == number)
            loadout["prepared"][spell_level] = [spell_id] * (base + bonus)
        loadout["domainPrepared"] = {
            key: [spell_id] for key, spell_id in
            CATALOG["classFeatures"]["npc-class-feature.fire-domain"]["domainSpells"].items()
            if key in row["spellsPerDay"] and int(key) > 0
        }
    for slot in race.get("choiceSlots", []):
        choice = racial_choices.get(slot["choiceId"])
        if choice:
            final[choice] += slot["options"][choice]["effects"]["abilityAdjustments"][choice]
    for item, class_record in zip(progression, [CATALOG["classes"][item["classId"]] for item in progression]):
        for current in range(1, item["levels"] + 1):
            for feature_id in class_record["levels"][str(current)]["featureGrants"] or []:
                feature = CATALOG["classFeatures"][feature_id]
                if feature.get("choiceId") and (feature_choices or {}).get(feature["choiceId"]) is None:
                    feature_choices = {**(feature_choices or {}), feature["choiceId"]: feature["allowedValues"][0]}
    return {"creationSystem": "npc", "concept": {"name": "Class dependency check"}, "selections": {
        "statblockUse": "full", "raceId": "npc-race.human", "racialChoices": racial_choices,
        "classProgression": [{"classId": item["classId"], "levels": item["levels"]} for item in progression],
        "abilityGeneration": {"method": "assigned-array", "arrayId": "npc-ability-array.heroic", "assignments": ability_scores},
        "levelIncreases": increases, "skillGeneration": {"method": "simplified", "skills": skills[:count]},
        "feats": [{"slotId": slot, "featId": feat_id} for slot, feat_id in zip(slots, selected_feats)],
        "classFeatureChoices": feature_choices or {}, "spellLoadout": loadout,
        "gearProfile": {"experienceProgression": "medium", "fantasyLevel": "normal"}, "gear": [],
    }}


class WarriorHighLevelTests(unittest.TestCase):
    def test_warrior_rows_match_the_archived_table(self):
        source_lines = (ROOT / "sources/npc/aonprd/npc-classes.txt").read_text().splitlines()
        warrior = CATALOG["classes"]["npc-class.warrior"]
        for level in (6, 10, 16, 20):
            row = warrior["levels"][str(level)]
            parts = source_lines[147 + level].split("\t")
            self.assertEqual(row["catalogStatus"], "resolved")
            self.assertEqual(row["bab"], int(parts[1].split("/")[0].lstrip("+")), level)
            self.assertEqual((row["fortitude"], row["reflex"], row["will"]),
                             (int(parts[2].lstrip("+")), int(parts[3].lstrip("+")), int(parts[4].lstrip("+"))), level)
            self.assertEqual(row["sourceRef"]["txtLines"], [148 + level, 148 + level])

    def test_warrior_sixteen_composes_with_bab_sixteen(self):
        result = evaluate(draft_for({"classId": "npc-class.warrior", "levels": 16}))
        self.assertEqual(result["status"], "valid", result["issues"])
        self.assertEqual(result["canonical"]["bab"], 16)

    def test_bab_sixteen_feat_prerequisite_becomes_evaluable(self):
        from monster_builder.npc.prerequisites import evaluate_prerequisite
        self.assertTrue(evaluate_prerequisite({"babAtLeast": 16}, bab=16))
        self.assertIs(evaluate_prerequisite({"babAtLeast": 16}, bab=15), False)

    def test_warrior_twenty_composes_with_ten_feat_slots(self):
        result = evaluate(draft_for({"classId": "npc-class.warrior", "levels": 20}))
        self.assertEqual(result["status"], "valid", result["issues"])
        self.assertEqual(result["canonical"]["bab"], 20)
        self.assertEqual(len(result["canonical"]["feats"]), 11)


class GearBudgetSourceRowsTests(unittest.TestCase):
    def test_medium_normal_carries_every_table_14_9_row(self):
        source_lines = (ROOT / "sources/npc/aonprd/creating-npcs.txt").read_text().splitlines()
        rows = CATALOG["gearBudgets"]["npc-gear.medium.normal"]["rows"]
        self.assertEqual(len(rows), 40)
        for category, level in (("basic", 7), ("basic", 20), ("heroic", 7), ("heroic", 20)):
            row = next(row for row in rows if row["npcCategory"] == category and row["level"] == level)
            line = row["sourceRef"]["txtLines"][0]
            columns = source_lines[line - 1].split("\t")
            index = 0 if category == "basic" else 1
            self.assertEqual(columns[index], str(level), (category, level))
            self.assertEqual(row["budgetCp"], int(columns[2].replace(",", "").replace(" gp", "")) * 100)
            self.assertEqual(row["effectiveLevel"], level)

    def test_level_seven_multiclass_uses_the_exact_heroic_row(self):
        draft = draft_for([{"classId": "npc-class.sorcerer", "levels": 6}, {"classId": "npc-class.warrior", "levels": 1}])
        result = evaluate(draft)
        self.assertEqual(result["status"], "valid", result["issues"])
        gear = result["canonical"]["gearBudget"]
        self.assertEqual((gear["gearBudgetId"], gear["level"], gear["effectiveLevel"]), ("npc-gear.medium.normal", 7, 7))
        self.assertEqual(gear["budgetCp"], 600000)  # Table 14-9 heroic level 7: 6,000 gp
        self.assertEqual(gear["npcCategory"], "heroic")

    def test_missing_row_is_an_explicit_gap_never_a_lower_row_approximation(self):
        from monster_builder.npc_catalog import NpcCatalog
        from monster_builder.creation_systems.npc import NpcCreation
        system = NpcCreation(NpcCatalog(json.loads((ROOT / "catalog/npc.json").read_text()), ROOT))
        gap_profile = {"gearProfile": {"experienceProgression": "fast", "fantasyLevel": "normal"},
                       "classProgression": [{"classId": "npc-class.warrior", "levels": 5}]}
        budget = system._gear_budget(gap_profile, 5)
        self.assertEqual(budget["catalogStatus"], "gap")
        resolved = {"gearProfile": {"experienceProgression": "medium", "fantasyLevel": "normal"},
                    "classProgression": [{"classId": "npc-class.warrior", "levels": 5}]}
        self.assertEqual(system._gear_budget(resolved, 20)["budgetCp"], 12300000)
        self.assertEqual(system._gear_budget(resolved, 0)["catalogStatus"], "gap")


class ClericStaysExplicitGapTests(unittest.TestCase):
    def test_cleric_class_and_levels_are_not_resolved(self):
        cleric = CATALOG["classes"]["npc-class.cleric"]
        self.assertEqual(cleric["catalogStatus"], "gap")
        self.assertTrue(all(row["catalogStatus"] == "gap" for row in cleric["levels"].values()))

    def test_cleric_level_one_keeps_sourced_partial_metadata(self):
        row = CATALOG["classes"]["npc-class.cleric"]["levels"]["1"]
        self.assertEqual((row["bab"], row["fortitude"], row["reflex"], row["will"]), (0, 2, 0, 2))
        self.assertEqual(row["spellsPerDay"], {"0": 3, "1": 1})
        self.assertIsNone(row["featureGrants"])
        self.assertIsNone(row["choiceSlots"])
        statuses = {ref["provenanceStatus"] for ref in row["sourceRef"]}
        self.assertEqual(statuses, {"resolved", "catalog-gap"})

    def test_cleric_draft_is_rejected_not_silently_spell_less(self):
        draft = draft_for({"classId": "npc-class.cleric", "levels": 1})
        result = evaluate(draft)
        self.assertEqual(result["status"], "invalid")
        self.assertIn("npc.catalog-gap", [issue["code"] for issue in result["issues"]])


class ClassFeatureDependencyTests(unittest.TestCase):
    def test_channel_energy_record_carries_the_channel_mechanics(self):
        feature = CATALOG["classFeatures"]["npc-class-feature.cleric-channel-energy"]
        self.assertEqual(feature["catalogStatus"], "resolved")
        self.assertEqual(feature["sourceRef"][0]["sourceId"], "source.aon-cleric")
        self.assertEqual(feature["sourceRef"][0]["txtLines"], [41, 43])
        effects = feature["effects"]
        self.assertEqual((effects["channelUsesBase"], effects["channelUsesAbility"]), (3, "charisma"))
        self.assertEqual((effects["channelSaveDCBase"], effects["channelSaveDCPlusHalfClassLevel"],
                          effects["channelSaveDCAbility"]), (10, True, "charisma"))
        self.assertEqual((effects["channelDamageDie"], effects["channelDamageDieStepPerTwoLevels"],
                          effects["channelRadiusFeet"], effects["channelActionCost"]), ("1d6", 1, 30, "standard"))

    def test_wild_shape_record_exposes_level_four_metadata_and_rules_text(self):
        feature = CATALOG["classFeatures"]["npc-class-feature.druid-wild-shape"]
        self.assertEqual(feature["catalogStatus"], "resolved")
        self.assertEqual(feature["effects"]["wildShape"], {"usesPerDay": 1, "hoursPerUse": 4})
        self.assertIn("Small or Medium animal", feature["rulesText"])
        self.assertEqual(feature["sourceRef"][0]["txtLines"], [58, 61])

    def test_resist_natures_lure_uses_the_conditional_modifier_shape(self):
        feature = CATALOG["classFeatures"]["npc-class-feature.druid-resist-natures-lure"]
        modifiers = feature["effects"]["conditionalModifiers"]
        self.assertEqual(modifiers, [{"condition": unittest_case_condition(), "stat": "savingThrows", "bonus": 4}])

    def test_druid_four_composes_and_grants_the_feat_dependencies(self):
        draft = draft_for({"classId": "npc-class.druid", "levels": 4})
        result = evaluate(draft)
        self.assertEqual(result["status"], "valid", result["issues"])
        self.assertEqual(result["canonical"]["bab"], 3)
        granted = {feature["featureId"] for feature in result["canonical"]["classFeatures"]}
        self.assertTrue({"npc-class-feature.druid-wild-shape", "npc-class-feature.druid-resist-natures-lure"} <= granted)

    def test_wild_shape_grant_satisfies_the_natural_spell_expression(self):
        from monster_builder.npc.prerequisites import evaluate_prerequisite
        expression = CATALOG["feats"]["feat.natural-spell"]["prerequisites"]
        self.assertTrue(evaluate_prerequisite(expression, class_features={"npc-class-feature.druid-wild-shape"},
                                              ability_scores={"wisdom": 13}))
        self.assertIs(evaluate_prerequisite(expression, class_features=set(), ability_scores={"wisdom": 13}), False)

    def test_natural_spell_is_correctly_rejected_at_its_druid_four_acquisition_level(self):
        # A druid 4 only has general-1/general-3 slots; at the level-3 acquisition
        # point Wis is 12 and wild shape is not yet granted, so the typed
        # prerequisite must reject the feat instead of silently accepting it.
        draft = draft_for({"classId": "npc-class.druid", "levels": 4},
                          feats=["feat.improved-initiative", "feat.natural-spell"])
        result = evaluate(draft)
        self.assertEqual(result["status"], "invalid")
        self.assertIn("npc.feat-prerequisite", [issue["code"] for issue in result["issues"]])

    def test_spell_mastery_is_correctly_rejected_without_wizard_levels(self):
        draft = draft_for({"classId": "npc-class.warrior", "levels": 16},
                          feats=["feat.improved-initiative", "feat.spell-mastery"])
        result = evaluate(draft)
        self.assertEqual(result["status"], "invalid")
        self.assertTrue(any("prerequisite" in issue["message"].casefold() or issue["code"] == "npc.prerequisite-unmet"
                            for issue in result["issues"]), result["issues"])


def unittest_case_condition():
    return ("saving throws against the spell-like and supernatural abilities of fey, "
            "and spells or effects that utilize or target plants")


if __name__ == "__main__":
    unittest.main()