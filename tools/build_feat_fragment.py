#!/usr/bin/env python3
"""Deterministic generator for catalog/npc/feats.fragment.json.

Scope: the 99-feat Core "Creating NPCs, Step 4" baseline (see
docs/npc-feat-support-audit.md) plus its transitive prerequisite records
(Greater Weapon Focus, Improved Precise Shot, Improved Shield Bash).
Every curated value is keyed to the archived Core feats chapter text
(sources/npc/aonprd/feats.txt); the tool derives table rows, description
blocks, line ranges and stable IDs from that file and refuses to build when
a curated prerequisite is not literally present in the source text.

This tool only writes catalog/npc/feats.fragment.json. It never writes the
compiled catalog/npc.json; that remains the owner's build step.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FEATS_TXT = ROOT / "sources/npc/aonprd/feats.txt"
CREATING_NPCS_TXT = ROOT / "sources/npc/aonprd/creating-npcs.txt"
FRAGMENT = ROOT / "catalog/npc/feats.fragment.json"

CHANNEL_FEATURE = "npc-class-feature.cleric-channel-energy"
SCHOOL_VALUES = ["abjuration", "conjuration", "divination", "enchantment",
                 "evocation", "illusion", "necromancy", "transmutation"]
WILD_SHAPE_FEATURE = "npc-class-feature.druid-wild-shape"

# ---------------------------------------------------------------------------
# Curated metadata keyed by Core feat name (straight apostrophes, as in
# feats.txt). treatment: subset of B/R/A/GM/M (docs audit column). support:
# C=calculated (generic effect families the runtime wires), GM=gm-handled,
# SO=selection-only (mechanics not yet implemented). pre: typed prerequisite
# expression (monster_builder/npc/prerequisites.py schema). Each pre component
# must appear verbatim in the source Prerequisites line (asserted below).
# ---------------------------------------------------------------------------
def ab(name):  # abilityAtLeast helper
    return name

PRE = {
    # name -> list of typed expression fragments, later combined under "all"
    "Arcane Strike": [{"any": [
        {"hasClassFeature": "npc-class-feature.sorcerer-spellcasting"},
        {"hasClassFeature": "npc-class-feature.bard-spellcasting"},
        {"hasClassFeature": "npc-class-feature.wizard-spellcasting"},
    ]}],
    "Alignment Channel": [{"hasClassFeature": CHANNEL_FEATURE}],
    "Armor Proficiency, Heavy": [
        {"hasFeat": "feat.armor-proficiency-light"},
        {"hasFeat": "feat.armor-proficiency-medium"},
    ],
    "Armor Proficiency, Medium": [{"hasFeat": "feat.armor-proficiency-light"}],
    "Brew Potion": [{"casterLevelAtLeast": 3}],
    "Channel Smite": [{"hasClassFeature": CHANNEL_FEATURE}],
    "Cleave": [{"abilityAtLeast": {"strength": 13}}, {"hasFeat": "feat.power-attack"}, {"babAtLeast": 1}],
    "Combat Expertise": [{"abilityAtLeast": {"intelligence": 13}}],
    "Command Undead": [{"hasClassFeature": CHANNEL_FEATURE}],
    "Craft Magic Arms and Armor": [{"casterLevelAtLeast": 5}],
    "Craft Rod": [{"casterLevelAtLeast": 9}],
    "Craft Staff": [{"casterLevelAtLeast": 11}],
    "Craft Wand": [{"casterLevelAtLeast": 5}],
    "Craft Wondrous Item": [{"casterLevelAtLeast": 3}],
    "Dazzling Display": [{"hasFeat": "feat.weapon-focus"}],
    "Deadly Aim": [{"abilityAtLeast": {"dexterity": 13}}, {"babAtLeast": 1}],
    "Deadly Stroke": [
        {"hasFeat": "feat.dazzling-display"},
        {"hasFeat": "feat.greater-weapon-focus"},
        {"hasFeat": "feat.shatter-defenses"},
        {"hasFeat": "feat.weapon-focus"},
        {"babAtLeast": 11},
    ],
    "Deflect Arrows": [{"abilityAtLeast": {"dexterity": 13}}, {"hasFeat": "feat.improved-unarmed-strike"}],
    "Dodge": [{"abilityAtLeast": {"dexterity": 13}}],
    "Double Slice": [{"abilityAtLeast": {"dexterity": 15}}, {"hasFeat": "feat.two-weapon-fighting"}],
    "Elemental Channel": [{"hasClassFeature": CHANNEL_FEATURE}],
    "Extra Channel": [{"hasClassFeature": CHANNEL_FEATURE}],
    "Far Shot": [{"hasFeat": "feat.point-blank-shot"}],
    "Forge Ring": [{"casterLevelAtLeast": 7}],
    "Gorgon's Fist": [
        {"hasFeat": "feat.improved-unarmed-strike"},
        {"hasFeat": "feat.scorpion-style"},
        {"babAtLeast": 6},
    ],
    "Great Cleave": [
        {"abilityAtLeast": {"strength": 13}},
        {"hasFeat": "feat.cleave"},
        {"hasFeat": "feat.power-attack"},
        {"babAtLeast": 4},
    ],
    "Greater Spell Focus": [{"hasFeat": "feat.spell-focus"}],
    "Greater Spell Penetration": [{"hasFeat": "feat.spell-penetration"}],
    "Greater Two-Weapon Fighting": [
        {"abilityAtLeast": {"dexterity": 19}},
        {"hasFeat": "feat.improved-two-weapon-fighting"},
        {"hasFeat": "feat.two-weapon-fighting"},
        {"babAtLeast": 11},
    ],
    "Greater Vital Strike": [
        {"hasFeat": "feat.improved-vital-strike"},
        {"hasFeat": "feat.vital-strike"},
        {"babAtLeast": 16},
    ],
    "Greater Weapon Focus": [
        {"hasFeat": "feat.weapon-focus"},
        {"babAtLeast": 1},
        {"classLevelAtLeast": {"npc-class.fighter": 8}},
    ],
    "Improved Bull Rush": [{"abilityAtLeast": {"strength": 13}}, {"hasFeat": "feat.power-attack"}, {"babAtLeast": 1}],
    "Improved Channel": [{"hasClassFeature": CHANNEL_FEATURE}],
    "Improved Critical": [{"babAtLeast": 8}],
    "Improved Disarm": [{"abilityAtLeast": {"intelligence": 13}}, {"hasFeat": "feat.combat-expertise"}],
    "Improved Feint": [{"abilityAtLeast": {"intelligence": 13}}, {"hasFeat": "feat.combat-expertise"}],
    "Improved Grapple": [{"abilityAtLeast": {"dexterity": 13}}, {"hasFeat": "feat.improved-unarmed-strike"}],
    "Improved Shield Bash": [{"hasFeat": "feat.shield-proficiency"}],
    "Improved Sunder": [{"abilityAtLeast": {"strength": 13}}, {"hasFeat": "feat.power-attack"}, {"babAtLeast": 1}],
    "Improved Trip": [{"abilityAtLeast": {"intelligence": 13}}, {"hasFeat": "feat.combat-expertise"}],
    "Improved Two-Weapon Fighting": [
        {"abilityAtLeast": {"dexterity": 17}},
        {"hasFeat": "feat.two-weapon-fighting"},
        {"babAtLeast": 6},
    ],
    "Improved Vital Strike": [{"hasFeat": "feat.vital-strike"}, {"babAtLeast": 11}],
    "Improved Precise Shot": [
        {"abilityAtLeast": {"dexterity": 19}},
        {"hasFeat": "feat.point-blank-shot"},
        {"hasFeat": "feat.precise-shot"},
        {"babAtLeast": 11},
    ],
    "Manyshot": [
        {"abilityAtLeast": {"dexterity": 17}},
        {"hasFeat": "feat.point-blank-shot"},
        {"hasFeat": "feat.rapid-shot"},
        {"babAtLeast": 6},
    ],
    "Medusa's Wrath": [
        {"hasFeat": "feat.improved-unarmed-strike"},
        {"hasFeat": "feat.gorgon-s-fist"},
        {"hasFeat": "feat.scorpion-style"},
        {"babAtLeast": 11},
    ],
    "Mobility": [{"abilityAtLeast": {"dexterity": 13}}, {"hasFeat": "feat.dodge"}],
    "Mounted Combat": [{"skillRanksAtLeast": {"skill.ride": 1}}],
    "Natural Spell": [
        {"abilityAtLeast": {"wisdom": 13}},
        {"hasClassFeature": WILD_SHAPE_FEATURE},
    ],
    "Pinpoint Targeting": [
        {"abilityAtLeast": {"dexterity": 19}},
        {"hasFeat": "feat.improved-precise-shot"},
        {"hasFeat": "feat.point-blank-shot"},
        {"hasFeat": "feat.precise-shot"},
        {"babAtLeast": 16},
    ],
    "Power Attack": [{"abilityAtLeast": {"strength": 13}}, {"babAtLeast": 1}],
    "Precise Shot": [{"hasFeat": "feat.point-blank-shot"}],
    "Rapid Shot": [{"abilityAtLeast": {"dexterity": 13}}, {"hasFeat": "feat.point-blank-shot"}],
    "Ride-By Attack": [{"skillRanksAtLeast": {"skill.ride": 1}}, {"hasFeat": "feat.mounted-combat"}],
    "Selective Channeling": [{"abilityAtLeast": {"charisma": 13}}, {"hasClassFeature": CHANNEL_FEATURE}],
    "Scribe Scroll": [{"casterLevelAtLeast": 1}],
    "Shatter Defenses": [{"hasFeat": "feat.weapon-focus"}, {"hasFeat": "feat.dazzling-display"}, {"babAtLeast": 6}],
    "Shield Focus": [{"hasFeat": "feat.shield-proficiency"}, {"babAtLeast": 1}],
    "Shield Master": [
        {"hasFeat": "feat.improved-shield-bash"},
        {"hasFeat": "feat.shield-proficiency"},
        {"hasFeat": "feat.shield-slam"},
        {"hasFeat": "feat.two-weapon-fighting"},
        {"babAtLeast": 11},
    ],
    "Shield Slam": [
        {"hasFeat": "feat.improved-shield-bash"},
        {"hasFeat": "feat.shield-proficiency"},
        {"hasFeat": "feat.two-weapon-fighting"},
        {"babAtLeast": 6},
    ],
    "Scorpion Style": [{"hasFeat": "feat.improved-unarmed-strike"}],
    "Shot on the Run": [
        {"abilityAtLeast": {"dexterity": 13}},
        {"hasFeat": "feat.dodge"},
        {"hasFeat": "feat.mobility"},
        {"hasFeat": "feat.point-blank-shot"},
        {"babAtLeast": 4},
    ],
    "Snatch Arrows": [
        {"abilityAtLeast": {"dexterity": 15}},
        {"hasFeat": "feat.deflect-arrows"},
        {"hasFeat": "feat.improved-unarmed-strike"},
    ],
    "Spell Mastery": [{"classLevelAtLeast": {"npc-class.wizard": 1}}],
    "Spirited Charge": [
        {"skillRanksAtLeast": {"skill.ride": 1}},
        {"hasFeat": "feat.mounted-combat"},
        {"hasFeat": "feat.ride-by-attack"},
    ],
    "Spring Attack": [
        {"abilityAtLeast": {"dexterity": 13}},
        {"hasFeat": "feat.dodge"},
        {"hasFeat": "feat.mobility"},
        {"babAtLeast": 4},
    ],
    "Stunning Fist": [
        {"abilityAtLeast": {"dexterity": 13}},
        {"abilityAtLeast": {"wisdom": 13}},
        {"hasFeat": "feat.improved-unarmed-strike"},
        {"babAtLeast": 8},
    ],
    "Trample": [{"skillRanksAtLeast": {"skill.ride": 1}}, {"hasFeat": "feat.mounted-combat"}],
    "Turn Undead": [{"hasClassFeature": CHANNEL_FEATURE}],
    "Two-Weapon Fighting": [{"abilityAtLeast": {"dexterity": 15}}],
    "Two-Weapon Defense": [{"abilityAtLeast": {"dexterity": 15}}, {"hasFeat": "feat.two-weapon-fighting"}],
    "Two-Weapon Rend": [
        {"abilityAtLeast": {"dexterity": 17}},
        {"hasFeat": "feat.double-slice"},
        {"hasFeat": "feat.improved-two-weapon-fighting"},
        {"hasFeat": "feat.two-weapon-fighting"},
        {"babAtLeast": 11},
    ],
    "Weapon Focus": [{"babAtLeast": 1}],
    "Vital Strike": [{"babAtLeast": 6}],
    "Whirlwind Attack": [
        {"abilityAtLeast": {"dexterity": 13}},
        {"abilityAtLeast": {"intelligence": 13}},
        {"hasFeat": "feat.combat-expertise"},
        {"hasFeat": "feat.dodge"},
        {"hasFeat": "feat.mobility"},
        {"hasFeat": "feat.spring-attack"},
        {"babAtLeast": 4},
    ],
}

META = {
    # name: (treatments, support, choice, requiredWeaponProficiency, effects)
    "Alignment Channel": (["GM"], "GM", {"field": "subtype", "values": ["chaotic", "evil", "good", "lawful"]}, False, {}),
    "Arcane Strike": (["A"], "C", None, False, {"combatOption": "arcane-strike"}),
    "Armor Proficiency, Heavy": (["B"], "C", None, False, {"armorProficiencies": ["heavy"]}),
    "Armor Proficiency, Light": (["B"], "C", None, False, {"armorProficiencies": ["light"]}),
    "Armor Proficiency, Medium": (["B"], "C", None, False, {"armorProficiencies": ["medium"]}),
    "Brew Potion": (["GM"], "GM", None, False, {}),
    "Channel Smite": (["A"], "SO", None, False, {"combatOption": "channel-smite"}),
    "Cleave": (["A", "GM"], "C", None, False, {"combatOption": "cleave"}),
    "Combat Casting": (["R"], "C", None, False, {
        "conditionalModifiers": [{"condition": "casting on the defensive or while grappled", "stat": "concentration", "bonus": 4}]}),
    "Combat Expertise": (["A"], "C", None, False, {"combatOption": "combat-expertise"}),
    "Combat Reflexes": (["GM"], "GM", None, False, {}),
    "Command Undead": (["A", "GM"], "SO", None, False, {"combatOption": "command-undead"}),
    "Craft Magic Arms and Armor": (["GM"], "GM", None, False, {}),
    "Craft Rod": (["GM"], "GM", None, False, {}),
    "Craft Staff": (["GM"], "GM", None, False, {}),
    "Craft Wand": (["GM"], "GM", None, False, {}),
    "Craft Wondrous Item": (["GM"], "GM", None, False, {}),
    "Dazzling Display": (["GM"], "GM", None, True, {}),
    "Deadly Aim": (["A"], "C", None, False, {"combatOption": "deadly-aim"}),
    "Deadly Stroke": (["A"], "SO", None, True, {"combatOption": "deadly-stroke"}),
    "Deflect Arrows": (["GM"], "GM", None, False, {}),
    "Dodge": (["B"], "C", None, False, {"dodgeAC": 1}),
    "Double Slice": (["A"], "C", None, False, {"combatOption": "double-slice"}),
    "Elemental Channel": (["GM"], "GM", {"field": "subtype", "values": ["air", "earth", "fire", "water"]}, False, {}),
    "Empower Spell": (["M"], "GM", None, False, {"slotAdjustment": 2}),
    "Enlarge Spell": (["M"], "GM", None, False, {"slotAdjustment": 1}),
    "Eschew Materials": (["GM"], "GM", None, False, {}),
    "Extend Spell": (["M"], "GM", None, False, {"slotAdjustment": 1}),
    "Extra Channel": (["B"], "SO", None, False, {}),
    "Far Shot": (["R"], "C", None, False, {
        "conditionalModifiers": [{"condition": "per full range increment beyond the first", "stat": "rangedAttackPenaltyPerIncrement", "bonus": -1}]}),
    "Forge Ring": (["GM"], "GM", None, False, {}),
    "Gorgon's Fist": (["A", "GM"], "C", None, False, {"combatOption": "gorgons-fist"}),
    "Great Cleave": (["A", "GM"], "C", None, False, {"combatOption": "great-cleave"}),
    "Great Fortitude": (["B"], "C", None, False, {"fortitude": 2}),
    "Greater Spell Focus": (["B"], "C", {"field": "school", "values": SCHOOL_VALUES}, False, {"schoolDCBonus": 1}),
    "Greater Spell Penetration": (["R"], "C", None, False, {
        "conditionalModifiers": [{"condition": "caster level checks to overcome spell resistance", "stat": "casterLevelCheck", "bonus": 2}]}),
    "Greater Two-Weapon Fighting": (["A"], "C", None, False, {"combatOption": "greater-two-weapon-fighting"}),
    "Greater Vital Strike": (["A"], "C", None, False, {"combatOption": "greater-vital-strike"}),
    "Greater Weapon Focus": (["B"], "P", {"field": "weaponId"}, True, {"weaponAttackBonus": 1}),
    "Heighten Spell": (["M"], "GM", None, False, {"slotAdjustment": {"special": "heighten"}}),
    "Improved Bull Rush": (["R", "GM"], "C", None, False, {
        "conditionalModifiers": [{"condition": "bull rush combat maneuvers", "stat": "cmb", "bonus": 2},
                                  {"condition": "defense against bull rush", "stat": "cmd", "bonus": 2}]}),
    "Improved Channel": (["B"], "SO", None, False, {
        "conditionalModifiers": [{"condition": "saving throws to resist your channel energy", "stat": "channelSaveDC", "bonus": 2}]}),
    "Improved Critical": (["B"], "C", {"field": "weaponId"}, True, {"doubleThreatRange": True}),
    "Improved Disarm": (["R", "GM"], "C", None, False, {
        "conditionalModifiers": [{"condition": "disarm combat maneuvers", "stat": "cmb", "bonus": 2},
                                  {"condition": "defense against disarm", "stat": "cmd", "bonus": 2}]}),
    "Improved Feint": (["GM"], "GM", None, False, {}),
    "Improved Grapple": (["R", "GM"], "C", None, False, {
        "conditionalModifiers": [{"condition": "grapple combat maneuvers", "stat": "cmb", "bonus": 2},
                                  {"condition": "defense against grapple", "stat": "cmd", "bonus": 2}]}),
    "Improved Initiative": (["B"], "C", None, False, {"initiative": 4}),
    "Improved Precise Shot": (["R", "GM"], "GM", None, False, {}),
    "Improved Shield Bash": (["R"], "SO", None, False, {}),
    "Improved Sunder": (["R", "GM"], "C", None, False, {
        "conditionalModifiers": [{"condition": "sunder combat maneuvers", "stat": "cmb", "bonus": 2},
                                  {"condition": "defense against sunder", "stat": "cmd", "bonus": 2}]}),
    "Improved Trip": (["R", "GM"], "C", None, False, {
        "conditionalModifiers": [{"condition": "trip combat maneuvers", "stat": "cmb", "bonus": 2},
                                  {"condition": "defense against trip", "stat": "cmd", "bonus": 2}]}),
    "Improved Two-Weapon Fighting": (["A"], "C", None, False, {"combatOption": "improved-two-weapon-fighting"}),
    "Improved Unarmed Strike": (["B", "GM"], "C", None, False, {}),
    "Improved Vital Strike": (["A"], "C", None, False, {"combatOption": "improved-vital-strike"}),
    "Lightning Reflexes": (["B"], "C", None, False, {"reflex": 2}),
    "Iron Will": (["B"], "C", None, False, {"will": 2}),
    "Manyshot": (["A"], "C", None, False, {"combatOption": "manyshot"}),
    "Maximize Spell": (["M"], "GM", None, False, {"slotAdjustment": 3}),
    "Medusa's Wrath": (["A"], "C", None, False, {"combatOption": "medusas-wrath"}),
    "Martial Weapon Proficiency": (["B"], "C", None, False, {"weaponProficiencyCategory": "martial"}),
    "Mobility": (["R"], "C", None, False, {
        "conditionalModifiers": [{"condition": "against attacks of opportunity caused by movement", "stat": "ac", "bonus": 4}]}),
    "Mounted Combat": (["GM"], "GM", None, False, {}),
    "Natural Spell": (["GM"], "GM", None, False, {}),
    "Pinpoint Targeting": (["GM", "A"], "C", None, False, {"combatOption": "pinpoint-targeting"}),
    "Point-Blank Shot": (["R"], "C", None, False, {
        "conditionalModifiers": [{"condition": "ranged attacks within 30 feet", "stat": "attackRoll", "bonus": 1},
                                  {"condition": "ranged attacks within 30 feet", "stat": "damageRoll", "bonus": 1}]}),
    "Power Attack": (["A"], "C", None, False, {"combatOption": "power-attack"}),
    "Precise Shot": (["R", "GM"], "C", None, False, {
        "conditionalModifiers": [{"condition": "ranged attacks into melee or against a target engaged in melee", "stat": "attackPenaltyNegated", "bonus": 4}]}),
    "Quicken Spell": (["M"], "GM", None, False, {"slotAdjustment": 4}),
    "Rapid Reload": (["GM", "A"], "SO", {"field": "weaponId"}, True, {}),
    "Rapid Shot": (["A"], "C", None, False, {"combatOption": "rapid-shot"}),
    "Ride-By Attack": (["GM"], "GM", None, False, {}),
    "Run": (["R", "GM"], "SO", None, False, {}),
    "Scorpion Style": (["A", "GM"], "C", None, False, {"combatOption": "scorpion-style"}),
    "Selective Channeling": (["GM"], "GM", None, False, {}),
    "Scribe Scroll": (["GM"], "GM", None, False, {}),
    "Shatter Defenses": (["GM"], "GM", None, True, {}),
    "Shield Focus": (["B"], "C", None, False, {"shieldAC": 1}),
    "Shield Master": (["A"], "SO", None, False, {"combatOption": "shield-master"}),
    "Shield Proficiency": (["B"], "C", None, False, {"shieldProficiencies": ["shield"]}),
    "Shield Slam": (["A", "GM"], "SO", None, False, {"combatOption": "shield-slam"}),
    "Shot on the Run": (["GM"], "GM", None, False, {}),
    "Silent Spell": (["M"], "GM", None, False, {"slotAdjustment": 1}),
    "Skill Focus": (["B"], "C", {"field": "skillId"}, False, {"skillFocus": True}),
    "Snatch Arrows": (["GM"], "GM", None, False, {}),
    "Spell Focus": (["B"], "C", {"field": "school", "values": SCHOOL_VALUES}, False, {"schoolDCBonus": 1}),
    "Spell Mastery": (["GM"], "GM", {"field": "spellIds"}, False, {}),
    "Spell Penetration": (["R"], "C", None, False, {
        "conditionalModifiers": [{"condition": "caster level checks to overcome spell resistance", "stat": "casterLevelCheck", "bonus": 2}]}),
    "Spirited Charge": (["A"], "SO", None, False, {"combatOption": "spirited-charge"}),
    "Spring Attack": (["GM"], "GM", None, False, {}),
    "Still Spell": (["M"], "GM", None, False, {"slotAdjustment": 1}),
    "Stunning Fist": (["A", "GM"], "C", None, False, {"combatOption": "stunning-fist"}),
    "Toughness": (["B"], "C", None, False, {"hpPerLevelMinimum": 3}),
    "Trample": (["A", "GM"], "SO", None, False, {"combatOption": "trample"}),
    "Turn Undead": (["A", "GM"], "SO", None, False, {"combatOption": "turn-undead"}),
    "Two-Weapon Defense": (["B", "A"], "SO", None, False, {
        "conditionalModifiers": [{"condition": "wielding a double weapon or two weapons (not natural weapons or unarmed strikes)", "stat": "ac", "bonus": 1},
                                  {"condition": "fighting defensively or using total defense while dual-wielding", "stat": "ac", "bonus": 1}]}),
    "Two-Weapon Fighting": (["A"], "C", None, False, {"combatOption": "two-weapon-fighting"}),
    "Two-Weapon Rend": (["A"], "SO", None, False, {"combatOption": "two-weapon-rend"}),
    "Vital Strike": (["A"], "C", None, False, {"combatOption": "vital-strike"}),
    "Weapon Focus": (["B"], "P", {"field": "weaponId"}, True, {"weaponAttackBonus": 1}),
    "Weapon Finesse": (["B"], "C", None, False, {"finesse": True}),
    "Whirlwind Attack": (["GM", "A"], "C", None, False, {"combatOption": "whirlwind-attack"}),
    "Widen Spell": (["M"], "GM", None, False, {"slotAdjustment": 3}),
}

# Transitive prerequisite records outside the 99 baseline (audit "Dependencies
# outside the literal list"): Greater Weapon Focus, Improved Precise Shot,
# Improved Shield Bash. Weapon Finesse/Rapid Shot/Martial Weapon Proficiency/
# Improved Initiative/Iron Will/Lightning Reflexes are baseline members.
SUPPORT = {"C": "calculated", "GM": "gm-handled", "SO": "selection-only", "P": "partial"}
# Explicit limitation strings for partial records (UI/readable export); the
# calculation applies to catalog weapon targets, virtual targets are missing.
SUPPORT_LIMITATIONS = {
    "Weapon Focus": "Virtual targets unarmed strike, grapple, and ray (spellcasters) "
                    "are not selectable yet; the +1 attack calculation applies to "
                    "catalog weapon item targets only.",
    "Greater Weapon Focus": "Virtual targets unarmed strike and grapple are not "
                            "selectable yet; the +1 attack calculation applies to "
                            "catalog weapon item targets only.",
}

# Source text fragments that must be present for a curated prerequisite to be
# considered source-backed. Maps curated component -> literal source fragment.
PREREQ_TEXT_EVIDENCE = {
    "feat.armor-proficiency-light": "Light Armor Proficiency",
    "feat.armor-proficiency-medium": "Medium Armor Proficiency",
    "feat.power-attack": "Power Attack",
    "feat.two-weapon-fighting": "Two-Weapon Fighting",
    "feat.cleave": "Cleave",
    "feat.combat-expertise": "Combat Expertise",
    "feat.dazzling-display": "Dazzling Display",
    "feat.greater-weapon-focus": "Greater Weapon Focus",
    "feat.shatter-defenses": "Shatter Defenses",
    "feat.weapon-focus": "Weapon Focus",
    "feat.improved-unarmed-strike": "Improved Unarmed Strike",
    "feat.scorpion-style": "Scorpion Style",
    "feat.gorgon-s-fist": "Gorgon's Fist",
    "feat.improved-two-weapon-fighting": "Improved Two-Weapon Fighting",
    "feat.improved-vital-strike": "Improved Vital Strike",
    "feat.vital-strike": "Vital Strike",
    "feat.point-blank-shot": "Point-Blank Shot",
    "feat.rapid-shot": "Rapid Shot",
    "feat.dodge": "Dodge",
    "feat.mobility": "Mobility",
    "feat.spring-attack": "Spring Attack",
    "feat.improved-precise-shot": "Improved Precise Shot",
    "feat.precise-shot": "Precise Shot",
    "feat.mounted-combat": "Mounted Combat",
    "feat.ride-by-attack": "Ride-By Attack",
    "feat.shield-proficiency": "Shield Proficiency",
    "feat.improved-shield-bash": "Improved Shield Bash",
    "feat.shield-slam": "Shield Slam",
    "feat.double-slice": "Double Slice",
    "feat.deflect-arrows": "Deflect Arrows",
    "feat.spell-focus": "Spell Focus",
    "feat.spell-penetration": "Spell Penetration",
    "dexterity 13": "Dex 13",
    "dexterity 15": "Dex 15",
    "dexterity 17": "Dex 17",
    "dexterity 19": "Dex 19",
    "strength 13": "Str 13",
    "intelligence 13": "Int 13",
    "wisdom 13": "Wis 13",
    "charisma 13": "Cha 13",
    "bab 1": "base attack bonus +1",
    "bab 4": "base attack bonus +4",
    "bab 6": "base attack bonus +6",
    "bab 8": "base attack bonus +8",
    "bab 11": "base attack bonus +11",
    "bab 16": "base attack bonus +16",
    "caster level 1": "Caster level 1st",
    "caster level 3": "Caster level 3rd",
    "caster level 5": "Caster level 5th",
    "caster level 7": "Caster level 7th",
    "caster level 9": "Caster level 9th",
    "caster level 11": "Caster level 11th",
    "skill ride 1": "Ride 1 rank",
    "class fighter 8": "8th-level fighter",
    "class wizard 1": "1st-level wizard",
    "channel": [
        "channel energy class feature",
        "Channel negative energy class feature",
        "Channel positive energy class feature",
        "Ability to channel energy",
    ],
    "wild shape": "wild shape class feature",
    "arcane": "Ability to cast arcane spells",
}

KNOWN_FEATURE_GAPS = {CHANNEL_FEATURE, WILD_SHAPE_FEATURE}

CHOICE_FIELDS = {"weaponId", "skillId", "school", "subtype", "spellIds"}
TREATMENTS = {"B", "R", "A", "GM", "M"}


def canonical(name: str) -> str:
    return name.replace("’", "'").strip()


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", canonical(name).lower()).strip("-")


def load_source_tables(lines):
    """Return (table_rows, description_blocks) keyed by canonical feat name."""
    table_rows = {}
    for index, line in enumerate(lines, 1):
        if 51 <= index <= 225 and "\t" in line and not line.startswith(
            ("Feats\t", "Item Creation Feats\t", "Metamagic Feats\t")
        ):
            name = canonical(line.split("\t")[0].removesuffix("*"))
            prereq, benefit = (line.split("\t")[1:3] + [""])[0:2]
            table_rows[name] = {"line": index, "prereq": prereq, "benefit": benefit}
    # The archived Table: Feats row for Improved Precise Shot lost a space
    # ("Improved PreciseShot"); match rows against headers space-insensitively.
    table_by_nospace = {name.replace(" ", ""): entry for name, entry in table_rows.items()}
    headers = {}
    for index, line in enumerate(lines, 1):
        if index < 227 or "\t" in line:
            continue
        match = re.match(r"^([A-Z].*?) \([A-Za-z, ]+\)$", line)
        candidate = canonical(match.group(1)) if match else canonical(line)
        row_name = candidate if candidate in table_rows else table_by_nospace.get(candidate.replace(" ", ""))
        row_name = next((n for n in table_rows if n == candidate), None) or \
            next((n for n, e in table_rows.items() if e is table_by_nospace.get(candidate.replace(" ", ""))), None)
        if row_name:
            headers.setdefault(candidate, (index, row_name))
    order = sorted(headers.items(), key=lambda kv: kv[1][0])
    blocks = {}
    for pos, (name, (header, row_name)) in enumerate(order):
        end = order[pos + 1][1][0] if pos + 1 < len(order) else len(lines) + 1
        body = lines[header:end - 1]
        prereq = ""
        benefit = ""
        special = ""
        intro = ""
        if body and not body[0].startswith(("Prerequisites:", "Prerequisite:", "Benefit:",
                                            "Normal:", "Special:")):
            intro = body[0].strip()
        for k, text in enumerate(body):
            if text.startswith(("Prerequisites:", "Prerequisite:")):
                prereq = text
                while k + 1 < len(body) and re.search(r"(,\s*$|\band\s*$|\bor\s*$)", body[k]) and not body[
                    k + 1
                ].startswith(("Benefit:", "Normal:", "Special:")):
                    k += 1
                    prereq += " " + body[k].strip()
            if text.startswith("Special:"):
                special = text[len("Special: "):]
                k2 = k
                while k + 1 < len(body) and not body[k + 1].startswith(
                    ("Normal:", "Special:", "Prerequisit", "Benefit:")
                ) and body[k + 1].rstrip() not in table_rows:
                    k += 1
                    special += " " + body[k].strip()
            if text.startswith("Benefit:"):
                benefit = text[len("Benefit: "):]
                while k + 1 < len(body) and not body[k + 1].startswith(
                    ("Normal:", "Special:", "Prerequisit")
                ) and body[k + 1].rstrip() not in table_rows:
                    k += 1
                    benefit += " " + body[k].strip()
        blocks[name] = {
            "headerLine": header,
            "headerText": lines[header - 1],
            "endLine": end - 1,
            "prereq": (prereq[len("Prerequisites: "):] if prereq.startswith("Prerequisites:")
                       else prereq[len("Prerequisite: "):]) if prereq else "",
            "benefit": benefit,
            "intro": intro,
            "special": special,
            "rowName": row_name,
        }
    return table_rows, blocks


def step4_baseline(table_rows, blocks):
    """The 99 identifiable Step-4 feats (audit methodology; 'M' excluded)."""
    source = CREATING_NPCS_TXT.read_text()
    section = source.split("Step 4: Feats\n", 1)[1].split("Step 5: Class Features", 1)[0]
    names = set()
    for line in section.splitlines():
        if ": " in line:
            names.update(line.split(": ", 1)[1].rstrip(".").replace(", and ", ", ").split(", "))
    names.discard("M")
    names.discard("Skill Focus (Ride)")
    names.remove("item creation feats (all)")
    names.remove("metamagic feats (all)")
    names.remove("Armor Proficiency (all)")
    for name in table_rows:
        if table_rows[name]["line"] in range(208, 216):
            names.add(name)
        elif table_rows[name]["line"] in range(217, 226):
            names.add(name)
        elif name.startswith("Armor Proficiency, ") and " (Combat)" in blocks[name]["headerText"]:
            names.add(name)
    return {canonical(n) for n in names}


def evidence_for(name, fragments):
    """Assert curated prerequisites are literally present in source text."""
    problems = []
    block = fragments["blocks"][name]
    prereq_text = (block["prereq"] or block["benefit"]).lower()
    for expr in fragments["pre"].get(name, []):
        for key, operand in expr.items():
            if key == "hasFeat":
                evidence = PREREQ_TEXT_EVIDENCE.get(operand)
                if evidence and evidence.lower() not in prereq_text:
                    problems.append(f"{name}: {operand} not found in source text")
            elif key == "abilityAtLeast":
                for ability, value in operand.items():
                    evidence = PREREQ_TEXT_EVIDENCE.get(f"{ability} {value}")
                    if evidence and evidence.lower() not in prereq_text:
                        problems.append(f"{name}: {ability} {value} not found in source text")
            elif key == "babAtLeast":
                evidence = PREREQ_TEXT_EVIDENCE.get(f"bab {operand}")
                if evidence and evidence.lower() not in prereq_text:
                    problems.append(f"{name}: bab {operand} not found in source text")
            elif key == "casterLevelAtLeast":
                evidence = PREREQ_TEXT_EVIDENCE.get(f"caster level {operand}")
                if evidence and evidence.lower() not in prereq_text:
                    problems.append(f"{name}: caster level {operand} not found in source text")
            elif key == "skillRanksAtLeast":
                for skill, value in operand.items():
                    evidence = PREREQ_TEXT_EVIDENCE.get(f"skill {skill.removeprefix('skill.')} {value}")
                    if evidence and evidence.lower() not in prereq_text:
                        problems.append(f"{name}: {skill} {value} ranks not found in source text")
            elif key == "classLevelAtLeast":
                for class_id, value in operand.items():
                    evidence = PREREQ_TEXT_EVIDENCE.get(f"class {class_id.removeprefix('npc-class.')} {value}")
                    if evidence and evidence.lower() not in prereq_text:
                        problems.append(f"{name}: {class_id} {value} not found in source text")
            elif key == "hasClassFeature":
                evidence = PREREQ_TEXT_EVIDENCE.get(
                    "wild shape" if "wild-shape" in operand else "channel"
                )
                if evidence and not any(candidate.lower() in prereq_text for candidate in evidence):
                    problems.append(f"{name}: {operand} not found in source text")
            elif key == "any":
                evidence = PREREQ_TEXT_EVIDENCE.get("arcane")
                if evidence and evidence.lower() not in prereq_text:
                    problems.append(f"{name}: arcane casting not found in source text")
    return problems


ABILITY_LONG = {"str": "strength", "dex": "dexterity", "con": "constitution",
                "int": "intelligence", "wis": "wisdom", "cha": "charisma"}
CLASS_NAME_TO_ID = {"wizard": "npc-class.wizard", "fighter": "npc-class.fighter",
                    "cleric": "npc-class.cleric"}
SKILL_NAME_TO_ID = {"ride": "skill.ride"}


def audit_prereq_coverage(names, blocks, pre):
    """Bidirectional audit: every source prerequisite component must map to a
    typed expression (or an explicitly-unmodeled clause), and every typed
    expression component must be present in the source line."""
    problems = []
    feat_names = set(blocks)
    for name in names:
        text = blocks[name]["prereq"]
        # Inverted armor-proficiency spellings in source text map to the
        # canonical comma-form feat names.
        text = text.replace("Light Armor Proficiency", "Armor Proficiency, Light")
        text = text.replace("Medium Armor Proficiency", "Armor Proficiency, Medium")
        record_pre = pre.get(name, [])
        flat = [item for expr in record_pre for item in expr.items()]
        if not text:
            if flat:
                problems.append(f"{name}: typed prerequisite without source text: {record_pre}")
            continue
        remaining = f" {text} "
        covered_abilities = {}
        covered_bab = set()
        covered_casters = set()
        covered_feats = set()
        covered_skills = set()
        covered_classes = set()
        # Feat-name components (longest names first so 'Two-Weapon Fighting'
        # inside 'Improved Two-Weapon Fighting' is not double-counted).
        for feat in sorted(feat_names, key=len, reverse=True):
            if feat != name and feat in remaining:
                covered_feats.add(feat)
                remaining = remaining.replace(feat, " ")
        for ability, value in re.findall(r"\b(Str|Dex|Con|Int|Wis|Cha) (\d+)\b", text):
            covered_abilities[ABILITY_LONG[ability.lower()]] = int(value)
        for value in re.findall(r"[Bb]ase attack bonus \+(\d+)", text):
            covered_bab.add(int(value))
        for value in re.findall(r"[Cc]aster level (\d+)", text):
            covered_casters.add(int(value))
        for skill, ranks in re.findall(r"\b([A-Z][a-z]+) (\d+) rank", text):
            covered_skills.add(SKILL_NAME_TO_ID.get(skill.lower(), f"skill.{skill.lower()}={ranks}"))
        for level, cls in re.findall(r"(\d+)(?:st|nd|rd|th)-level (\w+)", text):
            covered_classes.add((CLASS_NAME_TO_ID.get(cls.lower(), f"npc-class.{cls.lower()}"), int(level)))
        has_channel = bool(re.search(r"channel( (?:positive|negative))? energy", text, re.I)) or \
            "Ability to channel energy" in text
        has_wild_shape = "wild shape class feature" in text
        has_arcane = "cast arcane spells" in text
        has_proficiency = bool(re.search(
            r"[Ww]eapon [Pp]roficien|[Pp]roficien(t|cy) with (the )?(selected )?weapon", text))
        meta = META.get(name, (None, None, None, False, None))
        rwp = meta[3]
        # Remove every recognized span, then require nothing but punctuation.
        for feat in covered_feats:
            remaining = remaining.replace(feat, " ")
        remaining = re.sub(r"\b(Str|Dex|Con|Int|Wis|Cha) \d+\b", " ", remaining)
        remaining = re.sub(r"[Bb]ase attack bonus \+\d+", " ", remaining)
        remaining = re.sub(r"[Cc]aster level \d+(?:st|nd|rd|th)?", " ", remaining)
        remaining = re.sub(r"\b[A-Z][a-z]+ \d+ rank\b", " ", remaining)
        remaining = re.sub(r"\d+(?:st|nd|rd|th)-level \w+", " ", remaining)
        if has_channel:
            remaining = re.sub(r"[Aa]bility to channel energy", " ", remaining)
            remaining = re.sub(r"[Cc]hannel (?:positive |negative )?energy class feature", " ", remaining)
        if has_wild_shape:
            remaining = re.sub(r"wild shape class feature", " ", remaining)
        if has_arcane:
            remaining = re.sub(r"[Aa]bility to cast arcane spells", " ", remaining)
        if has_proficiency:
            remaining = re.sub(r"[Ww]eapon [Pp]roficien\w*[^,.;]*", " ", remaining)
            remaining = re.sub(r"[Pp]roficien(t|cy) with (the )?(selected )?weapon", " ", remaining)
        # Qualifier phrases that attach to chosen feat targets.
        remaining = remaining.replace("(crossbow type chosen)", " ")
        remaining = re.sub(r"with (the )?selected weapon", " ", remaining)
        leftover = remaining.replace(",", " ").replace(".", " ").strip()
        if leftover:
            problems.append(f"{name}: unrecognized prerequisite text: {leftover!r}")
        # Forward checks: source components must be in the typed expression.
        typed_abilities = {}
        typed_bab = set()
        typed_casters = set()
        typed_feats = set()
        typed_skills = set()
        typed_classes = set()
        typed_channel = False
        typed_wild_shape = False
        typed_arcane = False
        for expr in record_pre:
            for key, operand in expr.items():
                if key == "abilityAtLeast":
                    typed_abilities.update(operand)
                elif key == "babAtLeast":
                    typed_bab.add(operand)
                elif key == "casterLevelAtLeast":
                    typed_casters.add(operand)
                elif key == "hasFeat":
                    typed_feats.add(operand)
                elif key == "skillRanksAtLeast":
                    typed_skills.update(operand.items())
                elif key == "classLevelAtLeast":
                    typed_classes.update(operand.items())
                elif key == "hasClassFeature":
                    typed_channel = typed_channel or "channel" in operand
                    typed_wild_shape = typed_wild_shape or "wild-shape" in operand
                elif key == "any":
                    typed_arcane = True
        for ability, value in covered_abilities.items():
            if typed_abilities.get(ability) != value:
                problems.append(f"{name}: source needs {ability} {value}, typed has {typed_abilities.get(ability)}")
        for value in covered_bab:
            if value not in typed_bab:
                problems.append(f"{name}: source needs bab {value}, typed has {sorted(typed_bab)}")
        for value in covered_casters:
            if value not in typed_casters:
                problems.append(f"{name}: source needs caster level {value}, typed has {sorted(typed_casters)}")
        for skill in covered_skills:
            if skill not in dict(typed_skills):
                problems.append(f"{name}: source needs skill ranks {skill}, typed has {sorted(typed_skills)}")
        for class_id, level in covered_classes:
            if dict(typed_classes).get(class_id) != level:
                problems.append(f"{name}: source needs {class_id} {level}, typed has {typed_classes}")
        for feat in covered_feats:
            feat_id = f"feat.{slug(feat)}"
            if feat_id not in typed_feats and feat_id.replace("gorgons-", "gorgon-s-") not in typed_feats:
                problems.append(f"{name}: source needs hasFeat {feat_id}, typed has {sorted(typed_feats)}")
        if has_channel and not typed_channel:
            problems.append(f"{name}: source needs channel class feature, typed has none")
        if has_wild_shape and not typed_wild_shape:
            problems.append(f"{name}: source needs wild shape class feature, typed has none")
        if has_arcane and not typed_arcane:
            problems.append(f"{name}: source needs arcane casting, typed has none")
        if has_proficiency and not rwp:
            problems.append(f"{name}: source needs weapon proficiency, requiredWeaponProficiency missing")
    return problems


def build_record(name, existing_by_norm, table_rows, blocks):
    treatments, support, choice, rwp, effects = META[name]
    block = blocks[name]
    row = table_rows[block["rowName"]]
    record_id = existing_by_norm.get(re.sub(r"[^a-z0-9]", "", canonical(name).lower()), f"feat.{slug(name)}")
    official = f"https://legacy.aonprd.com/coreRulebook/feats.html#{slug(name)}"
    record = {
        "id": record_id,
        "name": name,
        "catalogStatus": "resolved",
        "category": "general",
        "treatments": treatments,
        "supportStatus": SUPPORT[support],
        "prerequisites": {"all": PRE.get(name, [])},
        "effects": effects,
        "rulesText": (f"{block['intro']} {block['benefit']}" if block.get("intro")
                      else block["benefit"]),
        "sourceRef": [
            {
                "sourceId": "source.aon-feats",
                "section": "Table: Feats" if row["line"] < 207 else
                          ("Table: Item Creation Feats" if row["line"] < 217 else "Table: Metamagic Feats"),
                "txtLines": [row["line"], row["line"]],
                "entry": f"{name}: {row['prereq']}; {row['benefit']}",
                "officialUrl": official,
                "provenanceStatus": "resolved",
            },
            {
                "sourceId": "source.aon-feats",
                "section": block["headerText"],
                "txtLines": [block["headerLine"], block["endLine"]],
                "entry": (f"Prerequisites: {block['prereq']} Benefit: {block['benefit']}"
                          if block["prereq"] else f"Benefit: {block['benefit']}"),
                "officialUrl": official,
                "provenanceStatus": "resolved",
            },
        ],
    }
    if choice is not None:
        if choice["field"] not in CHOICE_FIELDS:
            raise SystemExit(f"bad choice field for {name}: {choice}")
        record["choice"] = choice
    if rwp:
        record["requiredWeaponProficiency"] = True
    if SUPPORT[support] == "partial":
        limitation = SUPPORT_LIMITATIONS.get(name)
        if not limitation:
            raise SystemExit(f"{name}: partial supportStatus requires supportLimitations")
        record["supportLimitations"] = limitation
    if "combatOption" in effects:
        # Combat-option slugs must reference the record's own id.
        record["effects"]["combatOption"] = record_id.removeprefix("feat.")
    special = block.get("special", "")
    if re.search(r"(gain|take) (this|the) feat multiple times", special, re.I) or \
            re.search(r"gain (Exotic Weapon Proficiency|Extra \w+|Rapid Reload|Greater Weapon Focus|Improved Critical) multiple times", special):
        if re.search(r"effects? stack\b", special, re.I):
            record["repeatable"] = True
        elif re.search(r"applies to a new|select a new", special, re.I):
            record["repeatableChoices"] = True
        else:
            raise SystemExit(f"{name}: multiple-selections Special without stack/new-target clause")
    return record


def validate(records, skills, classes, class_features):
    # Reuse the engine's stdlib prerequisite validator. The normal catalog
    # builder validates the complete fragments and provenance after this tool.
    sys.path.insert(0, str(ROOT))
    from monster_builder.catalog import CatalogError
    from monster_builder.npc_catalog import _validate_prerequisite

    ids = {record["id"] for record in records}
    problems = []
    for record in records:
        if record.get("supportStatus") == "partial" and not record.get("supportLimitations"):
            problems.append(f"{record['name']}: partial requires supportLimitations")
        try:
            _validate_prerequisite(record.get("prerequisites"), record["id"])
        except CatalogError as error:
            problems.append(str(error))
    for record in records:
        if record["name"] not in META:
            continue
        for expr in record["prerequisites"]["all"]:
            for key, operand in expr.items():
                if key == "hasFeat" and operand not in ids:
                    problems.append(f"{record['name']}: prerequisite target {operand} missing")
                if key == "skillRanksAtLeast":
                    for skill in operand:
                        if skill not in skills:
                            problems.append(f"{record['name']}: unknown skill {skill}")
                if key == "classLevelAtLeast":
                    for class_id in operand:
                        if class_id not in classes:
                            problems.append(f"{record['name']}: unknown class {class_id}")
                if key == "hasClassFeature" and operand not in class_features and operand not in KNOWN_FEATURE_GAPS:
                    problems.append(f"{record['name']}: unknown class feature {operand}")
        if not set(record["treatments"]) <= TREATMENTS:
            problems.append(f"{record['name']}: bad treatments {record['treatments']}")
        if record["supportStatus"] not in SUPPORT.values():
            problems.append(f"{record['name']}: bad supportStatus {record['supportStatus']}")
    return problems


def main():
    lines = FEATS_TXT.read_text().splitlines()
    table_rows, blocks = load_source_tables(lines)
    baseline = step4_baseline(table_rows, blocks)
    transitive = {"Greater Weapon Focus", "Improved Precise Shot", "Improved Shield Bash"}
    names = sorted(baseline | transitive)
    missing_meta = [n for n in names if n not in META]
    if missing_meta:
        raise SystemExit(f"no curated metadata for: {missing_meta}")
    missing_source = [n for n in names if n not in blocks or not blocks[n].get("rowName")]
    if missing_source:
        raise SystemExit(f"no source text for: {missing_source}")

    # Source-backed prerequisite assertions.
    problems = []
    for name in names:
        problems.extend(evidence_for(name, {"blocks": blocks, "pre": PRE}))
    problems.extend(audit_prereq_coverage(names, blocks, PRE))
    if problems:
        raise SystemExit("prerequisite audit failures:\n" + "\n".join(problems))

    fragment = json.loads(FRAGMENT.read_text())
    norm = lambda name: re.sub(r"[^a-z0-9]", "", canonical(name).lower())
    existing_by_norm = {}
    for record in fragment["records"]:
        existing_by_norm.setdefault(norm(record["name"]), record["id"])

    new_records = {n: build_record(n, existing_by_norm, table_rows, blocks) for n in names}
    # Rebuilt records supersede any same-feat variants (e.g. the scaffold's
    # "Armor Proficiency (Heavy)" duplicates); ids are reused where present.
    rebuilt_norm = {norm(name) for name in new_records}
    records = [r for r in fragment["records"] if norm(r["name"]) not in rebuilt_norm]
    records.extend(new_records.values())
    records.sort(key=lambda r: canonical(r["name"]).lower())

    skills = {r["id"] for r in json.loads((ROOT / "catalog/npc/skills.fragment.json").read_text())["records"]}
    classes = {r["id"] for r in json.loads((ROOT / "catalog/npc/classes.fragment.json").read_text())["records"]}
    class_features = {r["id"] for r in json.loads((ROOT / "catalog/npc/class-features.fragment.json").read_text())["records"]}
    problems = validate(records, skills, classes, class_features)
    if problems:
        raise SystemExit("validation failures:\n" + "\n".join(problems))

    baseline_ids = {new_records[n]["id"] for n in baseline}
    if len(baseline_ids) != 99:
        raise SystemExit(f"baseline count {len(baseline_ids)} != 99")
    added = sorted((n for n in new_records if existing_by_norm.get(norm(n)) is None),
                   key=slug)
    fragment["records"] = records
    FRAGMENT.write_text(json.dumps(fragment, indent=1, ensure_ascii=False) + "\n")
    print(f"baseline={len(baseline_ids)} transitive={len(transitive)} "
          f"added={len(added)} totalRecords={len(records)}")
    print("added:", ", ".join(added))


if __name__ == "__main__":
    main()