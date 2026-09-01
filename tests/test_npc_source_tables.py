"""Independent source parsers and completeness assertions for the NPC catalog.

These tests re-parse the hash-anchored Core Rulebook spell-list extract with
their own expectations (frozen counts, line spot checks) and verify the
generated catalog against the full planned Core scope.  Nothing here invents
rules: every numeric domain without a local source must remain an explicit
catalog gap.
"""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from monster_builder.npc import evaluate_prerequisite  # noqa: E402
from monster_builder.npc_catalog import NpcCatalog, validate_npc_data  # noqa: E402
from tools.build_npc_catalog import build_catalog, serialized_catalog  # noqa: E402
from tools.parse_npc_sources import (  # noqa: E402
    EXTRACT_PATH,
    build_fragment,
    expected_membership_counts,
    parse_spell_lists,
)

NPC_PATH = ROOT / "catalog" / "npc.json"

EXPECTED_CLASS_LEVELS = {
    "bard": list(range(0, 7)),
    "cleric": list(range(0, 10)),
    "druid": list(range(0, 10)),
    "paladin": list(range(1, 5)),
    "ranger": list(range(1, 5)),
    "sorcerer": list(range(0, 10)),
    "wizard": list(range(0, 10)),
}
EXPECTED_EMPTY_SECTIONS = {("cleric", 7), ("druid", 3)}
# Frozen per-(class, level) membership counts asserted against every re-parse;
# any drift means the anchored extract or the parser changed.
EXPECTED_COUNTS = {
    ("bard", 0): 16, ("bard", 1): 26, ("bard", 2): 35, ("bard", 3): 30,
    ("bard", 4): 21, ("bard", 5): 16, ("bard", 6): 20,
    ("cleric", 0): 12, ("cleric", 1): 25, ("cleric", 2): 32, ("cleric", 3): 31,
    ("cleric", 4): 27, ("cleric", 5): 53, ("cleric", 6): 16, ("cleric", 8): 17, ("cleric", 9): 11,
    ("druid", 0): 13, ("druid", 1): 20, ("druid", 2): 26, ("druid", 4): 24,
    ("druid", 5): 34, ("druid", 6): 18, ("druid", 7): 13, ("druid", 8): 11, ("druid", 9): 10,
    ("paladin", 1): 15, ("paladin", 2): 9, ("paladin", 3): 10, ("paladin", 4): 9,
    ("ranger", 1): 19, ("ranger", 2): 12, ("ranger", 3): 13, ("ranger", 4): 7,
    ("sorcerer", 0): 23, ("sorcerer", 1): 36, ("sorcerer", 2): 68, ("sorcerer", 3): 26,
    ("sorcerer", 4): 42, ("sorcerer", 5): 47, ("sorcerer", 6): 54, ("sorcerer", 7): 33,
    ("sorcerer", 8): 27, ("sorcerer", 9): 34,
    ("wizard", 0): 23, ("wizard", 1): 36, ("wizard", 2): 68, ("wizard", 3): 26,
    ("wizard", 4): 42, ("wizard", 5): 47, ("wizard", 6): 54, ("wizard", 7): 33,
    ("wizard", 8): 27, ("wizard", 9): 34,
}
TOTAL_ROWS = 1431
TOTAL_SPELLS = 616

EXACT_IDS = {
    "races": {
        "npc-race.dwarf", "npc-race.elf", "npc-race.gnome", "npc-race.half-elf",
        "npc-race.half-orc", "npc-race.halfling", "npc-race.human",
    },
    "skills": {
        "skill.acrobatics", "skill.appraise", "skill.bluff", "skill.climb",
        "skill.craft", "skill.diplomacy", "skill.disable-device", "skill.disguise",
        "skill.escape-artist", "skill.fly", "skill.handle-animal", "skill.heal",
        "skill.intimidate", "skill.knowledge-arcana", "skill.knowledge-dungeoneering",
        "skill.knowledge-engineering", "skill.knowledge-geography", "skill.knowledge-history",
        "skill.knowledge-local", "skill.knowledge-nature", "skill.knowledge-nobility",
        "skill.knowledge-planes", "skill.knowledge-religion", "skill.linguistics",
        "skill.perception", "skill.perform", "skill.profession", "skill.ride",
        "skill.sense-motive", "skill.sleight-of-hand", "skill.spellcraft", "skill.stealth",
        "skill.survival", "skill.swim", "skill.use-magic-device",
    },
}

NPC_CLASS_IDS = {
    "npc-class.adept", "npc-class.aristocrat", "npc-class.commoner", "npc-class.expert", "npc-class.warrior",
}
PC_CLASS_IDS = {
    "npc-class.barbarian", "npc-class.bard", "npc-class.cleric", "npc-class.druid",
    "npc-class.fighter", "npc-class.monk", "npc-class.paladin", "npc-class.ranger",
    "npc-class.rogue", "npc-class.sorcerer", "npc-class.wizard",
}
ITEM_CATEGORIES = {"weapon", "armor", "shield", "goods", "magic"}


