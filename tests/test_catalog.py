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

    def test_all_subtype_and_template_grafts_are_catalogued(self):
        grafts = Catalog.load().data["grafts"]
        self.assertEqual(len(grafts["classGrafts"]), 19)
        self.assertEqual(len(grafts["subtypes"]), 41)
        self.assertEqual(len(grafts["templates"]), 10)
        self.assertIn("graft.subtype.clockwork", grafts["subtypes"])
        self.assertIn("graft.template.zombie", grafts["templates"])
        self.assertEqual(grafts["subtypes"]["graft.subtype.human"]["optionSlots"], [{"category": "combat/social", "count": 1}])
        self.assertEqual(grafts["subtypes"]["graft.subtype.dwarf"]["conditionalSaveBonuses"][0]["bonus"], 2)
        self.assertEqual(grafts["classGrafts"]["graft.class.alchemist"]["requiredSpellListId"], "spell-list.alchemy")
        self.assertEqual(grafts["classGrafts"]["graft.class.monk"]["unarmedDamage"], "1d6")
        self.assertEqual(grafts["templates"]["graft.template.half-celestial"]["conditionalSaveBonuses"], [{"bonus": 4, "against": ["poison"]}])
        paladin_smite = next(grant for grant in grafts["classGrafts"]["graft.class.paladin"]["optionGrants"] if grant["optionId"] == "option.smite")
        self.assertEqual(paladin_smite["parameters"], {"alignment": "evil"})
        monk_cr3 = next(entry for entry in grafts["classGrafts"]["graft.class.monk"]["crEntries"] if entry["minCR"] == 3)
        self.assertEqual(next(grant for grant in monk_cr3["optionGrants"] if grant["optionId"] == "option.bypass-dr")["parameters"], {"bypass": ["magic"]})
        vampire_at_will = next(grant for grant in grafts["templates"]["graft.template.vampire"]["optionGrants"] if grant["optionId"] == "option.at-will-magic")
        self.assertEqual(vampire_at_will["parameters"], {"spellId": "spell.core.dominate-person", "maxSpellLevel": 5})
        druid_cr5 = next(entry for entry in grafts["classGrafts"]["graft.class.druid"]["crEntries"] if entry["minCR"] == 5)
        self.assertEqual(next(grant for grant in druid_cr5["optionGrants"] if grant["optionId"] == "option.change-shape")["parameters"]["forms"], ["Tiny animal", "Small animal", "Medium animal", "Large animal", "Small elemental"])
        psychopomp_dr = next(grant for grant in grafts["subtypes"]["graft.subtype.psychopomp"]["optionGrants"] if grant["optionId"] == "option.damage-reduction")
        self.assertEqual((psychopomp_dr["value"], psychopomp_dr["parameters"]), (5, {"bypass": ["adamantine"]}))
        graveknight = grafts["templates"]["graft.template.graveknight"]
        graveknight_immunity = next(grant for grant in graveknight["optionGrants"] if grant["optionId"] == "option.immunity")
        self.assertEqual(graveknight_immunity["parameters"], {"immunities": ["cold", "electricity"]})
        for template_id in ("graft.template.half-celestial", "graft.template.half-fiend"):
            reduction = next(grant for grant in grafts["templates"][template_id]["optionGrants"] if grant["optionId"] == "option.damage-reduction")
            self.assertEqual((reduction["value"], reduction["parameters"], reduction["valueByCR"]), (5, {"bypass": ["magic"]}, [{"minCR": 12, "value": 10}]))
        for subtype, bypass in (("asura", "good"), ("inevitable", "chaotic")):
            regeneration = next(grant for grant in grafts["subtypes"][f"graft.subtype.{subtype}"]["optionGrants"] if grant["optionId"] == "option.regeneration")
            self.assertEqual(regeneration["parameters"], {"bypass": [bypass]})
        sense_subtypes = {
            "devil", "div", "dwarf", "earth", "elf", "giant", "gnome", "half-elf",
            "half-orc", "inevitable", "nightshade", "orc", "protean", "psychopomp",
        }
        self.assertTrue(all(grafts["subtypes"][f"graft.subtype.{name}"].get("senses") for name in sense_subtypes))
        self.assertTrue(all(graft.get("ruleText") for group in ("subtypes", "templates") for graft in grafts[group].values()))

    def test_all_step7_table_options_are_catalogued(self):
        options = Catalog.load().data["options"]
        self.assertGreaterEqual(len(options), 162)
        self.assertTrue({
            "option.ability-damage", "option.challenge", "option.breath-weapon",
            "option.accuracy", "option.damage-reduction", "option.magic-attack",
            "option.combat-casting", "option.inspire-courage", "option.alertness",
            "option.save-boost", "option.secondary-magic", "option.summon-allies",
        } <= set(options))
        self.assertTrue(all(option.get("ruleText") for option in options.values()))

    def test_versioned_catalog_has_source_backed_spell_inventory(self):
        catalog = Catalog.load()
        spells = catalog.data["spells"].values()
        self.assertRegex(catalog.version, r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(sum(spell["sourceBook"] in {"APG", "UM", "UC"} for spell in spells), 39)
        self.assertEqual(sum(spell["sourceBook"] == "ACG" for spell in spells), 5)
        self.assertIn("spell.apg.lead-blades", catalog.data["spells"])
        self.assertIn("spell.acg.heart-of-the-metal", catalog.data["spells"])
        non_core = [spell for spell in catalog.data["spells"].values() if spell["sourceBook"] != "CORE"]
        self.assertTrue(all(spell["catalogStatus"] == "resolved" for spell in non_core))
        for spell in non_core:
            local_ref = next(ref for ref in spell["sourceRef"] if ref["sourceId"] != "pathfinder-unchained-txt")
            self.assertEqual(local_ref["provenanceStatus"], "local-source")
            self.assertTrue(local_ref["file"] and local_ref["sha256"])
            self.assertTrue((Path(__file__).parents[1] / local_ref["file"]).is_file())
        self.assertTrue(all(
            rule["sourceRef"][0]["provenanceStatus"] == "local-source"
            for rule in catalog.data["metamagicRules"].values()
        ))
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
