"""Canonical component artifact decoders shared by installation and context estimation."""

from __future__ import annotations

import io
import stat
import zipfile
from base64 import b64decode
from binascii import Error as Base64Error
from dataclasses import dataclass
from pathlib import PureWindowsPath
from typing import Final

from ai_stp_foundation.canonical import canonize, from_json_bytes
from ai_stp_foundation.digests import digest_bytes
from ai_stp_passports.projections import MAX_PROJECTION_BYTES, MAX_PROJECTION_FILES
from ai_stp_passports.projections import PROJECTION_FORMAT as PROJECTION_FORMAT

MAX_COMPONENT_BYTES: Final[int] = 4 * 1024 * 1024
MAX_COMPONENT_TREE_BYTES: Final[int] = 32 * 1024 * 1024
MAX_COMPONENT_FILES: Final[int] = 1000
COMPONENT_FILE_FORMAT: Final[str] = "ai-stp-component-file/1"
COMPONENT_TREE_FORMAT: Final[str] = "ai-stp-component-tree/1"
IMPORTED_COMPONENT_FORMAT: Final[str] = "ai-stp-imported-component/1"


class ComponentArtifactError(ValueError):
    """Closed artifact decoding failed before its files were exposed."""

    def __init__(self, code: str, message: str, *, details: dict[str, str] | None = None) -> None:
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


@dataclass(frozen=True)
class ComponentFile:
    """One verified member expanded from a stored component artifact."""

    path: str
    content: bytes
    mode: int


def _safe_path(path: str) -> bool:
    return (
        bool(path)
        and not path.startswith(("/", "~"))
        and "\\" not in path
        and not PureWindowsPath(path).drive
        and all(part not in {"", ".", ".."} for part in path.split("/"))
    )


def _expand_imported(payload: bytes) -> tuple[ComponentFile, ...]:
    """The captured envelope, decoded under the same bounds as a stored tree.

    Bounds rather than trust: this artifact is built from bytes found on a
    machine, so the per-member and total limits that guard an adopted tree guard
    it too, and a member path is refused when it is absolute, escapes, or
    repeats. A `declared_key` member keeps its `path#key` spelling, which is the
    same shape the adopt path already hands the compiler.
    """
    try:
        document = from_json_bytes(payload)
        if not isinstance(document, dict) or set(document) != {"format", "files"}:
            raise ValueError("imported component envelope is not closed")
        raw_files = document.get("files")
        if document.get("format") != IMPORTED_COMPONENT_FORMAT or not isinstance(raw_files, list):
            raise ValueError("imported component format differs")
        answer: list[ComponentFile] = []
        seen: set[str] = set()
        total = 0
        for raw in raw_files:
            if not isinstance(raw, dict) or set(raw) != {"path", "content_base64"}:
                raise ValueError("imported component member is invalid")
            path = raw.get("path")
            encoded = raw.get("content_base64")
            if (
                not isinstance(path, str)
                or not path
                or path in seen
                or not _safe_path(path)
                or not isinstance(encoded, str)
            ):
                raise ValueError("imported component member identity is invalid")
            seen.add(path)
            content_bytes = b64decode(encoded, validate=True)
            total += len(content_bytes)
            if len(content_bytes) > MAX_COMPONENT_BYTES or total > MAX_COMPONENT_TREE_BYTES:
                raise ValueError("imported component member is larger than one may be")
            answer.append(ComponentFile(path, content_bytes, 0o644))
        if len(answer) > MAX_COMPONENT_FILES:
            raise ValueError("imported component has more members than one may hold")
        return tuple(answer)
    except (UnicodeError, ValueError, Base64Error) as error:
        raise ComponentArtifactError(
            "AI_STP_CONFLICT", "the stored imported component is corrupt"
        ) from error


