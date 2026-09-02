import copy
import json
import tempfile
import unittest
from pathlib import Path

from monster_builder import Engine


ROOT = Path(__file__).parents[1]
FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "goblin-sorcerer-6.json").read_text(encoding="utf-8"))


def request(request_id, operation, payload):
    return {"protocolVersion": "1", "requestId": request_id, "operation": operation, "payload": payload}


class GoblinSorcererTests(unittest.TestCase):
    def test_public_engine_builds_the_source_gated_level_six_slice(self):
        engine = Engine()
        created = engine.execute(request("goblin-sorcerer", "draft.create", {"draft": copy.deepcopy(FIXTURE)}))
        self.assertTrue(created["ok"], created)
        evaluation = created["result"]["evaluation"]
        self.assertEqual(evaluation["status"], "valid", evaluation["issues"])
        canonical = evaluation["canonical"]
        self.assertEqual((canonical["npcCategory"], canonical["cr"]), ("heroic", 5))
        self.assertEqual(canonical["abilityScores"], {
            "strength": 6, "dexterity": 18, "constitution": 12,
            "intelligence": 13, "wisdom": 10, "charisma": 14,
        })
        self.assertEqual((canonical["hp"], canonical["bab"]), (27, 3))
        self.assertEqual(canonical["defenses"], {
            "ac": 15, "touch": 15, "flatFooted": 11,
            "fortitude": 4, "reflex": 9, "will": 8,
            "acBreakdown": {"dexterity": 4, "size": 1},
        })
        self.assertEqual(canonical["initiative"], 8)
        self.assertEqual(canonical["gearBudget"]["budgetCp"], 465000)
        self.assertEqual(canonical["spells"]["perDay"], {"0": "at-will", "1": 7, "2": 6, "3": 3})
        self.assertEqual(canonical["spells"]["saveDcByLevel"], {"0": 12, "1": 13, "2": 14, "3": 15})
        self.assertIn("spell.burning-hands", canonical["spells"]["known"]["1"])
        self.assertIn("spell.scorching-ray", canonical["spells"]["known"]["2"])
        self.assertEqual(canonical["spells"]["known"]["3"], ["spell.fireball"])
        fire = next(feature for feature in canonical["classFeatures"] if feature["featureId"] == "npc-class-feature.sorcerer-bloodlines")
        self.assertEqual(fire["choice"], "elemental-fire")
        self.assertEqual(fire["arcana"]["energyType"], "fire")
        self.assertEqual(fire["powers"][0]["usesPerDay"], 5)
        self.assertEqual((fire["powers"][0]["attackBonus"], fire["powers"][0]["damageExpression"]), (8, "1d6+3"))
        self.assertEqual(fire["powers"][1]["resistance"], {"fire": 10})
        self.assertTrue(all(entry["sourceRefs"] for entry in evaluation["derivationTrace"]))

        requirements = engine.execute(request("goblin-sorcerer-requirements", "draft.choiceRequirements", {"draft": copy.deepcopy(FIXTURE)}))
        self.assertTrue(requirements["ok"], requirements)
        budgets = requirements["result"]["selectionBudgets"]
        self.assertEqual(budgets["spells"]["levels"], {"0": 7, "1": 4, "2": 2, "3": 1})
        self.assertEqual(budgets["gear"]["budgetCp"], 465000)

    def test_public_engine_rejects_an_incomplete_spell_loadout(self):
        draft = copy.deepcopy(FIXTURE)
        draft["selections"]["spellLoadout"]["known"]["3"].pop()
        response = Engine().execute(request("goblin-sorcerer-short-spells", "draft.create", {"draft": draft}))
        self.assertTrue(response["ok"], response)
        evaluation = response["result"]["evaluation"]
        self.assertEqual(evaluation["status"], "invalid")
        self.assertIn("npc.spell-count-invalid", {issue["code"] for issue in evaluation["issues"]})

    def test_finalize_reload_and_export_preserve_the_canonical_result(self):
        with tempfile.TemporaryDirectory() as workspace:
            engine = Engine(workspace=workspace)
            created = engine.execute(request("goblin-create", "draft.create", {"draft": copy.deepcopy(FIXTURE)}))
            self.assertTrue(created["ok"], created)
            draft = created["result"]["draft"]
            finalized = engine.execute(request("goblin-finalize", "monster.finalize", {
                "draftId": draft["draftId"], "baseRevision": draft["revision"], "baseFingerprint": draft["fingerprint"],
            }))
            self.assertTrue(finalized["ok"], finalized)
            monster = finalized["result"]["monster"]
            self.assertEqual(monster["result"]["spells"]["casterLevel"], 6)

            reloaded = Engine(workspace=workspace)
            loaded = reloaded.execute(request("goblin-reload", "monster.get", {"monsterId": monster["monsterId"]}))
            self.assertTrue(loaded["ok"], loaded)
            self.assertEqual(loaded["result"]["monster"], monster)
            for format_name in ("json", "markdown", "html"):
                exported = reloaded.execute(request(f"goblin-{format_name}", "monster.export", {
                    "monsterId": monster["monsterId"], "format": format_name,
                }))
                self.assertTrue(exported["ok"], exported)
                content = exported["result"]["content"]
                rendered = json.dumps(content) if isinstance(content, dict) else content
                self.assertIn("Cinder", rendered)
                if format_name != "json":
                    for expected in (
                        "Cinder CR 5/Level 6", "AC 15 (+4 Dex, +1 size)", "touch AC 15",
                        "flat-footed AC 11", "hp 27 (6d6+6)", "CMD 14",
                        "Elemental Ray +8 ranged touch (1d6+3 fire), 30 ft., 5/day",
                        "Skills Bluff +11, Spellcraft +10, Use Magic Device +11",
                        "Feats Improved Initiative, Iron Will, Lightning Reflexes, Eschew Materials",
                        "Sorcerer Spells (CL 6th; Cha-based)", "3rd (3/day, DC 15)—Fireball",
                    ):
                        self.assertIn(expected, rendered)


if __name__ == "__main__":
    unittest.main()
