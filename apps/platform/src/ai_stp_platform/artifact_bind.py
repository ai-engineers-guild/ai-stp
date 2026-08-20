"""Plan-scoped publication artifact bind (SPEC-026 REQ-2627, ADR-0093)."""

from __future__ import annotations

import io
import zipfile
from typing import Final

from ai_stp_foundation.digests import digest_bytes
from ai_stp_platform.safety.workdir import MAX_ARTIFACT_BYTES
from ai_stp_platform.storage.object_store import (
    ARTIFACT_DIGEST_DOMAIN,
    ImmutableObjectStore,
    ObjectIntegrityError,
    StoredObject,
)

_UNIX_SYMLINK: Final[int] = 0xA000
_UNIX_CHAR: Final[int] = 0x2000
_UNIX_BLOCK: Final[int] = 0x6000
_UNIX_FIFO: Final[int] = 0x1000
_UNIX_TYPE: Final[int] = 0xF000


class ArtifactBindError(ValueError):
    """Uploaded bytes are unsafe or do not match the publication plan."""


def inspect_publication_artifact(payload: bytes, *, max_bytes: int = MAX_ARTIFACT_BYTES) -> None:
    """Reject oversized, traversing, linked or special-file artifact content."""
    if len(payload) > max_bytes:
        raise ArtifactBindError("artifact exceeds the accepted size")
    if not _is_zip(payload):
        return
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile as exc:
        raise ArtifactBindError("artifact zip is invalid") from exc
    with archive:
        total = 0
        for info in archive.infolist():
            total += info.file_size
            if total > max_bytes:
                raise ArtifactBindError("artifact uncompressed size exceeds the accepted size")
            name = info.filename.replace("\\", "/")
            if name.startswith("/") or ".." in name.split("/"):
                raise ArtifactBindError("artifact zip path escapes the root")
            mode = (info.external_attr >> 16) & 0xFFFF
            kind = mode & _UNIX_TYPE
            if kind in {_UNIX_SYMLINK, _UNIX_CHAR, _UNIX_BLOCK, _UNIX_FIFO}:
                raise ArtifactBindError("artifact zip contains a link or special file")


async def bind_plan_artifact(
    *,
    store: ImmutableObjectStore,
    payload: bytes,
    expected_digest: str,
    expected_size: int,
) -> StoredObject:
    """Inspect, verify digest/size and commit immutable bytes."""
    inspect_publication_artifact(payload)
    actual = digest_bytes(ARTIFACT_DIGEST_DOMAIN, payload)
    if actual != expected_digest or len(payload) != expected_size:
        raise ObjectIntegrityError("object bytes do not match declared digest and size")
    return await store.put_immutable(
        payload,
        expected_digest=expected_digest,
        expected_size=expected_size,
    )


async def plan_artifact_is_durable(
    *,
    store: ImmutableObjectStore,
    content_digest: str,
    expected_size: int | None,
) -> bool:
    """Return whether the plan digest is already present and verified."""
    try:
        payload = await store.read_by_digest(content_digest, expected_size=expected_size)
    except ObjectIntegrityError:
        return False
    return payload is not None


def _is_zip(payload: bytes) -> bool:
    return len(payload) >= 4 and payload[:2] == b"PK"
