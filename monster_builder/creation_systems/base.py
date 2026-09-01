"""Internal creation-system contract behind :class:`Engine`."""

from __future__ import annotations

from typing import Any, Protocol


SIMPLE_MONSTER = "simple-monster"
NPC = "npc"
CREATION_SYSTEM_KEYS = frozenset({SIMPLE_MONSTER, NPC})


def creation_system_key(value: Any) -> str:
    """Validate an explicitly supplied creation-system key."""
    if not isinstance(value, str) or value not in CREATION_SYSTEM_KEYS:
        from ..errors import BoundaryError

        raise BoundaryError(
            "creation-system.invalid",
            "creationSystem must be simple-monster or npc",
            "/creationSystem",
        )
    return value


class CreationSystem(Protocol):
    key: str
    selection_fields: frozenset[str]

    def validate_input(self, draft: dict[str, Any]) -> None: ...

    def choice_requirements(self, draft: dict[str, Any]) -> dict[str, Any]: ...

    def evaluate(self, draft: dict[str, Any]) -> dict[str, Any]: ...

    def creation_decisions(
        self, selections: dict[str, Any], trace: list[dict[str, Any]]
    ) -> list[dict[str, Any]]: ...

    def fingerprint_selections(self, selections: dict[str, Any]) -> dict[str, Any]: ...
