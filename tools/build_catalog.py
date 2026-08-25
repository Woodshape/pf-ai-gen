import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UNCHAINED = ROOT / "Pathfinder Unchained.txt"
CORE = ROOT / "Pathfinder_RPG_Core_Rulebook.txt"
BESTIARY = ROOT / "beastiary.txt"
OUT = ROOT / "catalog/catalog-v1.json"

unchained_lines = UNCHAINED.read_text().splitlines()
core_lines = CORE.read_text().splitlines()
step6_page_by_line = {}
current_step6_page = None
for index, line in enumerate(unchained_lines, 1):
    stripped = line.strip()
    if stripped.isdigit() and 218 <= int(stripped) <= 227:
        current_step6_page = int(stripped)
    step6_page_by_line[index] = current_step6_page


def step6_page(line_number):
    return step6_page_by_line.get(line_number) or 218
unchained_hash = hashlib.sha256(UNCHAINED.read_bytes()).hexdigest()
core_hash = hashlib.sha256(CORE.read_bytes()).hexdigest()
bestiary_hash = hashlib.sha256(BESTIARY.read_bytes()).hexdigest()


def source_ref(*, source_id, file, sha256, section, txt_lines, printed_pages=None,
               viewer_pages=None, entry=None, table=None, official_url=None,
               provenance_status=None):
    result = {
        "sourceId": source_id,
        "file": file,
        "sha256": sha256,
        "section": section,
        "txtLines": list(txt_lines),
    }
    if printed_pages is not None and all(page is not None for page in printed_pages):
        result["printedPages"] = list(printed_pages)
    if viewer_pages is not None:
        result["viewerPages"] = list(viewer_pages)
    if entry is not None:
        result["entry"] = entry
    if table is not None:
        result["table"] = table
    if official_url is not None:
        result["officialUrl"] = official_url
    if provenance_status is not None:
        result["provenanceStatus"] = provenance_status
    return result


def unchained_ref(section, line, printed, *, entry=None, table=None):
    return source_ref(
        source_id="pathfinder-unchained-txt",
        file="Pathfinder Unchained.txt",
        sha256=unchained_hash,
        section=section,
        txt_lines=(line, line),
        printed_pages=(printed,),
        viewer_pages=(printed - 193,),
        entry=entry,
        table=table,
    )


def bestiary_ref(entry):
    return source_ref(
        source_id="bestiary-txt",
        file="beastiary.txt",
        sha256=bestiary_hash,
        section="Bestiary Table 3-1",
        txt_lines=(149, 159),
        printed_pages=(302,),
        viewer_pages=(2,),
        entry=entry,
        table="Table 3-1: Natural Attacks by Size",
    )


def external_ref(source_id, book, page, url):
    return source_ref(
        source_id=source_id,
        file=None,
        sha256=None,
        section="spell metadata",
        txt_lines=(),
        printed_pages=(page,),
        official_url=url,
        provenance_status="external-source-not-vendored",
    )


def cr_value(value):
    return 0.5 if value == "1/2" else int(value)


def number(value):
    return int(value.replace("−", "-").replace("–", "-"))


