"""Domain errors for article publication (SPEC-054)."""

from __future__ import annotations


class ContentError(Exception):
    """A typed article-publication failure that does not change active state."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)
