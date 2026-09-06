#!/usr/bin/env python3
"""Copy spell metadata from archived individual spell headers, never effects."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def enrich(records):
    for record in records:
        refs = record.get("sourceRef", [])
        refs = refs if isinstance(refs, list) else [refs]
        source = next((ref for ref in refs if ref.get("sourceId", "").startswith("source.aon-spell-")), None)
        if not source:
            continue
        path = ROOT / "sources/npc/aonprd" / (source["sourceId"].removeprefix("source.aon-") + ".txt")
        lines = path.read_text().splitlines()
        end = next(index for index, line in enumerate(lines) if line == "Description")
        for index, line in enumerate(lines[:end], 1):
            if line.startswith("School "):
                record["school"] = re.match(r"School (\w+)", line)[1].lower()
            for label, field in (("Components", "components"), ("Casting Time", "castingTime"),
                                 ("Range", "range"), ("Area", "area"), ("Duration", "duration")):
                if line.startswith(label + " "):
                    record[field] = line[len(label) + 1:]
        metadata_ref = {**source, "section": "Spell metadata", "txtLines": [3, end],
                        "entry": f"{record['name']}: school, components, casting time, range, area and duration"}
        refs = [ref for ref in refs if ref.get("section") != "Spell metadata"]
        record["sourceRef"] = [*refs, metadata_ref]
    return records


if __name__ == "__main__":
    path = ROOT / "catalog/npc/spells.fragment.json"
    data = json.loads(path.read_text())
    enrich(data["records"])
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
