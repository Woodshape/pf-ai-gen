import csv
import hashlib
import io
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UNCHAINED = ROOT / "Pathfinder Unchained.txt"
CORE = ROOT / "Pathfinder_RPG_Core_Rulebook.txt"
BESTIARY = ROOT / "beastiary.txt"
OUT = ROOT / "catalog/catalog.json"
BUILD_SCRIPT = Path(__file__).resolve()

# Keep form-feed characters inside their physical TXT lines so provenance
# line numbers match editors, `rg -n`, and the documented source map.
unchained_lines = UNCHAINED.read_text().split("\n")
core_lines = CORE.read_text().split("\n")
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
build_script_hash = hashlib.sha256(BUILD_SCRIPT.read_bytes()).hexdigest()
build_script_lines = BUILD_SCRIPT.read_text().split("\n")


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


def unchained_ref(section, line, printed, *, end_line=None, entry=None, table=None):
    return source_ref(
        source_id="pathfinder-unchained-txt",
        file="Pathfinder Unchained.txt",
        sha256=unchained_hash,
        section=section,
        txt_lines=(line, end_line or line),
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


def local_metadata_ref(source_id, page, url, entry):
    line = next(index for index, text in enumerate(build_script_lines, 1) if f'"{entry}"' in text)
    return source_ref(
        source_id=source_id,
        file="tools/build_catalog.py",
        sha256=build_script_hash,
        section="vendored rules metadata",
        txt_lines=(line, line),
        printed_pages=(page,),
        entry=entry,
        official_url=url,
        provenance_status="local-source",
    )


def cr_value(value):
    return 0.5 if value == "1/2" else int(value)


def number(value):
    return int(value.replace("−", "-").replace("–", "-"))


# Locate contiguous 31-row CR tables by row shape so extraction order and page
# markers cannot stale either parsing or provenance line numbers.
def table_starts(pattern):
    rows = [index for index, line in enumerate(unchained_lines) if re.match(pattern, line)]
    starts = [index for position, index in enumerate(rows) if position == 0 or index != rows[position - 1] + 1]
    return [start for start in starts if all(start + offset in rows for offset in range(31))]


main_starts = table_starts(r"^(?:1/2|\d+) \d+, t \d+, f \d+ ")
attack_starts = table_starts(r"^(?:1/2|\d+) [ +−-].*\(\d+\) ")
if len(main_starts) != 3 or len(attack_starts) != 3:
    raise ValueError("cannot locate the six Step-1 CR tables")
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
    expressions = re.findall(r"(?:(?:\d+d\d+)|d\d+)(?:[+−–-]\d+)?", expression_text)
    damage_table[f"{low}-{high}"] = {
        "min": int(low),
        "max": int(high),
        "expressions": dict(zip(dice_names, [value.replace("−", "-").replace("–", "-") for value in expressions])),
        "sourceRef": unchained_ref(
            "Step 9: Damage", index + 1, 241,
            entry=f"{low}–{high}", table="Table 5-9: Damage Dice Values",
        ),
    }
# The Medusa example explicitly replaces the table's 1d8+18 with this
# pre-Reality-Check expression; it is valid only for the published 21–23 row.
damage_table["21-23"]["expressions"]["2d8"] = "2d8+12"
damage_table["21-23"]["expressionSourceRefs"] = {
    "2d8": unchained_ref("Extended Example: Medusa", 4589, 243, entry="2d8+12"),
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
        local_metadata_ref(source_id, page, official_spell_url(book, name), name)
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
        "catalogStatus": "resolved",
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
level_header = re.compile(r"^(\d+)(?:st|nd|rd|th)?[-–]Level (.+?) Spells(?: \(.+\))?$")
current_class = None
current_level = None
pending_spell = None


def add_core_spell(spell_name, line_number):
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


for line_number, line in enumerate(core_lines, 1):
    stripped = line.strip()
    if class_header.match(stripped):
        current_class = re.sub(r"\s+(?:speLLs|Spells)$", "", stripped).strip().lower()
        current_level = None
        pending_spell = None
        continue
    level_match = level_header.match(stripped)
    if level_match and current_class:
        current_level = int(level_match.group(1))
        pending_spell = None
        continue
    if not current_class or current_level is None:
        continue
    if pending_spell and stripped.startswith(":"):
        add_core_spell(pending_spell, line_number - 1)
        pending_spell = None
        continue
    if ":" in stripped:
        spell_name = re.sub(r"[MF]+$", "", stripped.split(":", 1)[0].strip()).strip()
        if spell_name and len(spell_name) <= 80 and not spell_name[0].isdigit():
            add_core_spell(spell_name, line_number)
    elif re.match(r"^[A-Z][A-Za-z’' /,–-]+[MF]$", stripped):
        pending_spell = re.sub(r"[MF]+$", "", stripped).strip()
spells.update(core_spells)

# Extract Step-6 table columns from the PDF's word coordinates. The ordinary
# TXT extraction collapses Primary and Secondary into one stream; TSV retains
# the source table layout without making runtime PDF parsing necessary.
spell_lists = {}
current_list = None
current_band = None
for line_number, line in enumerate(unchained_lines, 1):
    if not 2230 <= line_number <= 3190:
        continue
    stripped = line.strip()
    if stripped == "Step 7: Monster Options":
        break
    header = re.match(r"^([A-Za-z][A-Za-z ]+) Spell List$", stripped)
    if header:
        display_name = {"ransmutation": "Transmutation", "ravel": "Travel", "rickery": "Trickery"}.get(header.group(1), header.group(1))
        current_list = display_name.lower().replace(" ", "-")
        current_band = None
        spell_lists[current_list] = {
            "id": f"spell-list.{current_list}",
            "name": display_name,
            "bands": {},
            "benefit": None,
            "sourceRef": unchained_ref(
                "Step 6: Spells", line_number, step6_page(line_number),
                entry=display_name, table="Spell Lists",
            ),
        }
        continue
    if not current_list:
        continue
    match = re.match(r"^(0–3|4–7|8–11|12–15|16\+) (.*)$", stripped)
    if match:
        current_band = match.group(1)
        spell_lists[current_list]["bands"][current_band] = {
            "primary": [],
            "secondary": [],
            "sourceRef": unchained_ref(
                "Step 6: Spells", line_number, step6_page(line_number),
                entry=current_band, table=f"{current_list} spell list",
            ),
        }
    elif stripped.startswith("Benefit:"):
        current_band = None
        spell_lists[current_list]["benefit"] = {
            "text": stripped.removeprefix("Benefit:").strip(),
            "sourceRef": unchained_ref(
                "Step 6: Spells", line_number, step6_page(line_number),
                entry="Benefit", table=f"{current_list} spell list",
            ),
        }
    elif current_band is None and spell_lists[current_list]["benefit"] and stripped and stripped != "T" and not stripped.isdigit() and not stripped.startswith("Monsters"):
        spell_lists[current_list]["benefit"]["text"] += " " + stripped

step6_tsv = subprocess.check_output([
    "pdftotext", "-f", "25", "-l", "34", "-tsv", str(ROOT / "Pathfinder Unchained.pdf"), "-",
], text=True)
words = []
for word in csv.DictReader(io.StringIO(step6_tsv), delimiter="\t"):
    if word["level"] == "5" and word["text"] not in {"Monsters", "5"} and not word["text"].isdigit():
        words.append({
            "page": int(word["page_num"]),
            "x": float(word["left"]),
            "y": round(float(word["top"]), 1),
            "text": word["text"],
        })

layout_columns = []
for page in range(25, 35):
    for side in ("left", "right"):
        x_min, x_max = ((0, 298) if side == "left" else (298, 596))
        primary_x, secondary_x = ((108, 212) if side == "left" else (348, 452))
        page_words = [word for word in words if word["page"] == page and x_min <= word["x"] < x_max]
        rows = []
        for y in sorted({word["y"] for word in page_words}):
            row = sorted((word for word in page_words if word["y"] == y), key=lambda word: word["x"])
            rows.append({
                "all": " ".join(word["text"] for word in row),
                "cr": " ".join(word["text"] for word in row if word["x"] < primary_x),
                "primary": " ".join(word["text"] for word in row if primary_x <= word["x"] < secondary_x),
                "secondary": " ".join(word["text"] for word in row if word["x"] >= secondary_x),
            })
        layout_columns.append(rows)

def spell_alias_name(value):
    return re.sub(r"[^a-z0-9]+", " ", normalized_spell_name(value)).strip()


spell_aliases = {}
for spell_id, spell in spells.items():
    names = {spell_alias_name(spell["name"])}
    if "," in spell["name"]:
        base, modifier = (part.strip() for part in spell["name"].split(",", 1))
        if modifier.lower() in {"greater", "lesser", "mass"}:
            names.add(spell_alias_name(f"{modifier} {base}"))
    for name in names:
        spell_aliases[name] = spell_id
for combined, variants in {
    "protection from chaos/evil/good/law": ("protection from chaos", "protection from evil", "protection from good", "protection from law", "protection from good or law"),
    "magic circle against chaos/evil/good/law": ("magic circle against chaos", "magic circle against evil", "magic circle against good", "magic circle against law"),
    "dispel chaos/evil/good/law": ("dispel chaos", "dispel evil", "dispel good", "dispel law"),
}.items():
    spell_id = spell_aliases.get(spell_alias_name(combined))
    if spell_id:
        spell_aliases.update({spell_alias_name(variant): spell_id for variant in variants})
spell_aliases["control wind"] = spell_aliases["control winds"]

metamagic_prefixes = {
    "empowered": "empower", "extended": "extend", "maximized": "maximize",
    "quickened": "quicken", "widened": "widen", "enlarged": "enlarge",
}


def resolve_spell_list_cell(text, list_id):
    expressions = [expression.strip() for expression in text.split(",") if expression.strip()]
    if not expressions:
        raise ValueError(f"spell-list cell has no spells: {list_id}: {text}")
    output = []
    for source_text in expressions:
        lookup_text = re.sub(r"\b(?:APG|UM|UC|ACG)\b", "", source_text, flags=re.IGNORECASE)
        lookup_text = re.sub(r"\*.*$|\bgood creatures only\.?$", "", lookup_text, flags=re.IGNORECASE).strip()
        metamagic = []
        while True:
            match = re.match(r"^(empowered|extended|maximized|quickened|widened|enlarged)\s+", lookup_text, re.IGNORECASE)
            if not match:
                break
            metamagic.append(metamagic_prefixes[match.group(1).lower()])
            lookup_text = lookup_text[match.end():]
        lookup_text = re.sub(r"\s*\([^)]*\)\s*$", "", lookup_text).strip()
        normalized = spell_alias_name(lookup_text)
        spell_id = spell_aliases.get(normalized)
        if spell_id is None:
            raise ValueError(f"unresolved Step-6 spell: {list_id}: {source_text!r} ({normalized!r})")
        spell = spells[spell_id]
        list_name = list_id.removeprefix("spell-list.")
        if list_name not in spell["listMemberships"]:
            spell["listMemberships"].append(list_name)
            spell["listMemberships"].sort()
        output.append({
            "spellId": spell_id,
            "name": spell["name"],
            "sourceText": source_text,
            "metamagic": metamagic,
        })
    return output

current_layout_list = None
current_layout_band = None
for rows in layout_columns:
    for row in rows:
        list_key = next((key for key, value in spell_lists.items() if f'{value["name"]} Spell List' in row["all"]), None)
        if list_key:
            current_layout_list = list_key
            current_layout_band = None
            continue
        if not current_layout_list:
            continue
        band = next((band for band in ("0–3", "4–7", "8–11", "12–15", "16+") if re.search(rf"(?<!\S){re.escape(band)}(?!\S)", row["cr"])), None)
        if band:
            current_layout_band = band
            spell_lists[current_layout_list]["bands"][band].setdefault("primaryText", "")
            spell_lists[current_layout_list]["bands"][band].setdefault("secondaryText", "")
        elif row["all"].startswith("Benefit:"):
            current_layout_band = None
            continue
        if current_layout_band:
            values = spell_lists[current_layout_list]["bands"][current_layout_band]
            values["primaryText"] = " ".join(filter(None, (values["primaryText"], row["primary"])))
            values["secondaryText"] = " ".join(filter(None, (values["secondaryText"], row["secondary"])))

for list_key, spell_list in spell_lists.items():
    if set(spell_list["bands"]) != {"0–3", "4–7", "8–11", "12–15", "16+"} or not spell_list["benefit"]:
        raise ValueError(f"incomplete Step-6 spell list: {list_key}")
    for band in spell_list["bands"].values():
        band["primary"] = resolve_spell_list_cell(band.pop("primaryText"), spell_list["id"])
        band["secondary"] = resolve_spell_list_cell(band.pop("secondaryText"), spell_list["id"])

energy_parameter = {"type": "enum", "values": ["acid", "cold", "electricity", "fire", "sonic"]}
speed_parameter = {"type": "selected-speed"}
skill_parameter = lambda values: {"type": "enum", "values": [f"skill.{value}" for value in values]}
resistance = lambda energy, values, immunity_at=None: {
    "type": "resistance", "energyType": energy, "values": values,
    **({"immunityAt": immunity_at} if immunity_at else {}),
}
# Benefits remain source text first. These records only type the numeric and
# user-choice consequences that the engine can apply without interpreting prose.
benefit_specs = {
    "abjuration": ({"energyType": energy_parameter}, [resistance({"parameter": "energyType"}, {"0": 5, "12": 10, "16": 20})]),
    "abyssal": ({}, [{"type": "abilityModifier", "ability": "strength", "values": {"0": 1, "13": 2, "17": 3}}]),
    "acid": ({}, [resistance("acid", {"0": 5, "12": 10}, 16)]),
    "air": ({"speedType": speed_parameter}, [{"type": "speedBonus", "speedType": {"parameter": "speedType"}, "value": 10}]),
    "alchemy": ({}, [{"type": "conditionalSaveBonus", "conditions": ["disease", "poison"], "value": 2}]),
    "animal": ({}, [{"type": "auraAttackBonus", "targets": "animal allies within 20 feet", "value": 1}]),
    "arcane": ({}, [{"type": "spellDCBonus", "condition": "metamagic", "value": 1}]),
    "artifice": ({}, [{"type": "conditionalDefenseBonus", "field": "ac", "condition": "after casting a spell from this list for 1 round", "valueFormula": "spellLevel"}]),
    "battle": ({}, [{"type": "attackBonus", "value": 1}]),
    "celestial": ({}, [resistance("acid", {"0": 5, "12": 10}), resistance("cold", {"0": 5, "12": 10})]),
    "charm": ({}, [{"type": "conditionalSaveBonus", "conditions": ["charm"], "value": 4}]),
    "cold": ({}, [resistance("cold", {"0": 5, "12": 10}, 16)]),
    "community": ({}, [{"type": "masterSkill", "skillId": "skill.diplomacy"}]),
    "conjuration": ({}, [{"type": "spellDurationMultiplier", "condition": "conjuration (summoning)", "value": 2}]),
    "darkness": ({}, [{"type": "spellLevelBonus", "condition": "darkness descriptor", "value": 1}]),
    "death": ({}, [{"type": "spellDCBonus", "condition": "death spell", "value": 1}]),
    "destined": ({}, [{"type": "allSavesBonus", "value": 1}]),
    "destruction": ({}, [{"type": "spellDCBonus", "condition": "spell deals damage", "value": 1}]),
    "draconic": ({"energyType": {"type": "enum", "values": ["acid", "cold", "electricity", "fire"]}}, [
        {"type": "defenseBonus", "fields": ["ac", "flatFootedAC"], "value": 2},
        resistance({"parameter": "energyType"}, {"0": 5}),
    ]),
    "earth": ({}, [resistance("acid", {"0": 5, "12": 10}, 16)]),
    "electricity": ({}, [resistance("electricity", {"0": 5, "12": 10}, 16)]),
    "elemental": ({"movementMode": {"type": "enum", "values": ["fly", "burrow", "land", "swim"]}}, [
        {"type": "movementChoice", "parameter": "movementMode", "choices": {
            "fly": {"operation": "set", "value": 60}, "burrow": {"operation": "set", "value": 30},
            "land": {"operation": "add", "value": 30}, "swim": {"operation": "set", "value": 60},
        }},
    ]),
    "enchantment": ({"skillId": skill_parameter(["bluff", "diplomacy"])}, [{"type": "masterSkill", "skillId": {"parameter": "skillId"}}]),
    "evocation": ({}, [{"type": "spellDamageBonus", "condition": "evocation", "valueFormula": "halfCR"}]),
    "fey": ({}, [{"type": "spellDCBonus", "condition": "compulsion", "value": 2}]),
    "fire": ({}, [resistance("fire", {"0": 5, "12": 10}, 16)]),
    "glory": ({}, [{"type": "conditionalSaveBonus", "conditions": ["fear"], "value": 4}]),
    "healing": ({"skillId": skill_parameter(["diplomacy", "heal"])}, [{"type": "masterSkill", "skillId": {"parameter": "skillId"}}]),
    "illusion": ({}, [{"type": "spellDCBonus", "condition": "illusion", "value": 1}]),
    "infernal": ({}, [
        resistance("fire", {"0": 5, "9": 10}),
        {"type": "conditionalSaveBonus", "conditions": ["poison"], "values": {"0": 2, "9": 4}},
    ]),
    "knowledge": ({"skillIds": {"type": "enum-array", "count": 2, "values": [f"skill.knowledge-{name}" for name in ("arcana", "dungeoneering", "engineering", "geography", "history", "local", "nature", "nobility", "planes", "religion")]}}, [
        {"type": "masterSkills", "skillIds": {"parameter": "skillIds"}},
    ]),
    "liberation": ({}, [{"type": "masterSkill", "skillId": "skill.escape-artist"}]),
    "luck": ({}, [{"type": "allSavesBonus", "value": 1}]),
    "madness": ({}, [{"type": "conditionalSaveBonus", "conditions": ["mind-affecting"], "value": 2}]),
    "magic": ({}, [{"type": "casterLevelCheckBonus", "condition": "overcome spell resistance", "value": 2}]),
    "metal": ({"speedType": speed_parameter}, [{"type": "speedBonus", "speedType": {"parameter": "speedType"}, "value": 10}]),
    "nobility": ({"skillId": skill_parameter(["diplomacy", "sense-motive"])}, [{"type": "masterSkill", "skillId": {"parameter": "skillId"}}]),
    "protection": ({}, [{"type": "allSavesBonus", "value": 1}]),
    "repose": ({}, [{"type": "conditionalSaveBonus", "conditions": ["death spells and effects"], "value": 4}]),
    "rune": ({"energyType": energy_parameter}, [resistance({"parameter": "energyType"}, {"0": 5, "12": 10, "16": 20})]),
    "sonic": ({}, [resistance("sonic", {"0": 5, "12": 10}, 16)]),
    "stealth": ({}, [{"type": "masterSkill", "skillId": "skill.stealth"}]),
    "strength": ({}, [{"type": "abilityModifier", "ability": "strength", "values": {"0": 1, "12": 2, "16": 3}}]),
    "sun": ({}, [{"type": "spellDCBonus", "condition": "from this spell list", "value": 1}]),
    "transmutation": ({"ability": {"type": "enum", "values": ["strength", "dexterity", "constitution"]}}, [
        {"type": "abilityModifier", "ability": {"parameter": "ability"}, "values": {"0": 1, "12": 2}},
    ]),
    "travel": ({"speedType": speed_parameter}, [{"type": "speedBonus", "speedType": {"parameter": "speedType"}, "value": 10}]),
    "trickery": ({"skillId": skill_parameter(["bluff", "stealth"])}, [{"type": "masterSkill", "skillId": {"parameter": "skillId"}}]),
    "undead": ({}, [{"type": "damageReduction", "against": "nonlethal damage", "bypass": "—", "values": {"0": 5, "8": 10}}]),
    "war": ({}, [{"type": "attackBonus", "value": 1}]),
    "water": ({}, [resistance("cold", {"0": 5, "12": 10}, 16)]),
    "weather": ({}, [resistance("electricity", {"0": 5, "12": 10}, 16)]),
}
for list_key, spell_list in spell_lists.items():
    parameters, effects = benefit_specs.get(list_key, ({}, []))
    spell_list["benefit"].update({"parameters": parameters, "effects": effects})

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

class_names = [
    "Alchemist", "Barbarian", "Bard", "Cavalier", "Cleric", "Druid", "Fighter",
    "Gunslinger", "Inquisitor", "Magus", "Monk", "Oracle", "Paladin", "Ranger",
    "Rogue", "Sorcerer", "Summoner", "Witch", "Wizard",
]
class_starts = {name: unchained_lines.index(name, 975, 1750) + 1 for name in class_names}
class_ordered_starts = sorted(class_starts.values())
class_page_starts = [(975, 206), (1051, 207), (1155, 208), (1258, 209), (1363, 210), (1437, 211), (1542, 212), (1646, 213)]
class_page = lambda line: max(page for page_start, page in class_page_starts if line >= page_start)
class_grafts = {}
for name in class_names:
    start = class_starts[name]
    end = next((line - 1 for line in class_ordered_starts if line > start), 1750)
    lines = unchained_lines[start - 1:end]
    text = " ".join(line.strip("\f") for line in lines if line.strip("\f") and not line.strip().isdigit() and line.strip() not in {"Monsters", "Monsters 5"})
    required = re.search(r"Required Array: (Combatant|Expert|Spellcaster)", text)
    printed = class_page(start)
    graft_id = f"graft.class.{slug(name)}"
    graft = {
        "id": graft_id, "name": name, "requiredArrayId": f"array.{required.group(1).lower()}",
        "ruleText": text, "statisticAdjustments": {}, "skillGrants": [],
        "optionGrants": [], "optionSlots": [], "crEntries": [],
        "sourceRef": unchained_ref("Step 2: Class Graft", start, printed, end_line=end, entry=name),
    }
    statistics_start = next((index for index, line in enumerate(lines) if line.startswith("Statistic Adjustments:")), None)
    if statistics_start is not None:
        paragraph = []
        for line in lines[statistics_start:]:
            if paragraph and (line.startswith("CR ") or line.startswith("Suggested ")):
                break
            paragraph.append(line.strip("\f"))
        graft["optionRuleText"] = " ".join(paragraph)
    sidebar_headings = {"Domain Options", "Mystery Options", "Bloodline Options", "Arcane School Options", "Animal Companions and Mounts", "Advanced Class Guide Classes"}
    for index, line in enumerate(lines):
        match = re.match(r"^CR (\d+):", line)
        if not match:
            continue
        paragraph = [line]
        for following in lines[index + 1:]:
            if re.match(r"^CR \d+:", following) or following.startswith("Suggested ") or following in sidebar_headings:
                break
            paragraph.append(following.strip("\f"))
        line_number = start + index
        graft["crEntries"].append({
            "minCR": int(match.group(1)), "ruleText": " ".join(paragraph),
            "optionGrants": [], "optionSlots": [],
            "sourceRef": unchained_ref("Step 2: Class Graft", line_number, class_page(line_number), end_line=line_number + len(paragraph) - 1, entry=f"{name} CR {match.group(1)}"),
        })
    class_grafts[graft_id] = graft

class_adjustments = {
    "alchemist": {"saveSourceArrayId": "array.combatant"},
    "barbarian": {"fortitude": 2, "speed": 10},
    "bard": {"reflex": 2}, "cavalier": {"fortitude": 1, "reflex": 1},
    "cleric": {"fortitude": 2}, "druid": {"fortitude": 2},
    "fighter": {"fortitude": 1, "reflex": 1}, "gunslinger": {"fortitude": 1, "reflex": 1},
    "inquisitor": {"fortitude": 1, "reflex": 1, "will": 2}, "magus": {"fortitude": 2},
    "monk": {"fortitude": 1, "reflex": 1, "will": 2}, "oracle": {"reflex": 1, "will": 1},
    "paladin": {"fortitude": 2, "will": 3}, "ranger": {"fortitude": 1, "reflex": 1},
    "rogue": {"reflex": 3}, "summoner": {"fortitude": 1, "reflex": 1},
    "witch": {"fortitude": 1, "reflex": 1},
}
class_skills = {
    "alchemist": [("craft-alchemy", "master", False)], "barbarian": [("intimidate", "master", False)],
    "bard": [("perform", "master", False)], "cavalier": [("ride", "master", False)],
    "cleric": [("knowledge-religion", "master", False)],
    "druid": [("knowledge-nature", "master", False), ("survival", "master", False)],
    "inquisitor": [("intimidate", "master", False), ("sense-motive", "master", False)],
    "monk": [("acrobatics", "master", False)],
    "ranger": [("perception", "master", False)],
    "rogue": [("perception", "master", False), ("stealth", "master", False)],
    "sorcerer": [("knowledge-arcana", "master", False)],
    "summoner": [("knowledge-planes", "master", False)],
    "wizard": [("knowledge-arcana", "master", False)],
}
for key, values in class_adjustments.items():
    graft = class_grafts[f"graft.class.{key}"]
    graft["speedAdjustment"] = values.get("speed", 0)
    if "saveSourceArrayId" in values:
        graft["saveSourceArrayId"] = values["saveSourceArrayId"]
    graft["statisticAdjustments"].update({field: value for field, value in values.items() if field not in {"saveSourceArrayId", "speed"}})
for key, grants in class_skills.items():
    class_grafts[f"graft.class.{key}"]["skillGrants"] = [
        {"skillId": f"skill.{skill}", "rank": rank, "additional": additional}
        for skill, rank, additional in grants
    ]
for key in ("sorcerer", "wizard"):
    class_grafts[f"graft.class.{key}"]["saveChoiceBonus"] = {"choices": ["fortitude", "reflex"], "value": 1}
class_grafts["graft.class.witch"]["unresolvedRules"] = ["Knowledge (arcana) skill rank is omitted by the source"]
oracle = class_grafts["graft.class.oracle"]
oracle["choiceSpec"] = {"name": "curse", "values": ["clouded-vision", "deaf", "haunted", "lame", "tongues", "wasting"]}
oracle["abilityChoiceSpecs"] = [{"name": "mystery", "values": ["battle", "bones", "flame", "heavens", "life", "lore", "nature", "stone", "waves", "wind"]}]
oracle["choiceEffects"] = {
    "clouded-vision": {"senses": [{"minCR": 0, "value": "darkvision 30 ft."}, {"minCR": 4, "replace": "darkvision 30 ft.", "value": "darkvision 60 ft."}, {"minCR": 9, "value": "blindsense 30 ft."}, {"minCR": 14, "value": "blindsight 15 ft."}], "limitations": ["cannot see beyond darkvision range"]},
    "deaf": {"conditions": ["permanently deafened"], "traits": ["ignores verbal spell components"], "senses": [{"minCR": 9, "value": "scent"}, {"minCR": 14, "value": "tremorsense 30 ft."}], "conditionalMasterSkills": [{"minCR": 4, "skillId": "skill.perception", "condition": "checks that do not rely on hearing"}]},
    "haunted": {"traits": ["stored items require a standard action to retrieve; dropped items land 10 feet away in a random direction"], "atWillSpellIds": ["spell.core.mage-hand", "spell.core.ghost-sound"]},
    "lame": {"speedAdjustment": -10, "immunities": [{"minCR": 4, "value": "fatigued"}, {"minCR": 14, "value": "exhausted"}]},
    "tongues": {"languageValues": ["abyssal", "aklo", "aquan", "auran", "celestial", "ignan", "infernal", "terran"], "traits": ["in combat can speak and understand only the selected curse languages"], "stages": [{"minCR": 9, "value": "understands any spoken language"}, {"minCR": 14, "value": "can speak any language outside combat"}]},
    "wasting": {"abilityModifierAdjustments": {"charisma": -4}, "immunities": [{"minCR": 4, "value": "sickened"}, {"minCR": 9, "value": "disease"}, {"minCR": 14, "value": "nauseated"}]},
}
class_grafts["graft.class.cleric"]["optionChoiceSpecs"] = [{
    "name": "spontaneousCasting", "optionId": "option.spontaneous-casting",
    "parameter": "spellType", "values": ["cure", "inflict"],
}]

for key in ("bard", "cleric", "druid", "inquisitor", "magus", "sorcerer", "summoner", "witch", "wizard"):
    class_grafts[f"graft.class.{key}"]["spellcastingClassId"] = key
alchemist = class_grafts["graft.class.alchemist"]
alchemist["spellcastingClassId"] = "alchemist"
alchemist["requiredSpellListId"] = "spell-list.alchemy"
alchemist["spellcastingMode"] = "supernatural-extracts"
class_grafts["graft.class.summoner"]["companionSpec"] = {
    "choiceName": "eidolonName", "arrayId": "array.combatant",
    "creatureTypeGraftId": "graft.creature-type.outsider", "crAdjustment": 0,
    "combinedCRAdjustment": 2, "awardsIndependentXP": True,
}
monk = class_grafts["graft.class.monk"]
monk["unarmedDamage"] = "1d6"
for entry in monk["crEntries"]:
    match = re.search(r"unarmed damage (\d+d\d+)", entry["ruleText"], re.IGNORECASE)
    if match:
        entry["unarmedDamage"] = match.group(1).lower()
def graft_records(names, section, prefix, first_line, last_line, printed_page):
    starts = {}
    for name in names:
        starts[name] = next(
            line_number for line_number, line in enumerate(unchained_lines, 1)
            if first_line <= line_number <= last_line
            and (line.lower().startswith(name.lower() + ":") or line.lower().startswith(name.lower() + " ("))
        )
    ordered = sorted(starts.values())
    records = {}
    for name, start in starts.items():
        end = next((line - 1 for line in ordered if line > start), last_line)
        text = " ".join(
            line.strip("\f") for line in unchained_lines[start - 1:end]
            if line.strip("\f") and line.strip() not in {"Monsters", "Monsters 5"}
            and not line.strip().isdigit()
        )
        graft_id = f"graft.{prefix}.{slug(name)}"
        records[graft_id] = {
            "id": graft_id, "name": name, "ruleText": text,
            "skillGrants": [], "optionGrants": [],
            "sourceRef": unchained_ref(section, start, printed_page(start), end_line=end, entry=name),
        }
    return records


subtype_names = [
    "Aeon", "Agathion", "Air", "Angel", "Aquatic", "Archon", "Asura", "Azata",
    "Clockwork", "Cold", "Daemon", "Demodand", "Demon", "Devil", "Div", "Dwarf",
    "Earth", "Elemental", "Elf", "Fire", "Giant", "Gnome", "Goblinoid", "Half-Elf",
    "Half-Orc", "Halfling", "Human", "Incorporeal", "Inevitable", "Kami", "Leshy",
    "Nightshade", "Oni", "Orc", "Protean", "Psychopomp", "Qlippoth", "Rakshasa",
    "Shapechanger", "Swarm", "Water",
]
subtypes = graft_records(
    subtype_names, "Step 3: Subtype Graft", "subtype", 1751, 1938,
    lambda line: 214 if line < 1817 else 215,
)
subtype_overrides = {
    "aeon": {"scaledStatisticAdjustments": {"ac": {"formula": "quarterCR"}}},
    "agathion": {"conditionalSaveBonuses": [{"bonus": 4, "against": ["poison"]}]},
    "air": {"movement": {"fly": 60}, "movementManeuverability": {"fly": "perfect"}, "skillGrants": [{"skillId": "skill.fly", "rank": "master", "additional": True}]},
    "angel": {"conditionalSaveBonuses": [{"bonus": 4, "against": ["poison"]}]},
    "aquatic": {"movement": {"swim": 30}, "skillGrants": [{"skillId": "skill.swim", "rank": "master", "additional": True}]},
    "archon": {"conditionalSaveBonuses": [{"bonus": 4, "against": ["poison"]}]},
    "asura": {"conditionalSaveBonuses": [{"bonus": 2, "against": ["enchantment spells"]}], "skillGrants": [{"skillId": f"skill.{skill}", "rank": "master", "additional": True} for skill in ("escape-artist", "perception")]},
    "clockwork": {"statisticAdjustments": {"ac": 2, "touchAC": 2, "reflex": 2}, "vulnerabilities": ["electricity"]},
    "cold": {"vulnerabilities": ["fire"]},
    "dwarf": {
        "senses": ["darkvision 60 ft."],
        "conditionalSaveBonuses": [{"bonus": 2, "against": ["poison", "spells", "spell-like abilities"]}],
    },
    "devil": {"senses": ["see in darkness"]},
    "div": {"senses": ["see in darkness"]},
    "earth": {"movement": {"burrow": 20}, "senses": ["tremorsense (range varies)"]},
    "elf": {"senses": ["low-light vision"], "skillChoiceGrant": {"name": "masterSkill", "rank": "master", "skillIds": ["skill.perception", "skill.spellcraft"]}},
    "fire": {"vulnerabilities": ["cold"]},
    "giant": {"senses": ["low-light vision"], "skillGrants": [{"skillId": "skill.intimidate", "rank": "good", "additional": True}]},
    "gnome": {"requiredSizeId": "graft.size.small", "senses": ["low-light vision"], "spellChoiceGrant": {"name": "spellId", "spellListId": "spell-list.illusion", "role": "primary", "frequency": "1/day"}},
    "goblinoid": {"skillGrants": [{"skillId": "skill.stealth", "rank": "good", "additional": True}]},
    "half-elf": {"senses": ["low-light vision"], "skillSlots": [{"rank": "master", "count": 1}]},
    "half-orc": {"senses": ["darkvision 60 ft."], "skillGrants": [{"skillId": "skill.intimidate", "rank": "good", "additional": True}]},
    "halfling": {"requiredSizeId": "graft.size.small", "conditionalSaveBonuses": [{"bonus": 2, "against": ["fear"]}]},
    "human": {"optionSlots": [{"category": "combat/social", "count": 1}]},
    "incorporeal": {"touchACEqualsAC": True},
    "inevitable": {"senses": ["low-light vision"]},
    "nightshade": {"senses": ["darksense", "low-light vision"], "traits": ["light aversion"]},
    "orc": {"senses": ["darkvision 60 ft."], "traits": ["light sensitivity"]},
    "protean": {"senses": ["blindsense (range varies)"]},
    "psychopomp": {"senses": ["spiritsense"]},
    "swarm": {"damageRules": ["takes 50% additional damage from area effects", "Tiny swarms take half damage from slashing and piercing weapons", "Fine or Diminutive swarms are immune to weapon damage"]},
    "water": {"movement": {"swim": 30}, "skillGrants": [{"skillId": "skill.swim", "rank": "master", "additional": True}]},
}
for key, values in subtype_overrides.items():
    subtypes[f"graft.subtype.{key}"].update(values)


template_names = [
    "Ghost", "Graveknight", "Half-Celestial", "Half-Dragon", "Half-Fiend",
    "Lich", "Lycanthrope", "Skeleton", "Vampire", "Zombie",
]
templates = graft_records(
    template_names, "Step 4: Template Graft", "template", 1939, 2090,
    lambda line: 216 if line < 2040 else 217,
)
template_overrides = {
    "ghost": {"minCR": 2, "requiredCreatureTypeId": "graft.creature-type.undead", "requiredSubtypeId": "graft.subtype.incorporeal", "movement": {"fly": 30}, "movementManeuverability": {"fly": "perfect"}, "abilityModifierOverrides": {"strength": None}, "abilityModifierAdjustments": {"charisma": 2}, "skillGrants": [{"skillId": f"skill.{skill}", "rank": "master", "additional": False} for skill in ("perception", "stealth")]},
    "graveknight": {"minCR": 5, "requiredCreatureTypeId": "graft.creature-type.undead", "linkedOptionChoiceSpec": {"energyName": "energyType", "energyValues": ["acid", "cold", "electricity", "fire"], "fixedShape": "cone"}, "statisticAdjustments": {"ac": 2, "touchAC": 4, "flatFootedAC": -6}, "skillGrants": [{"skillId": f"skill.{skill}", "rank": "master", "additional": False} for skill in ("intimidate", "perception", "ride")]},
    "half-celestial": {"minCR": 1, "requiredCreatureTypeId": "graft.creature-type.outsider", "movementMultiplier": {"from": "land", "to": "fly", "value": 2}, "movementManeuverability": {"fly": "good"}, "conditionalSaveBonuses": [{"bonus": 4, "against": ["poison"]}], "skillSlots": [{"rank": "master", "count": 1}]},
    "half-dragon": {"minCR": 3, "requiredCreatureTypeId": "graft.creature-type.dragon", "linkedOptionChoiceSpec": {"energyName": "energyType", "energyValues": ["acid", "cold", "electricity", "fire"], "shapeName": "breathShape", "shapeValues": ["cone", "line"]}, "skillSlots": [{"rank": "master", "count": 1}]},
    "half-fiend": {"minCR": 1, "requiredCreatureTypeId": "graft.creature-type.outsider", "movementMultiplier": {"from": "land", "to": "fly", "value": 2}, "movementManeuverability": {"fly": "good"}, "skillSlots": [{"rank": "master", "count": 1}]},
    "lich": {"minCR": 2, "requiredCreatureTypeId": "graft.creature-type.undead", "statisticAdjustments": {"ac": 2}, "skillGrants": [{"skillId": f"skill.{skill}", "rank": "master", "additional": False} for skill in ("perception", "sense-motive", "stealth")]},
    "lycanthrope": {"minCR": 1, "requiredCreatureTypeId": "graft.creature-type.humanoid", "requiredSubtypeId": "graft.subtype.shapechanger"},
    "skeleton": {"maxCR": 8, "requiredCreatureTypeId": "graft.creature-type.undead", "abilityModifierOverrides": {"intelligence": None}},
    "vampire": {"minCR": 5, "requiredCreatureTypeId": "graft.creature-type.undead", "statisticAdjustments": {"ac": 2, "flatFootedAC": 2}, "traits": ["spider climb (constant)", "vampire weaknesses"], "skillGrants": [{"skillId": f"skill.{skill}", "rank": "master", "additional": False} for skill in ("bluff", "perception", "sense-motive", "stealth")]},
    "zombie": {"maxCR": 9, "requiredCreatureTypeId": "graft.creature-type.undead", "abilityModifierOverrides": {"intelligence": None}, "conditions": ["staggered"], "traits": ["can perform only a single move action or standard action each round"], "skillBudgetOverride": {"master": 0, "good": 0}, "suppressAutomaticPerception": True},
}
for key, values in template_overrides.items():
    templates[f"graft.template.{key}"].update(values)

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

option_rows = []
for line_number, line in enumerate(unchained_lines, 1):
    if 3132 <= line_number <= 4333:
        match = re.match(r"^(.*?) (Combat|Magic|Social|Universal) (\d+)$", line.strip())
        if match:
            option_rows.append((match.group(1), match.group(2).lower(), int(match.group(3))))


def option_slug(name):
    return slug(name.replace("’s", "s").replace("'s", "s"))


option_starts = {}
for name, _, _ in option_rows:
    option_starts[name] = next(
        line_number for line_number, line in enumerate(unchained_lines, 1)
        if 3132 <= line_number <= 4333 and line.lower().startswith(name.lower() + ":")
    )
sorted_option_starts = sorted(option_starts.values())
table_row = re.compile(r"^.*? (?:Combat|Magic|Social|Universal) \d+$")
options = {}
for name, category, printed_page in option_rows:
    start = option_starts[name]
    end = next((line - 1 for line in sorted_option_starts if line > start), 4333)
    text_lines = [
        line.strip("\f") for line in unchained_lines[start - 1:end]
        if line.strip("\f") and not table_row.match(line.strip())
        and line.strip() not in {"Monsters", "Monsters 5", "T", "ough"}
        and not line.strip().isdigit()
    ]
    option_id = f"option.{option_slug(name)}"
    options[option_id] = {
        "id": option_id,
        "name": name,
        "category": category,
        "parameters": {},
        "effects": {"ability": option_slug(name)},
        "effectMode": "source-rule",
        "ruleText": " ".join(text_lines),
        "sourceRef": unchained_ref(
            "Step 7: Monster Options", start, printed_page, end_line=end, entry=name
        ),
    }

# Typed overrides for options already exercised by the deterministic engine.
typed_options = {
    "option.at-will-magic": {
        "id": "option.at-will-magic",
        "name": "At-Will Magic",
        "category": "magic",
        "parameters": {"spellId": {"type": "string", "catalogKind": "spell"}, "maxSpellLevel": {"type": "integer", "optional": True, "internal": True}},
        "effects": {"ability": "at-will-magic"},
        "sourceRef": unchained_ref("Step 7: Monster Options", 4126, 237, entry="At-Will Magic"),
    },
    "option.secondary-magic": {
        "id": "option.secondary-magic",
        "name": "Secondary Magic",
        "category": "universal",
        "parameters": {"spellListId": {"type": "string", "catalogKind": "spellList"}},
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
    },
    "option.gaze": {
        "id": "option.gaze", "name": "Gaze", "category": "combat",
        "parameters": {
            "range": {"type": "enum", "values": ["30 ft."]},
            "effect": {"type": "enum", "values": ["turn-to-stone-permanently"]},
            "save": {"type": "enum", "values": ["fortitude-negates"]},
        },
        "effects": {"type": "gaze"},
        "sourceRef": [
            unchained_ref("Step 7: Monster Options", 3311, 228, entry="Gaze"),
            unchained_ref("Extended Example: Medusa", 4556, 243, entry="Petrifying Gaze"),
        ],
    },
    "option.poison": {
        "id": "option.poison", "name": "Poison", "category": "combat",
        "parameters": {
            "attackTypes": {"type": "selected-attacks"},
            "ability": {"type": "enum", "values": ["strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"]},
            "advantages": {"type": "enum-array", "values": ["no-onset", "round-frequency", "increase-damage", "two-consecutive-saves"]},
        },
        "effects": {"type": "poison"},
        "sourceRef": [
            unchained_ref("Step 7: Monster Options", 3343, 230, entry="Poison"),
            unchained_ref("Extended Example: Medusa", 4562, 243, entry="Medusa Poison"),
        ],
    },
    "option.pounce": {
        "id": "option.pounce", "name": "Pounce", "category": "combat", "parameters": {},
        "effects": {"ability": "pounce"},
        "sourceRef": unchained_ref("Step 7: Monster Options", 3311, 228, entry="Pounce"),
    },
    "option.rake": {
        "id": "option.rake", "name": "Rake", "category": "combat", "parameters": {},
        "effects": {"ability": "rake", "attacks": 2, "attackType": "claw", "damageProfile": "weapon.low"},
        "sourceRef": unchained_ref("Step 7: Monster Options", 3708, 233, entry="Rake"),
    },
    "option.improved-initiative": {
        "id": "option.improved-initiative", "name": "Improved Initiative", "category": "combat",
        "parameters": {}, "effects": {"initiative": 4},
        "sourceRef": unchained_ref("Step 7: Monster Options", 3862, 235, end_line=3863, entry="Improved Initiative"),
    },
    "option.spontaneous-casting": {
        "id": "option.spontaneous-casting", "name": "Spontaneous Casting", "category": "magic",
        "parameters": {"spellType": {"type": "enum", "values": ["cure", "inflict", "summon-monster", "summon-natures-ally"]}},
        "effects": {"ability": "spontaneous-casting"},
        "sourceRef": unchained_ref("Step 7: Monster Options", 4159, 238, end_line=4165, entry="Spontaneous Casting"),
    },
    "option.change-shape": {
        "id": "option.change-shape", "name": "Change Shape", "category": "universal",
        "parameters": {"forms": {"type": "string-array", "optional": True}},
        "effects": {"ability": "change-shape"},
        "sourceRef": [
            unchained_ref("Step 2: Class Graft", 1189, 208, end_line=1192, entry="Druid Change Shape"),
            unchained_ref("Step 3: Subtype Graft", 1887, 215, entry="Shapechanger"),
        ],
    },
    "option.terrain-stride": {
        "id": "option.terrain-stride", "name": "Terrain Stride", "category": "universal",
        "parameters": {"terrain": {"type": "string"}}, "effects": {"ability": "terrain-stride"},
        "sourceRef": unchained_ref("Step 7: Monster Options", 4328, 239, end_line=4331, entry="Terrain Stride"),
    },
    "option.curse-of-lycanthropy": {
        "id": "option.curse-of-lycanthropy", "name": "Curse of Lycanthropy", "category": "combat",
        "parameters": {}, "effects": {"ability": "curse-of-lycanthropy"},
        "sourceRef": unchained_ref("Step 7: Monster Options", 3598, 232, end_line=3604, entry="Curse of Lycanthropy"),
    },
}
for option_id, definition in typed_options.items():
    options[option_id] = {**options.get(option_id, {}), **definition, "effectMode": "typed"}
    options[option_id].setdefault("ruleText", definition["name"])

direct_option_effects = {
    "option.accuracy": {"type": "attackBonus", "value": 2},
    "option.dodge-expert": {"type": "defenseBonuses", "values": {"ac": 2, "touchAC": 4, "flatFootedAC": -6}},
    "option.extra-armor": {"type": "defenseBonuses", "values": {"ac": 2, "touchAC": -6, "flatFootedAC": 4}},
    "option.combat-casting": {"type": "concentrationBonus", "value": 6},
    "option.spell-resistance": {"type": "spellResistance", "formula": "cr+11"},
    "option.save-boost": {"type": "saveChoice"},
    "option.animal-talker": {"type": "additionalMasterSkills", "skillIds": ["skill.handle-animal"]},
    "option.flying-acumen": {"type": "additionalMasterSkills", "skillIds": ["skill.fly"]},
    "option.sound-mimicry": {"type": "additionalMasterSkills", "skillIds": ["skill.bluff"]},
    "option.spell-penetration": {"type": "casterLevelCheckBonus", "values": {"0": 2, "11": 4}, "against": "spell resistance"},
    "option.extra-hit-points": {"type": "hitPointsPercent", "percent": 20},
    "option.immunity": {"type": "immunity"},
    "option.damage-reduction": {"type": "damageReduction"},
    "option.energy-resistance": {"type": "energyResistance"},
    "option.fast-healing": {"type": "fastHealing"},
    "option.regeneration": {"type": "regeneration"},
}
for option_id, effect in direct_option_effects.items():
    options[option_id].update({"effectMode": "typed", "effects": effect})
options["option.save-boost"]["parameters"] = {
    "save": {"type": "enum", "values": ["all", "fortitude", "reflex", "will"]},
}
options["option.extra-armor"]["parameters"] = {
    "armorSource": {"type": "enum", "values": ["natural", "manufactured"]},
}
energy_types = ["acid", "cold", "electricity", "fire", "force", "sonic"]
ability_names = ["strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"]
humanoid_favored_enemy_subtypes = ["aquatic", "dwarf", "elf", "giant", "gnome", "goblinoid", "half-elf", "half-orc", "halfling", "human", "orc", "shapechanger"]
outsider_favored_enemy_subtypes = ["aeon", "agathion", "air", "angel", "archon", "asura", "azata", "cold", "daemon", "demodand", "demon", "devil", "div", "earth", "elemental", "fire", "inevitable", "kami", "nightshade", "oni", "protean", "psychopomp", "qlippoth", "rakshasa", "water"]
favored_enemy_targets = [
    *creature_types,
    *(f"humanoid:{name}" for name in humanoid_favored_enemy_subtypes),
    *(f"outsider:{name}" for name in outsider_favored_enemy_subtypes),
]
parameter_specs = {
    "option.ability-damage": {"ability": {"type": "enum", "values": ability_names}, "mode": {"type": "enum", "values": ["damage", "drain"]}, "scope": {"type": "enum", "values": ["all-attacks", "weapons", "melee-touch"]}},
    "option.combatants-touch": {"ability": {"type": "enum", "values": ["strength", "dexterity", "constitution"]}},
    "option.favored-enemy": {"targets": {"type": "enum-array", "minCount": 1, "values": favored_enemy_targets}},
    "option.repositioning-attack": {"attackType": {"type": "selected-attack"}, "direction": {"type": "enum", "values": ["push", "pull"]}},
    "option.trap-squares": {"kind": {"type": "enum", "values": ["mundane", "magical"]}, "damageType": {"type": "enum", "values": ["bludgeoning", "piercing", "slashing", "acid", "cold", "electricity", "fire"]}},
    "option.breath-weapon": {"shape": {"type": "enum", "values": ["cone", "line"]}, "damageType": {"type": "enum", "values": energy_types}},
    "option.damaging-body": {"damageType": {"type": "enum", "values": ["bludgeoning", "piercing", "slashing", *energy_types]}},
    "option.disease": {"ability": {"type": "enum", "values": ability_names}, "attackType": {"type": "selected-attack"}},
    "option.draining-touch": {"ability": {"type": "enum", "values": ability_names}},
    "option.engulf": {"mode": {"type": "enum", "values": ["high-damage", "bleed", "blinded", "deafened", "energy-drain", "frightened", "nauseated", "paralyzed"]}},
    "option.fear-attack": {"area": {"type": "enum", "values": ["cone", "burst", "ray"]}},
    "option.energy-drain": {"attackType": {"type": "selected-attack"}},
    "option.paralysis": {"attackType": {"type": "selected-attack"}},
    "option.regeneration": {"bypass": {"type": "enum-array", "minCount": 1, "sourceDefaultCount": 2, "values": ["acid", "cold", "electricity", "fire", "sonic", "chaotic", "evil", "good", "lawful"]}},
    "option.critical-striker": {"attackType": {"type": "selected-attack"}},
    "option.power-attack": {"attackType": {"type": "selected-attack"}},
    "option.powerful-charge": {"attackType": {"type": "selected-attack"}},
    "option.quivering-palm": {"attackType": {"type": "selected-attack"}},
    "option.rage": {"trigger": {"type": "enum", "values": ["voluntary", "after-damage"]}},
    "option.slaying-attack": {"save": {"type": "enum", "values": ["fortitude", "will"]}},
    "option.stun-attack": {"attackType": {"type": "selected-attack"}},
    "option.extra-attack": {"attackMode": {"type": "enum", "values": ["melee", "ranged"]}},
    "option.mobile-attack": {"attackMode": {"type": "enum", "values": ["melee", "ranged"]}},
    "option.damage-reduction": {"bypass": {"type": "enum-array", "minCount": 1, "values": ["bludgeoning", "piercing", "slashing", "adamantine", "cold-iron", "silver", "magic", "chaotic", "evil", "good", "lawful", "none"]}},
    "option.energy-resistance": {"energyTypes": {"type": "enum-array", "minCount": 2, "values": ["acid", "cold", "electricity", "fire", "sonic"]}, "resistanceValue": {"type": "integer", "optional": True}},
    "option.immunity": {"immunities": {"type": "string-array", "minCount": 1}},
    "option.bestow-major-condition": {"condition": {"type": "enum", "values": ["dazed", "paralyzed", "stunned"]}},
    "option.bestow-minor-condition": {"condition": {"type": "enum", "values": ["dazzled", "deafened", "fatigued", "shaken", "sickened"]}},
    "option.bestow-moderate-condition": {"condition": {"type": "enum", "values": ["blinded", "exhausted", "frightened", "nauseated"]}},
    "option.bypass-dr": {"bypass": {"type": "enum-array", "minCount": 1, "sourceDefaultCount": 2, "values": ["adamantine", "chaotic", "cold-iron", "evil", "good", "lawful", "magic", "silver"]}},
    "option.channel-destruction": {"energyType": {"type": "enum", "values": energy_types[:4]}},
    "option.energy-explosion": {"energyType": {"type": "enum", "values": energy_types}},
    "option.energy-infusion": {"energyType": {"type": "enum", "values": energy_types}},
    "option.evil-eye": {"penalty": {"type": "enum", "values": ["ability-checks", "attack-rolls", "saving-throws", "skill-checks", "ac"]}},
    "option.magic-attack": {"damageType": {"type": "enum", "values": ["bludgeoning", "piercing", "slashing", "cold", "electricity", "fire", "force", "sonic"]}},
    "option.potent-magic-damage": {"descriptor": {"type": "string"}},
    "option.smite": {"alignment": {"type": "enum", "values": ["chaotic", "evil", "good", "lawful"]}},
    "option.channel-energy": {"energy": {"type": "enum", "values": ["positive", "negative"]}, "targets": {"type": "enum", "values": ["living", "undead"]}},
    "option.transfer-hit-points": {"direction": {"type": "enum", "values": ["self-to-ally", "ally-to-self"]}},
    "option.contingent-spell": {"spellId": {"type": "string", "catalogKind": "spell"}, "trigger": {"type": "string"}},
    "option.metamagic-spell": {"spellId": {"type": "string", "catalogKind": "spell"}, "metamagic": {"type": "enum", "values": ["empower", "enlarge", "extend", "maximize", "quicken", "widen"]}},
    "option.mutagen": {"package": {"type": "enum", "values": ["dexterity", "strength", "constitution"]}},
    "option.aura-of-resistance": {"descriptors": {"type": "string-array", "minCount": 1, "sourceDefaultCount": 2}},
    "option.inspire-competence": {"skillId": {"type": "string", "catalogKind": "skill"}},
    "option.magic-weapon": {"property": {"type": "enum", "values": ["bane", "energy", "keen", "returning", "seeking", "vicious", "aligned", "energy-burst"]}},
}
for option_id, parameters in parameter_specs.items():
    options[option_id]["parameters"] = parameters
class_grafts["graft.class.ranger"]["optionChoiceSpecs"] = [{
    "name": "favoredEnemyTargets", "optionId": "option.favored-enemy", "parameter": "targets",
    "type": "enum-array", "values": options["option.favored-enemy"]["parameters"]["targets"]["values"],
    "countThresholds": [4, 9, 14, 19],
}]
options["option.corrupting-touch"]["prerequisites"] = [{"type": "subtype", "id": "graft.subtype.incorporeal"}]
options["option.snatch"]["prerequisites"] = [{"type": "option", "id": "option.improved-combat-maneuver"}]
options["option.spontaneous-casting"]["prerequisites"] = [{"type": "array", "id": "array.spellcaster"}]

# Graft option text is source-controlled; variants remain verbatim while IDs
# and flexible slots become deterministic engine inputs.
option_names = sorted(
    [(definition["name"].lower(), option_id) for option_id, definition in options.items()]
    + [("mounted mastery", "option.mounted-master"), ("devastating blast", "option.breath-weapon")],
    key=lambda item: len(item[0]), reverse=True,
)
number_words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}


def parse_graft_options(text):
    parts = re.split(r"options?—", text.lower(), maxsplit=1)
    if len(parts) == 1:
        return [], []
    option_text = parts[1].replace("inf lict", "inflict")
    search_text = option_text
    matches_by_position = []
    occupied = []
    for name, option_id in option_names:
        matches = re.finditer(rf"(?<![a-z]){re.escape(name)}(?![a-z])", search_text)
        match = next((
            match for match in matches
            if search_text[:match.start()].count("(") == search_text[:match.start()].count(")")
            and not any(match.start() < end and match.end() > start for start, end in occupied)
        ), None)
        if match:
            occupied.append((match.start(), match.end()))
            parameters = {}
            argument_match = re.match(r"\s*\*?\s*(?:(\d+)\s*)?\(([^)]*)\)", option_text[match.end():])
            numeric_value = int(argument_match.group(1)) if argument_match and argument_match.group(1) else None
            argument = argument_match.group(2).strip().lower() if argument_match else None
            argument_items = [
                slug(item.strip()) for item in re.split(r",|\band\b", argument or "") if item.strip()
            ]
            if option_id == "option.immunity" and argument_items:
                parameters["immunities"] = [item.replace("-", " ") for item in argument_items]
            elif option_id == "option.energy-resistance" and argument_items and all(item in {"acid", "cold", "electricity", "fire", "sonic"} for item in argument_items):
                parameters["energyTypes"] = argument_items
            elif option_id == "option.smite" and argument_items and argument_items[0] in {"chaotic", "evil", "good", "lawful"}:
                parameters["alignment"] = argument_items[0]
            elif option_id == "option.bypass-dr" and argument_items and all(item in {"adamantine", "chaotic", "cold-iron", "evil", "good", "lawful", "magic", "silver"} for item in argument_items):
                parameters["bypass"] = argument_items
            elif option_id == "option.damage-reduction" and argument:
                fixed_dr = re.match(r"(\d+)\s*/\s*([a-z -]+)$", argument)
                if fixed_dr:
                    numeric_value = int(fixed_dr.group(1))
                    parameters["bypass"] = [slug(item.strip()) for item in re.split(r"\band\b", fixed_dr.group(2)) if item.strip()]
                elif argument_items and all(item in {"bludgeoning", "piercing", "slashing", "adamantine", "cold-iron", "silver", "magic", "chaotic", "evil", "good", "lawful", "none"} for item in argument_items):
                    parameters["bypass"] = argument_items
            elif option_id == "option.regeneration" and argument.startswith("overcome by "):
                bypass = [slug(item.strip()) for item in re.split(r"\bor\b|\band\b", argument.removeprefix("overcome by ")) if item.strip()]
                if all(item in {"acid", "cold", "electricity", "fire", "sonic", "chaotic", "evil", "good", "lawful"} for item in bypass):
                    parameters["bypass"] = bypass
            elif option_id == "option.aura-of-resistance" and argument_items:
                parameters["descriptors"] = [item.replace("-", " ") for item in argument_items]
            elif option_id == "option.magic-weapon" and argument_items and ("energy" in argument_items or argument_items[0] in {"bane", "keen", "returning", "seeking", "vicious", "aligned", "energy-burst"}):
                parameters["property"] = "energy" if "energy" in argument_items else argument_items[0]
            elif option_id == "option.slaying-attack" and argument_items and argument_items[0] in {"fortitude", "will"}:
                parameters["save"] = argument_items[0]
            elif option_id == "option.mobile-attack" and argument_items and argument_items[0] in {"melee", "ranged"}:
                parameters["attackMode"] = argument_items[0]
            elif option_id == "option.at-will-magic" and argument:
                spell = next((spell for spell in spells.values() if spell["name"].lower() == argument), None)
                if spell:
                    parameters["spellId"] = spell["id"]
                    if spell["highest"] > 1:
                        parameters["maxSpellLevel"] = spell["highest"]
            elif option_id == "option.change-shape" and argument:
                if argument == "small or medium animal":
                    parameters["forms"] = ["Small animal", "Medium animal"]
                else:
                    forms = re.split(r"\bor\b", argument.split(",", 1)[0])
                    parameters["forms"] = [form.strip().title() for form in forms if form.strip()]
            elif option_id == "option.secondary-magic":
                list_name = "good" if "secondary magic (good)" in option_text else "evil" if "secondary magic (evil)" in option_text else None
                if list_name:
                    parameters["spellListId"] = f"spell-list.{list_name}"
            elif option_id == "option.improved-combat-maneuver":
                parameters["maneuver"] = "grapple"
            elif option_id == "option.spontaneous-casting":
                choices = [
                    value for source_name, value in (("summon nature’s ally", "summon-natures-ally"), ("summon monster", "summon-monster"), ("cure", "cure"), ("inflict", "inflict"))
                    if source_name in option_text
                ]
                if len(choices) == 1:
                    parameters["spellType"] = choices[0]
            elif option_id == "option.change-shape" and "small or medium animal" in option_text:
                parameters["forms"] = ["Small animal", "Medium animal"]
            elif option_id == "option.terrain-stride" and "undergrowth" in option_text:
                parameters["terrain"] = "undergrowth"
            grant = {"optionId": option_id, "parameters": parameters, "sourceText": text}
            if numeric_value is not None and option_id in {"option.damage-reduction", "option.energy-resistance"}:
                grant["value"] = numeric_value
            elif option_id == "option.fast-healing":
                value_match = re.match(r"\s*(\d+)", option_text[match.end():])
                if value_match:
                    grant["value"] = int(value_match.group(1))
            matches_by_position.append((match.start(), grant))
    grants = [grant for _, grant in sorted(matches_by_position)]
    dr_match = re.search(r"\bdr (\d+)/([a-z -]+?)(?=\s*\(|,|;|\.|$)", option_text)
    if dr_match and not any(grant["optionId"] == "option.damage-reduction" for grant in grants):
        bypass = [slug(item.strip()) for item in re.split(r"\band\b", dr_match.group(2)) if item.strip()]
        grant = {"optionId": "option.damage-reduction", "parameters": {"bypass": bypass}, "value": int(dr_match.group(1)), "sourceText": text}
        increase = re.search(r"increases to dr (\d+)/[a-z -]+ at cr (\d+)", option_text)
        if increase:
            grant["valueByCR"] = [{"minCR": int(increase.group(2)), "value": int(increase.group(1))}]
        grants.append(grant)
    slots = [
        {"category": category, "count": number_words[count]}
        for count, category in re.findall(r"\b(one|two|three|four|five|six) (?:additional )?(combat|magic|social|any)(?! or\b)\b", option_text)
    ]
    return grants, slots


for graft in [*subtypes.values(), *templates.values()]:
    graft["optionGrants"], parsed_slots = parse_graft_options(graft["ruleText"])
    graft.setdefault("optionSlots", []).extend(parsed_slots)
half_dragon = templates["graft.template.half-dragon"]
next(grant for grant in half_dragon["optionGrants"] if grant["optionId"] == "option.immunity")["parameters"] = {"immunities": ["sleep", "paralysis"]}
next(grant for grant in half_dragon["optionGrants"] if grant["optionId"] == "option.breath-weapon")["frequency"] = "1/day"
ghost = templates["graft.template.ghost"]
ghost_choice_ids = [
    "option.at-will-magic", "option.corrupting-gaze", "option.draining-touch",
    "option.frightful-presence", "option.malevolence",
]
ghost["optionGrants"] = [grant for grant in ghost["optionGrants"] if grant["optionId"] not in ghost_choice_ids]
ghost["optionChoiceGrant"] = {
    "minCR": 6, "perCR": 3, "optionIds": ghost_choice_ids,
    "parametersByOption": {
        "option.at-will-magic": {"spellId": "spell.core.telekinesis", "maxSpellLevel": 5},
    },
}
for graft in class_grafts.values():
    graft["optionGrants"], graft["optionSlots"] = parse_graft_options(graft.get("optionRuleText", ""))
    for entry in graft.get("crEntries", []):
        entry["optionGrants"], entry["optionSlots"] = parse_graft_options(entry["ruleText"])
        if "replace secondary magic with spellcasting" in entry["ruleText"].lower():
            entry["removeOptionGrantIds"] = ["option.secondary-magic"]
        spellcasting = re.search(r"spellcasting \(as if CR (\d+)\)", entry["ruleText"], re.IGNORECASE)
        if spellcasting:
            entry["spellcastingAsCR"] = int(spellcasting.group(1))
        secondary_magic = re.search(r"secondary magic \(as if CR (\d+)\)", entry["ruleText"], re.IGNORECASE)
        if secondary_magic:
            entry["secondaryMagicAsCR"] = int(secondary_magic.group(1))
        speed = re.search(r"Increase speed by (\d+) feet", entry["ruleText"], re.IGNORECASE)
        if speed:
            entry["speedAdjustment"] = int(speed.group(1))
class_grafts["graft.class.bard"]["skillSlots"] = [{"rank": "master", "count": 1}]
class_grafts["graft.class.ranger"]["skillSlots"] = [{"rank": "master", "count": 1}]
druid_forms = {
    3: ["Small animal", "Medium animal"],
    5: ["Tiny animal", "Small animal", "Medium animal", "Large animal", "Small elemental"],
    7: ["Any size animal", "Medium or smaller elemental", "Small plant", "Medium plant"],
    9: ["Any size animal", "Large or smaller elemental", "Large or smaller plant"],
    11: ["Any size animal", "Huge or smaller elemental", "Huge or smaller plant"],
    18: ["Any size animal", "Huge or smaller elemental", "Huge or smaller plant"],
}
for entry in class_grafts["graft.class.druid"]["crEntries"]:
    if entry["minCR"] in druid_forms:
        next(grant for grant in entry["optionGrants"] if grant["optionId"] == "option.change-shape")["parameters"] = {"forms": druid_forms[entry["minCR"]]}

skills = {}
for skill in (
    "perception", "stealth", "survival", "climb", "fly", "swim", "intimidate", "acrobatics",
    "appraise", "bluff", "craft-alchemy", "diplomacy", "disable-device", "disguise",
    "escape-artist", "handle-animal", "heal", "perform", "ride", "sense-motive", "spellcraft",
    "use-magic-device",
    "knowledge-arcana", "knowledge-dungeoneering", "knowledge-engineering", "knowledge-geography",
    "knowledge-history", "knowledge-local", "knowledge-nature", "knowledge-nobility", "knowledge-planes",
    "knowledge-religion",
):
    skills[f"skill.{skill}"] = {
        "id": f"skill.{skill}",
        "name": skill.title(),
        "default": "abilityModifier",
        "sourceRef": unchained_ref("Step 8: Skills", 4334, 240, entry=skill.title()),
    }

catalog = {
    "schemaVersion": "1",
    "catalogVersion": None,
    "catalogStatus": {
        "step1": "complete",
        "worgVerticalSlice": "complete",
        "spellMetadata": "APG/UM/UC and ACG follow-up metadata locally anchored with official-source URLs",
        "spellListEvaluation": "structured primary/secondary bands and typed numeric/choice benefits complete",
        "coreSpellLists": "source-backed class-list metadata",
        "grafts": "all 19 class, 41 source-listed subtype, 10 template, and nine size grafts catalogued",
        "options": "all 159 Step-7 table options plus gaze, pounce, and change shape; direct numeric effects typed, complex actions retained as source rules",
    },
    "sources": {
        "pathfinder-unchained-txt": {"sourceId": "pathfinder-unchained-txt", "file": "Pathfinder Unchained.txt", "sha256": unchained_hash, "description": "Local extracted Pathfinder Unchained source"},
        "pathfinder-core-txt": {"sourceId": "pathfinder-core-txt", "file": "Pathfinder_RPG_Core_Rulebook.txt", "sha256": core_hash, "description": "Local extracted Core Rulebook source"},
        "bestiary-txt": {"sourceId": "bestiary-txt", "file": "beastiary.txt", "sha256": bestiary_hash, "description": "Local extracted Bestiary source"},
        "advanced-players-guide": {"sourceId": "advanced-players-guide", "file": "tools/build_catalog.py", "sha256": build_script_hash, "description": "Locally anchored official Paizo PRD APG spell metadata"},
        "ultimate-magic": {"sourceId": "ultimate-magic", "file": "tools/build_catalog.py", "sha256": build_script_hash, "description": "Locally anchored official Paizo PRD UM spell metadata"},
        "ultimate-combat": {"sourceId": "ultimate-combat", "file": "tools/build_catalog.py", "sha256": build_script_hash, "description": "Locally anchored official Paizo PRD UC spell metadata"},
        "advanced-class-guide": {"sourceId": "advanced-class-guide", "file": "tools/build_catalog.py", "sha256": build_script_hash, "description": "Locally anchored official Paizo PRD ACG spell metadata"},
        "core-rulebook-feats": {"sourceId": "core-rulebook-feats", "file": "tools/build_catalog.py", "sha256": build_script_hash, "description": "Locally anchored official Core metamagic feat metadata"},
    },
    "arrays": arrays,
    "grafts": {"creatureTypes": creature_types, "classGrafts": class_grafts, "subtypes": subtypes, "templates": templates, "sizes": sizes},
    "options": options,
    "skills": skills,
    "damage": damage_table,
    "naturalAttacksBySize": natural_attacks,
    "spellBands": [
        {"id": "0–3", "minCR": 0, "maxCR": 3},
        {"id": "4–7", "minCR": 4, "maxCR": 7},
        {"id": "8–11", "minCR": 8, "maxCR": 11},
        {"id": "12–15", "minCR": 12, "maxCR": 15},
        {"id": "16+", "minCR": 16, "maxCR": None},
    ],
    "spellLists": spell_lists,
    "spells": spells,
    "metamagic": {"empower": 2, "enlarge": 1, "extend": 1, "maximize": 3, "quicken": 4, "widen": 3},
    "metamagicRules": {
        key: {
            "id": f"metamagic.{key}",
            "name": name,
            "levelIncrease": increase,
            "sourceRef": [local_metadata_ref("core-rulebook-feats", None, "https://legacy.aonprd.com/coreRulebook/feats.html", name)],
        }
        for key, name, increase in (
            ("empower", "Empower Spell", 2),
            ("enlarge", "Enlarge Spell", 1),
            ("extend", "Extend Spell", 1),
            ("maximize", "Maximize Spell", 3),
            ("quicken", "Quicken Spell", 4),
            ("widen", "Widen Spell", 3),
        )
    },
    "derivedRules": {"cmb": "highAttackBonus", "concentration": "crPlusAbilityModifier", "hitDice": "max(1,cr)", "initiative": "dexterityModifier", "perception": "goodSkillUnlessMaster", "speed": "conceptSelection"},
    "aliases": {"arrays": {"combatant": "array.combatant", "expert": "array.expert", "spellcaster": "array.spellcaster"}, "grafts": {"magical-beast": "graft.creature-type.magical-beast", "medium": "graft.size.medium"}, "options": {"improved-combat-maneuver": "option.improved-combat-maneuver"}},
}
catalog["catalogVersion"] = "sha256:" + hashlib.sha256(json.dumps(
    {key: value for key, value in catalog.items() if key != "catalogVersion"},
    ensure_ascii=False, sort_keys=True, separators=(",", ":"),
).encode()).hexdigest()
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n")
print(f"wrote {OUT}: {len(spells)} spells, {len(spell_lists)} spell lists")