# The array tables are transcribed from their contiguous source rows. Keeping
# the rows as data makes the catalog auditable and avoids runtime PDF parsing.
main_starts = [375, 557, 703]  # zero-based indexes immediately before CR 1/2
attack_starts = [449, 596, 742]
array_names = ["combatant", "expert", "spellcaster"]
arrays = {}
for name, main_start, attack_start, printed in zip(
    array_names, main_starts, attack_starts, (198, 200, 202)
):
    main = {}
    for index in range(main_start, main_start + 31):
        line = unchained_lines[index].strip()
        match = re.match(
            r"^(1/2|\d+) (\d+), t (\d+), f (\d+) ([+−-]\d+) "
            r"([+−-]\d+) ([+−-]\d+) (\d+) (\d+) (\d+) (\d+) "
            r"([+−-]\d+), ([+−-]\d+), ([+−-]\d+) \+?(\d+) \((\d+)\) "
            r"\+?(\d+) \((\d+)\) (.*)$",
            line,
        )
        if not match:
            raise ValueError(f"Cannot parse array row {index + 1}: {line}")
        values = match.groups()
        cr = values[0]
        table_number = {"combatant": 1, "expert": 3, "spellcaster": 5}[name]
        row = {
            "cr": cr_value(cr),
            "ac": number(values[1]),
            "touchAC": number(values[2]),
            "flatFootedAC": number(values[3]),
            "fortitude": number(values[4]),
            "reflex": number(values[5]),
            "will": number(values[6]),
            "cmd": number(values[7]),
            "hp": number(values[8]),
            "abilityDC": number(values[9]),
            "spellDC": number(values[10]),
            "abilityModifiers": [number(values[11]), number(values[12]), number(values[13])],
            "masterBonus": number(values[14]),
            "masterCount": int(values[15]),
            "goodBonus": number(values[16]),
            "goodCount": int(values[17]),
            "options": [],
            "sourceRef": unchained_ref(
                "Step 1: Array", index + 1, printed,
                entry=f"CR {cr}",
                table=f"Table 5-{table_number}: {name.title()} Main Statistics",
            ),
        }
        for count, category in re.findall(
            r"(\d+) (combat|magic|social|universal|any)", values[18]
        ):
            row["options"].append({"category": category, "count": int(count)})
        main[cr] = row

    attack = {}
    for index in range(attack_start, attack_start + 31):
        line = unchained_lines[index].strip()
        match = re.match(
            r"^(1/2|\d+) (.*?)\s*\((\d+)\) (.*?)\s*\((\d+)\) "
            r"(.*?)\s*\((\d+)\) (.*?)\s*\((\d+)\)$",
            line,
        )
        if not match:
            raise ValueError(f"Cannot parse attack row {index + 1}: {line}")
        cr, high, high_damage, low, low_damage, two, two_damage, three, three_damage = match.groups()
        table_number = {"combatant": 2, "expert": 4, "spellcaster": 6}[name]

        def weapon_profile(text, damage):
            bonuses = [number(value) for value in re.findall(r"[+\-−–]\d+", text)]
            if not bonuses:
                raise ValueError(f"Cannot parse weapon attack bonuses: {text}")
            return {
                "attackBonuses": bonuses,
                "attackBonusText": text.replace("−", "-"),
                "averageDamage": int(damage),
                "entries": [{"count": 1, "attackBonuses": bonuses, "averageDamage": int(damage)}],
            }

        def natural_profile(text, trailing_damage):
            entries = []
            complete_text = f"{text} ({trailing_damage})"
            for count, bonus, damage_value in re.findall(r"(\d+)\s+at\s+([+\-−–]\d+)\s*\((\d+)\)", complete_text):
                entry = {"count": int(count), "attackBonuses": [number(bonus)], "averageDamage": int(damage_value)}
                entries.append(entry)
            if not entries:
                raise ValueError(f"Cannot parse natural attack profile: {complete_text}")
            return {
                "attackBonuses": [bonus for entry in entries for bonus in entry["attackBonuses"] * entry["count"]],
                "attackBonusText": complete_text.replace("−", "-"),
                "averageDamage": entries[0]["averageDamage"],
                "entries": entries,
            }

        attack[cr] = {
            "cr": cr_value(cr),
            "weapon": {"high": weapon_profile(high, high_damage), "low": weapon_profile(low, low_damage)},
            "natural": {"two": natural_profile(two, two_damage), "three": natural_profile(three, three_damage)},
            "sourceRef": unchained_ref(
                "Step 1: Array", index + 1, printed + 1,
                entry=f"CR {cr}",
                table=f"Table 5-{table_number}: {name.title()} Attack Statistics",
            ),
        }
    arrays[name] = {
        "id": f"array.{name}",
        "name": name.title(),
        "mainStatistics": main,
        "attackStatistics": attack,
    }

# Table 5-9 damage conversion.
damage_table = {}
damage_start = next(
    index for index, line in enumerate(unchained_lines)
    if line.startswith("Table 5–9: Damage Dice Values")
) + 2
dice_names = ["d4", "d6", "d8", "d10", "d12", "2d6", "3d6"]
for index in range(damage_start, damage_start + 33):
    line = unchained_lines[index].strip()
    match = re.match(r"^(\d+)–(\d+) (.*)$", line)
    if not match:
        raise ValueError(f"Cannot parse damage row {index + 1}: {line}")
    low, high, expression_text = match.groups()
    expressions = re.findall(r"(?:(?:\d+d\d+)|d\d+)(?:[+−-]\d+)?", expression_text)
    damage_table[f"{low}-{high}"] = {
        "min": int(low),
        "max": int(high),
        "expressions": dict(zip(dice_names, [value.replace("−", "-") for value in expressions])),
        "sourceRef": unchained_ref(
            "Step 9: Damage", index + 1, 241,
            entry=f"{low}–{high}", table="Table 5-9: Damage Dice Values",
        ),
    }


