"""Bounded read-only import ports for third-party component metadata."""

from __future__ import annotations

import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

from ai_stp_cli.local.component_sources import Diagnostic

MAX_MANIFEST_BYTES: Final[int] = 1024 * 1024
MAX_ENTRIES: Final[int] = 500
NORI_SOURCE: Final[str] = (
    "github.com/tilework-tech/nori-skillsets/blob/"
    "475129bbd6098137bdb77f3390b894b2340dbb2a/src/norijson/nori.ts"
)
ASKILL_SOURCE: Final[str] = (
    "github.com/avibe-bot/askill/blob/b4d968c96781b3996dcdfa4785782efd51860fdd/src/lock.ts"
)
_SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,254}$")
_HASH = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")


@dataclass(frozen=True)
class Candidate:
    absolute: Path
    component_type: str
    package_name: str
    package_version: str | None
    digest: str | None
    source: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class Result:
    candidates: tuple[Candidate, ...]
    diagnostics: tuple[Diagnostic, ...]


def discover(root: Path) -> Result:
    """Read only the two declared manifests inside one explicitly named root."""
    if unsafe := _unsafe_root(root):
        return Result((), (unsafe,))
    candidates: list[Candidate] = []
    diagnostics: list[Diagnostic] = []
    candidates.extend(_nori(root, diagnostics))
    candidates.extend(_skill_lock(root, diagnostics))
    unique = {(item.absolute, item.component_type): item for item in candidates}
    return Result(
        tuple(sorted(unique.values(), key=lambda item: (str(item.absolute), item.component_type))),
        tuple(diagnostics),
    )


def discover_skill_lock(root: Path) -> Result:
    """Read only an askill/Vercel-compatible lock at one declared scope root."""
    if unsafe := _unsafe_root(root):
        return Result((), (unsafe,))
    diagnostics: list[Diagnostic] = []
    candidates = _skill_lock(root, diagnostics)
    return Result(tuple(candidates), tuple(diagnostics))


def _nori(root: Path, diagnostics: list[Diagnostic]) -> list[Candidate]:
    document = _object(root / "nori.json", "nori.json", diagnostics)
    if document is None:
        return []
    name = _bounded_string(document.get("name"))
    version = _bounded_string(document.get("version"))
    if name is None or version is None:
        _invalid(diagnostics, "nori.json", "the Nori manifest requires bounded name and version")
        return []
    found: list[Candidate] = []
    manifest_type = document.get("type")
    if manifest_type in {"skill", "inlined-skill"} and _component_path(root, directory=True):
        found.append(_candidate(root, "skill", name, version, None, NORI_SOURCE, "nori.json"))
    mappings = (
        ("skills", "id", "skill", "skills", True),
        ("subagents", "id", "agent", "subagents", False),
        ("slashcommands", "command", "command", "slashcommands", False),
    )
    total = 0
    for field, identity, component_type, directory, directory_only in mappings:
        records = document.get(field)
        if records is None:
            continue
        if not isinstance(records, list):
            _invalid(diagnostics, "nori.json", "a Nori component collection has an invalid shape")
            continue
        held_records = cast(list[object], records)
        total += len(held_records)
        if total > MAX_ENTRIES:
            _bounded(diagnostics, "nori.json")
            return []
        for record in held_records:
            held = cast(dict[str, object], record) if isinstance(record, dict) else {}
            item_name = held.get(identity)
            if not isinstance(item_name, str) or _SLUG.fullmatch(item_name) is None:
                _invalid(diagnostics, "nori.json", "a Nori component identifier is unsafe")
                continue
            base = root / directory / item_name
            paths = (base,) if directory_only else (base, base.with_suffix(".md"))
            path = next(
                (item for item in paths if _component_path(item, directory=directory_only)), None
            )
            if path is None:
                _invalid(diagnostics, "nori.json", "a declared Nori component path is unavailable")
                continue
            found.append(
                _candidate(path, component_type, item_name, version, None, NORI_SOURCE, "nori.json")
            )
    return found