def parsed_extract():
    return parse_spell_lists(EXTRACT_PATH.read_text(encoding="utf-8"))


class SpellListSourceTests(unittest.TestCase):
    """The only locally hash-anchored numeric NPC domain: class spell lists."""

    def test_parse_covers_every_anchored_class_and_level(self):
        parsed = parse_spell_lists(EXTRACT_PATH.read_text(encoding="utf-8"))
        counts = {key: count for key, count in expected_membership_counts(parsed["rows"]).items() if count}
        self.assertEqual(counts, EXPECTED_COUNTS)
        self.assertEqual(set(parsed["emptySections"]), EXPECTED_EMPTY_SECTIONS)
        self.assertEqual(len(parsed["rows"]), TOTAL_ROWS)
        self.assertEqual(len(parsed["spells"]), TOTAL_SPELLS)

    def test_checked_in_fragment_matches_the_anchored_parse(self):
        parsed = parse_spell_lists(EXTRACT_PATH.read_text(encoding="utf-8"))
        regenerated = build_fragment(parsed)
        fragment_path = ROOT / "catalog" / "npc" / "spells.fragment.json"
        self.assertEqual(fragment_path.read_text(encoding="utf-8"), json.dumps(regenerated, ensure_ascii=False, indent=2) + "\n")

    def test_fragment_membership_rows_carry_resolving_line_provenance(self):
        lines = EXTRACT_PATH.read_text(encoding="utf-8").split("\n")
        catalog = json.loads(NPC_PATH.read_text(encoding="utf-8"))
        spells = catalog["spells"]
        # Spot checks: the spell on each cited line must match the record name
        # (a component marker may sit between the name and the colon).
        for spell_id in ("spell.dancing-lights", "spell.wish", "spell.purify-food-and-drink"):
            record = spells[spell_id]
            first = record["listMembership"][0]
            cited = lines[first["txtLines"][0] - 1].replace("\x0c", "").strip()
            self.assertTrue(cited.startswith(record["name"]), f"{spell_id}: {cited!r}")
        # Every membership row must cite a line whose text starts with the name.
        total_rows = 0
        for record in spells.values():
            self.assertEqual(record["catalogStatus"], "partial")
            for row in record["listMembership"]:
                total_rows += 1
                cited = lines[row["txtLines"][0] - 1].replace("\x0c", "").strip()
                self.assertTrue(cited.startswith(record["name"]), f"{record['id']}: {cited!r}")
                self.assertEqual(row["level"], record["levelsByClass"][row["classId"]])
        self.assertEqual(total_rows, TOTAL_ROWS)

    def test_known_spells_have_expected_membership(self):
        catalog = json.loads(NPC_PATH.read_text(encoding="utf-8"))
        self.assertEqual(catalog["spells"]["spell.wish"]["levelsByClass"], {"sorcerer": 9, "wizard": 9})
        self.assertEqual(catalog["spells"]["spell.fireball"]["levelsByClass"], {"sorcerer": 3, "wizard": 3})
        self.assertEqual(catalog["spells"]["spell.cure-light-wounds"]["levelsByClass"], {"bard": 1, "cleric": 1, "druid": 1, "paladin": 1, "ranger": 2})
        self.assertEqual(catalog["spells"]["spell.dancing-lights"]["levelsByClass"], {"bard": 0, "sorcerer": 0, "wizard": 0})
        # Ranger lists top out at 4th level in the anchored excerpt.
        ranger_levels = sorted({row["level"] for spell in catalog["spells"].values() for row in spell["listMembership"] if row["classId"] == "ranger"})
        self.assertEqual(ranger_levels, [1, 2, 3, 4])


