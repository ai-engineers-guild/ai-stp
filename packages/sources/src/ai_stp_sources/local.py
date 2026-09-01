"""Bounded local-path resolution inside a confirmed root (SPEC-057 REQ-5718)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from ai_stp_sources.archive import (
    MAX_EXTRACTED_BYTES,
    MAX_EXTRACTED_FILES,
    reject_binary,
    reject_secret_name,
)
from ai_stp_sources.coordinates import canonicalize_source
from ai_stp_sources.errors import INVALID_SOURCE, UNSAFE_ARCHIVE, SourceError
from ai_stp_sources.files import files_digest
from ai_stp_sources.models import PathIntent, SourceSnapshot


def _within_root(root: Path, candidate: Path) -> Path:
    try:
        resolved_root = root.resolve()
        resolved = candidate.resolve()
        resolved.relative_to(resolved_root)
    except (OSError, ValueError) as exc:
        raise SourceError(INVALID_SOURCE, "local path escapes the confirmed root") from exc
    return resolved


def resolve_local(
    intent: PathIntent,
    *,
    local_root: Path,
    now: datetime | None = None,
) -> SourceSnapshot:
    """Read files under the confirmed root; never records an absolute path."""
    if local_root.is_absolute() is False:
        raise SourceError(INVALID_SOURCE, "confirmed local root must be absolute")
    canonical = canonicalize_source(intent)
    assert isinstance(canonical, PathIntent)
    root = local_root.resolve()
    target = _within_root(root, root.joinpath(*canonical.relative_path.split("/")))
    files: dict[str, bytes] = {}
    total = 0
    if target.is_file():
        payload = target.read_bytes()
        total = len(payload)
        if total > MAX_EXTRACTED_BYTES:
            raise SourceError(UNSAFE_ARCHIVE, "extracted archive exceeds the accepted size")
        relative = canonical.relative_path.rsplit("/", 1)[-1]
        reject_secret_name(relative)
        reject_binary(payload)
        files = {relative: payload}
    elif target.is_dir():
        entries = sorted(path for path in target.rglob("*") if path.is_file())
        if len(entries) > MAX_EXTRACTED_FILES:
            raise SourceError(UNSAFE_ARCHIVE, "extracted archive exceeds the accepted size")
        for path in entries:
            _within_root(root, path)
            relative = path.relative_to(target).as_posix()
            reject_secret_name(relative)
            payload = path.read_bytes()
            total += len(payload)
            if total > MAX_EXTRACTED_BYTES:
                raise SourceError(UNSAFE_ARCHIVE, "extracted archive exceeds the accepted size")
            reject_binary(payload)
            files[relative] = payload
        if not files:
            raise SourceError(UNSAFE_ARCHIVE, "component root is missing")
    else:
        raise SourceError(INVALID_SOURCE, "local path does not exist")
    return SourceSnapshot(
        kind="path",
        canonical_coordinate=f"path:{canonical.relative_path}",
        exact_identity=files_digest(files),
        component_digest=files_digest(files),
        subpath=canonical.relative_path,
        files=files,
        fetched_at=now or datetime.now(UTC),
    )