def slug(value):
    return re.sub(r"[^a-z0-9]+", "-", value.lower().replace("’", "'" )).strip("-")


def normalized_spell_name(value):
    value = value.lower().replace("’", "'").replace("–", "-")
    value = re.sub(r"\b(empowered|maximized|quickened|widened|extended|heightened)\s+", "", value)
    value = re.sub(r"\s*(?:apg|um|uc|acg)\b", "", value)
    return re.sub(r"\s+", " ", value).strip(" .")


# Issue 09's source-backed APG/UM/UC inventory and the five ACG follow-ups.
noncore = [
    ("apg", "Winds of Vengeance", 256, {"cleric": 9, "druid": 9, "sorcerer": 9, "wizard": 9}),
    ("apg", "Ant Haul", 201, {"alchemist": 1, "cleric": 1, "druid": 1, "ranger": 1, "summoner": 1, "sorcerer": 1, "wizard": 1}),
    ("apg", "Vomit Swarm", 254, {"alchemist": 2, "witch": 2}),
    ("apg", "Dragon’s Breath", 217, {"alchemist": 4, "sorcerer": 4, "wizard": 4}),
    ("apg", "Twin Form", 252, {"alchemist": 6}),
    ("apg", "Fiery Body", 221, {"sorcerer": 9, "wizard": 9}),
    ("apg", "Blessing of Fervor", 205, {"cleric": 4}),
    ("apg", "Draconic Reservoir", 217, {"alchemist": 3, "sorcerer": 3, "wizard": 3}),
    ("apg", "Expeditious Excavation", 220, {"druid": 1, "sorcerer": 1, "wizard": 1}),
    ("apg", "Elemental Touch", 218, {"alchemist": 2, "sorcerer": 2, "wizard": 2}),
    ("apg", "Elemental Aura", 218, {"alchemist": 3, "sorcerer": 3, "wizard": 3}),
    ("apg", "Ball Lightning", 204, {"druid": 4, "sorcerer": 4, "wizard": 4}),
    ("apg", "Wall of Suppression", 255, {"sorcerer": 9, "wizard": 9}),
    ("apg", "Weapon of Awe", 256, {"cleric": 2, "inquisitor": 2, "paladin": 2}),
    ("apg", "Grace", 226, {"cleric": 2, "paladin": 1}),
    ("apg", "Spiritual Ally", 246, {"cleric": 4}),
    ("apg", "Hydraulic Push", 228, {"druid": 1, "sorcerer": 1, "wizard": 1}),
    ("apg", "Touch of the Sea", 250, {"alchemist": 1, "druid": 1, "sorcerer": 1, "wizard": 1}),
    ("apg", "Fluid Form", 223, {"alchemist": 4, "sorcerer": 6, "wizard": 6}),
    ("apg", "Lead Blades", 230, {"ranger": 1}),
    ("um", "Corrosive Touch", 213, {"magus": 1, "summoner": 1, "sorcerer": 1, "wizard": 1}),
    ("um", "Acidic Spray", 204, {"magus": 5, "sorcerer": 5, "wizard": 5}),
    ("um", "Corrosive Consumption", 212, {"magus": 5, "sorcerer": 5, "wizard": 5}),
    ("um", "Caustic Eruption", 210, {"sorcerer": 7, "wizard": 7}),
    ("um", "Frostbite", 221, {"druid": 1, "magus": 1, "witch": 1}),
    ("um", "Anticipate Peril", 206, {"alchemist": 1, "bard": 1, "ranger": 1, "sorcerer": 1, "wizard": 1}),
    ("um", "Unprepared Combatant", 246, {"bard": 1, "witch": 1, "sorcerer": 1, "wizard": 1}),
    ("um", "Prediction of Failure", 232, {"witch": 8, "sorcerer": 8, "wizard": 8}),
    ("um", "Overwhelming Presence", 230, {"bard": 6, "cleric": 9, "inquisitor": 6, "sorcerer": 9, "wizard": 9}),
    ("um", "Serenity", 236, {"bard": 4, "cleric": 5, "sorcerer": 6, "wizard": 6}),
    ("um", "Symbol of Mirroring", 241, {"witch": 2, "sorcerer": 2, "wizard": 2}),
    ("um", "Symbol of Slowing", 242, {"cleric": 4, "witch": 4}),
    ("um", "Symbol of Strife", 242, {"cleric": 9, "witch": 9}),
    ("um", "Symbol of Vulnerability", 243, {"cleric": 9, "witch": 9}),
    ("um", "Ear-Piercing Scream", 218, {"bard": 1, "inquisitor": 1, "witch": 1, "sorcerer": 1, "wizard": 1}),
    ("uc", "Debilitating Portent", 227, {"cleric": 4, "witch": 4}),
    ("uc", "Jolting Portent", 232, {"cleric": 7}),
    ("uc", "Pellet Blast", 238, {"magus": 4, "summoner": 3, "sorcerer": 3, "wizard": 3}),
    ("uc", "Wreath of Blades", 249, {"magus": 4, "summoner": 5, "witch": 5, "sorcerer": 5, "wizard": 5}),
]
acg = [
    ("acg", "Long Arm", None, {"alchemist": 1, "bloodrager": 1, "magus": 1, "sorcerer": 1, "wizard": 1, "summoner": 1, "witch": 1}),
    ("acg", "Stricken Heart", None, {"inquisitor": 2, "shaman": 3, "sorcerer": 2, "wizard": 2, "witch": 2}),
    ("acg", "Disguise Weapon", None, {"bard": 1, "magus": 1, "sorcerer": 1, "wizard": 1, "witch": 1}),
    ("acg", "Molten Orb", None, {"bloodrager": 2, "magus": 2, "sorcerer": 2, "wizard": 2, "witch": 2}),
    ("acg", "Heart of the Metal", None, {"magus": 3, "sorcerer": 3, "wizard": 3, "witch": 3}),
]

