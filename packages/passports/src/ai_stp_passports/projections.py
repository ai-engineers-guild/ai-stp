"""Deterministic component projection archives and their exact verifier."""

import io
import stat
import zipfile
from collections.abc import Mapping
from typing import Final

from ai_stp_foundation.digests import digest_bytes
from ai_stp_passports.versions import ScopeAdaptation

PROJECTION_FORMAT: Final[str] = "ai-stp-adaptation-projection/1"
MAX_PROJECTION_FILES: Final[int] = 8192
MAX_PROJECTION_BYTES: Final[int] = 67_108_864
_ZIP_TIMESTAMP: Final[tuple[int, int, int, int, int, int]] = (1980, 1, 1, 0, 0, 0)


class ProjectionArtifactError(ValueError):
    """The projection bytes do not close over their immutable declaration."""


def build_projection(
    scope: ScopeAdaptation,
    file_contents: Mapping[str, bytes],
) -> bytes:
    """Build the sole canonical ZIP representation of one scope projection."""
    if scope.projection_format != PROJECTION_FORMAT:
        raise ProjectionArtifactError("unsupported projection format")
    if len(scope.members) > MAX_PROJECTION_FILES:
        raise ProjectionArtifactError("projection exceeds the consumer member limit")
    expected_files = {member.path for member in scope.members if member.object_type == "file"}
    if set(file_contents) != expected_files:
        raise ProjectionArtifactError("projection file contents differ from declared members")
    for member in scope.members:
        if member.object_type != "file":
            continue
        content = file_contents[member.path]
        expected = member.content_artifact
        if expected is None or len(content) != expected.size_bytes:
            raise ProjectionArtifactError("projection member size differs")
        if digest_bytes("ai-stp:artifact:v1", content) != expected.digest:
            raise ProjectionArtifactError("projection member digest differs")
    if sum(len(content) for content in file_contents.values()) > MAX_PROJECTION_BYTES:
        raise ProjectionArtifactError("projection exceeds the consumer byte limit")

    output = io.BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_STORED) as archive:
        for member in sorted(scope.members, key=lambda item: item.path):
            name = member.path if member.object_type == "file" else f"{member.path}/"
            info = zipfile.ZipInfo(name, date_time=_ZIP_TIMESTAMP)
            info.create_system = 3
            info.compress_type = zipfile.ZIP_STORED
            kind = stat.S_IFREG if member.object_type == "file" else stat.S_IFDIR
            info.external_attr = (kind | member.mode) << 16
            archive.writestr(info, file_contents.get(member.path, b""))
    return output.getvalue()


def verify_projection(scope: ScopeAdaptation, payload: bytes) -> None:
    """Reject bytes unless identity, members, metadata and encoding are exact."""
    if len(payload) > MAX_PROJECTION_BYTES:
        raise ProjectionArtifactError("projection exceeds the consumer byte limit")
    if len(payload) != scope.projection_artifact.size_bytes:
        raise ProjectionArtifactError("projection artifact size differs")
    if digest_bytes("ai-stp:artifact:v1", payload) != scope.projection_artifact.digest:
        raise ProjectionArtifactError("projection artifact digest differs")
    try:
        with zipfile.ZipFile(io.BytesIO(payload), mode="r") as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                raise ProjectionArtifactError("projection contains duplicate members")
            contents: dict[str, bytes] = {}
            expected_names: set[str] = set()
            for member in scope.members:
                name = member.path if member.object_type == "file" else f"{member.path}/"
                expected_names.add(name)
                info = archive.getinfo(name)
                raw_mode = info.external_attr >> 16
                expected_kind = stat.S_ISREG if member.object_type == "file" else stat.S_ISDIR
                if (
                    info.compress_type != zipfile.ZIP_STORED
                    or info.date_time != _ZIP_TIMESTAMP
                    or not expected_kind(raw_mode)
                    or stat.S_IMODE(raw_mode) != member.mode
                    or info.create_system != 3
                ):
                    raise ProjectionArtifactError("projection member metadata differs")
                content = archive.read(info)
                if member.object_type == "directory" and content:
                    raise ProjectionArtifactError("projection directory contains bytes")
                if member.object_type == "file":
                    contents[member.path] = content
            if set(names) != expected_names:
                raise ProjectionArtifactError("projection contains undeclared members")
    except (KeyError, OSError, zipfile.BadZipFile) as error:
        raise ProjectionArtifactError("projection is not a valid closed archive") from error

    if build_projection(scope, contents) != payload:
        raise ProjectionArtifactError("projection archive encoding is not canonical")
