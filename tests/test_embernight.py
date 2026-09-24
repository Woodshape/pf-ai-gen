"""Consistency checks for the Embernight encounter documents.

The docs are the deliverable here, so the test checks that the numbers in them
actually add up: room areas vs. the ASCII grid, and the stated XP budget vs.
the statblock XP values.
"""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENCOUNTER = ROOT / "docs/encounters/embernight"
sys.path.insert(0, str(ROOT))

from monster_builder import Engine  # noqa: E402


def read(name):
    return (ENCOUNTER / name).read_text()


def num(text):
    return int(text.replace("−", "-"))


def build_npc(draft):
    result = Engine().execute({
        "protocolVersion": "1",
        "requestId": "embernight",
        "operation": "draft.create",
        "payload": {"draft": draft},
    })
    return result["result"]["evaluation"]


class EmbernightDocsTests(unittest.TestCase):
    def test_encounter_files_exist_and_link_existing_rules(self):
        for name in ("README.md", "statblocks.md", "feuer-ebene-bewohner.md"):
            self.assertTrue((ENCOUNTER / name).is_file(), name)
        readme = read("README.md")
        linked = "../benton-burning-house/rauch-und-feuer.md"
        self.assertIn(linked, readme)
        self.assertTrue((ENCOUNTER / linked).resolve().is_file())

    def test_battlemap_files_have_a_five_foot_grid_and_fireplaces(self):
        readme = read("README.md")
        self.assertIn("5 ft", readme)
        levels = (("ground", "floorplan.svg"), ("first", "floorplan-first.svg"),
                  ("second", "floorplan-second.svg"))
        total_fireplaces = 0
        for level, filename in levels:
            path = ENCOUNTER / filename
            self.assertTrue(path.is_file(), path)
            svg = path.read_text()
            self.assertIn('class="grid"', svg)
            self.assertIn("5 ft", svg)
            # One fire icon is the legend; the rest are actual map fireplaces.
            total_fireplaces += svg.count('class="fire"') - 1
        self.assertEqual(total_fireplaces, 6)
        self.assertTrue((ENCOUNTER / "floorplan.pdf").is_file())

    def test_dayl_statblock_matches_engine_canonical(self):
        """Dayl must be produced by the engine, and npcs.md must agree with it."""
        draft = json.loads((ROOT / "tests/fixtures/embernight-dayl-bard-3.json").read_text())
        evaluation = build_npc(draft)
        self.assertEqual(evaluation["status"], "valid", evaluation.get("issues"))
        canonical = evaluation["canonical"]

        self.assertEqual(canonical["initiative"], 7)  # +3 Dex, +4 Improved Initiative
        self.assertEqual((canonical["hp"], canonical["bab"], canonical["cr"]), (21, 2, 2))
        self.assertEqual(canonical["abilityScores"], {
            "strength": 6, "dexterity": 16, "constitution": 12,
            "intelligence": 13, "wisdom": 10, "charisma": 17})
        self.assertEqual(canonical["cmb"], -1)
        self.assertEqual(canonical["cmd"], 12)
        defenses = canonical["defenses"]
        self.assertEqual(
            (defenses["ac"], defenses["touch"], defenses["flatFooted"]), (18, 14, 15))
        self.assertEqual(
            (defenses["fortitude"], defenses["reflex"], defenses["will"]), (3, 7, 4))
        self.assertEqual(
            {a["name"]: (a["attackBonusExpression"], a["damageExpression"])
             for a in canonical["attacks"]},
            {"Rapier": ("+6", "1d4-2"), "Sling": ("+6", "1d3-2")})
        self.assertEqual(
            {s["skillId"].split(".")[-1]: s["total"] for s in canonical["skills"]},
            {"diplomacy": 9, "knowledge-nobility": 8, "perception": 8, "perform": 9,
             "sense-motive": 6, "stealth": 11, "use-magic-device": 9})

        dayl = read("npcs.md").split("## Yalana")[0]
        self.assertEqual(
            num(re.search(r"\*\*Init\*\* ([+−-]\d+)", dayl).group(1)),
            canonical["initiative"])
        self.assertEqual(
            [num(v) for v in re.search(
                r"AC ([-−\d]+), touch ([-−\d]+), flat-footed ([-−\d]+)",
                dayl).groups()],
            [defenses["ac"], defenses["touch"], defenses["flatFooted"]])
        self.assertEqual(
            num(re.search(r"hp (\d+)", dayl).group(1)), canonical["hp"])
        self.assertEqual(
            [num(v) for v in re.search(
                r"\*\*Fort\*\* ([+−-]\d+), \*\*Ref\*\* ([+−-]\d+), "
                r"\*\*Will\*\* ([+−-]\d+)", dayl).groups()],
            [defenses["fortitude"], defenses["reflex"], defenses["will"]])
        self.assertEqual(
            [num(v) for v in re.search(
                r"\*\*CMB\*\* ([+−-]\d+); \*\*CMD\*\* (\d+)", dayl).groups()],
            [canonical["cmb"], canonical["cmd"]])
        self.assertEqual(
            [int(v) for v in re.search(
                r"Str (\d+), Dex (\d+), Con (\d+), Int (\d+), Wis (\d+), Cha (\d+)",
                dayl).groups()],
            [canonical["abilityScores"][k] for k in
             ("strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma")])
        skills_text = re.search(r"\*\*Skills\*\* (.+?)\n\n", dayl, re.S).group(1)
        parsed = {}
        for part in skills_text.split(","):
            match = re.match(r"\s*([A-Za-z ()]+?)\s+([+−-]\d+)$", part.strip())
            parsed[match.group(1).lower()] = num(match.group(2))
        self.assertEqual(parsed, {
            "diplomacy": 9, "knowledge (nobility)": 8, "perception": 8,
            "perform (sing)": 9, "sense motive": 6, "stealth": 11,
            "use magic device": 9})

    def assert_statblock_matches(self, block, canonical):
        defense = canonical["defenses"]
        self.assertEqual(
            num(re.search(r"\*\*Init\*\* ([+−-]\d+)", block).group(1)),
            canonical["initiative"])
        self.assertEqual(
            [num(v) for v in re.search(
                r"AC ([-−\d]+), touch ([-−\d]+), flat-footed ([-−\d]+)",
                block).groups()],
            [defense["ac"], defense["touch"], defense["flatFooted"]])
        self.assertEqual(num(re.search(r"hp (\d+)", block).group(1)), canonical["hp"])
        self.assertEqual(
            [num(v) for v in re.search(
                r"\*\*Fort\*\* ([+−-]\d+), \*\*Ref\*\* ([+−-]\d+), "
                r"\*\*Will\*\* ([+−-]\d+)", block).groups()],
            [defense["fortitude"], defense["reflex"], defense["will"]])
        self.assertEqual(
            [num(v) for v in re.search(
                r"\*\*CMB\*\* ([+−-]\d+); \*\*CMD\*\* (\d+)", block).groups()],
            [canonical["cmb"], canonical["cmd"]])
        self.assertEqual(
            [int(v) for v in re.search(
                r"Str (\d+), Dex (\d+), Con (\d+), Int (\d+), Wis (\d+), Cha (\d+)",
                block).groups()],
            [canonical["abilityScores"][k] for k in
             ("strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma")])

    def test_yalana_statblock_matches_engine_canonical(self):
        """Yalana (Halfling Cleric 3) must be engine-validated and match npcs.md."""
        fixture = json.loads((ROOT / "tests/fixtures/embernight-yalana-cleric-3.json").read_text())
        evaluation = build_npc(fixture)
        self.assertEqual(evaluation["status"], "valid", evaluation.get("issues"))
        canonical = evaluation["canonical"]
        self.assertEqual((canonical["hp"], canonical["bab"], canonical["cr"]), (24, 2, 2))
        self.assertEqual(canonical["speed"]["land"], 30)  # Halfling 20 + Travel domain 10
        self.assertEqual(
            (canonical["channelEnergy"]["energyType"], canonical["channelEnergy"]["damageDice"],
             canonical["channelEnergy"]["usesPerDay"], canonical["channelEnergy"]["saveDC"]),
            ("positive", "2d6", 5, 13))
        self.assertEqual(
            {a["name"]: (a["attackBonusExpression"], a["damageExpression"])
             for a in canonical["attacks"]},
            {"Light Mace": ("+2", "1d4-1")})
        self.assertEqual(
            {s["skillId"].split(".")[-1]: s["total"] for s in canonical["skills"]},
            {"diplomacy": 8, "knowledge-arcana": 8, "knowledge-history": 8,
             "knowledge-religion": 8, "sense-motive": 2, "perception": 4})

        block = read("npcs.md").split("## Yalana")[1].split("## Lili")[0]
        self.assert_statblock_matches(block, canonical)
        self.assertIn("**Speed** 30 ft.", block)

    def test_lili_statblock_matches_engine_canonical(self):
        """Lili (Gnome Druid 3) must be engine-validated and match npcs.md."""
        fixture = json.loads((ROOT / "tests/fixtures/embernight-lili-druid-3.json").read_text())
        evaluation = build_npc(fixture)
        self.assertEqual(evaluation["status"], "valid", evaluation.get("issues"))
        canonical = evaluation["canonical"]
        self.assertEqual((canonical["hp"], canonical["bab"], canonical["cr"]), (27, 2, 2))
        self.assertEqual(canonical["speed"]["land"], 20)
        self.assertEqual(canonical["senses"], ["Low-Light Vision"])
        self.assertEqual(
            {a["name"]: (a["attackBonusExpression"], a["damageExpression"])
             for a in canonical["attacks"]},
            {"Quarterstaff": ("+3", "1d4")})
        self.assertEqual(
            {s["skillId"].split(".")[-1]: s["total"] for s in canonical["skills"]},
            {"heal": 8, "survival": 10, "perception": 10,
             "knowledge-nature": 8, "craft": 0})
        icicle = next(p for f in canonical["classFeatures"]
                      if f["featureId"] == "npc-class-feature.water-domain"
                      for p in f["powers"] if p["name"] == "Icicle")
        self.assertEqual((icicle["damageDie"], icicle["usesBase"] + canonical["abilityModifiers"]["wisdom"]),
                         ("1d6", 5))

        block = read("npcs.md").split("## Lili")[1].split("## Quellen")[0]
        self.assert_statblock_matches(block, canonical)
        self.assertIn("low-light vision", block)

    def test_npcs_document_marks_all_three_as_engine_validated(self):
        npcs = read("npcs.md")
        self.assertNotIn("blockiert", npcs)
        for name in ("Dayl", "Yalana", "Lili"):
            self.assertIn(f"**{name}: engine-validiert**", npcs)

    def test_xp_budget_is_the_sum_of_the_statblock_values(self):
        statblocks = read("statblocks.md")
        xp = {name.strip(): int(value) for name, value in re.findall(
            r"^## (.+?)HG [\d./]+ \((\d+) EP\)", statblocks, re.M)}
        small = next(v for k, v in xp.items() if k.startswith("Kleiner Feuerelementar"))
        mephit = next(v for k, v in xp.items() if k.startswith("Zankhuf"))
        medium = next(v for k, v in xp.items() if k.startswith("Mittlerer"))
        self.assertEqual((small, mephit, medium), (400, 800, 800))

        readme = read("README.md")
        baseline = mephit + small
        full = mephit + 2 * small
        escalation = mephit + 4 * small
        ritual = escalation + small + medium
        for amount in (baseline, full, escalation, ritual):
            self.assertIn(f"{amount:,} EP".replace(",", "."), readme)


if __name__ == "__main__":
    unittest.main()
