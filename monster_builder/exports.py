"""Deterministic projections of immutable FinishedMonster snapshots."""

from __future__ import annotations

import copy
import html
import json
from collections.abc import Mapping
from typing import Any


_PROFILES = {"sheet", "audit"}
_DEFENSES = (
    ("ac", "AC"), ("touchAC", "touch AC"), ("flatFootedAC", "flat-footed AC"),
    ("hp", "hp"), ("fortitude", "Fort"), ("reflex", "Ref"), ("will", "Will"), ("cmd", "CMD"),
)
_DEFENSE_EFFECTS = {
    "damageReduction", "damage-reduction", "defenseBonuses", "energyResistance", "energy-resistance",
    "fastHealing", "fast-healing", "hitPointsPercent", "hit-points-percent", "immunity", "regeneration",
    "saveBonus", "saveChoice", "spellResistance",
}
_ATTACK_EFFECTS = {"attackBonus"}
_SPECIAL_EFFECTS = {"disease", "gaze", "poison", "sneak-attack", "source-rule"}
# Same-parameter copies of these options are redundant, regardless of graft.
# Other options, notably Extra Attack, may legitimately repeat.
_REDUNDANT_AUTO_OPTION_IDS = {"option.secondary-magic", "option.terrain-stride"}


def structured_sheet(snapshot: Mapping[str, Any], profile: str = "sheet") -> dict[str, Any]:
    """Arrange existing snapshot values for display; never calculate rules."""
    if profile not in _PROFILES:
        raise ValueError("profile must be 'sheet' or 'audit'")
    if not isinstance(snapshot, Mapping) or not isinstance(snapshot.get("result"), Mapping):
        raise ValueError("FinishedMonster snapshot requires a result object")
    result = snapshot["result"]
    concept = snapshot.get("concept") if isinstance(snapshot.get("concept"), Mapping) else {}
    selections = snapshot.get("selections") if isinstance(snapshot.get("selections"), Mapping) else {}
    annotations = snapshot.get("fieldAnnotations") if isinstance(snapshot.get("fieldAnnotations"), Mapping) else {}
    creation_system = str(snapshot.get("creationSystem", "simple-monster"))
    name, cr, hit_dice = str(concept.get("name", "")), result.get("cr", selections.get("cr")), result.get("hitDice")
    level = result.get("level", result.get("totalLevel"))
    recommended_cr = result.get("recommendedCR")
    if creation_system == "npc":
        if recommended_cr is not None:
            header_label = f"{name} CR {recommended_cr}/Level {level}" if level is not None else f"{name} CR {recommended_cr}"
        else:
            header_label = f"{name} Level {level}" if level is not None else name
    else:
        header_label = f"{name} CR/HD {cr}" if cr == hit_dice else f"{name} CR {cr}/HD {hit_dice}"
    skills = result.get("skills") if isinstance(result.get("skills"), Mapping) else {}
    basics = {
        "initiative": result.get("initiative"),
        "perception": skills.get("perception"),
        "senses": copy.deepcopy(result.get("senses", [])),
        "size": _human(result.get("sizeId", selections.get("sizeId", ""))),
        "speed": copy.deepcopy(result.get("speed", selections.get("speed", {}))),
        "alignment": result.get("alignment"),
        "religion": result.get("religion"),
    }
    raw_defenses = result.get("defenses") if isinstance(result.get("defenses"), Mapping) else {}
    defense_fields = [
        _field(key, label, raw_defenses[key], annotations, _defense_text(key, raw_defenses[key], raw_defenses))
        for key, label in _DEFENSES if key in raw_defenses
    ]
    aggregate_defenses = {}
    for key, label in (
        ("damageReduction", "Damage Reduction"), ("fastHealing", "Fast Healing"),
        ("immunities", "Immunities"), ("regeneration", "Regeneration"),
        ("resistances", "Resistances"), ("spellResistance", "SR"),
        ("vulnerabilities", "Vulnerabilities"), ("conditions", "Conditions"),
    ):
        if result.get(key) not in (None, [], {}, ""):
            aggregate_defenses[key] = copy.deepcopy(result[key])
            defense_fields.append(_field(key, label, result[key], annotations, _value_text(result[key])))
    defenses = {key: copy.deepcopy(raw_defenses[key]) for key, _ in _DEFENSES if key in raw_defenses}
    defenses.update(aggregate_defenses)
    defenses["fields"] = defense_fields
    attacks = [_attack(value, index, annotations) for index, value in enumerate(result.get("attacks", [])) if isinstance(value, Mapping)]
    raw_options = [value for value in result.get("options", []) if isinstance(value, Mapping)]
    # Older snapshots may contain an explicit copy of an automatic grant. Keep
    # distinct grants and repeated explicit options, but hide only that redundant copy.
    automatic_option_signatures = {
        _option_signature(value)
        for value in raw_options
        if value.get("graftId") and value.get("optionId") in _REDUNDANT_AUTO_OPTION_IDS
    }
    options = [
        _option(value) for value in raw_options
        if value.get("graftId") or _option_signature(value) not in automatic_option_signatures
    ]
    defenses["options"] = [value for value in options if value["section"] == "defenses"]
    attack_options = [value for value in options if value["section"] == "attacks"]
    utility_options = [value for value in options if value["section"] == "statistics"]
    specials = [{"name": value["name"], "text": value["text"], "optionId": value["optionId"]} for value in options if value["section"] == "specialAbilities"]
    for value in result.get("graftAbilities", []):
        if isinstance(value, Mapping):
            specials.append({"name": str(value.get("name", value.get("graftId", "Ability"))), "text": str(value.get("text", value.get("ruleText", "")))})

    statistic_fields = []
    if creation_system == "npc" and isinstance(result.get("abilityScores"), Mapping) and result["abilityScores"]:
        statistic_fields.append(_field("abilityScores", "Ability Scores", result["abilityScores"], annotations, _scores(result["abilityScores"])))
    abilities = result.get("abilityModifiers") if isinstance(result.get("abilityModifiers"), Mapping) else {}
    if abilities:
        statistic_fields.append(_field("abilityModifiers", "Ability Modifiers", abilities, annotations, _abilities(abilities)))
    if creation_system == "npc":
        for key, label, text in (
            ("npcCategory", "NPC Category", _human(result.get("npcCategory", ""))),
            ("hitDiceExpression", "Hit Dice", str(result.get("hitDiceExpression", ""))),
            ("bab", "BAB", _signed(result.get("bab"))),
            ("classProgression", "Class Progression", _class_progression(result.get("classProgression"))),
        ):
            if result.get(key) not in (None, [], {}, ""):
                statistic_fields.append(_field(key, label, result[key], annotations, text))
    if skills:
        statistic_fields.append(_field("skills", "Skills", skills, annotations, ", ".join(f"{_human(key)} {_signed(value)}" for key, value in sorted(skills.items()))))
    for key, label in (("cmb", "CMB"), ("abilityDC", "Ability DC"), ("spellDC", "Spell DC"), ("concentration", "Concentration")):
        if result.get(key) is not None:
            statistic_fields.append(_field(key, label, result[key], annotations, _signed(result[key]) if key in {"cmb", "concentration"} else str(result[key])))
    if creation_system == "npc":
        for key, label, text in (
            ("feats", "Feats", _named_entries(result.get("feats"), "featId")),
            ("classFeatures", "Class Features", _named_entries(result.get("classFeatures"), "featureId")),
            ("gear", "Gear", _gear_entries(result.get("gear"))),
            ("gearBudget", "Gear Budget", _gear_budget(result.get("gearBudget"))),
            ("languages", "Languages", _value_text(result.get("languages", []))),
        ):
            if result.get(key) not in (None, [], {}, ""):
                statistic_fields.append(_field(key, label, result[key], annotations, text))
    spells = copy.deepcopy(result.get("spells", [])) if isinstance(result.get("spells"), list) else []
    spellcasting = {
        key: copy.deepcopy(result[key])
        for key in ("casterLevel", "spellcastingClassId", "spellcastingMode", "spellcastingAbility", "spellListBenefit")
        if result.get(key) not in (None, [], {}, "")
    }
    statistics = {"fields": statistic_fields, "options": utility_options, "spells": spells, "spellcasting": spellcasting}
    sections = [
        {"id": "basics", "title": "Init/Perception/Senses; Size/Speed", "fields": copy.deepcopy(basics)},
        {"id": "defenses", "title": "DEFENSES", "fields": copy.deepcopy(defense_fields), "options": copy.deepcopy(defenses["options"])},
        {"id": "attacks", "title": "ATTACKS", "attacks": copy.deepcopy(attacks), "options": copy.deepcopy(attack_options)},
        {"id": "statistics", "title": "STATISTICS", "fields": copy.deepcopy(statistic_fields), "options": copy.deepcopy(utility_options), "spells": spells},
    ]
    if specials:
        sections.append({"id": "specialAbilities", "title": "SPECIAL ABILITIES", "abilities": copy.deepcopy(specials)})
    model = {
        "profile": profile,
        "schemaVersion": copy.deepcopy(snapshot.get("schemaVersion")),
        "kind": copy.deepcopy(snapshot.get("kind")),
        "monsterId": copy.deepcopy(snapshot.get("monsterId")),
        "sourceDraft": copy.deepcopy(snapshot.get("sourceDraft")),
        "catalogVersion": copy.deepcopy(snapshot.get("catalogVersion")),
        "creationSystem": creation_system,
        "mode": copy.deepcopy(snapshot.get("mode")),
        "header": {
            "name": name,
            "cr": cr,
            "recommendedCR": recommended_cr,
            "level": level,
            "hitDice": hit_dice,
            "label": header_label.strip(),
        },
        "basics": basics,
        "defenses": defenses,
        "attacks": attacks,
        "attackOptions": attack_options,
        "statistics": statistics,
        "specialAbilities": specials,
        "sections": sections,
    }
    if profile == "audit":
        audit = snapshot.get("audit") if isinstance(snapshot.get("audit"), Mapping) else {}
        model["audit"] = {
            "concept": copy.deepcopy(concept),
            "acceptedAIRationale": copy.deepcopy(audit.get("acceptedAIRationale", [])),
            "creationDecisions": copy.deepcopy(audit.get("creationDecisions", [])),
            "validationFindings": copy.deepcopy(audit.get("validationFindings", [])),
            "sources": copy.deepcopy(audit.get("sources", [])),
            "derivationTrace": copy.deepcopy(snapshot.get("derivationTrace", [])),
        }
    return model