class CatalogCompletenessTests(unittest.TestCase):
    """Row-count assertions for the full planned Core data scope."""

    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads(NPC_PATH.read_text(encoding="utf-8"))
        cls.generated = build_catalog(ROOT)
        validate_npc_data(cls.catalog, ROOT)

    def test_generated_catalog_is_stale_free_and_self_versioned(self):
        self.assertEqual(serialized_catalog(self.generated), NPC_PATH.read_bytes())
        self.assertEqual(self.catalog["catalogVersion"], self.generated["catalogVersion"])

    def test_seven_core_races_are_present_as_gaps(self):
        self.assertEqual(set(self.catalog["races"]), EXACT_IDS["races"])
        for race in self.catalog["races"].values():
            self.assertEqual(race["catalogStatus"], "gap")
            self.assertIsNone(race["abilityAdjustments"])
            self.assertIsNone(race["sizeId"])

    def test_sixteen_classes_through_level_twenty(self):
        classes = self.catalog["classes"]
        self.assertEqual(set(classes), NPC_CLASS_IDS | PC_CLASS_IDS)
        for class_id, record in classes.items():
            category = "npc" if class_id in NPC_CLASS_IDS else "pc"
            self.assertEqual(record["category"], category, class_id)
            self.assertEqual(record["catalogStatus"], "gap")
            self.assertIsNone(record["hitDie"])
            self.assertEqual(set(record["levels"]), {str(level) for level in range(1, 21)}, class_id)
            for row in record["levels"].values():
                self.assertEqual(row["catalogStatus"], "gap")
                self.assertIsNone(row["bab"])
                self.assertIsNone(row["fortitude"])
                self.assertIsNone(row["hitDie"])
                self.assertIsNone(row["featureGrants"])
                self.assertIsNone(row["choiceSlots"])
                self.assertIn("sourceRef", row)

    def test_class_feature_slot_kinds_are_catalogued(self):
        features = self.catalog["classFeatures"]
        kinds = [record["kind"] for record in features.values()]
        self.assertEqual(kinds.count("feat-slot"), 6)
        self.assertEqual(kinds.count("choice-slot"), 10)
        for record in features.values():
            self.assertEqual(record["catalogStatus"], "gap")
            refs = record["sourceRef"]
            refs = refs if isinstance(refs, list) else [refs]
            self.assertTrue(any(ref["sourceId"] == "source.npc-mode-plan" for ref in refs))

    def test_thirty_five_core_skills(self):
        self.assertEqual(set(self.catalog["skills"]), EXACT_IDS["skills"])
        for skill in self.catalog["skills"].values():
            self.assertEqual(skill["catalogStatus"], "gap")
            self.assertIsNone(skill["keyAbility"])
            self.assertIsNone(skill["armorCheckPenalty"])

    def test_core_feats_are_present_with_unknown_prerequisites_as_gaps(self):
        feats = self.catalog["feats"]
        self.assertGreaterEqual(len(feats), 140)
        for record in feats.values():
            self.assertEqual(record["catalogStatus"], "gap")
            self.assertIsNone(record["prerequisites"], record["id"])
            self.assertIsNone(record["effects"], record["id"])
        for required in ("feat.power-attack", "feat.weapon-finesse", "feat.quicken-spell", "feat.brew-potion", "feat.diehard"):
            self.assertIn(required, feats)

    def test_mundane_and_magic_equipment_inventory(self):
        items = self.catalog["items"]
        self.assertEqual(len(items), 62)
        for item in items.values():
            self.assertIn(item["category"], ITEM_CATEGORIES)
            self.assertIsNone(item["priceCp"])
        for required in ("item.greatsword", "item.full-plate", "item.buckler", "item.spellbook", "item.cloak-of-resistance", "item.potion-of-cure-light-wounds"):
            self.assertIn(required, items)

    def test_all_nine_gear_profiles_are_catalogued(self):
        budgets = self.catalog["gearBudgets"]
        self.assertEqual(
            set(budgets),
            {f"npc-gear.{progression}.{fantasy}" for progression in ("slow", "medium", "fast") for fantasy in ("low", "normal", "high")},
        )
        for record in budgets.values():
            self.assertEqual(record["catalogStatus"], "gap")
            self.assertIsNone(record["budgetCp"])
            self.assertIsNone(record["effectiveLevel"])
            for value in record["categories"].values():
                self.assertIsNone(value)

    def test_only_policy_records_are_resolved(self):
        resolved = []
        for section in ("abilityArrays", "gearBudgets", "races", "classes", "classFeatures", "skills", "feats", "items", "spells", "derivedRules"):
            for record_id, record in self.catalog[section].items():
                if record.get("catalogStatus") in {"resolved", "policy"}:
                    resolved.append((section, record_id))
        self.assertEqual(
            sorted(resolved),
            [("derivedRules", "npc-rule.money-copper"), ("derivedRules", "npc-rule.typed-prerequisites")],
        )

    def test_money_policy_stays_integer_copper_with_null_gaps(self):
        def check(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    if key.endswith("Cp"):
                        self.assertTrue(child is None or (isinstance(child, int) and not isinstance(child, bool)), key)
                    check(child)
            elif isinstance(value, list):
                for child in value:
                    check(child)

        check(self.catalog)
        rule = self.catalog["derivedRules"]["npc-rule.money-copper"]
        self.assertEqual(rule["unit"], "cp")

    def test_typed_prerequisite_examples_still_evaluate(self):
        examples = self.catalog["derivedRules"]["npc-rule.typed-prerequisites"]["examples"]
        self.assertIs(evaluate_prerequisite(examples[0], ability_scores={"strength": 14}, bab=1), True)
        self.assertIs(evaluate_prerequisite(examples[0], ability_scores={"strength": 12}, bab=1), False)
        self.assertIs(evaluate_prerequisite(examples[1], feats={"feat.point-blank-shot"}), True)
        self.assertIs(evaluate_prerequisite(examples[1], feats=set()), False)
        self.assertIsNone(evaluate_prerequisite(examples[1]))


if __name__ == "__main__":
    unittest.main()