# Find list memberships directly in the local Step-6 source.
list_memberships = {}
current_list = None
for line_number, line in enumerate(unchained_lines, 1):
    if not 2136 <= line_number <= 3131:
        continue
    header = re.match(r"^([A-Za-z][A-Za-z ]+) Spell List$", line.strip())
    if header:
        current_list = header.group(1).lower().replace(" ", "-")
        current_list = {"ransmutation": "transmutation", "ravel": "travel", "rickery": "trickery"}.get(current_list, current_list)
        continue
    if current_list:
        normalized_line = normalized_spell_name(line)
        for _, name, _, _ in noncore + acg:
            if normalized_spell_name(name) in normalized_line:
                list_memberships.setdefault(normalized_spell_name(name), set()).add(current_list)


# A few extracted rows wrap the spell name over a page/column boundary. These
# memberships are still directly visible in the local Step-6 table and are
# recorded explicitly rather than inferred from a missing token.
list_memberships.update({
    "vomit swarm": {"alchemy"},
    "wall of suppression": {"protection"},
    "weapon of awe": {"strength"},
    "hydraulic push": {"water"},
    "touch of the sea": {"water"},
    "fluid form": {"water"},
    "corrosive consumption": {"acid"},
    "prediction of failure": {"divination", "knowledge"},
    "symbol of mirroring": {"rune"},
    "symbol of vulnerability": {"rune"},
    "ear-piercing scream": {"sonic"},
    "pellet blast": {"metal"},
})


def first_step6_line(name):
    normalized = normalized_spell_name(name)
    for line_number, line in enumerate(unchained_lines, 1):
        if 2136 <= line_number <= 3131 and normalized in normalized_spell_name(line):
            return line_number
    return None


def official_spell_url(book, name):
    # The list pages are the stable primary-source URLs used by Issue 09.
    return {
        "apg": "https://legacy.aonprd.com/advancedPlayersGuide/advancedSpellLists.html",
        "um": "https://legacy.aonprd.com/ultimateMagic/ultimateMagicSpellLists.html",
        "uc": "https://legacy.aonprd.com/ultimateCombat/ultimateCombatSpellLists.html",
        "acg": "https://legacy.aonprd.com/advancedclassguide/spells/spellLists.html",
    }[book]


