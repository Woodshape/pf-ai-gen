#!/usr/bin/env python3
"""Extract stable, line-citable text from the archived Archives of Nethys pages."""

from __future__ import annotations

import argparse
import re
import sys
from html import unescape
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "sources" / "reference" / "aonprd"
# Sections extracted from an already-archived page: extract name -> archived HTML name.
HTML_SOURCE_ALIASES = {
    "eidolon-base-forms-biped": "eidolon-base-forms",
    "eidolon-uc-base-forms-biped": "eidolon-uc-base-forms",
    "summoner-uc-evolutions-slam": "summoner-uc-evolutions",
}


def html_source_name(name: str) -> str:
    """Archived HTML page name providing the extract's section."""
    return HTML_SOURCE_ALIASES.get(name, name)
OUTPUT = ROOT / "sources" / "npc" / "aonprd"
SOURCES = {
    "creating-npcs": ("id", "MainContent_DetailedOutput"),
    "caster-level": ("id", "MainContent_DetailedOutput"),
    "getting-started": ("class", "body"),
    "core-races": ("class", "body"),
    "character-classes": ("class", "body"),
    "cleric": ("id", "MainContent_DataListTypes_LabelName_0"),
    "npc-classes": ("class", "body"),
    "skills": ("class", "body"),
    "skill-descriptions": ("class", "body"),
    "feats": ("class", "body"),
    "equipment": ("class", "body"),
    "combat": ("class", "body"),
    "goblin-race": ("id", "MainContent_DataListTypes_LabelName_0"),
    "halfling": ("id", "MainContent_DataListTypes_LabelName_0"),
    "druid": ("id", "MainContent_DataListTypes_LabelName_0"),
    "sorcerer": ("id", "MainContent_DataListTypes_LabelName_0"),
    "bard": ("id", "MainContent_DataListTypes_LabelName_0"),
    "ranger": ("id", "MainContent_DataListTypes_LabelName_0"),
    "rogue": ("id", "MainContent_DataListTypes_LabelName_0"),
    "magic-weapons": ("id", "MainContent_DetailedOutput"),
    "magic-armor": ("id", "MainContent_DetailedOutput"),
    "potions": ("id", "MainContent_DetailedOutput"),
    "fire-domain": ("heading", "Fire"),
    "elemental-bloodline": ("id", "MainContent_DataListTypes_LabelName_0"),
    "wands": ("id", "MainContent_DetailedOutput"),
    "use-magic-device": ("id", "MainContent_DataListTalentsAll_LabelName_0"),
    "skill-bluff": ("id", "MainContent_DataListTalentsAll_LabelName_0"),
    "skill-perform": ("id", "MainContent_DataListTalentsAll_LabelName_0"),
    "skill-perception": ("id", "MainContent_DataListTalentsAll_LabelName_0"),
    "skill-diplomacy": ("id", "MainContent_DataListTalentsAll_LabelName_0"),
    "skill-spellcraft": ("id", "MainContent_DataListTalentsAll_LabelName_0"),
    "cloak-of-resistance": ("id", "MainContent_DataListTypes_LabelName_0"),
    "designing-encounters": ("id", "MainContent_DetailedOutput"),
    **{
        f"spell-{name}": ("id", "MainContent_DataListTypes_LabelName_0")
        for name in (
            "acid-splash", "detect-magic", "light", "mage-hand", "prestidigitation", "read-magic",
            "burning-hands", "mage-armor", "magic-missile", "shield", "flaming-sphere", "mirror-image",
            "scorching-ray", "grease", "fireball", "flare", "barkskin", "cure-light-wounds",
            "entangle", "produce-flame", "summon-natures-ally-i", "summon-natures-ally-ii",
            "charm-person", "sleep", "silent-image", "feather-fall",
            "dancing-lights", "message",
        )
    },
    "spell-fireball": ("id", "MainContent_DataListTypes_LabelName_1"),
    "spell-barkskin": ("heading", "Barkskin"),
    "spell-cure-light-wounds": ("heading", "Cure Light Wounds"),
    "spell-charm-person": ("heading", "Charm Person"),
    "spell-sleep": ("heading", "Sleep"),
    "spell-silent-image": ("heading", "Silent Image"),
    "spell-feather-fall": ("heading", "Feather Fall"),
    "spell-dancing-lights": ("heading", "Dancing Lights"),
    "spell-message": ("heading", "Message"),
    "spell-entangle": ("heading", "Entangle"),
    "spell-produce-flame": ("heading", "Produce Flame"),
    "spell-summon-natures-ally-i": ("heading", "Summon Nature's Ally 1"),
    "spell-summon-natures-ally-ii": ("heading", "Summon Nature's Ally 2"),
    "elemental-ally": ("id", "MainContent_DataListTypes_LabelName_0"),
    "eidolon-unchained": ("id", "MainContent_DataListTypes_LabelName_0"),
    "eidolon-uc-subtypes": ("heading", "Elemental"),
    "eidolon-uc-base-forms-biped": ("id", "MainContent_DataListTypes_LabelName_1"),
    "summoner-uc-evolutions-slam": ("id", "MainContent_DataListTypes_LabelName_17"),
    "eidolon-base-forms": ("heading", "Quadruped"),
    "eidolon-base-forms-biped": ("heading", "Biped"),
}

