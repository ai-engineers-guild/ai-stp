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


@dataclass(frozen=True)
class ComponentBinding:
    """One component the verified bundle was built from.

    `member_paths` names the managed files the component projection wrote, so
    verification can say which component a drifted path belongs to instead of
    only that a path drifted.
    """

    stable_id: str
    version: str
    passport_digest: str
    component_kind: str
    member_paths: tuple[str, ...]


@dataclass(frozen=True)
class BundleOverview:
    """The verifiable identity of one verified HarnessBundle."""

    manifest: Manifest
    setup_stable_id: str = ""
    setup_version: str = ""
    setup_passport_digest: str = ""
    components: tuple[ComponentBinding, ...] = ()


def bundle_manifest(archive: Path) -> Manifest:
    """Read the exact managed file records from a verified cached bundle."""
    return _manifest(_bundle_document(archive))


def bundle_overview(archive: Path) -> BundleOverview:
    """The manifest plus the setup and component coordinates it was built from."""
    document = _bundle_document(archive)
    manifest = _manifest(document)
    setup = document.get("setup")
    held_setup = cast(dict[str, object], setup) if isinstance(setup, dict) else {}
    stable_id = held_setup.get("stable_id")
    version = held_setup.get("version")
    passport_digest = held_setup.get("passport_digest")
    bindings: list[ComponentBinding] = []
    adaptations = document.get("component_adaptations")
    if adaptations is not None:
        if not isinstance(adaptations, list):
            raise _failure("the verified HarnessBundle component bindings are invalid")
        adaptation_items = cast(list[object], adaptations)
        if len(adaptation_items) > MAX_MANAGED_FILES:
            raise _failure("the verified HarnessBundle component bindings are invalid")
        for raw_binding in adaptation_items:
            binding = cast(dict[str, object], raw_binding) if isinstance(raw_binding, dict) else {}
            member_paths = binding.get("member_paths")
            members = cast(list[object], member_paths) if isinstance(member_paths, list) else []
            if (
                not isinstance(binding.get("stable_id"), str)
                or not isinstance(binding.get("version"), str)
                or not isinstance(binding.get("passport_digest"), str)
                or not isinstance(binding.get("provider_component_kind"), str)
                or not isinstance(member_paths, list)
                or len(members) > MAX_MANAGED_FILES
                or any(not isinstance(member, str) or not _safe(member) for member in members)
            ):
                raise _failure("the verified HarnessBundle component bindings are invalid")
            bindings.append(
                ComponentBinding(
                    stable_id=str(binding["stable_id"]),
                    version=str(binding["version"]),
                    passport_digest=str(binding["passport_digest"]),
                    component_kind=str(binding["provider_component_kind"]),
                    member_paths=tuple(str(member) for member in members),
                )
            )
    return BundleOverview(
        manifest,
        setup_stable_id=stable_id if isinstance(stable_id, str) else "",
        setup_version=version if isinstance(version, str) else "",
        setup_passport_digest=passport_digest if isinstance(passport_digest, str) else "",
        components=tuple(bindings),
    )


def _bundle_document(archive: Path) -> dict[str, object]:
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
    return cast(dict[str, object], document)


def _manifest(document: dict[str, object]) -> Manifest:
    files = document.get("files")
    managed = document.get("managed_paths")
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
    if any(
        parent.as_posix() in records for path in records for parent in PurePosixPath(path).parents
    ):
        raise _failure("the verified HarnessBundle has colliding managed roots")
    scope = document.get("target_scope")
    return Manifest(
        records,
        _managed_roots(document, records),
        target_scope=scope if isinstance(scope, str) and scope else "global",
    )


def _managed_roots(document: dict[str, object], records: dict[str, str]) -> tuple[str, ...]:
    """Use the exact bundle's projection surfaces, never their shared parents.

    A nested settings file does not own its parent's logs or conversations.
    Without a conversion report, only the recorded files have known ownership.
    """
    report = document.get("conversion_report")
    if report is None:
        return tuple(sorted(records))
    if not isinstance(report, dict):
        raise _failure("the verified HarnessBundle conversion report is invalid")
    entries = cast(dict[str, object], report).get("entries")
    if not isinstance(entries, list):
        raise _failure("the verified HarnessBundle conversion entries are invalid")
    entry_items = cast(list[object], entries)
    if len(entry_items) > MAX_MANAGED_FILES:
        raise _failure("the verified HarnessBundle conversion entries are invalid")
    surfaces: set[str] = set()
    for entry in entry_items:
        if not isinstance(entry, dict):
            raise _failure("the verified HarnessBundle conversion entry is invalid")
        held = cast(dict[str, object], entry)
        surface = held.get("native_surface")
        if surface == "" and held.get("state") == "unsupported":
            continue
        if not isinstance(surface, str) or not _safe(surface):
            raise _failure("the verified HarnessBundle native surface is invalid")
        if any(path == surface or path.startswith(f"{surface}/") for path in records):
            surfaces.add(surface)
    roots = surfaces | {
        path
        for path in records
        if not any(path == surface or path.startswith(f"{surface}/") for surface in surfaces)
    }
    return tuple(
        sorted(
            root
            for root in roots
            if not any(p.as_posix() in roots for p in PurePosixPath(root).parents)
        )
    )


def _unsafe_parent(target: Path, root: str) -> bool:
    """Nested projection roots must not traverse links above the leaf."""
    parent = target
    for part in ("", *PurePosixPath(root).parts[:-1]):
        parent = parent / part
        try:
            mode = parent.lstat().st_mode
        except FileNotFoundError:
            return False
        except OSError as error:
            raise _failure("a managed target parent could not be inspected") from error
        if not stat.S_ISDIR(mode) or stat.S_ISLNK(mode):
            return True
    return False


def compare(target: Path, manifest: Manifest) -> tuple[Change, ...]:
    """Compare only allowlisted managed roots; never mutate or follow links."""
    current: dict[str, str] = {}
    files = 0
    total = 0
    for root in manifest.roots:
        if _unsafe_parent(target, root):
            for path in manifest.expected:
                if path == root or path.startswith(f"{root}/"):
                    current[path] = "unsafe"
            continue
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
        and bool(path.parts)
        and value == path.as_posix()
        and not value.startswith(("/", "~"))
        and "\\" not in value
        and ":" not in value
        and all(part not in {"", ".", ".."} for part in path.parts)
    )


def _failure(message: str) -> CliFailure:
    return CliFailure("AI_STP_PRECONDITION_FAILED", message)
