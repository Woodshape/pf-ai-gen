"""Race/class composition must not depend on which example NPC was implemented."""
import copy
import json
import unittest
from pathlib import Path

from monster_builder import Engine
from monster_builder.catalog import CatalogError
from monster_builder.npc_catalog import validate_npc_data

ROOT = Path(__file__).parents[1]


def evaluate(draft):
    response = Engine().execute({"protocolVersion": "1", "requestId": "composition",
                                 "operation": "draft.create", "payload": {"draft": draft}})
    assert response["ok"], response
    return response["result"]["evaluation"]


def draft_for(catalog, race_id, class_id, level):
    race, cls = catalog["races"][race_id], catalog["classes"][class_id]
    row = cls["levels"][str(level)]
    scores = {"strength": 8, "dexterity": 14, "constitution": 12,
              "intelligence": 13, "wisdom": 10, "charisma": 15}
    if class_id == "npc-class.druid":
        scores.update(wisdom=12, constitution=10)
    if class_id == "npc-class.warrior":
        scores.update(intelligence=8, strength=13)
    racial_choices = {slot["choiceId"]: "wisdom" for slot in race.get("choiceSlots", [])}
    final = {key: value + race.get("abilityAdjustments", {}).get(key, 0) for key, value in scores.items()}
    if racial_choices:
        final["wisdom"] += 2
    increases = {str(value): "wisdom" for value in range(4, level + 1, 4)}
    final["wisdom"] += len(increases)
    choices = {}
    for current in range(1, level + 1):
        for feature_id in cls["levels"][str(current)]["featureGrants"]:
            feature = catalog["classFeatures"][feature_id]
            if feature.get("choiceId"):
                choices[feature["choiceId"]] = feature["allowedValues"][0]
    skills = [key for key in cls["classSkills"] if catalog["skills"][key]["catalogStatus"] == "resolved"]
    count = max(1, cls["skillSelections"] + (final["intelligence"] - 10) // 2) + race.get("skillSelectionsBonus", 0)
    slots = [f"general-{value}" for value in range(1, level + 1, 2)] + [slot["slotId"] for slot in race.get("featSlots", [])]
    feat_ids = ["feat.improved-initiative", "feat.iron-will", "feat.lightning-reflexes", "feat.weapon-finesse"]
    loadout = {}
    class_key = class_id.removeprefix("npc-class.")
    if row.get("spellsKnown"):
        loadout["known"] = {key: [spell_id for spell_id, spell in catalog["spells"].items()
                                  if spell["catalogStatus"] == "resolved" and spell.get("levelsByClass", {}).get(class_key) == int(key)][:number]
                            for key, number in row["spellsKnown"].items()}
    elif row.get("spellsPerDay"):
        modifier = (final["wisdom"] - 10) // 2
        loadout["prepared"] = {}
        for key, base in row["spellsPerDay"].items():
            number = int(key)
            bonus = 1 + (modifier - number) // 4 if number and modifier >= number else 0
            if class_key == "ranger" and (final["wisdom"] < 10 + number or base + bonus == 0):
                continue
            spell_id = next(spell_id for spell_id, spell in catalog["spells"].items()
                            if spell["catalogStatus"] == "resolved" and spell.get("levelsByClass", {}).get(class_key) == number)
            loadout["prepared"][key] = [spell_id] * (base + bonus)
        if class_key == "druid":
            loadout["domainPrepared"] = {key: [spell_id] for key, spell_id in catalog["classFeatures"]["npc-class-feature.fire-domain"]["domainSpells"].items()
                                         if key in row["spellsPerDay"] and int(key) > 0}
    return {"creationSystem": "npc", "concept": {"name": "Composition check"}, "selections": {
        "statblockUse": "full", "raceId": race_id, "racialChoices": racial_choices,
        "classProgression": [{"classId": class_id, "levels": level}],
        "abilityGeneration": {"method": "assigned-array", "arrayId": "npc-ability-array.heroic", "assignments": scores},
        "levelIncreases": increases, "skillGeneration": {"method": "simplified", "skills": skills[:count]},
        "feats": [{"slotId": slot, "featId": feat_id} for slot, feat_id in zip(slots, feat_ids)],
        "classFeatureChoices": choices, "spellLoadout": loadout,
        "gearProfile": {"experienceProgression": "medium", "fantasyLevel": "normal"}, "gear": [],
    }}


class NpcCompositionTests(unittest.TestCase):
    def test_hp_policy_rounds_each_die_by_npc_category(self):
        for fixture, expected in [("human-warrior-3.json", 18), ("halfling-bard-2.json", 15),
                                  ("goblin-sorcerer-6.json", 32), ("kiramor-npc.json", 44)]:
            with self.subTest(fixture=fixture):
                draft = json.loads((ROOT / "tests/fixtures" / fixture).read_text())
                result = evaluate(draft)
                self.assertEqual(result["status"], "valid", result["issues"])
                self.assertEqual(result["canonical"]["hp"], expected)
                hp_trace = next(entry for entry in result["derivationTrace"] if entry["path"] == "/canonical/hp")
                self.assertTrue(any(ref["provenanceStatus"] == "product-policy" for ref in hp_trace["sourceRefs"]))

    def test_warchanter_reports_specific_missing_records_not_a_combination_gate(self):
        draft = json.loads((ROOT / "docs/goblin-warchanter-draft.json").read_text())
        result = evaluate(draft)
        self.assertEqual(result["status"], "invalid")
        self.assertEqual({issue["code"] for issue in result["issues"]}, {"npc.catalog-gap"})
        self.assertTrue(all(not issue["path"].startswith("/selections/classProgression") for issue in result["issues"]))
        self.assertIn("item.shortbow", {issue["details"]["recordId"] for issue in result["issues"]})

    def test_goblin_can_use_existing_bard_rules(self):
        draft = json.loads((ROOT / "tests/fixtures/halfling-bard-2.json").read_text())
        draft["selections"]["raceId"] = "npc-race.goblin"
        result = evaluate(draft)
        self.assertEqual(result["status"], "valid", result["issues"])
        self.assertEqual(result["canonical"]["level"], 2)

    def test_every_resolved_race_and_class_level_composes(self):
        catalog = json.loads((ROOT / "catalog/npc.json").read_text())
        for race in catalog["races"].values():
            if race["catalogStatus"] != "resolved":
                continue
            for cls in catalog["classes"].values():
                if cls["catalogStatus"] != "resolved":
                    continue
                for level, row in cls["levels"].items():
                    if row["catalogStatus"] != "resolved":
                        continue
                    with self.subTest(race=race["id"], cls=cls["id"], level=level):
                        draft = draft_for(catalog, race["id"], cls["id"], int(level))
                        result = evaluate(draft)
                        self.assertEqual(result["status"], "valid", result["issues"])
                        self.assertEqual(result["canonical"]["bab"], row["bab"])

    def test_multiclass_uses_each_class_level_in_either_order(self):
        catalog = json.loads((ROOT / "catalog/npc.json").read_text())
        for reverse, hp in [(False, 14), (True, 16)]:
            draft = draft_for(catalog, "npc-race.goblin", "npc-class.sorcerer", 1)
            selections = draft["selections"]
            selections["classProgression"].append({"classId": "npc-class.warrior", "levels": 1})
            if reverse:
                selections["classProgression"].reverse()
                selections["skillGeneration"]["skills"] = ["skill.climb", "skill.intimidate", "skill.swim"]
            result = evaluate(draft)
            self.assertEqual(result["status"], "valid", result["issues"])
            canonical = result["canonical"]
            self.assertEqual((canonical["totalLevel"], canonical["bab"], canonical["hp"]), (2, 1, hp))
            self.assertEqual(canonical["spells"]["casterLevel"], 1)
            self.assertEqual(canonical["npcCategory"], "heroic")
            self.assertEqual(canonical["gearBudget"]["npcCategory"], "heroic")

    def test_feat_prerequisite_uses_bab_not_character_level(self):
        catalog = json.loads((ROOT / "catalog/npc.json").read_text())
        draft = draft_for(catalog, "npc-race.goblin", "npc-class.bard", 1)
        draft["selections"]["feats"][0]["featId"] = "feat.deadly-aim"
        result = evaluate(draft)
        self.assertIn("npc.feat-prerequisite", {issue["code"] for issue in result["issues"]})
        draft = draft_for(catalog, "npc-race.goblin", "npc-class.bard", 2)
        draft["selections"]["feats"][0]["featId"] = "feat.deadly-aim"
        result = evaluate(draft)
        self.assertEqual(result["status"], "valid", result["issues"])

    def test_general_rapid_shot_is_not_restricted_to_a_ranger_grant(self):
        catalog = json.loads((ROOT / "catalog/npc.json").read_text())
        draft = draft_for(catalog, "npc-race.goblin", "npc-class.bard", 3)
        draft["selections"]["feats"] = [
            {"slotId": "general-1", "featId": "feat.point-blank-shot"},
            {"slotId": "general-3", "featId": "feat.rapid-shot"},
        ]
        result = evaluate(draft)
        self.assertEqual(result["status"], "valid", result["issues"])

    def test_catalog_rejects_holes_below_a_resolved_level(self):
        catalog = json.loads((ROOT / "catalog/npc.json").read_text())
        catalog["classes"]["npc-class.sorcerer"]["levels"]["1"]["catalogStatus"] = "gap"
        with self.assertRaisesRegex(CatalogError, "every lower level"):
            validate_npc_data(catalog, ROOT, check_version=False)

    def test_archetype_does_not_restrict_race(self):
        draft = json.loads((ROOT / "tests/fixtures/goblin-druid-3-elemental-ally.json").read_text())
        draft["selections"]["raceId"] = "npc-race.halfling"
        result = evaluate(draft)
        self.assertEqual(result["status"], "valid", result["issues"])
        self.assertEqual(result["canonical"]["linkedCreature"]["level"], 3)

    def test_resolved_class_progressions_have_no_missing_lower_levels(self):
        catalog = json.loads((ROOT / "catalog/npc.json").read_text())
        for record in catalog["classes"].values():
            resolved = [int(level) for level, row in record["levels"].items()
                        if row["catalogStatus"] == "resolved"]
            if resolved:
                with self.subTest(classId=record["id"]):
                    self.assertEqual(resolved and sorted(resolved), list(range(1, max(resolved) + 1)))


if __name__ == "__main__":
    unittest.main()
