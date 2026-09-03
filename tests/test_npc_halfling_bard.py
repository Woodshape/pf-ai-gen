import copy
import json
import tempfile
import unittest
from pathlib import Path

from monster_builder import Engine


ROOT = Path(__file__).parents[1]
FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "halfling-bard-2.json").read_text(encoding="utf-8"))


def request(request_id, operation, payload):
    return {"protocolVersion": "1", "requestId": request_id, "operation": operation, "payload": payload}


class HalflingBardTests(unittest.TestCase):
    def test_public_engine_builds_the_source_gated_level_two_slice(self):
        created = Engine().execute(request("halfling-bard", "draft.create", {"draft": copy.deepcopy(FIXTURE)}))
        self.assertTrue(created["ok"], created)
        evaluation = created["result"]["evaluation"]
        self.assertEqual(evaluation["status"], "valid", evaluation["issues"])
        canonical = evaluation["canonical"]
        self.assertEqual((canonical["level"], canonical["totalLevel"]), (2, 2))
        self.assertEqual((canonical["npcCategory"], canonical["cr"]), ("heroic", 1))
        self.assertEqual(canonical["abilityScores"], {
            "strength": 6, "dexterity": 16, "constitution": 12,
            "intelligence": 13, "wisdom": 10, "charisma": 17,
        })
        self.assertEqual((canonical["hp"], canonical["hitDiceExpression"], canonical["bab"]), (15, "2d8+2", 1))
        self.assertEqual(canonical["defenses"], {
            "ac": 14, "touch": 14, "flatFooted": 11,
            "fortitude": 3, "reflex": 8, "will": 5,
            "acBreakdown": {"dexterity": 3, "size": 1},
        })
        self.assertEqual(canonical["initiative"], 7)
        self.assertEqual(canonical["speed"], {"land": 20})
        self.assertEqual(canonical["languages"], ["Common", "Halfling"])
        skills = {entry["skillId"]: entry for entry in canonical["skills"]}
        self.assertEqual(skills["skill.perception"]["raceBonus"], 2)
        self.assertEqual(skills["skill.perception"]["total"], 7)
        self.assertEqual(skills["skill.perform"]["total"], 8)
        self.assertEqual(skills["skill.use-magic-device"]["total"], 8)
        self.assertEqual(canonical["spells"]["perDay"], {"0": "at-will", "1": 3})
        self.assertEqual(canonical["spells"]["saveDcByLevel"], {"0": 13, "1": 14})
        self.assertEqual(canonical["spells"]["castingAbility"], "charisma")
        self.assertIn("spell.charm-person", canonical["spells"]["known"]["1"])
        feature_ids = [feature["featureId"] for feature in canonical["classFeatures"]]
        for expected in (
            "npc-class-feature.bard-spellcasting", "npc-class-feature.bardic-performance",
            "npc-class-feature.inspire-courage", "npc-class-feature.versatile-performance",
            "npc-class-feature.well-versed",
        ):
            self.assertIn(expected, feature_ids)
        self.assertTrue(all(entry["sourceRefs"] for entry in evaluation["derivationTrace"]))

        requirements = Engine().execute(request("halfling-bard-requirements", "draft.choiceRequirements", {"draft": copy.deepcopy(FIXTURE)}))
        self.assertTrue(requirements["ok"], requirements)
        budgets = requirements["result"]["selectionBudgets"]
        self.assertEqual(budgets["spells"]["levels"], {"0": 5, "1": 3})
        self.assertEqual(budgets["gear"]["budgetCp"], 78000)
        self.assertEqual([slot["slotId"] for slot in budgets["feats"]["slots"]], ["general-1"])

    def test_public_engine_builds_level_one_and_level_three_variants(self):
        engine = Engine()
        for level, expected in (
            (1, {"hp": 9, "bab": 0, "known": {"0": 4, "1": 2}, "perDay": {"0": "at-will", "1": 2},
                 "saves": (3, 7, 4), "ac": 14}),
            (3, {"hp": 22, "bab": 2, "known": {"0": 6, "1": 4}, "perDay": {"0": "at-will", "1": 4},
                 "saves": (4, 8, 7), "ac": 14}),
        ):
            draft = copy.deepcopy(FIXTURE)
            draft["selections"]["classProgression"][0]["levels"] = level
            draft["selections"]["skillGeneration"]["skills"] = draft["selections"]["skillGeneration"]["skills"][:7]
            known = {"0": ["spell.detect-magic", "spell.flare", "spell.light", "spell.mage-hand",
                           "spell.prestidigitation", "spell.read-magic"][: expected["known"]["0"]],
                     "1": ["spell.charm-person", "spell.grease", "spell.sleep", "spell.cure-light-wounds"][: expected["known"]["1"]]}
            draft["selections"]["spellLoadout"]["known"] = known
            feat_ids = ["feat.improved-initiative", "feat.iron-will", "feat.lightning-reflexes"]
            slots = [slot for slot in (1, 3, 5, 7) if slot <= level]
            draft["selections"]["feats"] = [{"slotId": f"general-{slot}", "featId": feat_ids[index]}
                                            for index, slot in enumerate(slots)]
            created = engine.execute(request(f"halfling-bard-{level}", "draft.create", {"draft": draft}))
            self.assertTrue(created["ok"], created)
            evaluation = created["result"]["evaluation"]
            self.assertEqual(evaluation["status"], "valid", evaluation["issues"])
            canonical = evaluation["canonical"]
            self.assertEqual(canonical["level"], level)
            self.assertEqual((canonical["hp"], canonical["bab"]), (expected["hp"], expected["bab"]))
            defenses = canonical["defenses"]
            self.assertEqual((defenses["fortitude"], defenses["reflex"], defenses["will"]), expected["saves"])
            self.assertEqual(defenses["ac"], expected["ac"])
            self.assertEqual(canonical["spells"]["perDay"], expected["perDay"])
            self.assertEqual({level_key: len(ids) for level_key, ids in canonical["spells"]["known"].items()}, expected["known"])

    def test_slice_gate_rejects_out_of_scope_combinations(self):
        engine = Engine()
        cases = []
        level_four = copy.deepcopy(FIXTURE)
        level_four["selections"]["classProgression"][0]["levels"] = 4
        cases.append(level_four)
        human_bard = copy.deepcopy(FIXTURE)
        human_bard["selections"]["raceId"] = "npc-race.human"
        cases.append(human_bard)
        for index, draft in enumerate(cases):
            response = engine.execute(request(f"halfling-bard-slice-{index}", "draft.create", {"draft": draft}))
            self.assertTrue(response["ok"], response)
            evaluation = response["result"]["evaluation"]
            self.assertEqual(evaluation["status"], "invalid")
            codes = [issue["code"] for issue in evaluation["issues"]]
            self.assertIn("npc.slice-unsupported", codes)

    def test_weapon_finesse_applies_dexterity_to_light_and_rapier_attacks(self):
        draft = copy.deepcopy(FIXTURE)
        draft["selections"]["classProgression"][0]["levels"] = 1
        draft["selections"]["feats"] = [{"slotId": "general-1", "featId": "feat.weapon-finesse"}]
        draft["selections"]["gear"] = [{"itemId": "item.rapier", "quantity": 1}, {"itemId": "item.shortsword", "quantity": 1}]
        draft["selections"]["skillGeneration"]["skills"] = draft["selections"]["skillGeneration"]["skills"][:7]
        draft["selections"]["spellLoadout"]["known"] = {"0": ["spell.detect-magic", "spell.flare", "spell.light", "spell.mage-hand"],
                                                        "1": ["spell.charm-person", "spell.grease"]}
        created = Engine().execute(request("bard-finesse", "draft.create", {"draft": draft}))
        self.assertTrue(created["ok"], created)
        evaluation = created["result"]["evaluation"]
        self.assertEqual(evaluation["status"], "valid", evaluation["issues"])
        attacks = {attack["name"]: attack for attack in evaluation["canonical"]["attacks"]}
        self.assertEqual(set(attacks), {"Rapier", "Shortsword"})
        for attack in attacks.values():
            # bab 0 + Dex +3 + Small +1; damage keeps the Strength penalty.
            self.assertEqual(attack["attackBonuses"], [4])
            self.assertEqual(attack["damageExpression"], "1d4-2")

    def test_finalize_reload_and_exports_preserve_the_canonical_result(self):
        with tempfile.TemporaryDirectory() as workspace:
            engine = Engine(workspace=workspace)
            created = engine.execute(request("bard-create", "draft.create", {"draft": copy.deepcopy(FIXTURE)}))
            self.assertTrue(created["ok"], created)
            draft = created["result"]["draft"]
            finalized = engine.execute(request("bard-finalize", "monster.finalize", {
                "draftId": draft["draftId"], "baseRevision": draft["revision"], "baseFingerprint": draft["fingerprint"],
            }))
            self.assertTrue(finalized["ok"], finalized)
            monster = finalized["result"]["monster"]
            self.assertEqual(monster["creationSystem"], "npc")
            self.assertEqual(monster["result"]["spells"]["casterLevel"], 2)

            reloaded = Engine(workspace=workspace)
            loaded_draft = reloaded.execute(request("bard-reload-draft", "draft.get", {"draftId": draft["draftId"]}))
            loaded_monster = reloaded.execute(request("bard-reload-monster", "monster.get", {"monsterId": monster["monsterId"]}))
            self.assertTrue(loaded_draft["ok"], loaded_draft)
            self.assertTrue(loaded_monster["ok"], loaded_monster)
            self.assertEqual(loaded_draft["result"]["evaluation"]["status"], "valid")
            self.assertEqual(loaded_monster["result"]["monster"], monster)

            for format_name in ("json", "markdown", "html"):
                exported = reloaded.execute(request(f"bard-{format_name}", "monster.export", {
                    "monsterId": monster["monsterId"], "format": format_name,
                }))
                self.assertTrue(exported["ok"], exported)
                content = exported["result"]["content"]
                rendered = json.dumps(content, ensure_ascii=False) if isinstance(content, dict) else content
                self.assertIn("Perrin Underbough", rendered)

            markdown = reloaded.execute(request("bard-md-inspect", "monster.export", {
                "monsterId": monster["monsterId"], "format": "markdown",
            }))["result"]["content"]
            for expected in (
                "# Perrin Underbough CR 1/Level 2",
                "CN Small humanoid (halfling); Speed 20 ft.",
                "AC 14 (+3 Dex, +1 size); touch AC 14; flat-footed AC 11; hp 15 (2d8+2); Fort +3; Ref +8; Will +5; CMD 11",
                "Bard Spells (CL 2nd; Cha-based)",
                "0 (at will, DC 13)—Detect Magic, Flare, Light, Mage Hand, Prestidigitation",
                "1st (3/day, DC 14)—Charm Person, Grease, Sleep",
                "Skills Perform +8, Perception +7, Use Magic Device +8, Bluff +8, Diplomacy +8, Spellcraft +6, Intimidate +8",
                "Feats Improved Initiative",
                "Class Features Bard proficiencies, Bard spellcasting, Bard cantrips, Bardic knowledge, Bardic performance, Countersong, Distraction, Fascinate, Inspire courage +1, Versatile performance, Well-versed",
                "Languages Common, Halfling",
            ):
                self.assertIn(expected, markdown)


if __name__ == "__main__":
    unittest.main()