# Stop tag for heading-based extractions: the tag of the next titled entry.
HEADING_STOPS = {
    "fire-domain": "h2", "eidolon-uc-subtypes": "h2", "eidolon-base-forms": "h2",
    "eidolon-base-forms-biped": "h2",
}
BLOCK_TAGS = {
    "address", "article", "aside", "blockquote", "dd", "div", "dl", "dt",
    "figcaption", "figure", "footer", "h1", "h2", "h3", "h4", "h5", "h6",
    "header", "hr", "li", "main", "nav", "ol", "p", "pre", "section", "ul",
}


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


class ContentExtractor(HTMLParser):
    """Extract one identified element, rendering table rows as tab-separated lines."""

    def __init__(self, attribute: str, value: str) -> None:
        super().__init__(convert_charrefs=True)
        self.attribute = attribute
        self.value = value
        self.capturing = False
        self.target_tag = ""
        self.target_depth = 0
        self.target_count = 0
        self.output: list[str] = []
        self.row: list[str] | None = None
        self.cell: list[str] | None = None

    def _newline(self) -> None:
        if self.output and self.output[-1] != "\n":
            self.output.append("\n")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if not self.capturing:
            if attributes.get(self.attribute) != self.value:
                return
            self.capturing = True
            self.target_tag = tag
            self.target_depth = 1
            self.target_count += 1
            return
        if tag == self.target_tag:
            self.target_depth += 1
        if tag == "tr":
            self.row = []
        elif tag in {"td", "th"}:
            self.cell = []
        elif tag == "br" and self.cell is not None:
            self.cell.append(" / ")
        elif self.cell is None and (tag in BLOCK_TAGS or tag == "br"):
            self._newline()

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if not self.capturing:
            return
        if tag == "br" and self.cell is not None:
            self.cell.append(" / ")
        elif self.cell is None and (tag in BLOCK_TAGS or tag == "br"):
            self._newline()

    def handle_endtag(self, tag: str) -> None:
        if not self.capturing:
            return
        if tag in {"td", "th"} and self.cell is not None:
            if self.row is None:
                raise ValueError("table cell outside a row")
            self.row.append(_clean("".join(self.cell)))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if any(self.row):
                self._newline()
                self.output.append("\t".join(self.row))
                self._newline()
            self.row = None
        elif self.cell is None and tag in BLOCK_TAGS:
            self._newline()
        if tag == self.target_tag:
            self.target_depth -= 1
            if self.target_depth == 0:
                self.capturing = False

    def handle_data(self, data: str) -> None:
        if self.capturing:
            (self.cell if self.cell is not None else self.output).append(data)

    def extracted_text(self) -> str:
        if self.target_count != 1 or self.capturing:
            raise ValueError(f"expected one closed {self.attribute}={self.value!r} element")
        lines = []
        for raw_line in "".join(self.output).replace("\r", "").splitlines():
            line = "\t".join(_clean(cell) for cell in raw_line.split("\t")) if "\t" in raw_line else _clean(raw_line)
            if line and any(cell for cell in line.split("\t")):
                lines.append(line)
        return "\n".join(lines) + "\n"


