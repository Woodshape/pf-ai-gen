#!/usr/bin/env python3
"""Read-only inventory of Core NPC Step-4 feats and two mechanical probes.

Run: python3 tools/audit_npc_feats.py
This reports current behavior; it does not make missing feats selectable.
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from monster_builder import Engine


def normalized(name):
    return re.sub(r"[^a-z0-9]", "", name.lower())


def inventory():
    source = (ROOT / "sources/npc/aonprd/creating-npcs.txt").read_text()
    chapter = (ROOT / "sources/npc/aonprd/feats.txt").read_text().splitlines()
    section = source.split("Step 4: Feats\n", 1)[1].split("Step 5: Class Features", 1)[0]
    names = set()
    for line in section.splitlines():
        if ": " in line:
            names.update(line.split(": ", 1)[1].rstrip(".").replace(", and ", ", ").split(", "))
    # Source anomaly is documented, not interpreted as a real feat.
    names.discard("M")
    names.discard("Skill Focus (Ride)")  # A choice of Skill Focus, not another feat.
    for group, tag in (("item creation feats (all)", "Item Creation"), ("metamagic feats (all)", "Metamagic")):
        names.remove(group)
        names.update(line.removesuffix(f" ({tag})") for line in chapter if line.endswith(f" ({tag})"))
    names.remove("Armor Proficiency (all)")
    names.update(line.removesuffix(" (Combat)") for line in chapter if line.startswith("Armor Proficiency,") and line.endswith(" (Combat)"))
    catalog = json.loads((ROOT / "catalog/npc.json").read_text())
    records = {normalized(record["name"]): record for record in catalog["feats"].values()}
    headers = {normalized(re.sub(r" \((?:Combat|Metamagic|Item Creation)\)$", "", line)): index
               for index, line in enumerate(chapter, 1) if index >= 227 and "\t" not in line}
    rows = []
    for name in sorted(names):
        record = records.get(normalized(name), {})
        rows.append({"name": name, "id": record.get("id"), "catalogStatus": record.get("catalogStatus", "absent"),
                     "supportStatus": record.get("supportStatus", "unspecified"),
                     "treatments": record.get("treatments", []),
                     "sourceLine": headers[normalized(name)]})
    return rows


def evaluate(draft):
    response = Engine().execute({"protocolVersion": "1", "requestId": "feat-audit",
                                 "operation": "draft.create", "payload": {"draft": draft}})
    assert response["ok"], response
    evaluation = response["result"]["evaluation"]
    assert evaluation["status"] == "valid", evaluation["issues"]
    return evaluation["canonical"]


def probes():
    bard = json.loads((ROOT / "tests/fixtures/halfling-bard-2.json").read_text())
    bard["selections"]["feats"] = [{"slotId": "general-1", "featId": "feat.weapon-finesse"}]
    bard["selections"]["gear"] = [{"itemId": "item.rapier"}, {"itemId": "item.light-steel-shield"}]
    finesse = evaluate(bard)["attacks"][0]["attackBonuses"]

    # Reuse the existing composition fixture builder, not a special NPC runtime path.
    sys.path.insert(0, str(ROOT / "tests"))
    from test_npc_composition import draft_for
    catalog = json.loads((ROOT / "catalog/npc.json").read_text())
    archer = draft_for(catalog, "npc-race.human", "npc-class.warrior", 5)
    selections = archer["selections"]
    selections["classProgression"].append({"classId": "npc-class.ranger", "levels": 1})
    selections["classFeatureChoices"] = {"favoredEnemy": "humanoid-orc"}
    selections["skillGeneration"] = {"method": "simplified", "skills": [
        "skill.climb", "skill.swim", "skill.heal", "skill.knowledge-nature", "skill.perception", "skill.survival"]}
    selections["feats"][0]["featId"] = "feat.point-blank-shot"
    selections["feats"][1]["featId"] = "feat.rapid-shot"
    selections["gear"] = [{"itemId": "item.longbow"}]
    attacks = evaluate(archer)["attacks"]
    rapid = next(attack for attack in attacks if attack.get("rapidShot"))["attackBonuses"]
    return {"finesseWithProficientShield": {"actual": finesse, "expected": [4]},
            "rapidShotAtBab6": {"actual": rapid, "expected": [6, 6, 1]}}


if __name__ == "__main__":
    rows = inventory()
    print(json.dumps({"count": len(rows), "catalogCounts": dict(Counter(row["catalogStatus"] for row in rows)),
                      "supportCounts": dict(Counter(row["supportStatus"] for row in rows)),
                      "feats": rows, "mechanicalProbes": probes()}, indent=2, ensure_ascii=False))
