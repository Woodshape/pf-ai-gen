"""Independent source parsers and completeness assertions for the NPC catalog.

These tests re-parse hash-anchored source extracts with independent literals
and verify the generated catalog against the planned Core scope. Nothing here
invents rules: domains outside the human warrior levels 1–5, goblin Sorcerer
levels 5–6, and goblin Druid level 3 with Fire remain explicit catalog gaps.
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
        "npc-race.half-orc", "npc-race.halfling", "npc-race.human", "npc-race.goblin",
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
RESOLVED_SPELLS = {
    "spell.acid-splash", "spell.detect-magic", "spell.light", "spell.mage-hand",
    "spell.prestidigitation", "spell.read-magic", "spell.burning-hands", "spell.grease",
    "spell.mage-armor", "spell.magic-missile", "spell.shield", "spell.flaming-sphere",
    "spell.mirror-image", "spell.scorching-ray", "spell.fireball", "spell.flare",
    "spell.barkskin", "spell.cure-light-wounds", "spell.entangle", "spell.produce-flame",
    "spell.summon-nature-s-ally-i", "spell.summon-nature-s-ally-ii", "spell.charm-person", "spell.sleep",
    "spell.silent-image", "spell.feather-fall", "spell.dancing-lights", "spell.message",
}


def parsed_extract():
    return parse_spell_lists(EXTRACT_PATH.read_text(encoding="utf-8"))


class SpellListSourceTests(unittest.TestCase):
    """Independent checks for the hash-anchored class spell lists."""

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
        fragment = json.loads((ROOT / "catalog" / "npc" / "spells.fragment.json").read_text(encoding="utf-8"))
        generated_by_id = {record["id"]: record for record in regenerated["records"]}
        for index, record in enumerate(fragment["records"]):
            if record["id"] in RESOLVED_SPELLS:
                fragment["records"][index] = generated_by_id[record["id"]]
        self.assertEqual(fragment, regenerated)

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
            self.assertEqual(record["catalogStatus"], "resolved" if record["id"] in RESOLVED_SPELLS else "partial")
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

    def test_races_keep_only_the_two_production_selections_resolved(self):
        self.assertEqual(set(self.catalog["races"]), EXACT_IDS["races"])
        human = self.catalog["races"]["npc-race.human"]
        self.assertEqual(human["catalogStatus"], "resolved")
        self.assertEqual(human["sizeId"], "size.medium")
        self.assertEqual(self.catalog["races"]["npc-race.goblin"]["catalogStatus"], "resolved")
        halfling = self.catalog["races"]["npc-race.halfling"]
        self.assertEqual(halfling["catalogStatus"], "resolved")
        self.assertEqual(halfling["abilityAdjustments"], {"strength": -2, "dexterity": 2, "charisma": 2})
        self.assertEqual((halfling["sizeId"], halfling["speed"]), ("size.small", {"land": 20}))
        self.assertEqual(halfling["saveBonuses"], {"fortitude": 1, "reflex": 1, "will": 1})
        self.assertEqual(halfling["skillBonuses"], {"skill.perception": 2, "skill.acrobatics": 2, "skill.climb": 2, "skill.stealth": 4})
        elf = self.catalog["races"]["npc-race.elf"]
        self.assertEqual(elf["catalogStatus"], "resolved")
        self.assertEqual(elf["abilityAdjustments"], {"dexterity": 2, "intelligence": 2, "constitution": -2})
        self.assertEqual((elf["sizeId"], elf["speed"]), ("size.medium", {"land": 30}))
        self.assertEqual(elf["senses"], ["Low-Light Vision"])
        self.assertEqual(elf["skillBonuses"], {"skill.perception": 2})
        # The +2 bonus against enchantment is conditional and stays in the Elven
        # Immunities trait text; no unconditional saveBonuses may appear.
        self.assertNotIn("saveBonuses", elf)
        self.assertEqual(elf["languages"], ["Common", "Elven"])
        self.assertEqual(elf["bonusLanguages"], ["Celestial", "Draconic", "Gnoll", "Gnome", "Goblin", "Orc", "Sylvan"])
        for race_id, race in self.catalog["races"].items():
            if race_id not in {"npc-race.human", "npc-race.goblin", "npc-race.halfling", "npc-race.elf"}:
                self.assertEqual(race["catalogStatus"], "gap")

    def test_sixteen_classes_keep_only_production_levels_resolved(self):
        classes = self.catalog["classes"]
        self.assertEqual(set(classes), NPC_CLASS_IDS | PC_CLASS_IDS)
        for class_id, record in classes.items():
            self.assertEqual(record["category"], "npc" if class_id in NPC_CLASS_IDS else "pc", class_id)
            self.assertEqual(set(record["levels"]), {str(level) for level in range(1, 21)}, class_id)
            if class_id in {"npc-class.warrior", "npc-class.sorcerer"}:
                self.assertEqual(record["catalogStatus"], "resolved")
                for level in range(1, 21):
                    maximum = 6 if class_id == "npc-class.sorcerer" else 5
                    expected = "resolved" if level <= maximum else "gap"
                    self.assertEqual(record["levels"][str(level)]["catalogStatus"], expected)
            elif class_id == "npc-class.druid":
                self.assertEqual(record["catalogStatus"], "resolved")
                self.assertEqual(record["hitDie"], "d8")
                self.assertEqual(record["skillSelections"], 4)
                self.assertEqual(record["castingAbility"], "wisdom")
                self.assertEqual(record["castingMode"], "prepared")
                self.assertEqual(record["supportedLevels"], [3])
                self.assertEqual(record["levels"]["3"]["catalogStatus"], "resolved")
                self.assertEqual(record["levels"]["3"]["spellsPerDay"], {"0": 4, "1": 2, "2": 1})
                self.assertTrue(all(record["levels"][str(level)]["catalogStatus"] == "gap" for level in range(1, 21) if level != 3))
            elif class_id == "npc-class.bard":
                self.assertEqual(record["catalogStatus"], "resolved")
                self.assertEqual(record["hitDie"], "d8")
                self.assertEqual(record["skillSelections"], 6)
                self.assertEqual(record["castingAbility"], "charisma")
                self.assertEqual(record["castingMode"], "spontaneous")
                self.assertEqual(record["supportedLevels"], [1, 2, 3])
                self.assertEqual(record["levels"]["1"]["spellsPerDay"], {"1": 1})
                self.assertEqual(record["levels"]["3"]["spellsKnown"], {"0": 6, "1": 4})
                self.assertTrue(all(record["levels"][str(level)]["catalogStatus"] == "gap" for level in range(1, 21) if level > 3))
            elif class_id == "npc-class.ranger":
                self.assertEqual(record["catalogStatus"], "resolved")
                self.assertEqual(record["hitDie"], "d10")
                self.assertEqual(record["skillSelections"], 6)
                self.assertEqual(record["castingAbility"], "wisdom")
                self.assertEqual(record["castingMode"], "prepared")
                self.assertEqual(record["supportedLevels"], [1, 2, 3, 4])
                self.assertEqual(record["classSkills"], [
                    "skill.climb", "skill.craft", "skill.handle-animal", "skill.heal", "skill.intimidate",
                    "skill.knowledge-dungeoneering", "skill.knowledge-geography", "skill.knowledge-nature",
                    "skill.perception", "skill.profession", "skill.ride", "skill.spellcraft", "skill.stealth",
                    "skill.survival", "skill.swim",
                ])
                expected_ranger_rows = {
                    1: (1, 2, 2, 0), 2: (2, 3, 3, 0), 3: (3, 3, 3, 1), 4: (4, 4, 4, 1),
                }
                for level, (bab, fort, refx, will) in expected_ranger_rows.items():
                    row = record["levels"][str(level)]
                    self.assertEqual(row["catalogStatus"], "resolved")
                    self.assertEqual((row["bab"], row["fortitude"], row["reflex"], row["will"]), (bab, fort, refx, will))
                self.assertEqual(record["levels"]["4"]["spellsPerDay"], {"1": 0})
                self.assertTrue(all(record["levels"][str(level)]["catalogStatus"] == "gap" for level in range(5, 21)))
            elif class_id == "npc-class.rogue":
                self.assertEqual(record["catalogStatus"], "resolved")
                self.assertEqual(record["hitDie"], "d8")
                self.assertEqual(record["skillSelections"], 8)
                self.assertEqual(record["supportedLevels"], [1, 2])
                self.assertEqual(record["levels"]["1"]["catalogStatus"], "resolved")
                self.assertEqual(record["levels"]["1"]["bab"], 0)
                self.assertEqual((record["levels"]["1"]["fortitude"], record["levels"]["1"]["reflex"], record["levels"]["1"]["will"]), (0, 2, 0))
                self.assertEqual(record["levels"]["2"]["catalogStatus"], "resolved")
                self.assertEqual((record["levels"]["2"]["bab"], record["levels"]["2"]["fortitude"], record["levels"]["2"]["reflex"], record["levels"]["2"]["will"]), (1, 0, 3, 0))
                self.assertTrue(all(record["levels"][str(level)]["catalogStatus"] == "gap" for level in range(3, 21)))
            else:
                self.assertEqual(record["catalogStatus"], "gap")

    def test_only_production_class_features_are_resolved(self):
        features = self.catalog["classFeatures"]
        kinds = [record["kind"] for record in features.values()]
        self.assertEqual(kinds.count("feat-slot"), 6)
        self.assertEqual(kinds.count("choice-slot"), 14)
        self.assertEqual(kinds.count("archetype"), 1)
        self.assertEqual(kinds.count("automatic"), 33)
        resolved = {record_id for record_id, record in features.items() if record["catalogStatus"] == "resolved"}
        self.assertEqual(resolved, {
            "npc-class-feature.warrior-proficiencies", "npc-class-feature.sorcerer-spellcasting",
            "npc-class-feature.sorcerer-bloodlines", "npc-class-feature.sorcerer-eschew-materials",
            "npc-class-feature.druid-spellcasting", "npc-class-feature.druid-nature-bond",
            "npc-class-feature.druidic", "npc-class-feature.druid-nature-sense", "npc-class-feature.druid-wild-empathy",
            "npc-class-feature.druid-woodland-stride", "npc-class-feature.druid-trackless-step",
            "npc-class-feature.druid-proficiencies", "npc-class-feature.druid-orisons",
            "npc-class-feature.fire-domain", "npc-class-feature.druid-elemental-ally",
            "npc-class-feature.bard-proficiencies", "npc-class-feature.bard-spellcasting", "npc-class-feature.bard-cantrips",
            "npc-class-feature.bardic-knowledge", "npc-class-feature.bardic-performance", "npc-class-feature.countersong",
            "npc-class-feature.distraction", "npc-class-feature.fascinate", "npc-class-feature.inspire-courage",
            "npc-class-feature.versatile-performance", "npc-class-feature.well-versed", "npc-class-feature.inspire-competence",
            "npc-class-feature.ranger-proficiencies", "npc-class-feature.rogue-proficiencies",
            "npc-class-feature.ranger-favored-enemy", "npc-class-feature.ranger-track",
            "npc-class-feature.ranger-wild-empathy", "npc-class-feature.ranger-combat-styles",
            "npc-class-feature.ranger-endurance", "npc-class-feature.ranger-favored-terrain",
            "npc-class-feature.ranger-hunters-bond", "npc-class-feature.ranger-spellcasting",
            "npc-class-feature.rogue-sneak-attack", "npc-class-feature.rogue-trapfinding",
            "npc-class-feature.rogue-evasion", "npc-class-feature.rogue-talents",
        })

    def test_thirty_five_core_skills_keep_slice_selection_resolved(self):
        self.assertEqual(set(self.catalog["skills"]), EXACT_IDS["skills"])
        self.assertEqual(self.catalog["skills"]["skill.climb"]["keyAbility"], "strength")
        self.assertEqual(self.catalog["skills"]["skill.intimidate"]["keyAbility"], "charisma")
        resolved = {
            "skill.climb", "skill.intimidate", "skill.bluff", "skill.spellcraft", "skill.use-magic-device",
            "skill.heal", "skill.knowledge-nature", "skill.survival",
            "skill.perform", "skill.perception", "skill.diplomacy",
            "skill.escape-artist", "skill.knowledge-geography", "skill.stealth", "skill.swim",
        }
        self.assertEqual(self.catalog["skills"]["skill.heal"]["keyAbility"], "wisdom")
        self.assertEqual(self.catalog["skills"]["skill.knowledge-nature"]["keyAbility"], "intelligence")
        self.assertEqual(self.catalog["skills"]["skill.perform"]["keyAbility"], "charisma")
        self.assertEqual(self.catalog["skills"]["skill.perception"]["keyAbility"], "wisdom")
        self.assertEqual(self.catalog["skills"]["skill.escape-artist"]["keyAbility"], "dexterity")
        self.assertEqual(self.catalog["skills"]["skill.knowledge-geography"]["keyAbility"], "intelligence")
        self.assertEqual(self.catalog["skills"]["skill.stealth"]["keyAbility"], "dexterity")
        self.assertEqual(self.catalog["skills"]["skill.swim"]["keyAbility"], "strength")
        self.assertEqual(self.catalog["skills"]["skill.knowledge-geography"]["trainedOnly"], True)
        self.assertTrue(all(skill["catalogStatus"] == "gap" for skill_id, skill in self.catalog["skills"].items() if skill_id not in resolved))

    def test_source_backed_feats_are_resolved(self):
        feats = self.catalog["feats"]
        resolved = {record_id for record_id, record in feats.items() if record["catalogStatus"] == "resolved"}
        self.assertEqual(resolved, {
            "feat.endurance", "feat.improved-initiative", "feat.iron-will", "feat.lightning-reflexes",
            "feat.weapon-finesse", "feat.deadly-aim", "feat.point-blank-shot", "feat.rapid-shot",
        })
        self.assertTrue(all(record["category"] == "general" for record in feats.values()))
        self.assertEqual(feats["feat.deadly-aim"]["prerequisites"], {"all": [{"abilityAtLeast": {"dexterity": 13}}, {"babAtLeast": 1}]})
        self.assertEqual(feats["feat.deadly-aim"]["effects"], {})
        self.assertEqual(feats["feat.point-blank-shot"]["prerequisites"], {"all": []})
        self.assertEqual(feats["feat.point-blank-shot"]["effects"], {})
        self.assertEqual(feats["feat.rapid-shot"]["prerequisites"], {"all": [{"abilityAtLeast": {"dexterity": 13}}, {"hasFeat": "feat.point-blank-shot"}]})
        self.assertEqual(feats["feat.rapid-shot"]["effects"], {})
        rule = self.catalog["derivedRules"]["npc-rule.general-feat-slots"]
        self.assertIn("feat.deadly-aim", rule["allowedFeatIds"])
        self.assertIn("feat.point-blank-shot", rule["allowedFeatIds"])
        self.assertNotIn("feat.rapid-shot", rule["allowedFeatIds"])

    def test_only_production_items_are_resolved(self):
        items = self.catalog["items"]
        self.assertEqual(len(items), 73)
        self.assertTrue(all(item["category"] in ITEM_CATEGORIES for item in items.values()))
        resolved = {record_id for record_id, record in items.items() if record["catalogStatus"] == "resolved"}
        self.assertEqual(resolved, {
            "item.longsword", "item.chain-shirt", "item.light-steel-shield",
            "item.wand-of-burning-hands", "item.cloak-of-resistance-1",
            "item.sickle", "item.leather-armor", "item.heavy-wooden-shield",
            "item.rapier", "item.shortsword", "item.chainmail", "item.studded-leather-armor", "item.sling",
            "item.longbow", "item.rapier-masterwork", "item.longbow-plus-1",
            "item.studded-leather-plus-1", "item.potion-of-cure-moderate-wounds",
            "item.potion-of-invisibility", "item.arrows-20",
        })
        self.assertEqual(self.catalog["items"]["item.shortsword"]["effects"]["damageDieBySize"], {"small": "1d4", "medium": "1d6"})
        self.assertEqual(self.catalog["items"]["item.studded-leather-armor"]["effects"], {"armorBonus": 3, "maxDex": 5, "armorCheckPenalty": -1})
        self.assertEqual(self.catalog["items"]["item.chainmail"]["priceCp"], 15000)
        self.assertEqual(self.catalog["items"]["item.longbow"]["priceCp"], 7500)
        self.assertEqual(self.catalog["items"]["item.longbow"]["effects"]["noStrengthToDamage"], True)
        self.assertEqual(self.catalog["items"]["item.longbow-plus-1"]["priceCp"], 237500)
        self.assertEqual(self.catalog["items"]["item.longbow-plus-1"]["effects"]["attackBonus"], 1)
        self.assertEqual(self.catalog["items"]["item.longbow-plus-1"]["effects"]["damageBonus"], 1)
        self.assertEqual(self.catalog["items"]["item.rapier-masterwork"]["priceCp"], 32000)
        self.assertEqual(self.catalog["items"]["item.rapier-masterwork"]["effects"]["attackBonus"], 1)
        self.assertEqual(self.catalog["items"]["item.rapier-masterwork"]["effects"]["critRange"], 18)
        self.assertEqual(self.catalog["items"]["item.studded-leather-plus-1"]["priceCp"], 117500)
        self.assertEqual(self.catalog["items"]["item.studded-leather-plus-1"]["effects"], {"armorBonus": 4, "maxDex": 5, "armorCheckPenalty": 0})
        self.assertEqual(self.catalog["items"]["item.potion-of-cure-moderate-wounds"]["priceCp"], 30000)
        self.assertEqual(self.catalog["items"]["item.potion-of-cure-moderate-wounds"]["npcGearCategory"], "limitedUse")
        self.assertEqual(self.catalog["items"]["item.potion-of-invisibility"]["priceCp"], 40000)
        self.assertEqual(self.catalog["items"]["item.potion-of-invisibility"]["npcGearCategory"], "limitedUse")
        self.assertEqual(self.catalog["items"]["item.arrows-20"]["priceCp"], 100)
        self.assertEqual(self.catalog["items"]["item.arrows-20"]["weightLb"], 3)

    def test_all_nine_gear_profiles_remain_but_only_phase_two_rows_are_resolved(self):
        budgets = self.catalog["gearBudgets"]
        self.assertEqual(
            set(budgets),
            {f"npc-gear.{progression}.{fantasy}" for progression in ("slow", "medium", "fast") for fantasy in ("low", "normal", "high")},
        )
        resolved = budgets["npc-gear.medium.normal"]
        self.assertEqual(resolved["catalogStatus"], "resolved")
        self.assertEqual([row["level"] for row in resolved["rows"] if row["npcCategory"] == "basic"], [1, 2, 3, 4, 5])
        self.assertEqual([row["level"] for row in resolved["rows"] if row["npcCategory"] == "heroic"], [1, 2, 3, 4, 5, 6])
        self.assertEqual(next(row for row in resolved["rows"] if row["npcCategory"] == "heroic" and row["level"] == 4)["budgetCp"], 240000)
        self.assertEqual(
            next(row for row in resolved["rows"] if row["npcCategory"] == "heroic" and row["level"] == 4)["categories"],
            {"weapons": 90000, "protection": 100000, "magic": 0, "limitedUse": 30000, "gear": 20000},
        )
        self.assertEqual(next(row for row in resolved["rows"] if row["npcCategory"] == "heroic" and row["level"] == 1)["budgetCp"], 39000)
        self.assertEqual(next(row for row in resolved["rows"] if row["npcCategory"] == "heroic" and row["level"] == 2)["budgetCp"], 78000)
        self.assertEqual(next(row for row in resolved["rows"] if row["npcCategory"] == "heroic" and row["level"] == 3)["budgetCp"], 165000)
        self.assertTrue(all(record["catalogStatus"] == "gap" for record_id, record in budgets.items() if record_id != "npc-gear.medium.normal"))

    def test_phase_two_values_match_the_archived_aon_rows(self):
        npc_classes = (ROOT / "sources/npc/aonprd/npc-classes.txt").read_text(encoding="utf-8").splitlines()
        equipment = (ROOT / "sources/npc/aonprd/equipment.txt").read_text(encoding="utf-8").splitlines()
        creating = (ROOT / "sources/npc/aonprd/creating-npcs.txt").read_text(encoding="utf-8").splitlines()
        druid = (ROOT / "sources/npc/aonprd/druid.txt").read_text(encoding="utf-8").splitlines()
        self.assertEqual(npc_classes[150], "3rd\t+3\t+3\t+1\t+1")
        self.assertEqual(equipment[154], "Longsword\t15 gp\t1d6\t1d8\t19–20/×2\t—\t4 lbs.\tS\t—")
        self.assertEqual(creating[83], "3\t2\t780 gp\t350 gp\t200 gp\t—\t80 gp\t150 gp")
        self.assertEqual(creating[84], "4\t3\t1,650 gp\t650 gp\t800 gp\t—\t100 gp\t200 gp")
        self.assertEqual(druid[15], "3rd\t+2\t+3\t+1\t+3\tTrackless step\t4\t2\t1\t-\t-\t-\t-\t-\t-\t-")
        self.assertEqual(equipment[117], "Sickle\t6 gp\t1d4\t1d6\t×2\t—\t2 lbs.\tS\ttrip")
        self.assertEqual(equipment[323], "Leather\t10 gp\t+2\t+6\t0\t10%\t30 ft.\t20 ft.\t15 lbs.")
        self.assertEqual(equipment[340], "Shield, heavy wooden\t7 gp\t+2\t—\t–2\t15%\t—\t—\t10 lbs.")
        self.assertEqual(self.catalog["classes"]["npc-class.warrior"]["levels"]["3"]["bab"], 3)
        self.assertEqual(self.catalog["classes"]["npc-class.druid"]["levels"]["3"]["bab"], 2)
        ranger = (ROOT / "sources/npc/aonprd/ranger.txt").read_text(encoding="utf-8").splitlines()
        rogue = (ROOT / "sources/npc/aonprd/rogue.txt").read_text(encoding="utf-8").splitlines()
        self.assertEqual(ranger[13], "1st\t+1\t+2\t+2\t+0\t1st favored enemy, track, wild empathy\t-\t-\t-\t-")
        self.assertEqual(ranger[16], "4th\t+4\t+4\t+4\t+1\tHunter's bond\t0\t-\t-\t-")
        self.assertEqual(rogue[12], "1st\t+0\t+0\t+2\t+0\tSneak attack +1d6, trapfinding")
        self.assertEqual(rogue[13], "2nd\t+1\t+0\t+3\t+0\tEvasion, rogue talent")
        classes = self.catalog["classes"]
        self.assertEqual(classes["npc-class.ranger"]["levels"]["4"]["bab"], 4)
        self.assertEqual((classes["npc-class.ranger"]["levels"]["4"]["fortitude"], classes["npc-class.ranger"]["levels"]["4"]["reflex"], classes["npc-class.ranger"]["levels"]["4"]["will"]), (4, 4, 1))
        self.assertEqual((classes["npc-class.rogue"]["levels"]["2"]["bab"], classes["npc-class.rogue"]["levels"]["2"]["reflex"]), (1, 3))
        presets = self.catalog["abilityArrays"]
        self.assertEqual(presets["npc-ability-array.basic"]["presets"]["ranged"], {
            "strength": 11, "dexterity": 13, "constitution": 12, "intelligence": 10, "wisdom": 9, "charisma": 8,
        })
        self.assertEqual(presets["npc-ability-array.heroic"]["presets"]["ranged"], {
            "strength": 13, "dexterity": 15, "constitution": 14, "intelligence": 12, "wisdom": 10, "charisma": 8,
        })
        self.assertEqual(self.catalog["items"]["item.longsword"]["priceCp"], 1500)
        self.assertEqual(self.catalog["items"]["item.sickle"]["effects"]["damageDieBySize"], {"small": "1d4", "medium": "1d6"})
        self.assertEqual(self.catalog["items"]["item.sickle"]["weightLbBySize"], {"small": 1, "medium": 2})
        self.assertEqual(self.catalog["items"]["item.leather-armor"]["weightLbBySize"], {"small": 7.5, "medium": 15})
        self.assertEqual(self.catalog["items"]["item.heavy-wooden-shield"]["weightLbBySize"], {"small": 5, "medium": 10})
        gear_rows = self.catalog["gearBudgets"]["npc-gear.medium.normal"]["rows"]
        self.assertEqual(next(row for row in gear_rows if row["npcCategory"] == "basic" and row["level"] == 3)["budgetCp"], 78000)
        self.assertEqual(next(row for row in gear_rows if row["npcCategory"] == "heroic" and row["level"] == 1)["budgetCp"], 39000)
        self.assertEqual(next(row for row in gear_rows if row["npcCategory"] == "heroic" and row["level"] == 3)["budgetCp"], 165000)

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