spells = {}
for book, name, page, levels in noncore + acg:
    line_number = first_step6_line(name)
    source_refs = []
    if line_number:
        source_refs.append(
            unchained_ref("Step 6: Spells", line_number, step6_page(line_number), entry=name, table="Step-6 list")
        )
    source_id = {
        "apg": "advanced-players-guide",
        "um": "ultimate-magic",
        "uc": "ultimate-combat",
        "acg": "advanced-class-guide",
    }[book]
    source_refs.append(
        external_ref(source_id, book.upper(), page, official_spell_url(book, name))
    )
    spell_id = f"spell.{book}.{slug(name)}"
    spells[spell_id] = {
        "id": spell_id,
        "name": name,
        "sourceBook": book.upper(),
        "sourceRef": source_refs,
        "levelsByClass": levels,
        "highest": max(levels.values()),
        "listMemberships": sorted(list_memberships.get(normalized_spell_name(name), set())),
        "aliases": [],
        "metamagicVariants": [],
        "catalogStatus": "external-source-not-vendored",
    }

# Core class lists: metadata only, with local TXT provenance. The extracted
# file repeats printed page numbers, so retain the nearest page header rather
# than assigning every entry to the first page of the excerpt.
core_page_by_line = {}
current_core_page = None
for index, line in enumerate(core_lines, 1):
    stripped = line.strip()
    if stripped.isdigit() and 224 <= int(stripped) <= 239:
        current_core_page = int(stripped)
    core_page_by_line[index] = current_core_page
core_spells = {}
class_header = re.compile(r"^[A-Za-z/ ]+ speLLs$|^[A-Za-z/ ]+ Spells$")
level_header = re.compile(r"^(\d+)(?:st|nd|rd|th)-Level (.+?) Spells(?: \(.+\))?$")
current_class = None
current_level = None
for line_number, line in enumerate(core_lines, 1):
    stripped = line.strip()
    if class_header.match(stripped):
        current_class = stripped.replace("speLLs", "").replace("Spells", "").strip().lower()
        current_level = None
        continue
    level_match = level_header.match(stripped)
    if level_match and current_class:
        current_level = int(level_match.group(1))
        continue
    if not current_class or current_level is None or ":" not in stripped:
        continue
    spell_name = stripped.split(":", 1)[0].strip()
    if not spell_name or len(spell_name) > 80 or spell_name[0].isdigit():
        continue
    spell_name = re.sub(r"[MF]$", "", spell_name).strip()
    classes = ["sorcerer", "wizard"] if current_class == "sorcerer/wizard" else [current_class]
    spell_id = f"spell.core.{slug(spell_name)}"
    record = core_spells.setdefault(
        spell_id,
        {
            "id": spell_id,
            "name": spell_name,
            "sourceBook": "CORE",
            "sourceRef": [],
            "levelsByClass": {},
            "highest": 0,
            "listMemberships": [],
            "aliases": [],
            "metamagicVariants": [],
            "catalogStatus": "resolved",
        },
    )
    for class_name in classes:
        record["levelsByClass"][class_name] = current_level
    record["highest"] = max(record["levelsByClass"].values())
    record["sourceRef"].append(
        source_ref(
            source_id="pathfinder-core-txt",
            file="Pathfinder_RPG_Core_Rulebook.txt",
            sha256=core_hash,
            section="Core Rulebook spell list",
            txt_lines=(line_number, line_number),
            printed_pages=((core_page_by_line.get(line_number) or 224),),
            viewer_pages=(((core_page_by_line.get(line_number) or 224) - 223),),
            entry=spell_name,
            provenance_status="local-source",
        )
    )
spells.update(core_spells)

# Keep spell-list source text separate from spell identity/metadata.
spell_lists = {}
current_list = None
for line_number, line in enumerate(unchained_lines, 1):
    if not 2230 <= line_number <= 3131:
        continue
    header = re.match(r"^([A-Za-z][A-Za-z ]+) Spell List$", line.strip())
    if header:
        current_list = header.group(1).lower().replace(" ", "-")
        current_list = {"ransmutation": "transmutation", "ravel": "travel", "rickery": "trickery"}.get(current_list, current_list)
        spell_lists[current_list] = {
            "id": f"spell-list.{current_list}",
            "name": header.group(1),
            "bands": {},
            "sourceRef": unchained_ref(
                "Step 6: Spells", line_number, step6_page(line_number),
                entry=header.group(1), table="Spell Lists",
            ),
        }
        continue
    if not current_list:
        continue
    match = re.match(r"^(0–3|4–7|8–11|12–15|16\+) (.*)$", line.strip())
    if match and "Benefit:" not in line:
        band, rest = match.groups()
        # Source extraction collapses columns; preserve it as source text rather
        # than trying to manufacture IDs from metamagic/descriptor variants.
        spell_lists[current_list]["bands"][band] = {
            "sourceText": rest.strip(),
            "sourceRef": unchained_ref(
                "Step 6: Spells", line_number, step6_page(line_number),
                entry=band, table=f"{current_list} spell list",
            ),
        }

