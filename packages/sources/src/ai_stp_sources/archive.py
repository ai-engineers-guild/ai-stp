"""Bounded archive extraction shared with official upstream (SPEC-057 REQ-5718)."""

from __future__ import annotations

import io
import tarfile
import zipfile
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

from ai_stp_sources.errors import UNSAFE_ARCHIVE, SourceError

MAX_ARCHIVE_BYTES = 20 * 1024 * 1024
MAX_GIT_ARCHIVE_BYTES = 100 * 1024 * 1024
MAX_EXTRACTED_BYTES = 50 * 1024 * 1024
MAX_EXTRACTED_FILES = 20_000

_SECRET_NAMES = frozenset(
    {
        ".env",
        ".env.local",
        ".env.production",
        ".env.development",
        "id_rsa",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
        ".npmrc",
        ".pypirc",
        "credentials",
        "credentials.json",
    }
)
_SECRET_SUFFIXES = (".pem", ".p12", ".pfx", ".key")
# Committed empty templates. `.env`, `.env.local`, and other `.env.*` stay denied.
_ENV_TEMPLATE_NAMES = frozenset(
    {".env.example", ".env.sample", ".env.template", ".env.dist", "env.example"}
)


def extract_component_files(
    archive_bytes: bytes,
    *,
    subpath: str,
    max_archive_bytes: int = MAX_ARCHIVE_BYTES,
) -> dict[str, bytes]:
    """Extract component-root files; reject links, traversal, secrets, binaries."""
    if len(archive_bytes) > max_archive_bytes:
        raise SourceError(UNSAFE_ARCHIVE, "archive exceeds the accepted size")
    files: dict[str, bytes] = {}
    extracted = 0
    members = 0
    prefix = "" if subpath in {".", ""} else subpath.replace("\\", "/").strip("/")
    try:
        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:*") as tarball:
            for member in tarball.getmembers():
                relative = safe_member_path(member, reject_special=False)
                if relative is None:
                    continue
                if member.isdir():
                    continue
                if not member.isfile():
                    if _component_member_path(relative, prefix) is not None:
                        raise SourceError(UNSAFE_ARCHIVE, "archive contains a link or special file")
                    continue
                target = _component_member_path(relative, prefix)
                if target is None:
                    continue
                members += 1
                if members > MAX_EXTRACTED_FILES:
                    raise SourceError(UNSAFE_ARCHIVE, "extracted archive exceeds the accepted size")
                if extracted + member.size > MAX_EXTRACTED_BYTES:
                    raise SourceError(UNSAFE_ARCHIVE, "extracted archive exceeds the accepted size")
                stream = tarball.extractfile(member)
                if stream is None:
                    raise SourceError(UNSAFE_ARCHIVE, "archive member could not be read")
                payload = stream.read()
                extracted += len(payload)
                files[target] = payload
    except SourceError:
        raise
    except tarfile.TarError as exc:
        raise SourceError(UNSAFE_ARCHIVE, "archive is not a readable tar") from exc
    if not files:
        raise SourceError(UNSAFE_ARCHIVE, "component root is missing")
    for path, payload in files.items():
        reject_secret_name(path)
        reject_binary(payload)
    return files


def safe_member_path(member: tarfile.TarInfo, *, reject_special: bool = True) -> str | None:
    name = member.name.replace("\\", "/")
    if reject_special and (member.issym() or member.islnk() or member.isfifo() or member.isdev()):
        raise SourceError(UNSAFE_ARCHIVE, "archive contains a link or special file")
    if not name or name == ".":
        return None
    if name.startswith("/") or PurePosixPath(name).is_absolute():
        raise SourceError(UNSAFE_ARCHIVE, "archive path escapes the root")
    raw_parts = name.split("/")
    if any(part == ".." for part in raw_parts):
        raise SourceError(UNSAFE_ARCHIVE, "archive path escapes the root")
    parts = [part for part in raw_parts if part not in {"", "."}]
    if not parts:
        return None
    stripped = parts[1:] if len(parts) > 1 else ()
    if not stripped:
        return None
    return str(PurePosixPath(*stripped))


def _component_member_path(relative: str, prefix: str) -> str | None:
    if prefix == "":
        return relative
    if relative == prefix:
        return PurePosixPath(relative).name
    if relative.startswith(f"{prefix}/"):
        return relative[len(prefix) + 1 :]
    return None