def render_markdown(snapshot: Mapping[str, Any], profile: str = "sheet") -> str:
    model = structured_sheet(snapshot, profile)
    lines = [f"# {model['header']['label']}", ""]
    summary = _summary(model["basics"])
    if summary:
        lines.extend([summary, ""])
    identity = "; ".join(value for value in (model["basics"]["size"], _speed(model["basics"]["speed"])) if value)
    if identity:
        lines.extend([identity, ""])
    lines.extend(["## DEFENSES", "; ".join(_field_text(value) for value in model["defenses"]["fields"]) or "—"])
    if model["defenses"]["options"]:
        lines.append("Defense Options: " + "; ".join(value["text"] for value in model["defenses"]["options"]))
    lines.extend(["", "## ATTACKS", *[value["text"] for value in model["attacks"]]])
    if model["attackOptions"]:
        lines.append("Attack Options: " + "; ".join(value["text"] for value in model["attackOptions"]))
    if not model["attacks"] and not model["attackOptions"]:
        lines.append("—")
    lines.extend(["", "## STATISTICS", *[_field_text(value) for value in model["statistics"]["fields"]]])
    if model["statistics"]["options"]:
        lines.append("Utility Options: " + "; ".join(value["text"] for value in model["statistics"]["options"]))
    lines.extend(_spell_lines(model["statistics"]))
    if model["specialAbilities"]:
        lines.extend(["", "## SPECIAL ABILITIES", *[f"**{value['name']}:** {value['text']}" for value in model["specialAbilities"]]])
    if model.get("catalogVersion"):
        lines.extend(["", f"_Generated from catalog {model['catalogVersion']}._"])
    if profile == "audit":
        for key, title in _audit_headings(model["creationSystem"]):
            value = model["audit"][key]
            if value not in (None, {}, [], ""):
                lines.extend(["", f"## {title}", "```json", json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True), "```"])
    return "\n".join(lines).rstrip() + "\n"