# Base grafts and option data needed by the first executable slice.
type_specs = {
    "aberration": (["darkvision 60 ft."], {"will": 2}, []),
    "animal": (["low-light vision"], {"fortitude": 2, "reflex": 2}, ["set-intelligence-negative"]),
    "construct": (["darkvision 60 ft.", "low-light vision", "construct immunities"], {"fortitude": -2, "reflex": -2, "will": -2, "attackBonus": 2}, []),
    "dragon": (["darkvision 60 ft.", "low-light vision", "immune to paralysis and sleep"], {"lowSave": 2, "attackBonus": 2}, []),
    "fey": (["low-light vision"], {"reflex": 2, "will": 2, "attackBonus": -2}, []),
    "humanoid": ([], {"oneSave": 2}, []),
    "magical-beast": (["darkvision 60 ft.", "low-light vision"], {"fortitude": 2, "reflex": 2, "attackBonus": 2}, []),
    "monstrous-humanoid": (["darkvision 60 ft."], {"reflex": 2, "will": 2, "attackBonus": 2}, ["additional-good-skill"]),
    "ooze": (["blind", "blindsight", "mindless", "ooze immunities", "not subject to critical hits or flanking"], {"fortitude": 2, "reflex": -2, "will": -2}, []),
    "outsider": (["darkvision 60 ft."], {"oneSave": 2, "attackBonus": 2}, []),
    "plant": (["low-light vision", "plant immunities"], {"fortitude": 2}, []),
    "undead": (["darkvision 60 ft.", "undead immunities"], {"will": 2}, []),
    "vermin": (["darkvision 60 ft.", "mindless"], {"fortitude": 2}, []),
}
type_lines = {
    "aberration": 852, "animal": 858, "construct": 866, "dragon": 879,
    "fey": 891, "humanoid": 905, "magical-beast": 914, "monstrous-humanoid": 921,
    "ooze": 930, "outsider": 943, "plant": 953, "undead": 960, "vermin": 969,
}
creature_types = {}
for key, (traits, adjustments, elective) in type_specs.items():
    creature_types[f"graft.creature-type.{key}"] = {
        "id": f"graft.creature-type.{key}",
        "name": key.replace("-", " ").title(),
        "automaticTraits": traits,
        "statisticAdjustments": adjustments,
        "electiveAdjustments": elective,
        "sourceRef": unchained_ref("Step 2: Creature Type Graft", type_lines[key], 204, entry=key.title()),
    }

size_specs = [
    ("fine", 2, None, {"touchAC": 8, "flatFootedAC": 8, "cmb": -16, "cmd": -8}, ["fly", "stealth"], []),
    ("diminutive", 4, None, {"touchAC": 4, "flatFootedAC": 4, "cmb": -8, "cmd": -4}, ["fly", "stealth"], []),
    ("tiny", 6, None, {"touchAC": 2, "flatFootedAC": 2, "cmb": -4, "cmd": -2}, ["stealth"], ["fly"]),
    ("small", None, None, {"touchAC": 1, "flatFootedAC": 1, "cmb": -2, "cmd": -1}, [], ["stealth"]),
    ("medium", None, None, {}, [], []),
    ("large", None, 2, {"touchAC": -1, "flatFootedAC": 1, "cmb": 2, "cmd": 1}, [], []),
    ("huge", None, 4, {"touchAC": -2, "flatFootedAC": 3, "cmb": 4, "cmd": 2}, [], []),
    ("gargantuan", None, 6, {"touchAC": -4, "flatFootedAC": 5, "cmb": 8, "cmd": 4}, [], []),
    ("colossal", None, 8, {"touchAC": -8, "flatFootedAC": 6, "cmb": 16, "cmd": 8}, [], []),
]
size_lines = {"fine": 2101, "diminutive": 2105, "tiny": 2109, "small": 2114, "medium": 2114, "large": 2118, "huge": 2122, "gargantuan": 2126, "colossal": 2130}
sizes = {}
for key, max_cr, min_cr, adjustments, master, good in size_specs:
    restrictions = {}
    if key == "huge":
        restrictions = {"stealthMasterForbidden": True}
    elif key == "gargantuan":
        restrictions = {"flyMasterForbidden": True, "stealthGoodMasterForbidden": True}
    elif key == "colossal":
        restrictions = {"flyGoodMasterForbidden": True, "stealthGoodMasterForbidden": True}
    sizes[f"graft.size.{key}"] = {
        "id": f"graft.size.{key}",
        "name": key.title(),
        "minCR": min_cr,
        "maxCR": max_cr,
        "adjustments": adjustments,
        "additionalMasterSkills": master,
        "additionalGoodSkills": good,
        "restrictions": restrictions,
        "sourceRef": unchained_ref("Step 5: Size Graft", size_lines[key], 217, entry=key.title()),
    }

