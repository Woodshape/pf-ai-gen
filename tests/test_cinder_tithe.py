"""The playable encounter exercises catalog additions and final sheet exports."""
import json
from pathlib import Path
import unittest

from monster_builder import Engine

ROOT = Path(__file__).resolve().parents[1]
ENCOUNTER = ROOT / "docs/encounters/cinder-tithe"


class CinderTitheTests(unittest.TestCase):
    def test_three_shared_statblocks_finalize_and_export_without_invented_treasure(self):
        engine = Engine()

        def execute(operation, payload):
            response = engine.execute({"protocolVersion": "1", "requestId": f"{slug}-{operation}-{payload.get('format', '')}",
                                       "operation": operation, "payload": payload})
            self.assertTrue(response["ok"], response)
            return response["result"]

        expected = {"varkesh": (2, 23, 17), "sootfinger": (1, 17, 17),
                    "goblin-warrior": ("1/3", 6, 16)}
        roster = json.loads((ENCOUNTER / "roster.json").read_text())
        self.assertEqual([npc["sheet"] for npc in roster["npcs"]],
                         ["varkesh.md", "sootfinger.md", "goblin-warrior.md", "goblin-warrior.md", "goblin-warrior.md"])
        for slug, (cr, hp, ac) in expected.items():
            with self.subTest(npc=slug):
                created = execute("draft.create", {"draft": json.loads((ENCOUNTER / f"{slug}.draft.json").read_text())})
                evaluation = created["evaluation"]
                self.assertEqual(evaluation["status"], "valid", evaluation["issues"])
                self.assertEqual(evaluation["issues"], [])
                canonical = evaluation["canonical"]
                self.assertEqual((canonical["cr"], canonical["hp"], canonical["defenses"]["ac"]), (cr, hp, ac))
                if slug == "varkesh":
                    self.assertEqual(canonical["activeEffects"][0]["effectId"], "npc-effect.mage-armor")
                    self.assertEqual(canonical["abilityScores"]["dexterity"], 16)
                    self.assertEqual(canonical["abilityScores"]["constitution"], 15)
                    self.assertEqual(next(s for s in canonical["skills"] if s["skillId"] == "skill.stealth")["total"], 10)
                    self.assertEqual(canonical["hitDiceExpression"], "3d6+9")
                    self.assertEqual(canonical["spells"]["perDay"]["1"], 6)
                    self.assertIn("spell.burning-hands", canonical["spells"]["known"]["1"])
                draft = created["draft"]
                monster = execute("monster.finalize", {"draftId": draft["draftId"], "baseRevision": draft["revision"],
                                                       "baseFingerprint": draft["fingerprint"]})["monster"]
                self.assertEqual(monster["result"], canonical)
                for format_name in ("markdown", "html"):
                    sheet = execute("monster.export", {"monsterId": monster["monsterId"], "format": format_name,
                                                       "profile": "sheet"})["content"]
                    self.assertIn(canonical["name"], sheet)
                    self.assertIn(f"hp {hp} ({canonical['hitDiceExpression']})", sheet)
                    self.assertNotIn("gp in coins and gear", sheet)
                    if slug == "varkesh":
                        self.assertIn("Active Effects", sheet)
                        self.assertIn("Fire resistance 10", sheet)
                        self.assertIn("Elemental Ray +4 (1d6+1 fire)", sheet)
                    if slug == "sootfinger":
                        self.assertIn("Shortsword +6 (1d4/19-20)", sheet)
                        self.assertIn("bleeding attack", sheet)


if __name__ == "__main__":
    unittest.main()