def render_html(snapshot: Mapping[str, Any], profile: str = "sheet") -> str:
    model = structured_sheet(snapshot, profile)
    parts = [f'<main class="monster-sheet"><header><h1>{_esc(model["header"]["label"])}</h1></header>']
    if _summary(model["basics"]):
        parts.append(f"<p>{_esc(_summary(model['basics']))}</p>")
    identity = "; ".join(value for value in (model["basics"]["size"], _speed(model["basics"]["speed"])) if value)
    if identity:
        parts.append(f"<p>{_esc(identity)}</p>")
    parts.append(_html_section("DEFENSES", [_field_text(value) for value in model["defenses"]["fields"]], "Defense Options", model["defenses"]["options"]))
    parts.append(_html_section("ATTACKS", [value["text"] for value in model["attacks"]], "Attack Options", model["attackOptions"]))
    parts.append(_html_section("STATISTICS", [_field_text(value) for value in model["statistics"]["fields"]] + _spell_lines(model["statistics"]), "Utility Options", model["statistics"]["options"]))
    if model["specialAbilities"]:
        parts.append(_html_section("SPECIAL ABILITIES", [f"{value['name']}: {value['text']}" for value in model["specialAbilities"]]))
    if model.get("catalogVersion"):
        parts.append(f'<footer>Generated from catalog {_esc(model["catalogVersion"])}</footer>')
    if profile == "audit":
        for key, title in _audit_headings(model["creationSystem"]):
            value = model["audit"][key]
            if value not in (None, {}, [], ""):
                parts.append(f'<section class="audit"><h2>{_esc(title)}</h2><pre>{_esc(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))}</pre></section>')
    parts.append("</main>")
    css = "body{font-family:serif;line-height:1.35;max-width:52rem;margin:2rem auto}h2{border-bottom:1px solid}@page{margin:1.5cm}@media print{body{margin:0;max-width:none}.audit{break-before:page}section{break-inside:avoid}}"
    title = _esc(model["header"]["label"])
    return f'<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title><style>{css}</style></head><body>{"".join(parts)}</body></html>\n'