natural_rows = {
    "bite": (["1", "1d2", "1d3", "1d4", "1d6", "1d8", "2d6", "2d8", "4d6"], "B/S/P", "primary"),
    "claw": (["—", "1", "1d2", "1d3", "1d4", "1d6", "1d8", "2d6", "2d8"], "B/S", "primary"),
    "gore": (["1", "1d2", "1d3", "1d4", "1d6", "1d8", "2d6", "2d8", "4d6"], "P", "primary"),
    "hoof": (["—", "1", "1d2", "1d3", "1d4", "1d6", "1d8", "2d6", "2d8"], "B", "secondary"),
    "tentacle": (["—", "1", "1d2", "1d3", "1d4", "1d6", "1d8", "2d6", "2d8"], "B", "secondary"),
    "wing": (["—", "1", "1d2", "1d3", "1d4", "1d6", "1d8", "2d6", "2d8"], "B", "secondary"),
    "pincers": (["1", "1d2", "1d3", "1d4", "1d6", "1d8", "2d6", "2d8", "4d6"], "B", "secondary"),
    "tail-slap": (["1", "1d2", "1d3", "1d4", "1d6", "1d8", "2d6", "2d8", "4d6"], "B", "secondary"),
    "slam": (["—", "1", "1d2", "1d3", "1d4", "1d6", "1d8", "2d6", "2d8"], "B", "primary"),
    "sting": (["—", "1", "1d2", "1d3", "1d4", "1d6", "1d8", "2d6", "2d8"], "P", "primary"),
    "talons": (["—", "1", "1d2", "1d3", "1d4", "1d6", "1d8", "2d6", "2d8"], "S", "primary"),
    "other": (["—", "1", "1d2", "1d3", "1d4", "1d6", "1d8", "2d6", "2d8"], "B/S/P", "secondary"),
}
natural_attacks = {}
natural_sizes = ["fine", "diminutive", "tiny", "small", "medium", "large", "huge", "gargantuan", "colossal"]
for key, (dice, damage_type, classification) in natural_rows.items():
    natural_attacks[f"natural-attack.{key}"] = {
        "id": f"natural-attack.{key}",
        "name": key.replace("-", " ").title(),
        "bySize": dict(zip(natural_sizes, dice)),
        "damageType": damage_type,
        "classification": classification,
        "sourceRef": bestiary_ref(key),
    }

options = {
    "option.at-will-magic": {
        "id": "option.at-will-magic",
        "name": "At-Will Magic",
        "category": "magic",
        "parameters": {},
        "effects": {},
        "sourceRef": unchained_ref("Step 7: Monster Options", 4126, 237, entry="At-Will Magic"),
    },
    "option.secondary-magic": {
        "id": "option.secondary-magic",
        "name": "Secondary Magic",
        "category": "universal",
        "parameters": {"spellListId": {"type": "string"}},
        "effects": {},
        "sourceRef": unchained_ref("Step 7: Monster Options", 4320, 239, entry="Secondary Magic"),
    },
    "option.improved-combat-maneuver": {
        "id": "option.improved-combat-maneuver",
        "name": "Improved Combat Maneuver",
        "category": "combat",
        "parameters": {
            "maneuver": {"type": "enum", "values": ["bull-rush", "dirty-trick", "disarm", "drag", "grapple", "reposition", "steal", "sunder", "trip"]},
            "attackType": {"type": "string", "optional": True},
        },
        "effects": {"cmb": 4, "cmd": 4},
        "sourceRef": unchained_ref("Step 7: Monster Options", 3325, 229, entry="Improved Combat Maneuver"),
    }
}
skills = {}
for skill in ("perception", "stealth", "survival", "climb", "fly", "swim", "intimidate", "acrobatics"):
    skills[f"skill.{skill}"] = {
        "id": f"skill.{skill}",
        "name": skill.title(),
        "default": "abilityModifier",
        "sourceRef": unchained_ref("Step 8: Skills", 4334, 240, entry=skill.title()),
    }

