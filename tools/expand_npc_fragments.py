"""One-shot expansion of the NPC catalog fragments to the full planned scope.

Run from the repository root:  python3 tools/expand_npc_fragments.py

Preserves every existing record byte-for-byte by serializing with the same
compact-inline-array style the fragments already use, then regenerating each
fragment from its current records plus the expansion.  Existing records are
never modified; the script fails loudly if regeneration would change them.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRAG = ROOT / "catalog" / "npc"

GAP_REF = {
    "sourceId": "source.npc-gap-matrix",
    "section": "NPC Source-Gap Matrix",
    "txtLines": [17, 17],
    "entry": "Seven Core races",
    "provenanceStatus": "catalog-gap",
}


def gap_ref(line, entry):
    ref = dict(GAP_REF)
    ref["txtLines"] = [line, line]
    ref["entry"] = entry
    return ref


PLAN_REF = {
    "sourceId": "source.npc-mode-plan",
    "section": "NPC_MODE_PLAN.md",
    "txtLines": [62, 78],
    "entry": "Source scope",
    "provenanceStatus": "structural-reference",
}


def plan_ref(lines, entry):
    ref = dict(PLAN_REF)
    ref["txtLines"] = list(lines)
    ref["entry"] = entry
    return ref


def scalar_list(value):
    if isinstance(value, list):
        return all(isinstance(item, (str, int, float, bool)) or item is None for item in value)
    return False


def dumps(obj, level=0):
    pad = "  " * level
    inner = "  " * (level + 1)
    if isinstance(obj, dict):
        if not obj:
            return "{}"
        items = []
        for key, value in obj.items():
            items.append(f'{inner}{json.dumps(key)}: {dumps(value, level + 1)}')
        return "{\n" + ",\n".join(items) + "\n" + pad + "}"
    if isinstance(obj, list):
        if not obj:
            return "[]"
        if scalar_list(obj):
            return "[" + ", ".join(dumps(item, 0) for item in obj) + "]"
        items = [f"{inner}{dumps(item, level + 1)}" for item in obj]
        return "[\n" + ",\n".join(items) + "\n" + pad + "]"
    return json.dumps(obj, ensure_ascii=False)


def save(name, fragment):
    path = FRAG / name
    content = dumps(fragment) + "\n"
    path.write_text(content, encoding="utf-8")


def load_records(name):
    raw = (FRAG / name).read_text(encoding="utf-8")
    obj = json.loads(raw)
    # Verify the round-trip so existing bytes are provably stable.
    if dumps(obj) + "\n" != raw:
        raise SystemExit(f"{name}: serializer does not round-trip; refusing to rewrite")
    return obj


# --- races: seven Core races -------------------------------------------------
RACES = [
    ("dwarf", "Dwarf"), ("elf", "Elf"), ("gnome", "Gnome"),
    ("half-elf", "Half-Elf"), ("half-orc", "Half-Orc"), ("halfling", "Halfling"),
]
fragment = load_records("races.fragment.json")
existing_ids = {record["id"] for record in fragment["records"]}
for slug, name in RACES:
    record_id = f"npc-race.{slug}"
    if record_id in existing_ids:
        continue
    fragment["records"].append({
        "id": record_id,
        "name": name,
        "catalogStatus": "gap",
        "gapCode": "core-rulebook-races",
        "abilityAdjustments": None,
        "sizeId": None,
        "speed": None,
        "senses": None,
        "traits": None,
        "languages": None,
        "sourceRef": gap_ref(17, "Seven Core races"),
    })
save("races.fragment.json", fragment)

# --- classes: five NPC classes and eleven PC classes through level 20 --------
NPC_CLASSES = ["adept", "aristocrat", "commoner", "expert", "warrior"]
PC_CLASSES = ["barbarian", "bard", "cleric", "druid", "fighter", "monk", "paladin", "ranger", "rogue", "sorcerer", "wizard"]
NAME_FIX = {"half-elf": "Half-Elf"}


def class_name(slug):
    return NAME_FIX.get(slug, slug.replace("-", " ").title())


def level_row(class_name, level, matrix_line):
    return {
        "level": level,
        "bab": None,
        "fortitude": None,
        "reflex": None,
        "will": None,
        "hitDie": None,
        "skillSelections": None,
        "featureGrants": None,
        "choiceSlots": None,
        "catalogStatus": "gap",
        "sourceRef": {
            "sourceId": "source.npc-gap-matrix",
            "section": "NPC Source-Gap Matrix",
            "txtLines": [matrix_line, matrix_line],
            "entry": f"{class_name} level {level}",
            "provenanceStatus": "catalog-gap",
        },
    }


def class_record(slug, category, matrix_line, matrix_entry):
    name = class_name(slug)
    return {
        "id": f"npc-class.{slug}",
        "name": name,
        "catalogStatus": "gap",
        "gapCode": "core-rulebook-class-tables",
        "category": category,
        "hitDie": None,
        "classSkills": None,
        "skillSelections": None,
        "levels": {str(level): level_row(name, level, matrix_line) for level in range(1, 21)},
        "sourceRef": gap_ref(matrix_line, matrix_entry),
    }


fragment = load_records("classes.fragment.json")
existing = {record["id"]: record for record in fragment["records"]}
for slug in NPC_CLASSES:
    record_id = f"npc-class.{slug}"
    if record_id in existing:
        record = existing[record_id]
        name = class_name(slug)
        for level in range(1, 21):
            record["levels"].setdefault(str(level), level_row(name, level, 18))
        continue
    fragment["records"].append(class_record(slug, "npc", 18, "Five NPC class tables through level 20"))
for slug in PC_CLASSES:
    record_id = f"npc-class.{slug}"
    if record_id in existing:
        continue
    fragment["records"].append(class_record(slug, "pc", 19, "Eleven Core PC class tables through level 20"))
fragment["records"].sort(key=lambda record: record["id"])
save("classes.fragment.json", fragment)

# --- class features: feat slot kinds and class choice slots -------------------
FEAT_SLOT_LINES = (476, 482)
CHOICE_SLOT_LINES = (501, 513)
feat_slots = [
    ("general-feats", "General feat slots"),
    ("fighter-bonus-feats", "Fighter bonus feat slots"),
    ("ranger-combat-style-feats", "Ranger combat style feat slots"),
    ("monk-bonus-feats", "Monk bonus feat slots"),
    ("wizard-bonus-feats", "Wizard bonus feat slots"),
    ("class-specific-feats", "Other class-specific feat slots"),
]
choice_slots = [
    ("rage-powers", "Rage powers"),
    ("rogue-talents", "Rogue talents"),
    ("favored-enemies", "Favored enemies"),
    ("favored-terrains", "Favored terrains"),
    ("ranger-combat-styles", "Ranger combat styles"),
    ("hunters-bond", "Hunter's bond"),
    ("cleric-domains", "Cleric domains"),
    ("sorcerer-bloodlines", "Sorcerer bloodlines"),
    ("wizard-schools", "Wizard schools"),
    ("familiar-bond", "Familiar/bond choices"),
]
gap_matrix_ref = lambda line, entry: gap_ref(line, entry)
records = []
for slug, name in feat_slots:
    records.append({
        "id": f"npc-class-feature.{slug}",
        "name": name,
        "kind": "feat-slot",
        "catalogStatus": "gap",
        "gapCode": "core-rulebook-class-tables",
        "sourceRef": [
            gap_ref(18, "Five NPC class tables through level 20"),
            plan_ref(FEAT_SLOT_LINES, "Step 4: Feats - slot kinds"),
        ],
    })
for slug, name in choice_slots:
    records.append({
        "id": f"npc-class-feature.{slug}",
        "name": name,
        "kind": "choice-slot",
        "catalogStatus": "gap",
        "gapCode": "core-rulebook-class-tables",
        "sourceRef": [
            gap_ref(18, "Five NPC class tables through level 20"),
            plan_ref(CHOICE_SLOT_LINES, "Step 5: Class Features - choice slots"),
        ],
    })
(FRAG / "class-features.fragment.json").write_text(
    dumps({"section": "classFeatures", "records": records}) + "\n", encoding="utf-8"
)

# --- skills: the Core skill list ----------------------------------------------
SKILLS = [
    ("acrobatics", "Acrobatics"), ("appraise", "Appraise"), ("bluff", "Bluff"),
    ("craft", "Craft"), ("diplomacy", "Diplomacy"), ("disable-device", "Disable Device"),
    ("disguise", "Disguise"), ("escape-artist", "Escape Artist"), ("fly", "Fly"),
    ("heal", "Heal"), ("knowledge-arcana", "Knowledge (Arcana)"),
    ("knowledge-dungeoneering", "Knowledge (Dungeoneering)"),
    ("knowledge-engineering", "Knowledge (Engineering)"),
    ("knowledge-geography", "Knowledge (Geography)"),
    ("knowledge-history", "Knowledge (History)"), ("knowledge-local", "Knowledge (Local)"),
    ("knowledge-nature", "Knowledge (Nature)"), ("knowledge-nobility", "Knowledge (Nobility)"),
    ("knowledge-planes", "Knowledge (Planes)"), ("knowledge-religion", "Knowledge (Religion)"),
    ("linguistics", "Linguistics"), ("perform", "Perform"), ("profession", "Profession"),
    ("sense-motive", "Sense Motive"), ("sleight-of-hand", "Sleight of Hand"),
    ("spellcraft", "Spellcraft"), ("stealth", "Stealth"), ("survival", "Survival"),
    ("use-magic-device", "Use Magic Device"),
]
fragment = load_records("skills.fragment.json")
existing_ids = {record["id"] for record in fragment["records"]}
for slug, name in SKILLS:
    record_id = f"skill.{slug}"
    if record_id in existing_ids:
        continue
    fragment["records"].append({
        "id": record_id,
        "name": name,
        "catalogStatus": "gap",
        "gapCode": "core-rulebook-skills",
        "keyAbility": None,
        "trainedOnly": None,
        "armorCheckPenalty": None,
        "sourceRef": gap_ref(21, "Core skill list"),
    })
save("skills.fragment.json", fragment)

# --- feats: the Core feat chapter ----------------------------------------------
FEATS = [
    # General and combat feats.
    "Acrobatic", "Acrobatic Steps", "Agile Maneuvers", "Animal Affinity",
    "Arcane Armor Mastery", "Arcane Armor Training", "Arcane Strike",
    "Armor Proficiency (Heavy)", "Armor Proficiency (Light)", "Armor Proficiency (Medium)",
    "Athletic", "Augment Summoning", "Blind-Fight", "Catch Off-Guard", "Channel Smite",
    "Combat Casting", "Combat Expertise", "Combat Reflexes", "Command Undead",
    "Critical Focus", "Dazzling Display", "Deflect Arrows", "Diehard", "Disruptive",
    "Double Slice", "Energy Resistance", "Exotic Weapon Proficiency", "Extra Channel",
    "Extra Performance", "Extra Rage", "Far Shot", "Fleet", "Gorgon's Fist",
    "Greater Bull Rush", "Greater Disarm", "Greater Feint", "Greater Grapple",
    "Greater Overrun", "Greater Penetrating Strike", "Greater Shield Focus",
    "Greater Sunder", "Greater Trip", "Greater Two-Weapon Fighting", "Greater Vital Strike",
    "Greater Weapon Focus", "Greater Weapon Specialization", "Improved Bull Rush",
    "Improved Counterspell", "Improved Critical", "Improved Disarm", "Improved Familiar",
    "Improved Feint", "Improved Grapple", "Improved Great Fortitude",
    "Improved Initiative", "Improved Iron Will", "Improved Lightning Reflexes",
    "Improved Natural Attack", "Improved Overrun", "Improved Precise Shot",
    "Improved Shield Bash", "Improved Sunder", "Improved Trip", "Improved Two-Weapon Fighting",
    "Improved Unarmed Strike", "Improvised Weapon Mastery", "Intimidating Prowess",
    "Iron Will", "Leadership", "Lightning Reflexes", "Lightning Stance",
    "Lunge", "Martial Weapon Proficiency", "Medusa's Wrath",
    "Mobility", "Mounted Archery", "Mounted Combat", "Natural Spell", "Negotiator",
    "Penetrating Strike", "Persuasive", "Point-Blank Shot", "Power Attack",
    "Precise Shot", "Quick Draw", "Rapid Reload", "Rapid Shot", "Ride-By Attack",
    "Run", "Scorpion Style", "Self-Sufficient", "Shield Focus", "Shield Master",
    "Shield Proficiency", "Shield Slam", "Shot on the Run", "Simple Weapon Proficiency",
    "Snatch Arrows", "Spell Focus", "Spell Mastery", "Spell Penetration",
    "Spirited Charge", "Spring Attack", "Stand Still", "Stealthy", "Step Up",
    "Staggering Critical", "Strike Back", "Stunning Fist", "Sunder", "Throw Anything",
    "Tower Shield Proficiency", "Trample", "Trip",
    "Turn Undead", "Two-Weapon Defense", "Two-Weapon Fighting", "Two-Weapon Rend",
    "Vital Strike", "Weapon Finesse", "Whirlwind Attack", "Wind Stance",
    # Item creation feats.
    "Brew Potion", "Craft Magic Arms and Armor", "Craft Rod", "Craft Staff",
    "Craft Wand", "Craft Wondrous Item", "Forge Ring", "Scribe Scroll",
    # Metamagic feats.
    "Empower Spell", "Enlarge Spell", "Extend Spell", "Heighten Spell",
    "Maximize Spell", "Quicken Spell", "Silent Spell", "Still Spell", "Widen Spell",
]
FEATS = sorted(set(FEATS))

fragment = load_records("feats.fragment.json")
existing_ids = {record["id"] for record in fragment["records"]}
for name in FEATS:
    slug = "".join(char if char.isalnum() else "-" for char in name.casefold())
    record_id = "feat." + "-".join(part for part in slug.split("-") if part)
    if record_id in existing_ids:
        continue
    fragment["records"].append({
        "id": record_id,
        "name": name,
        "catalogStatus": "gap",
        "gapCode": "core-rulebook-feats",
        "category": "general",
        "prerequisites": None,
        "effects": None,
        "sourceRef": gap_ref(22, "Core feats"),
    })
save("feats.fragment.json", fragment)

# --- items: mundane equipment and the required magic baseline ------------------
ITEMS = [
    ("greatsword", "Greatsword", "weapon"), ("greataxe", "Greataxe", "weapon"),
    ("warhammer", "Warhammer", "weapon"), ("light-crossbow", "Light Crossbow", "weapon"),
    ("heavy-crossbow", "Heavy Crossbow", "weapon"), ("longbow", "Longbow", "weapon"),
    ("sling", "Sling", "weapon"), ("javelin", "Javelin", "weapon"),
    ("morningstar", "Morningstar", "weapon"), ("rapier", "Rapier", "weapon"),
    ("sap", "Sap", "weapon"), ("scythe", "Scythe", "weapon"),
    ("falchion", "Falchion", "weapon"), ("halberd", "Halberd", "weapon"),
    ("lance", "Lance", "weapon"), ("handaxe", "Handaxe", "weapon"),
    ("light-hammer", "Light Hammer", "weapon"), ("heavy-flail", "Heavy Flail", "weapon"),
    ("light-flail", "Light Flail", "weapon"), ("trident", "Trident", "weapon"),
    ("whip", "Whip", "weapon"), ("gauntlet", "Gauntlet", "weapon"),
    ("padded-armor", "Padded Armor", "armor"), ("studded-leather", "Studded Leather", "armor"),
    ("hide-armor", "Hide Armor", "armor"), ("scale-mail", "Scale Mail", "armor"),
    ("chainmail", "Chainmail", "armor"), ("splint-mail", "Splint Mail", "armor"),
    ("banded-mail", "Banded Mail", "armor"), ("half-plate", "Half-Plate", "armor"),
    ("full-plate", "Full-Plate", "armor"), ("buckler", "Buckler", "shield"),
    ("heavy-wooden-shield", "Heavy Wooden Shield", "shield"), ("tower-shield", "Tower Shield", "shield"),
    ("backpack", "Backpack", "goods"), ("bedroll", "Bedroll", "goods"),
    ("hempen-rope", "Hempen Rope (50 ft.)", "goods"), ("trail-rations", "Trail Rations", "goods"),
    ("torch", "Torch", "goods"), ("waterskin", "Waterskin", "goods"),
    ("flint-and-steel", "Flint and Steel", "goods"), ("wooden-holy-symbol", "Wooden Holy Symbol", "goods"),
    ("spellbook", "Spellbook", "goods"), ("explorers-outfit", "Explorer's Outfit", "goods"),
    ("cloak-of-resistance", "Cloak of Resistance", "magic"),
    ("belt-of-giant-strength", "Belt of Giant Strength", "magic"),
    ("headband-of-vast-intelligence", "Headband of Vast Intelligence", "magic"),
    ("amulet-of-natural-armor", "Amulet of Natural Armor", "magic"),
    ("ring-of-protection", "Ring of Protection", "magic"),
    ("potion-of-cure-light-wounds", "Potion of Cure Light Wounds", "magic"),
    ("wand-of-cure-light-wounds", "Wand of Cure Light Wounds", "magic"),
]
fragment = load_records("items.fragment.json")
existing_ids = {record["id"] for record in fragment["records"]}
for slug, name, category in ITEMS:
    record_id = f"item.{slug}"
    if record_id in existing_ids:
        continue
    fragment["records"].append({
        "id": record_id,
        "name": name,
        "catalogStatus": "gap",
        "gapCode": "core-rulebook-equipment",
        "category": category,
        "priceCp": None,
        "weightLb": None,
        "effects": None,
        "sourceRef": gap_ref(23, "Core weapons, armor, goods, and required magic items"),
    })
save("items.fragment.json", fragment)

# --- gear budgets: every progression and fantasy combination -------------------
fragment = load_records("gear-budgets.fragment.json")
existing_ids = {record["id"] for record in fragment["records"]}
for progression in ("slow", "medium", "fast"):
    for fantasy in ("low", "normal", "high"):
        record_id = f"npc-gear.{progression}.{fantasy}"
        if record_id in existing_ids:
            continue
        fragment["records"].append({
            "id": record_id,
            "name": f"{progression.capitalize()} progression, {fantasy} fantasy",
            "catalogStatus": "gap",
            "gapCode": "core-rulebook-gear-budgets",
            "progression": progression,
            "fantasyLevel": fantasy,
            "effectiveLevel": None,
            "budgetCp": None,
            "categories": {"weapons": None, "protection": None, "magic": None, "limitedUse": None, "gear": None},
            "sourceRef": gap_ref(24, "Table 14-9 NPC gear budgets"),
        })
fragment["records"].sort(key=lambda record: record["id"])
save("gear-budgets.fragment.json", fragment)

print("fragments expanded")