_AUDIT_HEADINGS = (
    ("concept", "MONSTER CONCEPT"), ("acceptedAIRationale", "ACCEPTED AI RATIONALE"),
    ("creationDecisions", "CREATION DECISIONS: STEPS 1–9"), ("validationFindings", "VALIDATION FINDINGS"),
    ("sources", "SOURCES"), ("derivationTrace", "DERIVATION TRACE"),
)


def _audit_headings(creation_system: str) -> tuple[tuple[str, str], ...]:
    if creation_system != "npc":
        return _AUDIT_HEADINGS
    return tuple(
        (key, "CREATION DECISIONS: STEPS 1–8" if key == "creationDecisions" else title)
        for key, title in _AUDIT_HEADINGS
    )


def _defense_text(key: str, value: Any, defenses: Mapping[str, Any]) -> str | None:
    if key in {"fortitude", "reflex", "will"}:
        return _signed(value)
    if key != "ac" or not isinstance(defenses.get("acBreakdown"), Mapping):
        return None
    labels = {"armor": "armor", "shield": "shield", "dexterity": "Dex", "size": "size"}
    parts = [f"{_signed(bonus)} {labels.get(source, _human(source))}" for source, bonus in defenses["acBreakdown"].items()]
    return f"{value} ({', '.join(parts)})" if parts else str(value)


def _field(key: str, label: str, value: Any, annotations: Mapping[str, Any], text: str | None = None) -> dict[str, Any]:
    result = {"key": key, "label": label, "value": copy.deepcopy(value), "text": str(value) if text is None else text}
    if annotations.get(key):
        result["annotation"] = str(annotations[key])
    return result


def _field_text(value: Mapping[str, Any]) -> str:
    return f"{value['label']} {value['text']}" + (f" ({value['annotation']})" if value.get("annotation") else "")


