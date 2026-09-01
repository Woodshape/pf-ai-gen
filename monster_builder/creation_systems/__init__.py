"""Rules adapters selected by a draft's immutable creationSystem."""

from .base import CREATION_SYSTEM_KEYS, NPC, SIMPLE_MONSTER, CreationSystem, creation_system_key
from .simple_monster import SimpleMonsterCreation


def installed_creation_systems(catalogs):
    """Construct the required adapter without loading optional catalogs."""
    return {
        SIMPLE_MONSTER: SimpleMonsterCreation(catalogs.for_system(SIMPLE_MONSTER)),
    }


def load_optional_creation_system(key, catalogs):
    """Load an optional adapter only when a draft selects it."""
    if key != NPC:
        from ..errors import BoundaryError

        raise BoundaryError(
            "creation-system.unavailable",
            f"creation system is not installed: {key}",
            "/creationSystem",
            kind="product-constraint",
        )
    try:
        from .npc import NpcCreation
    except ModuleNotFoundError as exc:
        if exc.name != "monster_builder.creation_systems.npc":
            raise
        from ..errors import BoundaryError

        raise BoundaryError(
            "creation-system.unavailable",
            "creation system is not installed: npc",
            "/creationSystem",
            kind="product-constraint",
        ) from exc
    return NpcCreation(catalogs.for_system(NPC))


__all__ = [
    "CREATION_SYSTEM_KEYS",
    "NPC",
    "SIMPLE_MONSTER",
    "CreationSystem",
    "SimpleMonsterCreation",
    "creation_system_key",
    "installed_creation_systems",
    "load_optional_creation_system",
]