def _skill_lock(root: Path, diagnostics: list[Diagnostic]) -> list[Candidate]:
    relative = ".agents/.skill-lock.json"
    document = _object(root / relative, "skill-lock", diagnostics)
    if document is None:
        return []
    if document.get("version") != 3 or not isinstance(document.get("skills"), dict):
        _invalid(diagnostics, "skill-lock", "the skill lock is not supported version 3")
        return []
    records = cast(dict[str, object], document["skills"])
    if len(records) > MAX_ENTRIES:
        _bounded(diagnostics, "skill-lock")
        return []
    found: list[Candidate] = []
    for name in sorted(records):
        record = records[name]
        safe_name = _sanitized_name(name)
        held = cast(dict[str, object], record) if isinstance(record, dict) else {}
        source = _bounded_string(held.get("source"))
        digest = held.get("skillFolderHash")
        if (
            safe_name is None
            or source is None
            or not isinstance(digest, str)
            or not _HASH.fullmatch(digest)
        ):
            _invalid(
                diagnostics, "skill-lock", "a skill lock entry lacks safe source or exact digest"
            )
            continue
        path = root / ".agents" / "skills" / safe_name
        if not _component_path(path, directory=True):
            _invalid(diagnostics, "skill-lock", "a locked skill path is unavailable")
            continue
        algorithm = "sha1" if len(digest) == 40 else "sha256"
        found.append(
            _candidate(
                path,
                "skill",
                source,
                None,
                f"{algorithm}:{digest}",
                ASKILL_SOURCE,
                relative,
            )
        )
    return found


def _object(path: Path, source: str, diagnostics: list[Diagnostic]) -> dict[str, object] | None:
    descriptor: int | None = None
    try:
        link_state = path.lstat()
        if stat.S_ISLNK(link_state.st_mode):
            _invalid(diagnostics, source, "the interop manifest could not be read safely")
            return None
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or link_state.st_dev != before.st_dev
            or link_state.st_ino != before.st_ino
        ):
            _invalid(diagnostics, source, "the interop manifest is not one regular file")
            return None
        if before.st_size > MAX_MANIFEST_BYTES:
            _bounded(diagnostics, source)
            return None
        chunks: list[bytes] = []
        remaining = MAX_MANIFEST_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        after = os.fstat(descriptor)
        if (
            len(payload) > MAX_MANIFEST_BYTES
            or before.st_ino != after.st_ino
            or before.st_dev != after.st_dev
            or len(payload) != after.st_size
        ):
            _bounded(diagnostics, source)
            return None
    except FileNotFoundError:
        return None
    except OSError:
        _invalid(diagnostics, source, "the interop manifest could not be read safely")
        return None
    finally:
        if descriptor is not None:
            os.close(descriptor)
    try:
        parsed: object = json.loads(payload, object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        _invalid(diagnostics, source, "the interop manifest is not unambiguous UTF-8 JSON")
        return None
    if not isinstance(parsed, dict):
        _invalid(diagnostics, source, "the interop manifest root is not an object")
        return None
    return cast(dict[str, object], parsed)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _component_path(path: Path, *, directory: bool) -> bool:
    try:
        held = path.lstat()
    except OSError:
        return False
    if stat.S_ISLNK(held.st_mode):
        return False
    if directory:
        if not stat.S_ISDIR(held.st_mode):
            return False
        try:
            manifest = (path / "SKILL.md").lstat()
        except OSError:
            return False
        return stat.S_ISREG(manifest.st_mode) and not stat.S_ISLNK(manifest.st_mode)
    return stat.S_ISDIR(held.st_mode) or stat.S_ISREG(held.st_mode)


def _unsafe_root(root: Path) -> Diagnostic | None:
    try:
        held = root.lstat()
    except OSError:
        return Diagnostic("invalid_record", "interop-root", "the interop root is unavailable")
    if stat.S_ISLNK(held.st_mode) or not stat.S_ISDIR(held.st_mode):
        return Diagnostic(
            "invalid_record", "interop-root", "the interop root is not a real directory"
        )
    return None


def _sanitized_name(value: str) -> str | None:
    sanitized = re.sub(r"[^a-z0-9._]+", "-", value.lower()).strip(".-")[:255]
    return sanitized or None


def _bounded_string(value: object) -> str | None:
    return (
        value if isinstance(value, str) and 0 < len(value) <= 512 and "\x00" not in value else None
    )


def _candidate(
    path: Path,
    component_type: str,
    name: str,
    version: str | None,
    digest: str | None,
    source: str,
    evidence: str,
) -> Candidate:
    return Candidate(path, component_type, name, version, digest, source, (evidence,))


def _invalid(diagnostics: list[Diagnostic], source: str, reason: str) -> None:
    diagnostics.append(Diagnostic("invalid_record", source, reason))


def _bounded(diagnostics: list[Diagnostic], source: str) -> None:
    diagnostics.append(
        Diagnostic("bounded_limit", source, "the interop manifest exceeded its bound")
    )
