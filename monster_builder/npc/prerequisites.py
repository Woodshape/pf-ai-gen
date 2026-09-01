"""Typed prerequisite evaluation for class-based NPC choices."""

from __future__ import annotations

from typing import Any


def _canonical(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.rsplit(".", 1)[-1].casefold()


def _contains(values: set[str], value: Any) -> bool:
    return _canonical(value) in values or (isinstance(value, str) and value in values)


def evaluate_prerequisite(
    expression: Any,
    *,
    ability_scores: dict[str, int] | None = None,
    ability_modifiers: dict[str, int] | None = None,
    bab: int | None = None,
    character_level: int | None = None,
    class_levels: dict[str, int] | None = None,
    skill_ranks: dict[str, int] | None = None,
    race_id: str | None = None,
    alignment: str | None = None,
    feats: set[str] | list[str] | None = None,
    class_features: set[str] | list[str] | None = None,
    caster_level: int | None = None,
) -> bool | None:
    """Evaluate one catalog prerequisite expression.

    ``True`` and ``False`` mean that the expression is known and satisfied or
    failed. ``None`` means the expression cannot be evaluated from the current
    context.  Returning ``None`` instead of treating missing data as success is
    important for source-bounded catalogs and for acquisition-level checks.
    """

    if expression is None:
        return True
    if not isinstance(expression, dict) or len(expression) != 1:
        return None

    operator, operand = next(iter(expression.items()))
    if operator in {"all", "any"}:
        if not isinstance(operand, list) or (operator == "any" and not operand):
            return None
        values = [
            evaluate_prerequisite(
                child,
                ability_scores=ability_scores,
                ability_modifiers=ability_modifiers,
                bab=bab,
                character_level=character_level,
                class_levels=class_levels,
                skill_ranks=skill_ranks,
                race_id=race_id,
                alignment=alignment,
                feats=feats,
                class_features=class_features,
                caster_level=caster_level,
            )
            for child in operand
        ]
        if operator == "all":
            if any(value is False for value in values):
                return False
            return True if all(value is True for value in values) else None
        if any(value is True for value in values):
            return True
        return False if all(value is False for value in values) else None

    if operator == "not":
        value = evaluate_prerequisite(
            operand,
            ability_scores=ability_scores,
            ability_modifiers=ability_modifiers,
            bab=bab,
            character_level=character_level,
            class_levels=class_levels,
            skill_ranks=skill_ranks,
            race_id=race_id,
            alignment=alignment,
            feats=feats,
            class_features=class_features,
            caster_level=caster_level,
        )
        return None if value is None else not value

    if operator == "abilityAtLeast":
        if not isinstance(operand, dict) or not operand:
            return None
        scores = ability_scores or {}
        modifiers = ability_modifiers or {}
        unknown = False
        for ability, minimum in operand.items():
            value = scores.get(ability)
            if value is None:
                value = modifiers.get(ability)
                if value is not None:
                    # A modifier map cannot prove a raw score threshold except
                    # for thresholds that are directly represented by a score.
                    unknown = True
                    continue
            if not isinstance(value, int) or isinstance(value, bool):
                unknown = True
                continue
            if not isinstance(minimum, int) or isinstance(minimum, bool):
                return None
            if value < minimum:
                return False
        return None if unknown else True

    if operator == "babAtLeast":
        return None if bab is None or not isinstance(operand, int) or isinstance(operand, bool) else bab >= operand
    if operator == "characterLevelAtLeast":
        return None if character_level is None or not isinstance(operand, int) or isinstance(operand, bool) else character_level >= operand
    if operator == "casterLevelAtLeast":
        return None if caster_level is None or not isinstance(operand, int) or isinstance(operand, bool) else caster_level >= operand

    if operator == "classLevelAtLeast":
        if not isinstance(operand, dict) or not operand or class_levels is None:
            return None
        normalized = {_canonical(key): value for key, value in class_levels.items()}
        for class_id, minimum in operand.items():
            if not isinstance(minimum, int) or isinstance(minimum, bool):
                return None
            value = normalized.get(_canonical(class_id), 0)
            if value < minimum:
                return False
        return True

    if operator == "skillRanksAtLeast":
        if not isinstance(operand, dict) or not operand or skill_ranks is None:
            return None
        normalized = {_canonical(key): value for key, value in skill_ranks.items()}
        for skill_id, minimum in operand.items():
            if not isinstance(minimum, int) or isinstance(minimum, bool):
                return None
            value = normalized.get(_canonical(skill_id), 0)
            if value < minimum:
                return False
        return True

    if operator == "race":
        return None if race_id is None or not isinstance(operand, str) else _canonical(race_id) == _canonical(operand)
    if operator == "alignment":
        return None if alignment is None or not isinstance(operand, str) else alignment.casefold() == operand.casefold()
    if operator == "hasFeat":
        if feats is None or not isinstance(operand, str):
            return None
        normalized = {_canonical(value) for value in feats}
        return _canonical(operand) in normalized
    if operator == "hasClassFeature":
        if class_features is None or not isinstance(operand, str):
            return None
        normalized = {_canonical(value) for value in class_features}
        return _canonical(operand) in normalized
    return None