def reject_secret_name(relative: str) -> None:
    name = Path(relative).name.lower()
    if name in _ENV_TEMPLATE_NAMES or (name.startswith(".env.") and name.endswith(".example")):
        return
    if name in _SECRET_NAMES or name.startswith(".env.") or name.endswith(_SECRET_SUFFIXES):
        raise SourceError(UNSAFE_ARCHIVE, "archive contains a secret-like file")


def reject_binary(payload: bytes) -> None:
    if b"\x00" in payload:
        raise SourceError(UNSAFE_ARCHIVE, "archive contains a binary file")
    try:
        payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SourceError(UNSAFE_ARCHIVE, "archive contains a binary file") from exc


def read_named_members(archive_bytes: bytes, wanted: frozenset[str]) -> dict[str, bytes]:
    """Read selected metadata files from a tar or zip; reject traversal and secrets."""
    if len(archive_bytes) > MAX_ARCHIVE_BYTES:
        raise SourceError(UNSAFE_ARCHIVE, "archive exceeds the accepted size")
    if archive_bytes.startswith(b"PK"):
        return _zip_named(archive_bytes, wanted)
    return _tar_named(archive_bytes, wanted)


def _member_basename(name: str) -> str | None:
    cleaned = name.replace("\\", "/")
    if cleaned.startswith("/") or PurePosixPath(cleaned).is_absolute():
        raise SourceError(UNSAFE_ARCHIVE, "archive path escapes the root")
    parts = cleaned.split("/")
    if any(part == ".." for part in parts):
        raise SourceError(UNSAFE_ARCHIVE, "archive path escapes the root")
    kept = [part for part in parts if part not in {"", "."}]
    if not kept:
        return None
    return kept[-1]


def _tar_named(archive_bytes: bytes, wanted: frozenset[str]) -> dict[str, bytes]:
    selected: dict[str, bytes] = {}
    extracted = 0
    try:
        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:*") as tarball:
            for member in tarball.getmembers():
                if member.issym() or member.islnk() or member.isfifo() or member.isdev():
                    raise SourceError(UNSAFE_ARCHIVE, "archive contains a link or special file")
                if member.isdir() or not member.isfile():
                    continue
                basename = _member_basename(member.name)
                if basename is None or basename not in wanted or basename in selected:
                    continue
                reject_secret_name(basename)
                if extracted + member.size > MAX_EXTRACTED_BYTES:
                    raise SourceError(UNSAFE_ARCHIVE, "extracted archive exceeds the accepted size")
                stream = tarball.extractfile(member)
                if stream is None:
                    raise SourceError(UNSAFE_ARCHIVE, "archive member could not be read")
                payload = stream.read()
                extracted += len(payload)
                selected[basename] = payload
    except SourceError:
        raise
    except tarfile.TarError as exc:
        raise SourceError(UNSAFE_ARCHIVE, "archive is not a readable tar") from exc
    return selected


def _zip_named(archive_bytes: bytes, wanted: frozenset[str]) -> dict[str, bytes]:
    selected: dict[str, bytes] = {}
    extracted = 0
    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                basename = _member_basename(info.filename)
                if basename is None or basename not in wanted or basename in selected:
                    continue
                reject_secret_name(basename)
                if extracted + info.file_size > MAX_EXTRACTED_BYTES:
                    raise SourceError(UNSAFE_ARCHIVE, "extracted archive exceeds the accepted size")
                payload = archive.read(info)
                extracted += len(payload)
                selected[basename] = payload
    except SourceError:
        raise
    except zipfile.BadZipFile as exc:
        raise SourceError(UNSAFE_ARCHIVE, "archive is not a readable zip") from exc
    return selected


def component_root(files: Mapping[str, bytes], subpath: str) -> dict[str, bytes]:
    prefix = "" if subpath in {".", ""} else subpath.replace("\\", "/").strip("/")
    selected: dict[str, bytes] = {}
    for path, content in files.items():
        if prefix == "":
            selected[path] = content
            continue
        if path == prefix:
            selected[PurePosixPath(path).name] = content
            continue
        if path.startswith(f"{prefix}/"):
            relative = path[len(prefix) + 1 :]
            if relative:
                selected[relative] = content
    if not selected:
        raise SourceError(UNSAFE_ARCHIVE, "component root is missing")
    return selected
