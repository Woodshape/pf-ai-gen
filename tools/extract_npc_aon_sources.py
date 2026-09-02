#!/usr/bin/env python3
"""Extract stable, line-citable text from the archived Archives of Nethys pages."""

from __future__ import annotations

import argparse
import re
import sys
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "sources" / "reference" / "aonprd"
OUTPUT = ROOT / "sources" / "npc" / "aonprd"
SOURCES = {
    "creating-npcs": ("id", "MainContent_DetailedOutput"),
    "core-races": ("class", "body"),
    "character-classes": ("class", "body"),
    "npc-classes": ("class", "body"),
    "skills": ("class", "body"),
    "skill-descriptions": ("class", "body"),
    "feats": ("class", "body"),
    "equipment": ("class", "body"),
    "combat": ("class", "body"),
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify extracts without rewriting them")
    args = parser.parse_args(argv)
    for name, (attribute, value) in SOURCES.items():
        source = RAW / f"{name}.html"
        destination = OUTPUT / f"{name}.txt"
        try:
            content = extract(source, attribute, value)
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
