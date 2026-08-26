"""Public API for the Pathfinder Simple Monster Creation engine."""

import os

from .catalog import Catalog, CatalogError
from .engine import BoundaryError, Engine

Application = Engine

__all__ = ["Application", "BoundaryError", "Catalog", "CatalogError", "Engine", "execute"]

_default_engine: Engine | None = None


def execute(request):
    """Execute one versioned operation against the process-local workspace."""
    global _default_engine
    if _default_engine is None:
        _default_engine = Engine(workspace=os.environ.get("MONSTER_BUILDER_WORKSPACE") or None)
    return _default_engine.execute(request)
