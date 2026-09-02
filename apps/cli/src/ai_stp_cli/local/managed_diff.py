"""Read-only managed-path diff against one exact cached HarnessBundle."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final, cast

from ai_stp_cli.errors import CliFailure

MAX_MANAGED_FILES: Final[int] = 4000
MAX_MANAGED_BYTES: Final[int] = 64 * 1024 * 1024
MAX_MANIFEST_BYTES: Final[int] = 4 * 1024 * 1024
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


@dataclass(frozen=True)
class Change:
    code: str
    path: str
    expected_digest: str = ""
    observed_digest: str = ""


@dataclass(frozen=True)
class Manifest:
    expected: dict[str, str]
    roots: tuple[str, ...]
    #: The projection scope the bundle was compiled for; absent in the
    #: manifest means `global` (`harness-bundle.md`).
    target_scope: str = "global"


def bundle_manifest(archive: Path) -> Manifest:
    """Read the exact managed file records from a verified cached bundle."""
    try:
        with zipfile.ZipFile(archive) as held:
            info = held.getinfo("bundle.json")
            if info.file_size > MAX_MANIFEST_BYTES:
                raise _failure("the verified HarnessBundle manifest exceeds its size bound")
            raw = held.read("bundle.json")
    except (OSError, KeyError, zipfile.BadZipFile) as error:
        raise _failure("the verified HarnessBundle manifest is unavailable") from error
    try:
        document: object = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _failure("the verified HarnessBundle manifest is invalid") from error
    if not isinstance(document, dict):
        raise _failure("the verified HarnessBundle manifest is not an object")
    held_document = cast(dict[str, object], document)
    files = held_document.get("files")
    managed = held_document.get("managed_paths")
    if not isinstance(files, list) or not isinstance(managed, list):
        raise _failure("the verified HarnessBundle has no managed file manifest")
    file_items = cast(list[object], files)
    managed_items = cast(list[object], managed)
    if len(file_items) > MAX_MANAGED_FILES or len(managed_items) > MAX_MANAGED_FILES:
        raise _failure("the verified HarnessBundle manifest exceeds its file bound")
    records: dict[str, str] = {}
    for raw_record in file_items:
        record = cast(dict[str, object], raw_record) if isinstance(raw_record, dict) else {}
        path = record.get("path")
        digest = record.get("digest")
        if (
            not isinstance(path, str)
            or not _safe(path)
            or not isinstance(digest, str)
            or _DIGEST.fullmatch(digest) is None
            or path in records
        ):
            raise _failure("the verified HarnessBundle managed file record is invalid")
        records[path] = digest
    if sorted(item for item in managed_items if isinstance(item, str)) != sorted(records):
        raise _failure("the verified HarnessBundle managed paths disagree with its files")
    roots = tuple(sorted({PurePosixPath(path).parts[0] for path in records}))
    if any(
        root in records and any(path.startswith(f"{root}/") for path in records) for root in roots
    ):
        raise _failure("the verified HarnessBundle has colliding managed roots")
    scope = held_document.get("target_scope")
    return Manifest(
        records, roots, target_scope=scope if isinstance(scope, str) and scope else "global"
    )


def compare(target: Path, manifest: Manifest) -> tuple[Change, ...]:
    """Compare only allowlisted managed roots; never mutate or follow links."""
    current: dict[str, str] = {}
    files = 0
    total = 0
    for root in manifest.roots:
        root_path = target / root
        expected_root_file = root in manifest.expected
        try:
            root_mode = root_path.lstat().st_mode
        except FileNotFoundError:
            continue
        except OSError as error:
            raise _failure("a managed target root could not be inspected") from error
        if stat.S_ISLNK(root_mode) and not expected_root_file:
            for path in manifest.expected:
                if path.startswith(f"{root}/"):
                    current[path] = "unsafe"
            continue
        candidates = (root_path,) if expected_root_file else _walk(root_path)
        for path in candidates:
            relative = path.relative_to(target).as_posix()
            try:
                held = path.lstat()
            except FileNotFoundError:
                continue
            except OSError as error:
                raise _failure("a managed target path could not be inspected") from error
            if stat.S_ISLNK(held.st_mode) or not stat.S_ISREG(held.st_mode):
                if relative in manifest.expected:
                    current[relative] = "unsafe"
                continue
            files += 1
            total += held.st_size
            if files > MAX_MANAGED_FILES or total > MAX_MANAGED_BYTES:
                raise _failure("the managed target surface exceeds its inspection bound")
            current[relative] = _digest_regular(path, held)

    changes: list[Change] = []
    for path, expected in manifest.expected.items():
        observed = current.get(path)
        if observed is None:
            changes.append(Change("deleted", path, expected_digest=expected))
        elif observed != expected:
            changes.append(Change("modified", path, expected, observed))
    for path, observed in current.items():
        if path not in manifest.expected:
            changes.append(Change("added", path, observed_digest=observed))
    return tuple(sorted(changes, key=lambda item: (item.code, item.path)))


def _walk(root: Path) -> tuple[Path, ...]:
    try:
        held = root.lstat()
    except FileNotFoundError:
        return ()
    except OSError as error:
        raise _failure("a managed target root could not be inspected") from error
    if stat.S_ISLNK(held.st_mode):
        return (root,)
    if not stat.S_ISDIR(held.st_mode):
        return (root,)
    found: list[Path] = []
    stack = [root]
    while stack:
        directory = stack.pop()
        try:
            entries = sorted(directory.iterdir(), reverse=True)
        except OSError as error:
            raise _failure("a managed target directory could not be inspected") from error
        for entry in entries:
            try:
                mode = entry.lstat().st_mode
            except OSError as error:
                raise _failure("a managed target path could not be inspected") from error
            if stat.S_ISDIR(mode) and not stat.S_ISLNK(mode):
                stack.append(entry)
            else:
                found.append(entry)
            if len(found) + len(stack) > MAX_MANAGED_FILES:
                raise _failure("the managed target surface exceeds its inspection bound")
    return tuple(found)


def _digest_regular(path: Path, held: os.stat_result) -> str:
    digest = hashlib.sha256()
    descriptor = -1
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or (held.st_dev, held.st_ino) != (
            opened.st_dev,
            opened.st_ino,
        ):
            raise _failure("a managed target file changed while it was inspected")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            while chunk := stream.read(64 * 1024):
                digest.update(chunk)
            after = os.fstat(stream.fileno())
    except CliFailure:
        raise
    except OSError as error:
        raise _failure("a managed target file could not be read") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if (held.st_dev, held.st_ino, held.st_size, held.st_mtime_ns) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise _failure("a managed target file changed while it was inspected")
    return f"sha256:{digest.hexdigest()}"


def _safe(value: str) -> bool:
    path = PurePosixPath(value)
    return (
        bool(value)
        and not value.startswith(("/", "~"))
        and "\\" not in value
        and all(part not in {"", ".", ".."} for part in path.parts)
    )


def _failure(message: str) -> CliFailure:
    return CliFailure("AI_STP_PRECONDITION_FAILED", message)
