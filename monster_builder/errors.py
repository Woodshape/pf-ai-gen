"""Shared boundary errors for the public execute seam and rule adapters."""

from __future__ import annotations

from typing import Any


class BoundaryError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        path: str = "",
        *,
        kind: str = "boundary",
        details: Any = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.path = path
        self.kind = kind
        self.details = details
