"""Source-backed active-effect snapshots and typed bonus stacking.

Selections assert that an effect has already been legally activated on this NPC.
They do not grant spells/features or simulate casting, rounds, damage or resource use.
"""
import copy

from monster_builder.errors import BoundaryError

ENERGIES = ("acid", "cold", "electricity", "fire", "sonic")
SAVES = ("fortitude", "reflex", "will")
BONUS_TYPES = {"armor", "shield", "deflection", "dodge", "morale", "competence", "resistance", "untyped"}
TARGETS = {"ac", "attack", "weaponDamage", "saves", *SAVES, "skills", "skill", "strength", "constitution"}


def validate_record(record):
    """Catalog build-time validation; runtime never interprets arbitrary formulas."""
    if record.get("catalogStatus") != "resolved":
        return
    if record.get("kind") not in {"spell", "class-ability"}:
        raise ValueError("active effect kind must be spell or class-ability")
    if any(not isinstance(record.get(field), str) or not record[field] for field in ("rulesText", "duration")):
        raise ValueError("active effects require rulesText and duration")
    restrictions = record.get("restrictions", [])
    if not isinstance(restrictions, list) or any(not isinstance(text, str) for text in restrictions):
        raise ValueError("active effect restrictions must be text entries")
    parameters = record.get("parameters", [])
    if not isinstance(parameters, list) or len(set(parameters)) != len(parameters) or set(parameters) - {"energyType", "skillId"}:
        raise ValueError("unsupported active effect parameters")
    tiers = record.get("tiers")
    if not isinstance(tiers, list) or not tiers:
        raise ValueError("active effects require level tiers")
    previous = 0
    for tier in tiers:
        if not isinstance(tier, dict) or set(tier) - {"level", "modifiers", "energyResistance", "absorptionPerLevel", "absorptionMaximum"}:
            raise ValueError("unsupported active effect tier fields")
        if ("absorptionPerLevel" in tier) != ("absorptionMaximum" in tier):
            raise ValueError("absorption requires both per-level and maximum values")
        if not isinstance(tier.get("modifiers", []), list):
            raise ValueError("effect modifiers must be an array")
        level = tier.get("level")
        if type(level) is not int or not previous < level <= 20:
            raise ValueError("effect tiers must have increasing levels from 1 through 20")
        previous = level
        for modifier in tier.get("modifiers", []):
            if not isinstance(modifier, dict) or set(modifier) - {"stat", "type", "value", "condition"} or modifier.get("stat") not in TARGETS or modifier.get("type") not in BONUS_TYPES or type(modifier.get("value")) is not int:
                raise ValueError("invalid typed active-effect modifier")
            if modifier["stat"] == "skill" and "skillId" not in parameters:
                raise ValueError("a selected-skill modifier requires the skillId parameter")
            if "condition" in modifier and (not isinstance(modifier["condition"], str) or not modifier["condition"]):
                raise ValueError("invalid effect condition")
        for field in ("energyResistance", "absorptionPerLevel", "absorptionMaximum"):
            if field in tier and (type(tier[field]) is not int or tier[field] <= 0 or "energyType" not in parameters):
                raise ValueError("energy effects require positive values and an energy parameter")


def validate_selections(values, catalog):
    path = "/selections/activeEffects"
    if not isinstance(values, list) or len(values) > 64:
        raise BoundaryError("selection.type-invalid", "activeEffects must be an array of at most 64 effects", path)
    seen = set()
    for index, value in enumerate(values):
        location = f"{path}/{index}"
        allowed = {"effectId", "sourceLevel", "enabled", "energyType", "skillId", "sourceName", "remainingDuration"}
        if not isinstance(value, dict) or set(value) - allowed:
            raise BoundaryError("selection.type-invalid", "invalid active effect fields", location)
        effect_id = value.get("effectId")
        if not isinstance(effect_id, str) or effect_id not in catalog.entries("activeEffect"):
            raise BoundaryError("catalog.id-unknown", "unknown active effect ID", f"{location}/effectId")
        record = catalog.entries("activeEffect")[effect_id]
        if record.get("catalogStatus") != "resolved":
            raise BoundaryError("npc.catalog-gap", "active effect rules are not resolved", location)
        level = value.get("sourceLevel")
        if type(level) is not int or not record["tiers"][0]["level"] <= level <= 20:
            raise BoundaryError("selection.value-invalid", f"sourceLevel must be {record['tiers'][0]['level']}–20 (caster or supplying class level)", f"{location}/sourceLevel")
        if "enabled" in value and not isinstance(value["enabled"], bool):
            raise BoundaryError("selection.type-invalid", "enabled must be a boolean", f"{location}/enabled")
        for field in ("sourceName", "remainingDuration"):
            if field in value and (not isinstance(value[field], str) or not value[field].strip() or len(value[field]) > 200):
                raise BoundaryError("selection.type-invalid", f"{field} must be nonempty text of at most 200 characters", f"{location}/{field}")
        parameters = record.get("parameters", [])
        for parameter, options in (("energyType", ENERGIES), ("skillId", catalog.entries("skill"))):
            selected = value.get(parameter)
            if parameter in parameters:
                if not isinstance(selected, str) or selected not in options:
                    raise BoundaryError("selection.value-invalid", f"choose a valid {parameter}", f"{location}/{parameter}")
                if parameter == "skillId" and catalog.entries("skill")[selected].get("catalogStatus") != "resolved":
                    raise BoundaryError("npc.catalog-gap", "selected effect skill is not source-resolved", f"{location}/{parameter}")
            elif parameter in value:
                raise BoundaryError("selection.value-invalid", f"this effect has no {parameter} parameter", f"{location}/{parameter}")
        identity = (effect_id, value.get("energyType"), value.get("skillId"))
        if value.get("enabled", True):
            if identity in seen:
                raise BoundaryError("npc.active-effect-duplicate", "keep one active instance of each effect/parameter combination", location)
            seen.add(identity)


