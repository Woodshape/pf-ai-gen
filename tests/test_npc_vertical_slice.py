import copy
import json
import unittest
from pathlib import Path

from monster_builder import Catalog, CatalogRegistry, Engine
from monster_builder.catalog import CatalogError
from monster_builder.creation_systems.npc import NpcCreation
from monster_builder.npc_catalog import NpcCatalog


ROOT = Path(__file__).parents[1]
FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "human-warrior-3.json").read_text())


def request(request_id, operation, payload):
    return {
        "protocolVersion": "1",
        "requestId": request_id,
        "operation": operation,
        "payload": payload,
    }


class ResolvedNpcCatalog:
    """Small source-shaped catalog used to exercise the evaluator math.

    The checked-in catalog intentionally records the unavailable Core tables as
    gaps.  This test catalog only replaces those rows with explicit values so
    the adapter's table-driven path can be tested without changing npc.json.
    """

    SECTIONS = {
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

    def __init__(self):
        base = NpcCatalog.load()
        self.data = copy.deepcopy(base.data)
        self.version = "npc-test-catalog"
        ref = copy.deepcopy(self.data["sources"]["source.npc-adr"])
        ref.update({"section": "vertical test source", "txtLines": []})

        array = self.data["abilityArrays"]["npc-ability-array.basic"]
        array.update({
            "catalogStatus": "resolved",
            "scores": [13, 12, 11, 10, 9, 8],
            "meleeOrder": ["strength", "constitution", "dexterity", "wisdom", "intelligence", "charisma"],
        })
        race = self.data["races"]["npc-race.human"]
        race.update({
            "catalogStatus": "resolved",
            "abilityAdjustments": {ability: 0 for ability in ("strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma")},
            "sizeId": "size.medium",
            "speed": {"land": 30},
            "senses": [],
            "traits": [],
            "languages": ["Common"],
            "skillSelectionsBonus": 1,
            "sizeModifiers": {"ac": 0, "cmb": 0, "cmd": 0},
        })
        warrior = self.data["classes"]["npc-class.warrior"]
        warrior.update({
            "catalogStatus": "resolved",
            "hitDie": "d10",
            "classSkills": ["skill.climb", "skill.intimidate"],
            "skillSelections": 2,
            "classSkillBonus": 3,
        })
        for level in range(1, 6):
            warrior["levels"][str(level)].update({
                "catalogStatus": "resolved",
                "bab": level,
                "fortitude": level,
                "reflex": level // 2,
                "will": level // 3,
                "hitDie": "d10",
                "skillSelections": 2,
                "featureGrants": [],
                "choiceSlots": [],
            })
        for skill in self.data["skills"].values():
            skill.update({"catalogStatus": "resolved", "keyAbility": "strength", "trainedOnly": False, "armorCheckPenalty": True})
        for feat in self.data["feats"].values():
            feat.update({"catalogStatus": "resolved", "prerequisites": None, "effects": None})
        self.data["feats"]["feat.power-attack"]["prerequisites"] = {
            "all": [{"abilityAtLeast": {"strength": 13}}, {"babAtLeast": 1}]
        }
        self.data["feats"]["feat.improved-initiative"]["effects"] = {"initiative": 4}
        for item in self.data["items"].values():
            item.update({"catalogStatus": "resolved", "priceCp": 100, "weightLb": 1, "effects": {}})
        self.data["items"]["item.longsword"]["effects"] = {"damageDie": "1d8", "damageType": "S"}
        self.data["items"]["item.chain-shirt"]["effects"] = {"armorBonus": 4, "maxDex": 4, "armorCheckPenalty": -2}
        self.data["items"]["item.light-steel-shield"]["effects"] = {"shieldBonus": 1}
        self.data["gearBudgets"]["npc-gear.medium.normal"].update({
            "catalogStatus": "resolved",
            "budgetCp": 1000,
            "effectiveLevel": 3,
            "categories": {"weapons": 300, "protection": 300, "magic": 0, "limitedUse": 0, "gear": 400},
        })
        self.data["derivedRules"].update({
            "npc-rule.ability-increase": {
                "id": "npc-rule.ability-increase", "name": "Ability score increases", "kind": "ability-increase",
                "levels": [4, 8, 12, 16, 20], "amount": 1, "catalogStatus": "policy", "sourceRef": ref,
            },
            "npc-rule.average-hp": {
                "id": "npc-rule.average-hp", "name": "Average hit points", "kind": "average-hp",
                "rounding": "floor", "constitutionPerLevel": True, "catalogStatus": "policy", "sourceRef": ref,
            },
            "npc-rule.general-feat-slots": {
                "id": "npc-rule.general-feat-slots", "name": "General feat slots", "kind": "general-feat-slots",
                "levels": [1, 3, 5, 7, 9], "catalogStatus": "policy", "sourceRef": ref,
            },
        })

    def entries(self, kind):
        return self.data[self.SECTIONS[kind]]

    def resolve_id(self, kind, value):
        if not isinstance(value, str) or not value:
            raise CatalogError(f"{kind} id must be a non-empty string")
        records = self.entries(kind)
        if value in records:
            return records[value].get("id", value), records[value]
        for key, record in records.items():
            if record.get("id") == value or value in record.get("aliases", []):
                return record.get("id", key), record
        prefixes = {
            "abilityArray": "npc-ability-array.", "gearBudget": "npc-gear.", "race": "npc-race.",
            "class": "npc-class.", "skill": "skill.", "feat": "feat.", "item": "item.",
            "spell": "spell.", "derivedRule": "npc-rule.",
        }
        candidate = prefixes.get(kind, "") + value
        if candidate in records:
            return candidate, records[candidate]
        raise CatalogError(f"unknown NPC {kind} id: {value}")


def valid_test_draft():
    draft = copy.deepcopy(FIXTURE)
    draft["selections"]["abilityGeneration"] = {
        "method": "assigned-array",
        "scores": {
            "strength": 13,
            "constitution": 12,
            "dexterity": 11,
            "wisdom": 10,
            "intelligence": 9,
            "charisma": 8,
        },
    }
    draft["selections"]["skillGeneration"]["skills"] = ["skill.climb", "skill.intimidate"]
    draft["selections"]["feats"] = [
        {"slotId": "general-1", "featId": "feat.improved-initiative"},
        {"slotId": "general-3", "featId": "feat.power-attack"},
    ]
    draft["selections"]["gear"] = [
        {"itemId": "item.longsword"},
        {"itemId": "item.chain-shirt"},
        {"itemId": "item.light-steel-shield"},
    ]
    return draft


class NpcVerticalSliceTests(unittest.TestCase):
    def test_public_fixture_has_no_derived_selections_and_reports_source_gaps(self):
        computed = {
            "level", "totalLevel", "npcCategory", "abilityScores", "abilityModifiers", "hp", "bab",
            "defenses", "initiative", "attacks", "cmb", "cmd", "skills", "canonical", "effective",
            "derivationTrace", "evaluation",
        }
        self.assertFalse(computed.intersection(FIXTURE["selections"]))
        response = Engine().execute(request("human-warrior-3", "draft.create", {"draft": FIXTURE}))
        self.assertTrue(response["ok"], response)
        evaluation = response["result"]["evaluation"]
        self.assertEqual(evaluation["status"], "invalid")
        self.assertTrue(any(issue["code"] == "npc.catalog-gap" for issue in evaluation["issues"]))
        self.assertTrue(all(issue.get("sourceRefs") for issue in evaluation["issues"] if issue["kind"] == "catalog-data"))

    def test_choice_requirements_expose_nested_npc_slots_and_budgets(self):
        response = Engine().execute(request("human-warrior-3-requirements", "draft.choiceRequirements", {"draft": FIXTURE}))
        self.assertTrue(response["ok"], response)
        result = response["result"]
        paths = {item["path"] for item in result["requirements"]}
        self.assertTrue({
            "/selections/raceId",
            "/selections/classProgression/0/classId",
            "/selections/classProgression/0/levels",
            "/selections/abilityGeneration/method",
            "/selections/skillGeneration/method",
            "/selections/skillGeneration/skills",
            "/selections/gearProfile/experienceProgression",
            "/selections/gearProfile/fantasyLevel",
            "/selections/gear",
        } <= paths)
        self.assertEqual(result["creationSystem"], "npc")
        self.assertIn("feats", result["selectionBudgets"])
        self.assertIn("gear", result["selectionBudgets"])
        self.assertIsNone(result["selectionBudgets"]["gear"]["budgetCp"])

    def test_resolved_human_warrior_three_derives_all_requested_combat_fields(self):
        catalog = ResolvedNpcCatalog()
        registry = CatalogRegistry(Catalog.load())
        registry.register("npc", catalog)
        engine = Engine(catalogs=registry, creation_systems={"npc": NpcCreation(catalog)})
        response = engine.execute(request("resolved-human-warrior-3", "draft.create", {"draft": valid_test_draft()}))
        self.assertTrue(response["ok"], response)
        evaluation = response["result"]["evaluation"]
        self.assertEqual(evaluation["status"], "valid")
        canonical = evaluation["canonical"]
        self.assertEqual(canonical["level"], 3)
        self.assertEqual(canonical["npcCategory"], "basic")
        self.assertEqual(canonical["abilityScores"], {
            "strength": 13, "dexterity": 11, "constitution": 12,
            "intelligence": 9, "wisdom": 10, "charisma": 8,
        })
        self.assertEqual(canonical["abilityModifiers"], {
            "strength": 1, "dexterity": 0, "constitution": 1,
            "intelligence": -1, "wisdom": 0, "charisma": -1,
        })
        self.assertEqual(canonical["bab"], 3)
        self.assertEqual(canonical["hp"], 19)
        self.assertEqual(canonical["defenses"], {
            "ac": 15, "touchAC": 10, "flatFootedAC": 15, "hp": 19,
            "fortitude": 4, "reflex": 1, "will": 1, "cmd": 14,
        })
        self.assertEqual(canonical["initiative"], 4)
        self.assertEqual(canonical["cmb"], 4)
        self.assertEqual(canonical["attacks"][0]["attackBonus"], [4])
        self.assertEqual(canonical["attacks"][0]["damageExpression"], "1d8+1")
        self.assertEqual(canonical["skills"], {"climb": 5, "intimidate": 5})
        self.assertEqual([feat["slotId"] for feat in canonical["feats"]], ["general-1", "general-3"])
        self.assertEqual(canonical["feats"][0]["featId"], "feat.improved-initiative")
        self.assertEqual(canonical["gearBudget"]["spentCp"], 300)
        self.assertEqual(canonical["gearBudget"]["deltaCp"], -700)
        self.assertTrue(all(entry["sourceRefs"] for entry in evaluation["derivationTrace"] if entry["path"].startswith("/canonical/")))

    def test_nested_racial_skill_bonus_reaches_canonical_trace(self):
        catalog = ResolvedNpcCatalog()
        race = catalog.data["races"]["npc-race.human"]
        race["effects"] = {"effects": {"skillBonuses": {"skill.climb": 2}}}
        registry = CatalogRegistry(Catalog.load())
        registry.register("npc", catalog)
        engine = Engine(catalogs=registry, creation_systems={"npc": NpcCreation(catalog)})
        response = engine.execute(request("nested-racial-skill", "draft.create", {"draft": valid_test_draft()}))
        self.assertTrue(response["ok"], response)
        evaluation = response["result"]["evaluation"]
        self.assertEqual(evaluation["status"], "valid")
        self.assertEqual(evaluation["canonical"]["skills"]["climb"], 7)
        skills_trace = next(item for item in evaluation["derivationTrace"] if item["path"] == "/canonical/skills")
        climb = next(item for item in skills_trace["inputs"] if item["source"] == "skill.climb")
        racial = next(item for item in climb["components"] if item["source"] == "racial skill bonus")
        self.assertEqual(racial["value"], 2)

    def test_derived_values_are_rejected_as_draft_selections(self):
        draft = copy.deepcopy(FIXTURE)
        draft["selections"]["hp"] = 19
        response = Engine().execute(request("computed-selection", "draft.create", {"draft": draft}))
        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "draft.computed-selection")


if __name__ == "__main__":
    unittest.main()