catalog = {
    "schemaVersion": "1",
    "catalogVersion": "catalog-1",
    "catalogStatus": {
        "step1": "complete",
        "worgVerticalSlice": "complete",
        "spellMetadata": "APG/UM/UC complete; ACG follow-up metadata with local vendoring pending",
        "spellListEvaluation": "catalogued; CR-band/frequency/list-benefit resolver pending",
        "coreSpellLists": "source-backed class-list metadata",
        "grafts": "Worg path plus type/size baseline",
        "options": "Worg path plus typed option metadata",
    },
    "sources": {
        "pathfinder-unchained-txt": {"sourceId": "pathfinder-unchained-txt", "file": "Pathfinder Unchained.txt", "sha256": unchained_hash, "description": "Local extracted Pathfinder Unchained source"},
        "pathfinder-core-txt": {"sourceId": "pathfinder-core-txt", "file": "Pathfinder_RPG_Core_Rulebook.txt", "sha256": core_hash, "description": "Local extracted Core Rulebook source"},
        "bestiary-txt": {"sourceId": "bestiary-txt", "file": "beastiary.txt", "sha256": bestiary_hash, "description": "Local extracted Bestiary source"},
        "advanced-players-guide": {"sourceId": "advanced-players-guide", "file": None, "sha256": None, "description": "Official Paizo PRD metadata; vendoring pending"},
        "ultimate-magic": {"sourceId": "ultimate-magic", "file": None, "sha256": None, "description": "Official Paizo PRD metadata; vendoring pending"},
        "ultimate-combat": {"sourceId": "ultimate-combat", "file": None, "sha256": None, "description": "Official Paizo PRD metadata; vendoring pending"},
        "advanced-class-guide": {"sourceId": "advanced-class-guide", "file": None, "sha256": None, "description": "Official Paizo PRD metadata; vendoring pending"},
        "core-rulebook-feats": {"sourceId": "core-rulebook-feats", "file": None, "sha256": None, "description": "Official Core metamagic feat metadata; local feat excerpt pending"},
    },
    "arrays": arrays,
    "grafts": {"creatureTypes": creature_types, "classGrafts": {}, "subtypes": {}, "templates": {}, "sizes": sizes},
    "options": options,
    "skills": skills,
    "damage": damage_table,
    "naturalAttacksBySize": natural_attacks,
    "spellLists": spell_lists,
    "spells": spells,
    "metamagic": {"empower": 2, "extend": 1, "maximize": 3, "quicken": 4, "widen": 3},
    "metamagicRules": {
        key: {
            "id": f"metamagic.{key}",
            "name": name,
            "levelIncrease": increase,
            "sourceRef": [external_ref("core-rulebook-feats", "CORE", None, "https://legacy.aonprd.com/coreRulebook/feats.html")],
        }
        for key, name, increase in (
            ("empower", "Empower Spell", 2),
            ("extend", "Extend Spell", 1),
            ("maximize", "Maximize Spell", 3),
            ("quicken", "Quicken Spell", 4),
            ("widen", "Widen Spell", 3),
        )
    },
    "derivedRules": {"cmb": "highAttackBonus", "concentration": "crPlusAbilityModifier", "hitDice": "max(1,cr)", "initiative": "dexterityModifier", "perception": "goodSkillUnlessMaster", "speed": "conceptSelection"},
    "aliases": {"arrays": {"combatant": "array.combatant", "expert": "array.expert", "spellcaster": "array.spellcaster"}, "grafts": {"magical-beast": "graft.creature-type.magical-beast", "medium": "graft.size.medium"}, "options": {"improved-combat-maneuver": "option.improved-combat-maneuver"}},
}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n")
print(f"wrote {OUT}: {len(spells)} spells, {len(spell_lists)} spell lists")