def _attack(value: Mapping[str, Any], index: int, annotations: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(value))
    bonus = result.get("attackBonusText") or ("/".join(_signed(item) for item in result.get("attackBonus", [])) if isinstance(result.get("attackBonus"), list) else "")
    details = []
    if result.get("damageExpression") is not None:
        details.append(str(result["damageExpression"]))
    if result.get("averageDamage") is not None:
        details.append("average " + str(result["averageDamage"]))
    if result.get("damageType"):
        details.append(str(result["damageType"]))
    name = str(result.get("name", "Attack"))
    if result.get("count") not in (None, 1):
        name += f" ×{result['count']}"
    text = name + (f" {bonus}" if bonus else "") + (" (" + "; ".join(details) + ")" if details else "")
    annotation = annotations.get(f"attacks.{index}", annotations.get("attacks"))
    result["text"] = text + (f" ({annotation})" if annotation else "")
    return result


def _option_signature(value: Mapping[str, Any]) -> tuple[Any, str]:
    return (
        value.get("optionId"),
        json.dumps(value.get("parameters", {}), ensure_ascii=False, sort_keys=True, separators=(",", ":")),
    )


def _option(value: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(value))
    option_id = str(result.get("optionId", "option"))
    effect = result.get("effect") if isinstance(result.get("effect"), Mapping) else {}
    parameters = result.get("parameters") if isinstance(result.get("parameters"), Mapping) else {}
    effect_type = effect.get("type")
    explicit_section = result.get("section", result.get("placement"))
    category = result.get("category")
    if explicit_section in {"defenses", "attacks", "statistics", "specialAbilities"}:
        section = explicit_section
    elif effect_type in _DEFENSE_EFFECTS:
        section = "defenses"
    elif effect_type in _ATTACK_EFFECTS:
        section = "attacks"
    elif effect_type in _SPECIAL_EFFECTS:
        section = "specialAbilities"
    elif any(key in parameters for key in ("attackMode", "attackType", "attackTypes", "maneuver")) or category in {"attack", "combat", "offense"}:
        section = "attacks"
    elif category in {"defense", "defensive"}:
        section = "defenses"
    else:
        section = "statistics"
    details = {**parameters, **effect}
    name = str(result.get("name", _human(option_id)))
    result.update({"optionId": option_id, "name": name, "section": section, "text": name + (f" ({_mapping(details)})" if details else "")})
    return result


def _summary(basics: Mapping[str, Any]) -> str:
    values = []
    if basics["initiative"] is not None:
        values.append(f"Init {_signed(basics['initiative'])}")
    if basics["perception"] is not None:
        values.append(f"Perception {_signed(basics['perception'])}")
    text = "; ".join(values)
    if basics["senses"]:
        senses = "; ".join(map(str, basics["senses"]))
        text = f"{text} ({senses})" if text else f"Senses {senses}"
    return text


def _speed(value: Any) -> str:
    if not isinstance(value, Mapping) or not value:
        return ""
    preferred = ("land", "climb", "fly", "swim", "burrow")
    keys = [key for key in preferred if key in value] + sorted(key for key in value if key not in preferred)
    return "Speed " + ", ".join((f"{_human(key)} " if len(value) > 1 or key != "land" else "") + f"{value[key]} ft." for key in keys)


def _spell_lines(statistics: Mapping[str, Any]) -> list[str]:
    metadata = statistics["spellcasting"]
    if not statistics["spells"] and not metadata:
        return []
    caster = []
    if metadata.get("casterLevel") is not None:
        caster.append(f"Caster Level {metadata['casterLevel']}")
    if metadata.get("spellcastingClassId"):
        caster.append(_human(metadata["spellcastingClassId"]))
    lines = ["Spellcasting" + (" (" + ", ".join(caster) + ")" if caster else "")]
    for key, label in (("spellcastingMode", "Mode"), ("spellcastingAbility", "Ability")):
        if metadata.get(key):
            caster.append(f"{label} {_human(metadata[key])}")
    lines[0] = "Spellcasting" + (" (" + ", ".join(caster) + ")" if caster else "")
    for spell in statistics["spells"]:
        if isinstance(spell, Mapping):
            name = str(spell.get("name", _human(spell.get("spellId", "Spell"))))
            details = []
            for key, label in (
                ("spellDC", "DC"), ("spellLevel", "level"), ("baseLevel", "base level"),
                ("effectiveLevel", "effective level"), ("usesPerDay", "uses/day"),
                ("spellLevelSource", "source"), ("metamagic", "metamagic"), ("role", "role"), ("sourceBand", "band"),
            ):
                if spell.get(key) is not None:
                    details.append(f"{label} {_human(spell[key]) if key == 'spellLevelSource' else spell[key]}")
            lines.append((f"{spell['frequency']}—" if spell.get("frequency") else "") + name + (" (" + ", ".join(details) + ")" if details else ""))
    if metadata.get("spellListBenefit") not in (None, {}, [], ""):
        lines.append("Spell List Benefit: " + _value_text(metadata["spellListBenefit"]))
    return lines


