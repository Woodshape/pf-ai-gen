"""Consistency checks for the Embernight encounter documents.

The docs are the deliverable here, so the test checks that the numbers in them
actually add up: room areas vs. the ASCII grid, and the stated XP budget vs.
the statblock XP values.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENCOUNTER = ROOT / "docs/encounters/embernight"


def read(name):
    return (ENCOUNTER / name).read_text()


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