def expand_component_artifact(payload: bytes, content_format: str) -> tuple[ComponentFile, ...]:
    """Expand only the closed component artifact formats stored at adoption."""
    if content_format == COMPONENT_FILE_FORMAT:
        return (ComponentFile("", payload, 0o644),)
    if content_format == IMPORTED_COMPONENT_FORMAT:
        return _expand_imported(payload)
    if content_format == PROJECTION_FORMAT:
        try:
            with zipfile.ZipFile(io.BytesIO(payload), "r") as archive:
                answer: list[ComponentFile] = []
                names = archive.namelist()
                if len(names) != len(set(names)) or len(names) > MAX_PROJECTION_FILES:
                    raise ValueError("projection members are repeated or excessive")
                total_size = 0
                for info in archive.infolist():
                    total_size += info.file_size
                    if total_size > MAX_PROJECTION_BYTES:
                        raise ValueError("projection members exceed byte limits")
                    if not _safe_path(info.filename.rstrip("/")):
                        raise ValueError("projection member path is unsafe")
                    mode = info.external_attr >> 16
                    if info.is_dir():
                        continue
                    if info.compress_type != zipfile.ZIP_STORED or not stat.S_ISREG(mode):
                        raise ValueError("projection member metadata is unsafe")
                    answer.append(
                        ComponentFile(info.filename, archive.read(info), stat.S_IMODE(mode))
                    )
                return tuple(answer)
        except (OSError, ValueError, zipfile.BadZipFile) as error:
            raise ComponentArtifactError(
                "AI_STP_CONFLICT", "the stored projection is corrupt"
            ) from error
    if content_format != COMPONENT_TREE_FORMAT:
        raise ComponentArtifactError(
            "AI_STP_PRECONDITION_FAILED",
            "the component content format is unsupported",
            details={"content_format": content_format},
        )
    try:
        with zipfile.ZipFile(io.BytesIO(payload), "r") as archive:
            names = archive.namelist()
            if len(names) != len(set(names)) or "component.json" not in names:
                raise ValueError("component artifact members are incomplete or repeated")
            total_size = 0
            for info in archive.infolist():
                mode = info.external_attr >> 16
                total_size += info.file_size
                if (
                    info.compress_type != zipfile.ZIP_STORED
                    or not stat.S_ISREG(mode)
                    or info.file_size > MAX_COMPONENT_BYTES
                    or total_size > MAX_COMPONENT_TREE_BYTES
                ):
                    raise ValueError("component artifact member metadata is unsafe")
            parsed = from_json_bytes(archive.read("component.json"))
            if not isinstance(parsed, dict) or set(parsed) != {"format", "files"}:
                raise ValueError("component artifact manifest is not closed")
            files_value = parsed.get("files")
            if parsed.get("format") != COMPONENT_TREE_FORMAT or not isinstance(files_value, list):
                raise ValueError("component artifact format differs")
            if canonize(parsed) != archive.read("component.json"):
                raise ValueError("component artifact manifest is not canonical")
            answer: list[ComponentFile] = []
            expected = {"component.json"}
            for raw in files_value:
                if not isinstance(raw, dict) or set(raw) != {
                    "path",
                    "digest",
                    "byte_length",
                    "mode",
                }:
                    raise ValueError("component artifact file entry is invalid")
                path = raw.get("path")
                if not isinstance(path, str) or not path or not _safe_path(path):
                    raise ValueError("component artifact path is unsafe")
                name = f"files/{path}"
                if name in expected:
                    raise ValueError("component artifact path is repeated")
                expected.add(name)
                content_bytes = archive.read(name)
                mode_value = raw.get("mode")
                if (
                    digest_bytes("ai-stp:artifact:v1", content_bytes) != raw.get("digest")
                    or len(content_bytes) != raw.get("byte_length")
                    or not isinstance(mode_value, int)
                    or isinstance(mode_value, bool)
                    or mode_value not in {0o644, 0o755}
                ):
                    raise ValueError("component artifact member identity differs")
                answer.append(ComponentFile(path, content_bytes, mode_value))
            if set(names) != expected or len(answer) > MAX_COMPONENT_FILES:
                raise ValueError("component artifact has undeclared members")
            return tuple(answer)
    except (KeyError, ValueError, zipfile.BadZipFile) as error:
        raise ComponentArtifactError(
            "AI_STP_CONFLICT",
            "the stored component artifact is corrupt",
            details={"reason": str(error)},
        ) from error
