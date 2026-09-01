"""Reusable rules helpers for the class-based NPC creation adapter.

The adapter in :mod:`monster_builder.creation_systems.npc` owns the public
creation-system contract.  This package contains small, side-effect-free
helpers that are useful to tests and to future NPC class/feat expansions.
"""

from .prerequisites import evaluate_prerequisite

__all__ = ["evaluate_prerequisite"]