def extract(path: Path, attribute: str, value: str) -> str:
    parser = ContentExtractor(attribute, value)
    parser.feed(path.read_text(encoding="utf-8"))
    parser.close()
    return parser.extracted_text()


TITLE_HEADING = re.compile(
    r'<(?P<tag>h[12])\b[^>]*\bclass=["\\\']title["\\\'][^>]*>.*?</(?P=tag)>',
    re.IGNORECASE | re.DOTALL,
)


def _heading_text(markup: str) -> str:
    without_images = re.sub(r"<img\b[^>]*>", " ", markup, flags=re.IGNORECASE)
    without_tags = re.sub(r"<[^>]+>", " ", without_images)
    return re.sub(r"\s+", " ", unescape(without_tags)).strip()


def extract_heading_section(path: Path, heading: str, stop_tag: str) -> str:
    """Extract one titled AoN entry without adjacent variants or subdomains."""
    html = path.read_text(encoding="utf-8")
    matches = list(TITLE_HEADING.finditer(html))
    targets = [match for match in matches if _heading_text(match.group(0)) == heading]
    if len(targets) != 1:
        raise ValueError(f"expected one {heading!r} title heading, found {len(targets)}")
    target = targets[0]
    stops = [match.start() for match in matches if match.start() > target.start() and match.group("tag").lower() == stop_tag]
    end = stops[0] if stops else len(html)
    parser = ContentExtractor("id", "named-section")
    parser.feed(f'<div id="named-section">{html[target.start():end]}</div>')
    parser.close()
    return parser.extracted_text()


def extract_source(name: str, path: Path, attribute: str, value: str) -> str:
    if attribute == "heading":
        return extract_heading_section(path, value, HEADING_STOPS.get(name, "h1"))
    html = path.read_text(encoding="utf-8")
    if name == "designing-encounters":
        start = html.find("<b>Adding NPCs</b>:")
        end = html.find("<b>High CR Encounters</b>", start)
        if start < 0 or end < 0:
            raise ValueError("expected Adding NPCs section")
        parser = ContentExtractor("id", "adding-npcs")
        parser.feed(f'<div id="adding-npcs">{html[start:end]}</div>')
        parser.close()
        return parser.extracted_text()
    content = extract(path, attribute, value)
    if name not in {"sorcerer", "druid"}:
        return content
    start = html.find("<b>Weapon and Armor Proficiency</b>")
    end = html.find('<h2 class="title">Alternate Capstones</h2>', start)
    if start < 0 or end < 0:
        raise ValueError("expected Sorcerer class-feature section")
    parser = ContentExtractor("id", "sorcerer-features")
    parser.feed(f'<div id="sorcerer-features">{html[start:end]}</div>')
    parser.close()
    return content + parser.extracted_text()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify extracts without rewriting them")
    args = parser.parse_args(argv)
    for name, (attribute, value) in SOURCES.items():
        source = RAW / f"{html_source_name(name)}.html"
        destination = OUTPUT / f"{name}.txt"
        try:
            content = extract_source(name, source, attribute, value)
        except (OSError, UnicodeError, ValueError) as exc:
            print(f"AoN extraction failed for {source}: {exc}", file=sys.stderr)
            return 2
        if args.check:
            if not destination.is_file() or destination.read_text(encoding="utf-8") != content:
                print(f"AoN extract is stale: {destination}", file=sys.stderr)
                return 1
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content, encoding="utf-8")
    print("AoN extracts are up to date" if args.check else f"Wrote {len(SOURCES)} AoN extracts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
