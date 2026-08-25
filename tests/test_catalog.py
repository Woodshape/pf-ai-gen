import unittest

from monster_builder import Catalog


class CatalogTests(unittest.TestCase):
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