def _ability_values(values: Mapping[str, Any], *, signed: bool) -> str:
    labels = {"strength": "Str", "dexterity": "Dex", "constitution": "Con", "intelligence": "Int", "wisdom": "Wis", "charisma": "Cha"}
    order = tuple(labels)
    keys = [key for key in order if key in values] + sorted(key for key in values if key not in order)
    render = _signed if signed else str
    return ", ".join(f"{labels.get(key, _human(key))} {render(values[key])}" for key in keys)


def _abilities(values: Mapping[str, Any]) -> str:
    return _ability_values(values, signed=True)


def _scores(values: Mapping[str, Any]) -> str:
    return _ability_values(values, signed=False)


def _class_progression(value: Any) -> str:
    if not isinstance(value, list):
        return _value_text(value)
    entries = []
    for item in value:
        if isinstance(item, Mapping):
            name = item.get("name", _human(item.get("classId", "Class")))
            levels = item.get("levels", item.get("level"))
            entries.append(f"{name} {levels}" if levels is not None else str(name))
        else:
            entries.append(str(item))
    return ", ".join(entries)


def _named_entries(value: Any, id_key: str) -> str:
    if not isinstance(value, list):
        return _value_text(value)
    entries = []
    for item in value:
        if isinstance(item, Mapping):
            entries.append(str(item.get("name", _human(item.get(id_key, "")))))
        else:
            entries.append(str(item))
    return ", ".join(entry for entry in entries if entry)


def _gear_entries(value: Any) -> str:
    if not isinstance(value, list):
        return _value_text(value)
    entries = []
    for item in value:
        if isinstance(item, Mapping):
            name = str(item.get("name", _human(item.get("itemId", "Item"))))
            quantity = item.get("quantity")
            entries.append(f"{name} ×{quantity}" if quantity not in (None, 1) else name)
        else:
            entries.append(str(item))
    return ", ".join(entries)


def _gear_budget(value: Any) -> str:
    if not isinstance(value, Mapping):
        return _value_text(value)
    fields = []
    for key, label in (("budgetCp", "budget"), ("spentCp", "spent"), ("deltaCp", "delta")):
        if value.get(key) is not None:
            fields.append(f"{value[key]} cp {label}")
    return ", ".join(fields) if fields else _value_text(value)


def _signed(value: Any) -> str:
    return f"{value:+g}" if isinstance(value, (int, float)) and not isinstance(value, bool) else str(value)


def _human(value: Any) -> str:
    return str(value).rsplit(".", 1)[-1].replace("-", " ").replace("_", " ").title()


def _value_text(value: Any) -> str:
    if isinstance(value, Mapping):
        return _mapping(value)
    if isinstance(value, list):
        return ", ".join(_value_text(item) for item in value)
    return str(value)


def _mapping(value: Mapping[str, Any]) -> str:
    return "; ".join(f"{key}: {_value_text(item)}" for key, item in sorted(value.items()) if key != "type")


def _html_section(title: str, lines: list[str], option_title: str | None = None, options: list[Mapping[str, Any]] | None = None) -> str:
    items = "".join(f"<li>{_esc(value)}</li>" for value in lines) or "<li>—</li>"
    extra = f'<h3>{_esc(option_title)}</h3><ul>{"".join(f"<li>{_esc(value["text"])}</li>" for value in options)}</ul>' if option_title and options else ""
    return f'<section><h2>{_esc(title)}</h2><ul>{items}</ul>{extra}</section>'


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


__all__ = ["structured_sheet", "render_markdown", "render_html"]
