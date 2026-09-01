#!/usr/bin/env python3
"""Independent parser for the hash-anchored Core Rulebook spell-list extract.

The local Core Rulebook PDF is a 16-page excerpt whose only complete, machine
readable NPC-relevant data is the class spell-list chapter.  This tool parses
``sources/npc/core-rulebook-extract.spell-lists.txt`` (hash recorded in
``sources/npc/MANIFEST.json``) into the ``spells`` catalog fragment with full
per-row line provenance.  It never guesses: any line it cannot classify is
reported and, by default, fails the run so silent data loss cannot happen.

Usage from the repository root::

    python3 tools/parse_npc_sources.py --check
    python3 tools/parse_npc_sources.py --write
    python3 tools/parse_npc_sources.py --stats
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from monster_builder.catalog import CatalogError  # noqa: E402

EXTRACT_PATH = ROOT / "sources" / "npc" / "core-rulebook-extract.spell-lists.txt"
FRAGMENT_PATH = ROOT / "catalog" / "npc" / "spells.fragment.json"
MANIFEST_PATH = ROOT / "sources" / "npc" / "MANIFEST.json"
SOURCE_ID = "source.npc-crb-spell-lists"
GAP_CODE = "core-rulebook-spell-descriptions"

# Class section headers, e.g. "0-Level Bard Spells", "7th–Level Cleric Spells"
# (the extract uses both hyphen and en-dash), "0-Level Cleric Spells (Orisons)",
# and "0-Level Sorcerer/Wizard Spells (Cantrips)".
HEADER = re.compile(
    r"^(?P<level>\d+)(?:st|nd|rd|th)?[-\u2013](?:Level|-level)\s+(?P<classes>[A-Za-z/]+)\s+Spells(?:\s+\((?:Orisons|Cantrips)\))?$"
)

# List entries look like "Spell Name: description" or "Analyze DweomerF : ...";
# a single trailing M or F component marker may sit before the colon.
ENTRY = re.compile(
    r"^(?P<name>[A-Z][A-Za-z\u2019'()/,\- ]+?)\s*(?P<marker>[MF])?\s*:\s*(?P<rest>\S.*)$"
)
# Chapter furniture and page furniture: page headers/footers, the small-caps
# class-section headers ("BArd speLLs", "CLeriC speLLs"), school group headers
# inside lists, and the descriptions-section header.
FURNITURE = re.compile(
    r"^(Spells|speLLs|\d+|[A-Za-z]+ speLLs|Abjuration|Conjuration|Divination|Enchantment|Evocation|Illusion|Necromancy|Transmutation|Universal)$"
)

# Wrapped description lines that begin with a capital letter.  Every other
# capitalised line without a colon is treated as data loss, so a wrapped spell
# name can never be silently swallowed by the continuation rule.
KNOWN_CONTINUATIONS = {
    (161, "Ref lex saves, and attack rolls."),
    (1231, "AC, and Ref lex saves."),
    (1238, "AC, Ref lex saves, and attack rolls."),
    (1337, "HD or less until it performs a task."),
    (1356, "Huge animal, or Small or Medium magical beast."),
    # Two-column interleaving in the excerpt carries the first description
    # lines into the tail of the list region.
    (1668, "Acid fog creates a billowing mass of misty vapors like the solid fog"),
    (1674, "ACID SPLASH"),
    (1678, "Astral Plane."),
}

EXPECTED_LEVELS = {
    "bard": list(range(0, 7)),
    "cleric": list(range(0, 10)),
    "druid": list(range(0, 10)),
    "paladin": list(range(1, 5)),
    "ranger": list(range(1, 5)),
    "sorcerer": list(range(0, 10)),
    "wizard": list(range(0, 10)),
}

# The excerpt is the locally available portion of the Core Rulebook spell
# chapter (sources/npc/MANIFEST.json → core-rulebook-extract-spell-lists).
EXPECTED_SOURCE_LINE_COUNT = 1691

# Two-column extraction losses at page boundaries: the excerpt contains these
# list headers with zero entries between them and the next header.  They are
# recorded as empty sections instead of failing so the loss stays visible.
EXPECTED_EMPTY_SECTIONS = {("cleric", 7), ("druid", 3)}


def slugify(name: str) -> str:
    slug = "".join(char if char.isalnum() else "-" for char in name.casefold())
    return "spell." + "-".join(part for part in slug.split("-") if part)


def parse_spell_lists(text: str) -> dict[str, Any]:
    """Parse the anchored extract into class-level rows and spell records."""
    # Split on newlines only: pdftotext emits form feeds (\x0c) between pages
    # and str.splitlines would treat each one as an extra line, breaking the
    # 1-based line numbers that provenance references are anchored to.
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()  # a trailing newline is not a line
    if len(lines) != EXPECTED_SOURCE_LINE_COUNT:
        raise CatalogError(
            f"spell-list extract has {len(lines)} lines; expected {EXPECTED_SOURCE_LINE_COUNT} "
            "(the anchored fragment is immutable; update the manifest if the source changes)"
        )
    rows: list[dict[str, Any]] = []
    spells: dict[str, dict[str, Any]] = {}
    unknown: list[tuple[int, str]] = []
    current: tuple[list[str], int] | None = None  # (class ids, level)
    for offset, raw in enumerate(lines, start=1):
        line = raw.replace("\x0c", "").strip()
        if not line:
            continue
        header = HEADER.match(line)
        if header:
            classes = header.group("classes").casefold()
            keys = ["sorcerer", "wizard"] if classes == "sorcerer/wizard" else [classes]
            current = (keys, int(header.group("level")))
            continue
        if current is None or FURNITURE.match(line):
            continue
        entry = ENTRY.match(line)
        if entry is None:
            # Continuation text of a wrapped description.  Only allow-listed
            # lines are accepted; anything else fails the parse so a wrapped
            # spell name can never be silently dropped.
            if line[0].isupper() and (offset, line) not in KNOWN_CONTINUATIONS:
                unknown.append((offset, line))
            continue
        name = " ".join(entry.group("name").split())
        marker = entry.group("marker")
        for class_id in current[0]:
            rows.append({
                "classId": class_id,
                "level": current[1],
                "spellName": name,
                "componentMarker": marker,
                "txtLines": [offset, offset],
            })
        spell = spells.setdefault(name, {"classes": {}, "firstLine": offset})
        for class_id in current[0]:
            spell["classes"][class_id] = current[1]
    if unknown:
        detail = "; ".join(f"{number}: {text[:60]}" for number, text in unknown[:5])
        raise CatalogError(f"spell-list extract has unclassified capitalised lines ({len(unknown)}): {detail}")
    counts = expected_membership_counts(rows)
    empty = sorted((class_id, level) for (class_id, level), count in counts.items() if count == 0)
    counts = {key: value for key, value in counts.items() if value > 0}
    parsed_levels = set(counts)
    expected = {(class_id, level) for class_id, levels in EXPECTED_LEVELS.items() for level in levels}
    unexpected = sorted(parsed_levels - expected)
    missing = sorted(expected - parsed_levels - EXPECTED_EMPTY_SECTIONS)
    if unexpected:
        raise CatalogError(f"spell-list extract contains unexpected sections: {unexpected}")
    if missing:
        raise CatalogError(f"spell-list extract is missing expected sections: {missing}")
    empty = sorted(EXPECTED_EMPTY_SECTIONS)
    return {"rows": rows, "spells": spells, "emptySections": empty}


def expected_membership_counts(rows: list[dict[str, Any]]) -> dict[tuple[str, int], int]:
    counts: dict[tuple[str, int], int] = {}
    for row in rows:
        key = (row["classId"], row["level"])
        counts[key] = counts.get(key, 0) + 1
    return counts


def build_fragment(parsed: dict[str, Any]) -> dict[str, Any]:
    records = []
    for name in sorted(parsed["spells"]):
        spell = parsed["spells"][name]
        levels = {}
        for key, level in spell["classes"].items():
            if isinstance(key, tuple):
                for entry in key:
                    levels[entry] = level
            else:
                levels[key] = level
        membership = [
            {"classId": row["classId"], "level": row["level"], "txtLines": row["txtLines"]}
            for row in parsed["rows"]
            if row["spellName"] == name
        ]
        membership.sort(key=lambda item: (item["classId"], item["level"]))
        records.append({
            "id": slugify(name),
            "name": name,
            "catalogStatus": "partial",
            "gapCode": GAP_CODE,
            "school": None,
            "components": None,
            "levelsByClass": dict(sorted(levels.items())),
            "listMembership": membership,
            "sourceRef": {
                "sourceId": SOURCE_ID,
                "section": "Core Rulebook class spell lists",
                "txtLines": [parsed["spells"][name]["firstLine"], parsed["spells"][name]["firstLine"]],
                "entry": name,
                "provenanceStatus": "list-membership-resolved",
            },
        })
    return {"section": "spells", "records": records}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Parse the anchored Core Rulebook spell-list extract")
    parser.add_argument("--write", action="store_true", help="write the spells fragment in place")
    parser.add_argument("--check", action="store_true", help="verify the checked-in fragment matches the parse")
    parser.add_argument("--stats", action="store_true", help="print parsed counts and exit")
    args = parser.parse_args(argv)
    try:
        parsed = parse_spell_lists(EXTRACT_PATH.read_text(encoding="utf-8"))
        fragment = build_fragment(parsed)
        content = (json.dumps(fragment, ensure_ascii=False, indent=2, sort_keys=False) + "\n").encode("utf-8")
        counts = expected_membership_counts(parsed["rows"])
        if args.stats or not (args.write or args.check):
            print(f"rows={len(parsed['rows'])} spells={len(parsed['spells'])}")
            for key in sorted(counts):
                print(f"  {key[0]} level {key[1]}: {counts[key]}")
        if args.write:
            FRAGMENT_PATH.write_bytes(content)
            print(f"wrote {FRAGMENT_PATH}")
        if args.check:
            current = FRAGMENT_PATH.read_bytes()
            if current != content:
                print("spells fragment is stale; run: python3 tools/parse_npc_sources.py --write", file=sys.stderr)
                return 1
            print("spells fragment matches the anchored parse")
        return 0
    except (CatalogError, OSError) as exc:
        print(f"NPC source parse failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())