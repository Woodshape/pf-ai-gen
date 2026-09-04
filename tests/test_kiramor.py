import copy
import json
import tempfile
import unittest
from pathlib import Path

from monster_builder import Engine


ROOT = Path(__file__).parents[1]
NPC_FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "kiramor-npc.json").read_text(encoding="utf-8"))
PRINTED_FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "kiramor-printed.json").read_text(encoding="utf-8"))


def request(request_id, operation, payload):
    return {
        "protocolVersion": "1",
        "requestId": request_id,
        "operation": operation,
        "payload": payload,
    }


class KiramorTests(unittest.TestCase):
    def create(self, engine, draft=None, request_id="kiramor-create"):
        response = engine.execute(request(request_id, "draft.create", {"draft": copy.deepcopy(draft or NPC_FIXTURE)}))
        self.assertTrue(response["ok"], response)
        return response["result"]

    def test_rules_derived_and_printed_oracles_remain_separate(self):
        result = self.create(Engine())["evaluation"]
        self.assertEqual(result["status"], "valid", result["issues"])
        canonical = result["canonical"]
        self.assertEqual(canonical["abilityScores"], {
            "strength": 13, "dexterity": 18, "constitution": 12,
            "intelligence": 14, "wisdom": 10, "charisma": 8,
        })
        self.assertEqual(canonical["hp"], 40)
        self.assertEqual(canonical["bab"], 5)
        self.assertEqual(
            {key: canonical["defenses"][key] for key in ("fortitude", "reflex", "will")},
            {"fortitude": 5, "reflex": 11, "will": 1},
        )
        self.assertEqual(canonical["hitDiceExpression"], "4d10+2d8+6")
        self.assertEqual(canonical["cmb"], 6)
        self.assertEqual(canonical["cmd"], 20)
        self.assertEqual(canonical["spells"]["casterLevel"], 1)
        self.assertEqual(canonical["spells"]["prepared"], {})

        self.assertEqual(PRINTED_FIXTURE["oracle"], "printed")
        self.assertEqual(
            {key: PRINTED_FIXTURE["abilities"][key] for key in
             ("strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma")},
            {"strength": 13, "dexterity": 18, "constitution": 12,
             "intelligence": 14, "wisdom": 10, "charisma": 8},
        )
        self.assertEqual(PRINTED_FIXTURE["hitPoints"]["value"], 39)
        self.assertEqual(PRINTED_FIXTURE["hitPoints"]["hitDiceExpression"], "4d10+2d8+6")
        self.assertEqual(
            {key: PRINTED_FIXTURE["saves"][key] for key in ("fortitude", "reflex", "will")},
            {"fortitude": 6, "reflex": 12, "will": 2},
        )
        self.assertEqual(PRINTED_FIXTURE["attacks"]["rapier"]["attackBonus"], 10)
        self.assertEqual(PRINTED_FIXTURE["attacks"]["longbow"]["attackBonus"], 10)
        self.assertEqual(PRINTED_FIXTURE["attacks"]["rapidShot"]["attackBonuses"], [8, 8])
        self.assertEqual(PRINTED_FIXTURE["skills"]["values"]["Acrobatics"], 13)

        printed_fields = (
            "name", "identity", "initiative", "senses", "armorClass", "hitPoints",
            "saves", "defensiveAbilities", "speed", "specialAttacks", "abilities",
            "combatManeuvers", "feats", "skills", "languages", "specialQualities", "gear",
        )
        printed_refs = [PRINTED_FIXTURE[field]["sourceRef"] for field in printed_fields]
        printed_refs.extend(attack["sourceRef"] for attack in PRINTED_FIXTURE["attacks"].values())
        self.assertTrue(all(ref["sourceId"] == "source.aon-creating-npcs" for ref in printed_refs))
        self.assertTrue(all(len(ref["txtLines"]) == 2 for ref in printed_refs))

        deltas = {entry["field"]: entry for entry in PRINTED_FIXTURE["classifiedDeltas"]}
        self.assertEqual(set(deltas), {
            "saves.fortitude", "saves.reflex", "saves.will", "hitPoints",
            "skillSelections", "languages", "huntersBond", "initiative.forest",
        })
        self.assertEqual(
            {key: deltas[f"saves.{key}"]["printedMinusRules"] for key in ("fortitude", "reflex", "will")},
            {"fortitude": 1, "reflex": 1, "will": 1},
        )
        self.assertEqual(deltas["hitPoints"]["printedMinusRules"], -1)
        self.assertEqual(deltas["skillSelections"]["printed"]["listedInsteadOfIntimidate"], "Acrobatics +13")
        self.assertEqual(deltas["languages"]["classification"], "unmodeled source-consistent bonus-language selections")
        self.assertEqual(deltas["huntersBond"]["printed"], "nature bond (wolf)")
        self.assertEqual(deltas["initiative.forest"]["printedMinusRules"], 2)
        for delta in deltas.values():
            self.assertTrue(delta["sourceRefs"], delta["field"])
            for ref in delta["sourceRefs"]:
                self.assertTrue(ref["sourceId"].startswith("source."), ref)
                self.assertEqual(ref["provenanceStatus"], "resolved", ref)
                self.assertEqual(len(ref["txtLines"]), 2, ref)
        self.assertNotEqual(canonical["hp"], PRINTED_FIXTURE["hitPoints"]["value"])
        self.assertTrue(all(len(ref["txtLines"]) == 2 for entry in result["derivationTrace"] for ref in entry["sourceRefs"]))

    def test_canonical_skills_features_feats_and_attacks_are_source_derived(self):
        evaluation = self.create(Engine(), request_id="kiramor-canonical-details")["evaluation"]
        canonical = evaluation["canonical"]
        self.assertEqual(canonical["classProgression"], [
            {"classId": "npc-class.ranger", "className": "Ranger", "levels": 4},
            {"classId": "npc-class.rogue", "className": "Rogue", "levels": 2},
        ])
        self.assertEqual(
            [(skill["skillId"], skill["ranks"], skill["classId"], skill["total"]) for skill in canonical["skills"]],
            [
                ("skill.climb", 6, "npc-class.ranger", 10),
                ("skill.heal", 6, "npc-class.ranger", 9),
                ("skill.intimidate", 6, "npc-class.ranger", 8),
                ("skill.knowledge-geography", 6, "npc-class.ranger", 11),
                ("skill.knowledge-nature", 6, "npc-class.ranger", 11),
                ("skill.perception", 6, "npc-class.ranger", 11),
                ("skill.stealth", 6, "npc-class.ranger", 13),
                ("skill.survival", 6, "npc-class.ranger", 9),
                ("skill.escape-artist", 2, "npc-class.rogue", 9),
                ("skill.swim", 2, "npc-class.rogue", 6),
            ],
        )

        feats = {feat["featId"]: feat for feat in canonical["feats"]}
        self.assertEqual(set(feats), {
            "feat.point-blank-shot", "feat.deadly-aim", "feat.weapon-finesse",
            "feat.rapid-shot", "feat.endurance",
        })
        self.assertEqual(feats["feat.rapid-shot"]["grantedBy"], "npc-class-feature.ranger-combat-styles")
        self.assertTrue(feats["feat.rapid-shot"]["prerequisitesWaived"])
        self.assertEqual(feats["feat.endurance"]["grantedBy"], "npc-class-feature.ranger-endurance")

        features = {feature["featureId"]: feature for feature in canonical["classFeatures"]}
        self.assertEqual(features["npc-class-feature.ranger-favored-enemy"]["choice"], "humanoid-orc")
        self.assertEqual(features["npc-class-feature.ranger-combat-styles"]["choice"], "archery")
        self.assertEqual(features["npc-class-feature.ranger-favored-terrain"]["choice"], "forest")
        self.assertEqual(features["npc-class-feature.ranger-hunters-bond"]["choice"], "companion-bond")
        self.assertEqual(features["npc-class-feature.rogue-talents"]["choice"], "bleeding-attack")
        self.assertEqual(features["npc-class-feature.rogue-sneak-attack"]["sneakAttackDice"], "1d6")

        attacks = {(attack["itemId"], bool(attack.get("rapidShot"))): attack for attack in canonical["attacks"]}
        self.assertEqual(attacks[("item.rapier-masterwork", False)]["attackBonuses"], [10])
        self.assertEqual(attacks[("item.rapier-masterwork", False)]["damageExpression"], "1d6+1")
        self.assertEqual(attacks[("item.rapier-masterwork", False)]["critical"], "18-20/x2")
        self.assertEqual(attacks[("item.longbow-plus-1", False)]["attackBonuses"], [10])
        self.assertEqual(attacks[("item.longbow-plus-1", False)]["damageExpression"], "1d8+1")
        self.assertEqual(attacks[("item.longbow-plus-1", False)]["rangeIncrement"], 100)
        self.assertEqual(attacks[("item.longbow-plus-1", True)]["attackBonuses"], [8, 8])
        self.assertTrue(attacks[("item.longbow-plus-1", True)]["fullAttack"])

        self.assertEqual(canonical["initiative"], 4)
        self.assertEqual(next(skill for skill in canonical["skills"] if skill["skillId"] == "skill.perception")["total"], 11)
        self.assertEqual(next(skill for skill in canonical["skills"] if skill["skillId"] == "skill.survival")["total"], 9)
        self.assertEqual(features["npc-class-feature.ranger-favored-terrain"]["conditionalBonuses"]["initiative"], 2)
        self.assertEqual(features["npc-class-feature.ranger-favored-enemy"]["conditionalBonuses"]["attack"], 2)
        self.assertEqual(
            [(attack["attackBonuses"], attack["damageExpression"]) for attack in canonical["attacks"] if attack["itemId"] == "item.longbow-plus-1"],
            [([10], "1d8+1"), ([8, 8], "1d8+1")],
        )

    def test_choice_requirements_expose_multiclass_groups_and_class_choices(self):
        engine = Engine()
        result = engine.execute(request("kiramor-requirements", "draft.choiceRequirements", {"draft": copy.deepcopy(NPC_FIXTURE)}))
        self.assertTrue(result["ok"], result)
        requirements = {entry["path"]: entry for entry in result["result"]["requirements"]}
        self.assertEqual(requirements["/selections/abilityGeneration/method"]["values"], ["ranged-preset", "assigned-array"])
        self.assertEqual(
            [entry["id"] for entry in requirements["/selections/classProgression/0/classId"]["values"]],
            ["npc-class.ranger"],
        )
        self.assertEqual(requirements["/selections/classProgression/0/levels"]["values"], [1, 2, 3, 4])
        self.assertEqual(
            [entry["id"] for entry in requirements["/selections/classProgression/1/classId"]["values"]],
            ["npc-class.rogue"],
        )
        self.assertEqual(requirements["/selections/classProgression/1/levels"]["values"], [1, 2])
        self.assertEqual(requirements["/selections/classFeatureChoices/combatStyle"]["values"], ["archery"])
        self.assertEqual(requirements["/selections/classFeatureChoices/favoredEnemy"]["values"], ["humanoid-orc"])
        self.assertEqual(requirements["/selections/classFeatureChoices/favoredTerrain"]["values"], ["forest"])
        self.assertEqual(requirements["/selections/classFeatureChoices/huntersBond"]["values"], ["companion-bond"])
        self.assertEqual(requirements["/selections/classFeatureChoices/rogueTalent"]["values"], ["bleeding-attack"])
        self.assertIn("/selections/spellLoadout/prepared", requirements)
        skills = result["result"]["selectionBudgets"]["skills"]
        self.assertEqual(skills["count"], 10)
        self.assertEqual([(group["classId"], group["count"], group["ranks"]) for group in skills["groups"]], [
            ("npc-class.ranger", 8, 6), ("npc-class.rogue", 2, 2),
        ])
        budgets = result["result"]["selectionBudgets"]
        self.assertEqual(budgets["gear"]["budgetCp"], 465000)
        self.assertEqual(budgets["spells"]["levels"]["1"], {"base": 0, "wisdomBonus": 0, "total": 0})
        self.assertEqual(
            [(feat["featId"], feat["grantedBy"]) for feat in budgets["feats"]["granted"]],
            [
                ("feat.rapid-shot", "npc-class-feature.ranger-combat-styles"),
                ("feat.endurance", "npc-class-feature.ranger-endurance"),
            ],
        )

    def test_bounded_lower_level_combinations_are_valid(self):
        expected_bab = {
            (1, 1): 1, (1, 2): 2, (2, 1): 2, (2, 2): 3,
            (3, 1): 3, (3, 2): 4, (4, 1): 4, (4, 2): 5,
        }
        for index, ((ranger_level, rogue_level), bab) in enumerate(expected_bab.items()):
            draft = copy.deepcopy(NPC_FIXTURE)
            selections = draft["selections"]
            selections["classProgression"] = [
                {"classId": "npc-class.ranger", "levels": ranger_level},
                {"classId": "npc-class.rogue", "levels": rogue_level},
            ]
            total_level = ranger_level + rogue_level
            selections["abilityGeneration"]["levelIncreases"] = {"4": "dexterity"} if total_level >= 4 else {}
            selections["feats"] = [
                {"slotId": f"general-{level}", "featId": feat_id}
                for level, feat_id in ((1, "feat.point-blank-shot"), (3, "feat.deadly-aim"), (5, "feat.weapon-finesse"))
                if level <= total_level
            ]
            choices = {"favoredEnemy": "humanoid-orc"}
            if ranger_level >= 2:
                choices["combatStyle"] = "archery"
            if ranger_level >= 3:
                choices["favoredTerrain"] = "forest"
            if ranger_level >= 4:
                choices["huntersBond"] = "companion-bond"
            if rogue_level >= 2:
                choices["rogueTalent"] = "bleeding-attack"
            selections["classFeatureChoices"] = choices
            result = self.create(Engine(), draft, f"kiramor-lower-{index}")
            self.assertEqual(result["evaluation"]["status"], "valid", result["evaluation"]["issues"])
            self.assertEqual(result["evaluation"]["canonical"]["bab"], bab)

    def test_unsupported_class_order_and_levels_are_rejected(self):
        scenarios = (
            ("order", [
                {"classId": "npc-class.rogue", "levels": 2},
                {"classId": "npc-class.ranger", "levels": 4},
            ], {"npc.multiclass-unsupported", "npc.slice-unsupported"}),
            ("ranger-level", [
                {"classId": "npc-class.ranger", "levels": 5},
                {"classId": "npc-class.rogue", "levels": 2},
            ], {"npc.multiclass-unsupported", "npc.catalog-gap"}),
            ("rogue-level", [
                {"classId": "npc-class.ranger", "levels": 4},
                {"classId": "npc-class.rogue", "levels": 3},
            ], {"npc.multiclass-unsupported", "npc.catalog-gap"}),
        )
        for name, progression, expected_codes in scenarios:
            with self.subTest(name=name):
                draft = copy.deepcopy(NPC_FIXTURE)
                draft["selections"]["classProgression"] = progression
                evaluation = self.create(Engine(), draft, f"kiramor-unsupported-{name}")["evaluation"]
                self.assertEqual(evaluation["status"], "invalid")
                self.assertTrue(expected_codes.issubset({issue["code"] for issue in evaluation["issues"]}))

    def test_prerequisite_failure_and_ranger_spell_warning_are_reported(self):
        low_dex = copy.deepcopy(NPC_FIXTURE)
        selections = low_dex["selections"]
        selections["classProgression"] = [
            {"classId": "npc-class.ranger", "levels": 1},
            {"classId": "npc-class.rogue", "levels": 1},
        ]
        selections["abilityGeneration"] = {
            "method": "assigned-array",
            "arrayId": "npc-ability-array.basic",
            "assignments": {
                "strength": 13, "dexterity": 8, "constitution": 12,
                "intelligence": 9, "wisdom": 10, "charisma": 11,
            },
        }
        selections["skillGeneration"]["skills"] = NPC_FIXTURE["selections"]["skillGeneration"]["skills"][:6] + NPC_FIXTURE["selections"]["skillGeneration"]["skills"][8:10]
        selections["feats"] = [{"slotId": "general-1", "featId": "feat.deadly-aim"}]
        selections["classFeatureChoices"] = {"favoredEnemy": "humanoid-orc"}
        result = self.create(Engine(), low_dex, "kiramor-prerequisite")["evaluation"]
        self.assertEqual(result["status"], "invalid")
        self.assertIn("npc.feat-prerequisite", {issue["code"] for issue in result["issues"]})

        warning = self.create(Engine(), request_id="kiramor-spell-warning")["evaluation"]
        self.assertIn("npc.casting-ability-insufficient", {issue["code"] for issue in warning["warnings"]})
        self.assertEqual(warning["canonical"]["spells"]["slotsByLevel"]["1"], {"base": 0, "wisdomBonus": 0, "total": 0})

    def test_animal_companion_remains_a_catalog_gap(self):
        draft = copy.deepcopy(NPC_FIXTURE)
        draft["selections"]["classFeatureChoices"]["huntersBond"] = "animal-companion"
        result = self.create(Engine(), draft, "kiramor-companion")["evaluation"]
        self.assertEqual(result["status"], "invalid")
        issue = next(issue for issue in result["issues"] if issue["code"] == "npc.catalog-gap")
        self.assertEqual(issue["path"], "/selections/classFeatureChoices/huntersBond")
        self.assertEqual(issue["details"]["recordId"], "npc-animal-companion.wolf")
        self.assertEqual(issue["kind"], "catalog-data")
        self.assertTrue(issue["sourceRefs"])

    def test_engine_acceptance_finalizes_exports_and_indexes_kiramor(self):
        with tempfile.TemporaryDirectory() as workspace:
            engine = Engine(workspace=workspace)
            created = self.create(engine, request_id="kiramor-accept-create")
            draft = created["draft"]
            applied = engine.execute(request("kiramor-accept-apply", "draft.applyChanges", {
                "draftId": draft["draftId"],
                "baseRevision": draft["revision"],
                "baseFingerprint": draft["fingerprint"],
                "changes": [{
                    "changeId": "acceptance-description",
                    "type": "set-concept",
                    "field": "description",
                    "value": "Engine acceptance run",
                }],
            }))
            self.assertTrue(applied["ok"], applied)
            draft = applied["result"]["draft"]
            finalized = engine.execute(request("kiramor-accept-finalize", "monster.finalize", {
                "draftId": draft["draftId"],
                "baseRevision": draft["revision"],
                "baseFingerprint": draft["fingerprint"],
            }))
            self.assertTrue(finalized["ok"], finalized)
            monster = finalized["result"]["monster"]
            self.assertEqual(monster["result"]["hp"], 40)

            for format_name in ("json", "markdown", "html"):
                exported = engine.execute(request(
                    f"kiramor-accept-export-{format_name}", "monster.export",
                    {"monsterId": monster["monsterId"], "format": format_name},
                ))
                self.assertTrue(exported["ok"], exported)
                self.assertTrue(exported["result"]["content"])

            library = engine.execute(request("kiramor-accept-search", "library.search", {"query": "Kiramor"}))
            self.assertTrue(library["ok"], library)
            self.assertEqual([entry["id"] for entry in library["result"]["monsters"]], [monster["monsterId"]])
            self.assertEqual(library["result"]["monsters"][0]["creationSystem"], "npc")


if __name__ == "__main__":
    unittest.main()
