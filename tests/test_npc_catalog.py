import copy
import hashlib
import json
import unittest
from pathlib import Path

from monster_builder import Catalog
from monster_builder.catalog import CatalogError, CatalogRegistry
from monster_builder.npc_catalog import NpcCatalog, catalog_fingerprint, validate_npc_data
from tools.build_npc_catalog import build_catalog, serialized_catalog, validate_source_manifest
from tools.extract_npc_aon_sources import OUTPUT as AON_OUTPUT, RAW as AON_RAW, SOURCES as AON_SOURCES, extract as extract_aon


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

    def test_phase_one_inventory_is_bounded_by_declared_source_gaps(self):
        catalog = NpcCatalog.load().data
        self.assertEqual(set(catalog["abilityArrays"]), {"npc-ability-array.basic", "npc-ability-array.heroic"})
        self.assertIsNone(catalog["abilityArrays"]["npc-ability-array.basic"]["scores"])
        self.assertEqual(catalog["abilityArrays"]["npc-ability-array.basic"]["gapCode"], "core-rulebook-ability-arrays")

        human = catalog["races"]["npc-race.human"]
        self.assertEqual(human["catalogStatus"], "gap")
        self.assertIsNone(human["abilityAdjustments"])

        warrior = catalog["classes"]["npc-class.warrior"]
        self.assertEqual(set(warrior["levels"]), {str(level) for level in range(1, 21)})
        self.assertTrue(all(row["catalogStatus"] == "gap" for row in warrior["levels"].values()))
        self.assertTrue(all(row["sourceRef"]["sourceId"] == "source.npc-gap-matrix" for row in warrior["levels"].values()))

        self.assertIn("skill.perception", catalog["skills"])
        self.assertIn("skill.handle-animal", catalog["skills"])
        self.assertTrue(all(item["catalogStatus"] == "gap" for item in catalog["skills"].values()))
        self.assertIn("feat.toughness", catalog["feats"])
        self.assertTrue(all(item["category"] == "general" for item in catalog["feats"].values()))
        self.assertIn("item.longsword", catalog["items"])
        self.assertIn("item.chain-shirt", catalog["items"])
        self.assertIsNone(catalog["items"]["item.longsword"]["priceCp"])
        self.assertEqual(catalog["gearBudgets"]["npc-gear.medium.normal"]["progression"], "medium")
        self.assertEqual(catalog["gearBudgets"]["npc-gear.medium.normal"]["fantasyLevel"], "normal")

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
                extract_aon(AON_RAW / f"{name}.html", attribute, value),
                (AON_OUTPUT / f"{name}.txt").read_text(encoding="utf-8"),
            )
        creating_npcs = (AON_OUTPUT / "creating-npcs.txt").read_text(encoding="utf-8")
        self.assertIn("1\t—\t260 gp\t50 gp\t130 gp\t—\t40 gp\t40 gp", creating_npcs)
        self.assertIn("Kiramor, The Forest Shadow", creating_npcs)
        self.assertIn("5th\t+5\t+4\t+1\t+1", (AON_OUTPUT / "npc-classes.txt").read_text(encoding="utf-8"))

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
