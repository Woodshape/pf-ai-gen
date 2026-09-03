import copy
import hashlib
import json
import unittest
from pathlib import Path

from monster_builder import Catalog
from monster_builder.catalog import CatalogError, CatalogRegistry
from monster_builder.npc_catalog import NpcCatalog, catalog_fingerprint, validate_npc_data
from tools.build_npc_catalog import build_catalog, serialized_catalog, validate_source_manifest
from tools.extract_npc_aon_sources import OUTPUT as AON_OUTPUT, RAW as AON_RAW, SOURCES as AON_SOURCES, extract_source as extract_aon


ROOT = Path(__file__).parents[1]
NPC_PATH = ROOT / "catalog" / "npc.json"
NPC_SCHEMA_PATH = ROOT / "catalog" / "npc.schema.json"
SIMPLE_CATALOG_PATH = ROOT / "catalog" / "catalog.json"


class NpcCatalogTests(unittest.TestCase):
    def test_generated_catalog_is_deterministic_and_self_versioned(self):
        generated = build_catalog(ROOT)
        self.assertEqual(generated["catalogVersion"], catalog_fingerprint(generated))
        self.assertEqual(serialized_catalog(generated), NPC_PATH.read_bytes())
        self.assertEqual(NpcCatalog.load().version, generated["catalogVersion"])

    def test_schema_is_draft_2020_12_and_requires_independent_sections(self):
        schema = json.loads(NPC_SCHEMA_PATH.read_text(encoding="utf-8"))
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(schema["$id"], "https://pf-ai-gen.local/npc.schema.json")
        self.assertEqual(schema["properties"]["catalogVersion"]["pattern"], "^sha256:[0-9a-f]{64}$")
        self.assertEqual(
            set(schema["required"]),
            {
                "schemaVersion", "catalogVersion", "catalogStatus", "sources",
                "abilityArrays", "gearBudgets", "races", "classes", "classFeatures",
                "skills", "feats", "items", "spells", "derivedRules",
            },
        )

    def test_production_catalog_keeps_the_human_warrior_slice_resolved(self):
        catalog = NpcCatalog.load().data
        basic = catalog["abilityArrays"]["npc-ability-array.basic"]
        self.assertEqual(basic["scores"], [13, 12, 11, 10, 9, 8])
        self.assertEqual(basic["presets"]["melee"]["strength"], 13)
        self.assertEqual(catalog["abilityArrays"]["npc-ability-array.heroic"]["catalogStatus"], "resolved")

        human = catalog["races"]["npc-race.human"]
        self.assertEqual(human["catalogStatus"], "resolved")
        self.assertEqual(human["speed"], {"land": 30})
        self.assertTrue(all(race["catalogStatus"] == "gap" for race_id, race in catalog["races"].items() if race_id not in {"npc-race.human", "npc-race.goblin"}))

        warrior = catalog["classes"]["npc-class.warrior"]
        self.assertEqual(set(warrior["levels"]), {str(level) for level in range(1, 21)})
        self.assertTrue(all(warrior["levels"][str(level)]["catalogStatus"] == "resolved" for level in range(1, 6)))
        self.assertTrue(all(warrior["levels"][str(level)]["catalogStatus"] == "gap" for level in range(6, 21)))
        self.assertEqual(warrior["levels"]["5"]["bab"], 5)

        self.assertEqual(catalog["skills"]["skill.climb"]["keyAbility"], "strength")
        self.assertEqual(catalog["skills"]["skill.intimidate"]["keyAbility"], "charisma")
        self.assertEqual(catalog["feats"]["feat.improved-initiative"]["effects"], {"initiative": 4})
        self.assertEqual(catalog["items"]["item.longsword"]["priceCp"], 1500)
        self.assertEqual(catalog["items"]["item.chain-shirt"]["effects"]["armorBonus"], 4)
        budget = catalog["gearBudgets"]["npc-gear.medium.normal"]
        self.assertEqual([row["budgetCp"] for row in budget["rows"] if row["npcCategory"] == "basic"], [26000, 39000, 78000, 165000, 240000])

    def test_goblin_sorcerer_levels_five_and_six_catalog_slice_is_resolved(self):
        catalog = NpcCatalog.load().data
        heroic = catalog["abilityArrays"]["npc-ability-array.heroic"]
        self.assertEqual(heroic["scores"], [15, 14, 13, 12, 10, 8])
        self.assertEqual(heroic["presets"]["arcane"], {
            "strength": 8, "dexterity": 14, "constitution": 12,
            "intelligence": 13, "wisdom": 10, "charisma": 15,
        })
        goblin = catalog["races"]["npc-race.goblin"]
        self.assertEqual(goblin["abilityAdjustments"], {"strength": -2, "dexterity": 4, "charisma": -2})
        self.assertEqual(goblin["sizeId"], "size.small")
        self.assertEqual(goblin["skillBonuses"], {"skill.ride": 4, "skill.stealth": 4})

        sorcerer = catalog["classes"]["npc-class.sorcerer"]
        self.assertTrue(all(sorcerer["levels"][str(level)]["catalogStatus"] == "resolved" for level in range(1, 7)))
        self.assertEqual(sorcerer["levels"]["5"]["bab"], 2)
        self.assertEqual(sorcerer["levels"]["5"]["spellsPerDay"], {"1": 6, "2": 4})
        self.assertEqual(sorcerer["levels"]["5"]["spellsKnown"], {"0": 6, "1": 4, "2": 2})
        self.assertEqual(sorcerer["levels"]["6"]["spellsKnown"], {"0": 7, "1": 4, "2": 2, "3": 1})
        self.assertEqual(catalog["classFeatures"]["npc-class-feature.sorcerer-bloodlines"]["catalogStatus"], "resolved")

        for spell_id in ("burning-hands", "flaming-sphere", "scorching-ray", "fireball", "flare"):
            self.assertEqual(catalog["spells"][f"spell.{spell_id}"]["catalogStatus"], "resolved")
        self.assertEqual(catalog["items"]["item.wand-of-burning-hands"]["priceCp"], 75000)
        self.assertEqual(catalog["items"]["item.wand-of-burning-hands"]["npcGearCategory"], "weapons")
        self.assertEqual(catalog["items"]["item.cloak-of-resistance-1"]["priceCp"], 100000)
        self.assertEqual(catalog["items"]["item.cloak-of-resistance-1"]["npcGearCategory"], "protection")
        heroic_five = next(row for row in catalog["gearBudgets"]["npc-gear.medium.normal"]["rows"] if row["npcCategory"] == "heroic" and row["level"] == 5)
        self.assertEqual(heroic_five["budgetCp"], 345000)
        self.assertEqual(catalog["derivedRules"]["npc-rule.classed-npc-cr"]["pcClassAdjustment"], -1)

    def test_goblin_druid_level_three_fire_catalog_slice_is_resolved(self):
        catalog = NpcCatalog.load().data
        heroic = catalog["abilityArrays"]["npc-ability-array.heroic"]
        self.assertEqual(heroic["presets"]["divine"], {
            "strength": 12, "dexterity": 8, "constitution": 14,
            "intelligence": 10, "wisdom": 15, "charisma": 13,
        })

        druid = catalog["classes"]["npc-class.druid"]
        self.assertEqual(druid["catalogStatus"], "resolved")
        self.assertEqual(druid["hitDie"], "d8")
        self.assertEqual(druid["skillSelections"], 4)
        self.assertEqual(druid["castingAbility"], "wisdom")
        self.assertEqual(druid["castingMode"], "prepared")
        self.assertEqual(druid["supportedLevels"], [3])
        self.assertEqual(druid["levels"]["3"]["catalogStatus"], "resolved")
        self.assertEqual(druid["levels"]["3"]["bab"], 2)
        self.assertEqual(druid["levels"]["3"]["spellsPerDay"], {"0": 4, "1": 2, "2": 1})
        self.assertTrue(all(druid["levels"][str(level)]["catalogStatus"] == "gap" for level in range(1, 21) if level != 3))
        self.assertIn("npc-class-feature.druidic", druid["levels"]["3"]["featureGrants"])

        nature_bond = catalog["classFeatures"]["npc-class-feature.druid-nature-bond"]
        self.assertEqual(nature_bond["allowedValues"], ["fire-domain"])
        self.assertEqual(nature_bond["options"]["fire-domain"]["featureId"], "npc-class-feature.fire-domain")
        fire = catalog["classFeatures"]["npc-class-feature.fire-domain"]
        self.assertEqual(fire["slotsPerSpellLevel"], 1)
        self.assertEqual(fire["domainSpells"], {"1": "spell.burning-hands", "2": "spell.produce-flame"})
        self.assertEqual(fire["powers"][0]["damageDie"], "1d6")
        self.assertEqual(fire["powers"][0]["damageBonusPerTwoLevels"], 1)
        self.assertEqual(fire["powers"][0]["usesBase"], 3)
        self.assertEqual(fire["powers"][0]["usesAbility"], "wisdom")
        self.assertEqual(catalog["classFeatures"]["npc-class-feature.druid-spellcasting"]["effects"]["castingMode"], "prepared")
        self.assertEqual(
            catalog["classFeatures"]["npc-class-feature.druid-spellcasting"]["effects"]["spontaneousConversion"]["spellIdsBySlotLevel"],
            {"1": ["spell.summon-nature-s-ally-i"], "2": ["spell.summon-nature-s-ally-i", "spell.summon-nature-s-ally-ii"]},
        )
        proficiencies = catalog["classFeatures"]["npc-class-feature.druid-proficiencies"]
        self.assertEqual(proficiencies["catalogStatus"], "resolved")
        self.assertIn("sickle", proficiencies["effects"]["weaponProficiencies"])
        self.assertEqual(proficiencies["effects"]["armorProficiencies"], ["light", "medium"])
        self.assertIn(
            "npc-class-feature.druid-proficiencies",
            catalog["classes"]["npc-class.druid"]["levels"]["3"]["featureGrants"],
        )
        orisons = catalog["classFeatures"]["npc-class-feature.druid-orisons"]
        self.assertEqual(orisons["catalogStatus"], "resolved")
        self.assertEqual(orisons["effects"], {"notExpendedWhenCast": True, "mayBePreparedMultipleTimes": True})
        self.assertEqual(catalog["skills"]["skill.perception"]["catalogStatus"], "resolved")
        self.assertEqual(catalog["skills"]["skill.perception"]["keyAbility"], "wisdom")
        self.assertEqual(catalog["items"]["item.sickle"]["weightLbBySize"], {"small": 1, "medium": 2})
        self.assertEqual(catalog["items"]["item.leather-armor"]["weightLbBySize"], {"small": 7.5, "medium": 15})
        self.assertEqual(catalog["items"]["item.heavy-wooden-shield"]["weightLbBySize"], {"small": 5, "medium": 10})

        for spell_id in (
            "barkskin", "cure-light-wounds", "entangle", "produce-flame",
            "summon-nature-s-ally-i", "summon-nature-s-ally-ii",
        ):
            self.assertEqual(catalog["spells"][f"spell.{spell_id}"]["catalogStatus"], "resolved")
        self.assertEqual(catalog["spells"]["spell.barkskin"]["levelsByClass"]["druid"], 2)
        self.assertEqual(catalog["spells"]["spell.summon-nature-s-ally-ii"]["levelsByClass"]["druid"], 2)

        self.assertEqual(catalog["skills"]["skill.heal"]["catalogStatus"], "resolved")
        self.assertEqual(catalog["skills"]["skill.knowledge-nature"]["catalogStatus"], "resolved")
        self.assertEqual(catalog["skills"]["skill.survival"]["catalogStatus"], "resolved")
        self.assertEqual(catalog["items"]["item.sickle"]["priceCp"], 600)
        self.assertEqual(catalog["items"]["item.leather-armor"]["effects"]["armorBonus"], 2)
        self.assertEqual(catalog["items"]["item.heavy-wooden-shield"]["effects"]["shieldBonus"], 2)
        heroic_three = next(
            row for row in catalog["gearBudgets"]["npc-gear.medium.normal"]["rows"]
            if row["npcCategory"] == "heroic" and row["level"] == 3
        )
        self.assertEqual(heroic_three["budgetCp"], 165000)
        self.assertEqual(heroic_three["categories"], {
            "weapons": 65000, "protection": 80000, "magic": 0,
            "limitedUse": 10000, "gear": 20000,
        })

    def test_money_is_integer_copper_and_prerequisite_examples_are_typed(self):
        catalog = NpcCatalog.load().data

        def check_money(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    if key.endswith("Cp"):
                        self.assertTrue(child is None or (isinstance(child, int) and not isinstance(child, bool)), key)
                    check_money(child)
            elif isinstance(value, list):
                for child in value:
                    check_money(child)

        check_money(catalog)
        examples = catalog["derivedRules"]["npc-rule.typed-prerequisites"]["examples"]
        self.assertEqual(examples[0], {"all": [{"abilityAtLeast": {"strength": 13}}, {"babAtLeast": 1}]})
        self.assertEqual(examples[1], {"hasFeat": "feat.point-blank-shot"})

    def test_every_record_and_nested_class_level_has_hash_anchored_provenance(self):
        catalog = NpcCatalog.load().data
        source_ids = set(catalog["sources"])

        def refs(value):
            if isinstance(value, dict):
                if "sourceRef" in value:
                    raw = value["sourceRef"]
                    for ref in raw if isinstance(raw, list) else [raw]:
                        self.assertIn(ref["sourceId"], source_ids)
                        self.assertEqual(ref["file"], catalog["sources"][ref["sourceId"]]["file"])
                        self.assertEqual(ref["sha256"], catalog["sources"][ref["sourceId"]]["sha256"])
                        self.assertIn("section", ref)
                        self.assertIn("txtLines", ref)
                for child in value.values():
                    refs(child)
            elif isinstance(value, list):
                for child in value:
                    refs(child)

        for section in ("abilityArrays", "gearBudgets", "races", "classes", "classFeatures", "skills", "feats", "items", "spells", "derivedRules"):
            for record in catalog[section].values():
                self.assertIn("sourceRef", record)
                refs(record)

    def test_source_manifest_and_catalog_source_hashes_are_checked(self):
        validate_source_manifest(ROOT)
        catalog = copy.deepcopy(NpcCatalog.load().data)
        source_id = "source.npc-gap-matrix"
        catalog["sources"][source_id]["sha256"] = "0" * 64
        with self.assertRaises(CatalogError):
            validate_npc_data(catalog, ROOT, check_version=False)

    def test_archived_aon_extracts_are_deterministic_and_keep_rule_tables(self):
        for name, (attribute, value) in AON_SOURCES.items():
            self.assertEqual(
                extract_aon(name, AON_RAW / f"{name}.html", attribute, value),
                (AON_OUTPUT / f"{name}.txt").read_text(encoding="utf-8"),
            )
        creating_npcs = (AON_OUTPUT / "creating-npcs.txt").read_text(encoding="utf-8")
        self.assertIn("1\t—\t260 gp\t50 gp\t130 gp\t—\t40 gp\t40 gp", creating_npcs)
        self.assertIn("Kiramor, The Forest Shadow", creating_npcs)
        self.assertIn("5th\t+5\t+4\t+1\t+1", (AON_OUTPUT / "npc-classes.txt").read_text(encoding="utf-8"))

    def test_current_aon_sources_gate_the_goblin_sorcerer_slice(self):
        expected = {
            "goblin-race": "+4 Dexterity, –2 Strength, –2 Charisma",
            "sorcerer": "5th\t+2\t+1\t+1\t+4\tBloodline spell\t6\t4",
            "elemental-bloodline": "Elemental Ray",
            "wands": "level of the spell × the creator's caster level × 750 gp",
            "spell-burning-hands": "1d4 points of fire damage per caster level",
            "spell-scorching-ray": "4d6 points of fire damage",
            "spell-fireball": "1d6 points of fire damage per caster level",
            "designing-encounters": "CR equal to its class levels –1",
            "spell-grease": "10-ft. square",
            "cloak-of-resistance": "+1 to +5 resistance bonus on all saving throws",
        }
        for name, text in expected.items():
            self.assertIn(text, (AON_OUTPUT / f"{name}.txt").read_text(encoding="utf-8"))

    def test_catalog_loader_is_lazy_and_registry_does_not_touch_simple_catalog(self):
        calls = []
        registry = CatalogRegistry(Catalog.load(), loaders={"npc": lambda: calls.append("npc") or NpcCatalog.load()})
        self.assertEqual(calls, [])
        loaded = registry.for_system("npc")
        self.assertIsInstance(loaded, NpcCatalog)
        self.assertEqual(calls, ["npc"])
        self.assertIs(registry.for_system("npc"), loaded)
        self.assertEqual(calls, ["npc"])

    def test_build_pipeline_does_not_modify_simple_catalog(self):
        before = SIMPLE_CATALOG_PATH.read_bytes()
        before_hash = hashlib.sha256(before).hexdigest()
        build_catalog(ROOT)
        self.assertEqual(SIMPLE_CATALOG_PATH.read_bytes(), before)
        self.assertEqual(hashlib.sha256(SIMPLE_CATALOG_PATH.read_bytes()).hexdigest(), before_hash)

    def test_npc_resolve_id_supports_canonical_and_short_prefixes(self):
        catalog = NpcCatalog.load()
        self.assertEqual(catalog.resolve_id("race", "npc-race.human")[0], "npc-race.human")
        self.assertEqual(catalog.resolve_id("race", "human")[0], "npc-race.human")
        self.assertEqual(catalog.resolve_id("class", "warrior")[0], "npc-class.warrior")
        self.assertEqual(catalog.resolve_id("item", "longsword")[0], "item.longsword")
        self.assertEqual(catalog.resolve_id("race", "elf")[0], "npc-race.elf")
        with self.assertRaises(CatalogError):
            catalog.resolve_id("race", "kobold")


if __name__ == "__main__":
    unittest.main()
