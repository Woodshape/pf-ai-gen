import copy
import json
import tempfile
import unittest
from pathlib import Path

from monster_builder import Engine


ROOT = Path(__file__).parents[1]
FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "goblin-druid-3-fire.json").read_text(encoding="utf-8"))

SLOT_BUDGET = {
    "0": {"base": 4, "wisdomBonus": 0, "domain": 0, "total": 4},
    "1": {"base": 2, "wisdomBonus": 1, "domain": 1, "total": 4},
    "2": {"base": 1, "wisdomBonus": 1, "domain": 1, "total": 3},
}


def request(request_id, operation, payload):
    return {"protocolVersion": "1", "requestId": request_id, "operation": operation, "payload": payload}


def evaluation_for(draft, request_id="goblin-druid-eval"):
    response = Engine().execute(request(request_id, "draft.create", {"draft": draft}))
    if not response["ok"]:
        return None, response["error"]
    return response["result"]["evaluation"], None


class GoblinDruidTests(unittest.TestCase):
    def test_public_engine_builds_the_source_gated_prepared_caster_slice(self):
        created = Engine().execute(request("goblin-druid", "draft.create", {"draft": copy.deepcopy(FIXTURE)}))
        self.assertTrue(created["ok"], created)
        evaluation = created["result"]["evaluation"]
        self.assertEqual(evaluation["status"], "valid", evaluation["issues"])
        canonical = evaluation["canonical"]
        self.assertEqual((canonical["level"], canonical["totalLevel"]), (3, 3))
        self.assertEqual((canonical["npcCategory"], canonical["cr"]), ("heroic", 2))
        self.assertEqual(canonical["classProgression"], [{"classId": "npc-class.druid", "className": "Druid", "levels": 3}])
        self.assertEqual(canonical["abilityScores"], {
            "strength": 10, "dexterity": 12, "constitution": 14,
            "intelligence": 10, "wisdom": 15, "charisma": 11,
        })
        self.assertEqual(canonical["abilityModifiers"], {
            "strength": 0, "dexterity": 1, "constitution": 2,
            "intelligence": 0, "wisdom": 2, "charisma": 0,
        })
        self.assertEqual((canonical["hp"], canonical["hitDiceExpression"], canonical["bab"]), (27, "3d8+6", 2))
        self.assertEqual(canonical["defenses"], {
            "ac": 16, "touch": 12, "flatFooted": 15,
            "fortitude": 5, "reflex": 2, "will": 7,
            "acBreakdown": {"armor": 2, "shield": 2, "dexterity": 1, "size": 1},
        })
        self.assertEqual((canonical["initiative"], canonical["cmb"], canonical["cmd"]), (5, 1, 12))
        self.assertEqual(canonical["languages"], ["Goblin", "Druidic"])
        self.assertEqual(canonical["gearBudget"]["budgetCp"], 165000)
        self.assertEqual(canonical["gearBudget"]["spentCp"], 2300)
        self.assertEqual(canonical["gearBudget"]["remainingCp"], 162700)

        skills = {entry["skillId"]: entry for entry in canonical["skills"]}
        self.assertEqual(skills["skill.knowledge-nature"]["total"], 8)
        self.assertEqual(skills["skill.knowledge-nature"]["classFeatureBonus"], 2)
        self.assertEqual(skills["skill.survival"]["total"], 10)
        self.assertEqual(skills["skill.survival"]["classFeatureBonus"], 2)
        self.assertEqual(skills["skill.heal"]["total"], 8)
        self.assertEqual(skills["skill.spellcraft"]["total"], 6)

        gear = {entry["itemId"]: entry for entry in canonical["gear"]}
        self.assertEqual(gear["item.sickle"]["weightLb"], 1)
        self.assertEqual(gear["item.leather-armor"]["weightLb"], 7.5)
        self.assertEqual(gear["item.heavy-wooden-shield"]["weightLb"], 5)

        spells = canonical["spells"]
        self.assertEqual(spells["castingMode"], "prepared")
        self.assertEqual(spells["casterLevel"], 3)
        self.assertEqual((spells["castingAbility"], spells["castingAbilityModifier"]), ("wisdom", 2))
        self.assertEqual(spells["slotsByLevel"], SLOT_BUDGET)
        self.assertEqual(spells["saveDcByLevel"], {"0": 12, "1": 13, "2": 14})
        self.assertEqual(spells["prepared"]["0"], ["spell.detect-magic", "spell.light", "spell.flare", "spell.detect-magic"])
        self.assertEqual(spells["prepared"]["1"], ["spell.produce-flame", "spell.entangle", "spell.cure-light-wounds"])
        self.assertEqual(spells["prepared"]["2"], ["spell.flaming-sphere", "spell.barkskin"])
        self.assertEqual(spells["domainPrepared"], {"1": ["spell.burning-hands"], "2": ["spell.produce-flame"]})
        self.assertEqual(spells["spontaneousConversion"], {
            "name": "Summon Nature’s Ally", "from": "prepared", "excludesDomainSlots": True,
            "spellIdsBySlotLevel": {
                "1": ["spell.summon-nature-s-ally-i"],
                "2": ["spell.summon-nature-s-ally-i", "spell.summon-nature-s-ally-ii"],
            },
        })

        features = {feature["featureId"]: feature for feature in canonical["classFeatures"]}
        self.assertEqual(
            [feature["featureId"] for feature in canonical["classFeatures"]],
            [
                "npc-class-feature.druid-proficiencies", "npc-class-feature.druid-spellcasting",
                "npc-class-feature.druid-orisons", "npc-class-feature.druid-nature-bond",
                "npc-class-feature.druidic", "npc-class-feature.druid-nature-sense",
                "npc-class-feature.druid-wild-empathy", "npc-class-feature.druid-woodland-stride",
                "npc-class-feature.druid-trackless-step", "npc-class-feature.fire-domain",
            ],
        )
        proficiencies = features["npc-class-feature.druid-proficiencies"]
        self.assertIn("sickle", proficiencies["effects"]["weaponProficiencies"])
        self.assertEqual(proficiencies["effects"]["armorProficiencies"], ["light", "medium"])
        self.assertIn("wooden", proficiencies["effects"]["shieldProficiencies"])
        self.assertEqual(features["npc-class-feature.druid-orisons"]["effects"], {"notExpendedWhenCast": True, "mayBePreparedMultipleTimes": True})
        self.assertEqual(features["npc-class-feature.druid-nature-bond"]["choice"], "fire-domain")
        self.assertEqual(features["npc-class-feature.druid-nature-sense"]["skillBonuses"], {"skill.knowledge-nature": 2, "skill.survival": 2})
        self.assertEqual(features["npc-class-feature.druid-wild-empathy"]["checkBonus"], 3)
        fire = features["npc-class-feature.fire-domain"]
        self.assertEqual(fire["powers"][0]["name"], "Fire Bolt")
        self.assertEqual(fire["powers"][0]["damageExpression"], "1d6+1")
        self.assertEqual(fire["powers"][0]["usesPerDay"], 5)
        self.assertEqual(fire["powers"][0]["attackBonus"], 4)

        self.assertEqual(canonical["attacks"][0], {
            "name": "Sickle", "itemId": "item.sickle", "attackBonuses": [3],
            "attackBonusExpression": "+3", "damageExpression": "1d4", "damageType": "S",
        })
        self.assertEqual(canonical["attacks"][1]["name"], "Fire Bolt")
        self.assertEqual((canonical["attacks"][1]["attackBonuses"], canonical["attacks"][1]["attackBonusExpression"]), ([4], "+4"))

        self.assertTrue(all(entry["sourceRefs"] for entry in evaluation["derivationTrace"]))
        warning_codes = {warning["code"] for warning in evaluation["warnings"]}
        self.assertEqual(warning_codes, {"npc.gear-budget-approximate"})

        requirements = Engine().execute(request("goblin-druid-requirements", "draft.choiceRequirements", {"draft": copy.deepcopy(FIXTURE)}))
        self.assertTrue(requirements["ok"], requirements)
        budgets = requirements["result"]["selectionBudgets"]
        self.assertEqual(budgets["spells"], {"required": True, "mode": "prepared", "levels": SLOT_BUDGET})
        self.assertEqual(budgets["gear"]["budgetCp"], 165000)
        self.assertEqual(budgets["gear"]["spentCp"], 2300)
        self.assertEqual(budgets["skills"], {"method": "simplified", "count": 4, "selected": 4})
        self.assertEqual([slot["slotId"] for slot in budgets["feats"]["slots"]], ["general-1", "general-3"])
        paths = {item["path"]: item for item in requirements["result"]["requirements"]}
        self.assertEqual(paths["/selections/classFeatureChoices/natureBond"]["values"], ["fire-domain"])
        self.assertIn("/selections/spellLoadout/prepared", paths)
        self.assertIn("/selections/spellLoadout/domainPrepared", paths)

    def test_prepared_loadout_rejections_are_deterministic(self):
        cases = [
            ("drop-orison", lambda selections: selections["spellLoadout"]["prepared"]["0"].pop(), "npc.spell-count-invalid"),
            ("excess-first-level", lambda selections: selections["spellLoadout"]["prepared"]["1"].append("spell.entangle"), "npc.spell-count-invalid"),
            ("wrong-regular-level", lambda selections: selections["spellLoadout"]["prepared"]["2"].__setitem__(0, "spell.produce-flame"), "npc.spell-level-invalid"),
            ("wrong-domain-spell", lambda selections: selections["spellLoadout"]["domainPrepared"]["1"].__setitem__(0, "spell.entangle"), "npc.domain-spell-invalid"),
            ("missing-domain-level", lambda selections: selections["spellLoadout"]["domainPrepared"].pop("2"), "npc.spell-levels-invalid"),
            ("extra-loadout-field", lambda selections: selections["spellLoadout"].update({"known": {}}), "npc.spell-loadout-invalid"),
            ("wrong-nature-bond", lambda selections: selections["classFeatureChoices"].__setitem__("natureBond", "animal-companion"), "npc.choice-invalid"),
        ]
        for request_id, mutate, expected_code in cases:
            with self.subTest(request_id=request_id):
                draft = copy.deepcopy(FIXTURE)
                mutate(draft["selections"])
                evaluation, error = evaluation_for(draft, request_id)
                self.assertIsNone(error)
                self.assertEqual(evaluation["status"], "invalid")
                self.assertIn(expected_code, {issue["code"] for issue in evaluation["issues"]})

    def test_missing_domain_level_points_at_the_domain_path(self):
        draft = copy.deepcopy(FIXTURE)
        draft["selections"]["spellLoadout"]["domainPrepared"].pop("2")
        evaluation, _ = evaluation_for(draft, "goblin-druid-missing-domain")
        issue = next(issue for issue in evaluation["issues"] if issue["code"] == "npc.spell-levels-invalid")
        self.assertEqual(issue["path"], "/selections/spellLoadout/domainPrepared")

    def test_casting_ability_minimum_is_source_gated(self):
        draft = copy.deepcopy(FIXTURE)
        draft["selections"]["abilityGeneration"] = {
            "method": "assigned-array",
            "arrayId": "npc-ability-array.heroic",
            "assignments": {
                "strength": 15, "dexterity": 14, "constitution": 13,
                "intelligence": 12, "wisdom": 10, "charisma": 8,
            },
        }
        evaluation, _ = evaluation_for(draft, "goblin-druid-low-wisdom")
        self.assertEqual(evaluation["status"], "invalid")
        issue = next(issue for issue in evaluation["issues"] if issue["code"] == "npc.casting-ability-insufficient")
        self.assertEqual((issue["details"]["actual"], issue["details"]["required"]), (10, 12))

    def test_unresolved_spell_record_is_a_catalog_gap(self):
        draft = copy.deepcopy(FIXTURE)
        draft["selections"]["spellLoadout"]["prepared"]["0"][0] = "spell.guidance"
        evaluation, error = evaluation_for(draft, "goblin-druid-gap-spell")
        self.assertIsNone(error)
        self.assertEqual(evaluation["status"], "invalid")
        issue = next(issue for issue in evaluation["issues"] if issue["code"] == "npc.catalog-gap")
        self.assertEqual(issue["path"], "/selections/spellLoadout/prepared/0/0")
        self.assertEqual(issue["details"]["recordId"], "spell.guidance")

    def test_unknown_spells_and_computed_values_are_public_boundary_errors(self):
        draft = copy.deepcopy(FIXTURE)
        draft["selections"]["spellLoadout"]["prepared"]["0"][0] = "spell.definitely-not-catalogued"
        response = Engine().execute(request("goblin-druid-unknown-spell", "draft.create", {"draft": draft}))
        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "catalog.unknown-id")
        self.assertEqual(response["error"]["path"], "/selections/spellLoadout/prepared/0/0")

        draft = copy.deepcopy(FIXTURE)
        draft["selections"]["hp"] = 19
        response = Engine().execute(request("goblin-druid-computed", "draft.create", {"draft": draft}))
        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "draft.computed-selection")

    def test_finalize_reload_and_exports_preserve_the_canonical_result(self):
        with tempfile.TemporaryDirectory() as workspace:
            engine = Engine(workspace=workspace)
            created = engine.execute(request("druid-create", "draft.create", {"draft": copy.deepcopy(FIXTURE)}))
            self.assertTrue(created["ok"], created)
            draft = created["result"]["draft"]
            finalized = engine.execute(request("druid-finalize", "monster.finalize", {
                "draftId": draft["draftId"], "baseRevision": draft["revision"], "baseFingerprint": draft["fingerprint"],
            }))
            self.assertTrue(finalized["ok"], finalized)
            monster = finalized["result"]["monster"]
            self.assertEqual(monster["creationSystem"], "npc")
            self.assertEqual(monster["result"]["spells"]["casterLevel"], 3)
            self.assertEqual(monster["result"]["spells"]["castingMode"], "prepared")

            reloaded = Engine(workspace=workspace)
            loaded_draft = reloaded.execute(request("druid-reload-draft", "draft.get", {"draftId": draft["draftId"]}))
            loaded_monster = reloaded.execute(request("druid-reload-monster", "monster.get", {"monsterId": monster["monsterId"]}))
            self.assertTrue(loaded_draft["ok"], loaded_draft)
            self.assertTrue(loaded_monster["ok"], loaded_monster)
            self.assertEqual(loaded_draft["result"]["evaluation"]["status"], "valid")
            self.assertEqual(loaded_monster["result"]["monster"], monster)

            for format_name in ("json", "markdown", "html"):
                exported = reloaded.execute(request(f"druid-{format_name}", "monster.export", {
                    "monsterId": monster["monsterId"], "format": format_name,
                }))
                self.assertTrue(exported["ok"], exported)
                content = exported["result"]["content"]
                rendered = json.dumps(content, ensure_ascii=False) if isinstance(content, dict) else content
                self.assertIn("Zarka", rendered)

            markdown = reloaded.execute(request("druid-md-inspect", "monster.export", {
                "monsterId": monster["monsterId"], "format": "markdown",
            }))["result"]["content"]
            for expected in (
                "# Zarka CR 2/Level 3",
                "Init +5 (darkvision 60 ft.)",
                "NE Small humanoid (goblinoid); Speed 30 ft.",
                "AC 16 (+2 armor, +2 shield, +1 Dex, +1 size); touch AC 12; flat-footed AC 15; hp 27 (3d8+6); Fort +5; Ref +2; Will +7; CMD 12",
                "Sickle +3 (1d4; S)",
                "Fire Bolt +4 ranged touch (1d6+1 fire), 30 ft., 5/day",
                "Skills Knowledge (Nature) +8, Heal +8, Spellcraft +6, Survival +10",
                "Feats Iron Will, Improved Initiative",
                "Class Features Druid Proficiencies, Druid spellcasting, Orisons, Nature Bond (Fire domain), Druidic, Nature Sense, Wild Empathy, Woodland Stride, Trackless Step, Fire Domain",
                "Languages Goblin, Druidic",
                "Gear Sickle (6 gp), Leather Armor (10 gp), Heavy Wooden Shield (7 gp)",
                "Gear Budget 1,650 gp budget, 23 gp spent, 1,627 gp unallocated",
                "Druid Spells (CL 3rd; Wis-based)",
                "2nd (3 slots: 1 base, 1 Wis, 1 domain, DC 14)—Flaming Sphere, Barkskin, Produce Flameᴰ",
                "1st (4 slots: 2 base, 1 Wis, 1 domain, DC 13)—Produce Flame, Entangle, Cure Light Wounds, Burning Handsᴰ",
                "0 (4 slots: 4 base, DC 12)—Detect Magic, Light, Flare, Detect Magic",
                "ᴰ Fire-domain spell",
                "Spontaneous conversion: prepared spells may become Summon Nature’s Ally I–II (domain slots excluded)",
            ):
                self.assertIn(expected, markdown)

            html = reloaded.execute(request("druid-html-inspect", "monster.export", {
                "monsterId": monster["monsterId"], "format": "html",
            }))["result"]["content"]
            for expected in (
                "Druid Spells (CL 3rd; Wis-based)",
                "1st (4 slots: 2 base, 1 Wis, 1 domain, DC 13)—Produce Flame, Entangle, Cure Light Wounds, Burning Handsᴰ",
                "Spontaneous conversion: prepared spells may become Summon Nature’s Ally I–II (domain slots excluded)",
                "AC 16 (+2 armor, +2 shield, +1 Dex, +1 size)",
                "Fire Bolt +4 ranged touch (1d6+1 fire), 30 ft., 5/day",
            ):
                self.assertIn(expected, html)


if __name__ == "__main__":
    unittest.main()