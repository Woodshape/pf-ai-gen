import unittest
from pathlib import Path

from monster_builder import Catalog


class CatalogTests(unittest.TestCase):
    def test_graft_provenance_uses_physical_txt_line_numbers(self):
        catalog = Catalog.load().data
        lines = (Path(__file__).parents[1] / "Pathfinder Unchained.txt").read_text().split("\n")
        refs = {
            "Druid": catalog["grafts"]["classGrafts"]["graft.class.druid"]["sourceRef"],
            "Goblinoid:": catalog["grafts"]["subtypes"]["graft.subtype.goblinoid"]["sourceRef"],
            "Shapechanger:": catalog["grafts"]["subtypes"]["graft.subtype.shapechanger"]["sourceRef"],
            "LYCANTHROPE": catalog["grafts"]["templates"]["graft.template.lycanthrope"]["sourceRef"],
            "Curse of Lycanthropy:": catalog["options"]["option.curse-of-lycanthropy"]["sourceRef"],
        }
        for text, source_ref in refs.items():
            source_ref = source_ref[0] if isinstance(source_ref, list) else source_ref
            start, end = source_ref["txtLines"]
            self.assertIn(text, "\n".join(lines[start - 1:end]))

    def test_versioned_catalog_has_source_backed_spell_inventory(self):
        catalog = Catalog.load()
        spells = catalog.data["spells"].values()
        self.assertRegex(catalog.version, r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(sum(spell["sourceBook"] in {"APG", "UM", "UC"} for spell in spells), 39)
        self.assertEqual(sum(spell["sourceBook"] == "ACG" for spell in spells), 5)
        self.assertIn("spell.apg.lead-blades", catalog.data["spells"])
        self.assertIn("spell.acg.heart-of-the-metal", catalog.data["spells"])
        self.assertEqual(catalog.data["spells"]["spell.apg.lead-blades"]["catalogStatus"], "external-source-not-vendored")
        natural = catalog.data["arrays"]["combatant"]["attackStatistics"]["2"]["natural"]
        self.assertEqual(natural["two"]["entries"], [{"count": 2, "attackBonuses": [2], "averageDamage": 6}])
        self.assertEqual(natural["three"]["entries"], [
            {"count": 1, "attackBonuses": [2], "averageDamage": 6},
            {"count": 2, "attackBonuses": [-3], "averageDamage": 4},
        ])
        self.assertEqual(catalog.data["damage"]["99-101"]["expressions"]["d6"], "1d6+97")
        self.assertEqual(len(catalog.data["spellLists"]), 60)
        self.assertEqual(sum(bool(spell_list["benefit"]["effects"]) for spell_list in catalog.data["spellLists"].values()), 51)
        self.assertEqual(set(catalog.data["options"]) & {"option.pounce", "option.rake"}, {"option.pounce", "option.rake"})
        for spell_list in catalog.data["spellLists"].values():
            self.assertEqual(set(spell_list["bands"]), {"0–3", "4–7", "8–11", "12–15", "16+"})
            self.assertTrue(spell_list["benefit"]["text"])
            for band in spell_list["bands"].values():
                self.assertTrue(band["primary"])
                self.assertTrue(band["secondary"])
        for spell in catalog.data["spells"].values():
            self.assertEqual(spell["highest"], max(spell["levelsByClass"].values()))
            self.assertTrue(spell["sourceRef"])


if __name__ == "__main__":
    unittest.main()
