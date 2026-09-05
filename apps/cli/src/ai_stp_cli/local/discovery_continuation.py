"""Opaque remaining-walk cursor for bounded component discovery (`REQ-535`)."""

from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
from binascii import Error as BinasciiError
from pathlib import Path, PurePosixPath
from typing import Final, Literal, cast

from ai_stp_cli.errors import CliFailure
from ai_stp_foundation.canonical import (
    CanonicalizationError,
    JsonValue,
    canonize,
    from_json_bytes,
)

WALKS: Final[frozenset[str]] = frozenset({"portable_skills", "path_inventory"})
Walk = Literal["portable_skills", "path_inventory"]


def encode(
    walk: Walk,
    stack: list[tuple[str, int]],
    covered: list[str] | None = None,
) -> str:
    """Encode remaining relative frames as an opaque cursor."""
    body: dict[str, JsonValue] = {
        "schema_version": 1,
        "walk": walk,
        "stack": [{"relative": relative, "depth": depth} for relative, depth in stack],
        "covered": list(covered or ()),
    }
    return urlsafe_b64encode(canonize(body)).decode("ascii").rstrip("=")


def decode(token: str) -> tuple[Walk, list[tuple[str, int]], list[str]]:
    """Decode a cursor. Rejects absolute paths, `..`, and unknown walks."""
    padding = "=" * ((4 - len(token) % 4) % 4)
    try:
        document = from_json_bytes(urlsafe_b64decode(token + padding))
    except (OSError, ValueError, TypeError, CanonicalizationError, BinasciiError) as error:
        raise _invalid() from error
    if not isinstance(document, dict):
        raise _invalid()
    held = cast(dict[str, JsonValue], document)
    if held.get("schema_version") != 1:
        raise _invalid()
    walk = held.get("walk")
    if not isinstance(walk, str) or walk not in WALKS:
        raise _invalid()
    raw_stack = held.get("stack")
    if not isinstance(raw_stack, list):
        raise _invalid()
    stack: list[tuple[str, int]] = []
    for item in cast(list[object], raw_stack):
        if not isinstance(item, dict):
            raise _invalid()
        frame = cast(dict[str, JsonValue], item)
        relative = frame.get("relative")
        depth = frame.get("depth")
        if not isinstance(relative, str) or not isinstance(depth, int) or depth < 0:
            raise _invalid()
        stack.append((_relative(relative), depth))
    raw_covered = held.get("covered")
    covered: list[str] = []
    if raw_covered is None:
        raw_covered = []
    if not isinstance(raw_covered, list):
        raise _invalid()
    for item in cast(list[object], raw_covered):
        if not isinstance(item, str):
            raise _invalid()
        covered.append(_relative(item) if item != "." else ".")
    return cast(Walk, walk), stack, covered


def join(root: Path, relative: str) -> Path:
    """Resolve a cursor frame inside `root`. Escape is a validation error."""
    child = (root / relative).resolve(strict=False)
    try:
        child.relative_to(root.resolve(strict=False))
    except ValueError as error:
        raise _invalid() from error
    return child


def relative_to(root: Path, path: Path) -> str:
    """POSIX path relative to the named root."""
    held = path.resolve(strict=False).relative_to(root.resolve(strict=False))
    text = PurePosixPath(held.as_posix()).as_posix()
    return "." if text == "." else text


def _relative(value: str) -> str:
    if not value or value.startswith("/") or "\\" in value:
        raise _invalid()
    posix = PurePosixPath(value)
    if posix.is_absolute() or ".." in posix.parts:
        raise _invalid()
    return posix.as_posix()


def _invalid() -> CliFailure:
    return CliFailure(
        "AI_STP_VALIDATION_ERROR",
        "the discovery continuation is not a cursor from this command",
        next_actions=["component discover --root <path> --json"],
    )
