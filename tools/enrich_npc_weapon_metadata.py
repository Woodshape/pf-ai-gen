#!/usr/bin/env python3
"""Refresh resolved Core weapon dice/critical/hand metadata from Table: Weapons."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def enrich(records):
    rows = {}
    hand = None
    hand_line = 108
    for number, line in enumerate((ROOT / "sources/npc/aonprd/equipment.txt").read_text().splitlines(), 1):
        if not 108 <= number <= 215:
            continue
        if line in {"Light Melee Weapons", "One-Handed Melee Weapons", "Two-Handed Melee Weapons", "Ranged Weapons"}:
            hand = line.split(" Melee")[0].replace(" Weapons", "").lower()
            hand_line = number
        cells = line.split("\t")
        if len(cells) == 9:
            rows[cells[0].lower()] = (number, cells, hand, hand_line)
    for record in records:
        if record["id"] == "item.greatsword":
            record.update(catalogStatus="resolved", priceCp=5000, weightLb=8, npcGearCategory="weapons",
                          effects={"weaponType": "greatsword", "weaponCategory": "martial", "damageType": "S"})
            record.pop("gapCode", None)
        if record.get("catalogStatus") != "resolved" or record.get("category") != "weapon":
            continue
        effects = record["effects"]
        name = {"shortsword": "sword, short"}.get(effects.get("weaponType"), effects.get("weaponType"))
        if name not in rows:
            continue
        number, cells, hand, hand_line = rows[name]
        effects.update(damageDieBySize={"small": cells[2], "medium": cells[3]},
                       critRange=int(cells[4].split("–")[0]) if "–" in cells[4] else 20,
                       critMultiplier=int(re.search(r"×(\d+)", cells[4])[1]), handedness=hand)
        effects.pop("damageDie", None)
        if hand == "light":
            effects["lightWeapon"] = True
        if hand == "two-handed":
            effects["twoHanded"] = True
        if hand == "ranged":
            effects["rangeIncrement"] = int(cells[5].split()[0])
        if name == "sling":
            effects["reloadAction"] = "move"
        refs = record.get("sourceRef", [])
        refs = refs if isinstance(refs, list) else [refs]
        refs = [ref for ref in refs if ref.get("section") != "Table: Weapons; attack metadata" and ref.get("provenanceStatus") != "catalog-gap"]
        record["sourceRef"] = [*refs, {"sourceId": "source.aon-equipment", "section": "Table: Weapons; attack metadata",
                                      "txtLines": [hand_line, 274 if name == "sling" else number], "entry": "\t".join(cells),
                                      "provenanceStatus": "resolved"}]
    return records


if __name__ == "__main__":
    path = ROOT / "catalog/npc/items.fragment.json"
    data = json.loads(path.read_text())
    enrich(data["records"])
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
