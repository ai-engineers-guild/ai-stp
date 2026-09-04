"""Inspect a provider wheel without running anything from it (`SPEC-008` REQ-849)."""

from __future__ import annotations

import base64
import hashlib
import zipfile
from dataclasses import dataclass
from pathlib import Path

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.paths import redact_home

_SYMLINK_MASK = 0o170000
_SYMLINK_TYPE = 0o120000
_MAX_WHEEL_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class WheelPayload:
    executable_name: str
    executable: bytes
    license_id: str
    version: str


def inspect(
    archive: Path,
    *,
    project: str,
    version: str,
    platform_name: str,
) -> WheelPayload:
    """Read one native binary out of an already-downloaded wheel."""
    if archive.is_symlink() or not archive.is_file():
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "the provider distribution is not a regular wheel",
            details={"artifact": redact_home(archive)},
        )
    size = archive.stat().st_size
    if size <= 0 or size > _MAX_WHEEL_BYTES:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the provider distribution is not a regular wheel",
            details={"artifact": redact_home(archive), "size": str(size)},
        )
    try:
        with zipfile.ZipFile(archive) as held:
            names = _safe_names(held)
            _verify_record(held, names)
            expected = _expected_executable(project, platform_name)
            payload = _exactly_one_executable(held, names, expected)
            metadata = _metadata(held, names, project, version)
    except zipfile.BadZipFile as error:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the provider distribution is not a regular wheel",
            details={"artifact": redact_home(archive)},
        ) from error
    return WheelPayload(
        executable_name=Path(expected).name,
        executable=payload,
        license_id=metadata[0],
        version=metadata[1],
    )


def _safe_names(held: zipfile.ZipFile) -> tuple[str, ...]:
    names: list[str] = []
    for info in held.infolist():
        name = info.filename.replace("\\", "/")
        if name.startswith("/") or name.startswith("../") or "/../" in f"/{name}/":
            raise CliFailure(
                "AI_STP_PRECONDITION_FAILED",
                "the provider wheel contains a path that leaves the archive",
                details={"member": name},
            )
        if ".." in Path(name).parts:
            raise CliFailure(
                "AI_STP_PRECONDITION_FAILED",
                "the provider wheel contains a path that leaves the archive",
                details={"member": name},
            )
        unix_type = (info.external_attr >> 16) & _SYMLINK_MASK
        if unix_type == _SYMLINK_TYPE:
            raise CliFailure(
                "AI_STP_PRECONDITION_FAILED",
                "the provider wheel contains a symbolic link",
                details={"member": name},
            )
        if not name.endswith("/"):
            names.append(name)
    return tuple(names)


def _verify_record(held: zipfile.ZipFile, names: tuple[str, ...]) -> None:
    record_name = next((name for name in names if name.endswith(".dist-info/RECORD")), "")
    if not record_name:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the provider wheel RECORD does not match the archive",
            details={"field": "RECORD"},
        )
    listed: dict[str, tuple[str, str]] = {}
    for raw in held.read(record_name).decode("utf-8").splitlines():
        if not raw.strip():
            continue
        parts = raw.split(",")
        if len(parts) != 3:
            raise CliFailure(
                "AI_STP_PRECONDITION_FAILED",
                "the provider wheel RECORD does not match the archive",
                details={"field": "RECORD"},
            )
        path, digest, size = parts
        listed[path] = (digest, size)
    members = set(names)
    recorded = set(listed)
    if members - recorded - {record_name}:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the provider wheel RECORD does not match the archive",
            details={"field": "RECORD"},
        )
    for name in names:
        if name == record_name:
            continue
        digest, size = listed.get(name, ("", ""))
        payload = held.read(name)
        if size and size != str(len(payload)):
            raise CliFailure(
                "AI_STP_PRECONDITION_FAILED",
                "the provider wheel RECORD does not match the archive",
                details={"member": name},
            )
        if digest.startswith("sha256="):
            expected = digest.removeprefix("sha256=")
            observed = (
                base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).rstrip(b"=").decode()
            )
            if observed != expected:
                raise CliFailure(
                    "AI_STP_PRECONDITION_FAILED",
                    "the provider wheel RECORD does not match the archive",
                    details={"member": name},
                )


def _expected_executable(project: str, platform_name: str) -> str:
    package = project.replace("-", "_")
    suffix = ".exe" if platform_name.startswith("windows/") else ""
    return f"{package}/bin/{project}{suffix}"


def _exactly_one_executable(held: zipfile.ZipFile, names: tuple[str, ...], expected: str) -> bytes:
    binaries = [name for name in names if "/bin/" in name and not name.endswith("/")]
    if expected not in binaries:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the provider wheel executable is not at the expected path",
            details={"expected": expected},
        )
    extras = [name for name in binaries if name != expected]
    if extras:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the provider wheel does not contain exactly one executable payload",
            details={"extra": extras[0]},
        )
    return held.read(expected)


def _metadata(
    held: zipfile.ZipFile, names: tuple[str, ...], project: str, version: str
) -> tuple[str, str]:
    meta_name = next((name for name in names if name.endswith(".dist-info/METADATA")), "")
    if not meta_name:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the provider distribution is not a regular wheel",
            details={"field": "METADATA"},
        )
    text = held.read(meta_name).decode("utf-8")
    fields: dict[str, str] = {}
    for line in text.splitlines():
        if not line or ":" not in line:
            if line == "":
                break
            continue
        key, value = line.split(":", 1)
        fields.setdefault(key.strip(), value.strip())
    name = fields.get("Name", "").replace("_", "-").lower()
    found_version = fields.get("Version", "")
    if name != project.lower() or found_version != version:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the provider distribution is not a regular wheel",
            details={"name": name, "version": found_version},
        )
    license_id = fields.get("License-Expression") or fields.get("License") or ""
    if not license_id or license_id in {"NOASSERTION", "NONE", "UNKNOWN"}:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the provider distribution is not a regular wheel",
            details={"field": "License"},
        )
    return license_id, found_version