def resolve(values, catalog):
    """Return canonical active entries and expanded typed modifiers, without mutation."""
    entries, modifiers, refs = [], [], []
    for selection in values:
        if not selection.get("enabled", True):
            continue
        record = catalog.entries("activeEffect")[selection["effectId"]]
        level = selection["sourceLevel"]
        tier = next(t for t in reversed(record["tiers"]) if t["level"] <= level)
        source_refs = record["sourceRef"] if isinstance(record["sourceRef"], list) else [record["sourceRef"]]
        refs.extend(copy.deepcopy(source_refs))
        entry = {**copy.deepcopy(selection), "name": record["name"], "kind": record["kind"],
                 "duration": record["duration"], "rulesText": record["rulesText"], "sourceRefs": copy.deepcopy(source_refs)}
        entry["modifiers"] = []
        for modifier in tier.get("modifiers", []):
            stat = modifier["stat"]
            targets = SAVES if stat == "saves" else [selection["skillId"] if stat == "skill" else stat]
            for target in targets:
                expanded = {**modifier, "stat": target, "effectId": record["id"]}
                modifiers.append(expanded)
                entry["modifiers"].append(copy.deepcopy(expanded))
        if "energyResistance" in tier:
            entry["energyResistance"] = tier["energyResistance"]
        if "absorptionPerLevel" in tier:
            entry["absorptionPool"] = min(tier["absorptionMaximum"], tier["absorptionPerLevel"] * level)
        entry["restrictions"] = copy.deepcopy(record.get("restrictions", []))
        entries.append(entry)
    return entries, modifiers, refs


def bonus(modifiers, stat, bonus_type=None, baseline=0, condition=None):
    """Highest same-type bonus; distinct penalties stack; dodge/untyped stack.

    `baseline` is an existing bonus of `bonus_type` (armor, shield, resistance).
    Conditional modifiers are opt-in and never leak into unconditional totals.
    """
    by_type = {}
    if bonus_type is not None:
        by_type[bonus_type] = [baseline]
    for modifier in modifiers:
        if modifier["stat"] != stat and not (stat.startswith("skill.") and modifier["stat"] == "skills"):
            continue
        if modifier.get("condition") not in (None, condition):
            continue
        if bonus_type is None or modifier["type"] == bonus_type:
            by_type.setdefault(modifier["type"], []).append(modifier["value"])
    return sum(sum(values) if kind in {"dodge", "untyped"} else
               max([0, *[v for v in values if v > 0]]) + sum(v for v in values if v < 0)
               for kind, values in by_type.items())


def conditional_modifiers(modifiers, resistance_bonus=0):
    """Additional conditional increments above the already-applied typed baseline."""
    results = []
    for stat, kind, condition in sorted({(m["stat"], m["type"], m["condition"]) for m in modifiers if m.get("condition")}):
        baseline = resistance_bonus if kind == "resistance" and stat in SAVES else 0
        unconditional = bonus(modifiers, stat, kind, baseline)
        delta = bonus(modifiers, stat, kind, baseline, condition) - unconditional
        if delta:
            results.append({"stat": stat, "bonus": delta, "bonusType": kind,
                            "condition": f"{condition} ({kind}; same-type conditional bonuses do not stack)"})
    return results
