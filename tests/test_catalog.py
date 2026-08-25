import unittest

from monster_builder import Catalog


class CatalogTests(unittest.TestCase):
    def test_versioned_catalog_has_source_backed_spell_inventory(self):
        catalog = Catalog.load()
        spells = catalog.data["spells"].values()
        self.assertEqual(catalog.version, "catalog-1")
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
        for spell in catalog.data["spells"].values():
            self.assertEqual(spell["highest"], max(spell["levelsByClass"].values()))
            self.assertTrue(spell["sourceRef"])


if __name__ == "__main__":
    unittest.main()
