"""Register a directory as one embedded component and one setup identity."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

from ulid import ULID

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import content, revisions, setup_compose, versions
from ai_stp_cli.local.composition import rule_for
from ai_stp_passports import SetupVersionPassport
from ai_stp_passports.versions import COMPONENT_TYPES, ComponentType
from ai_stp_sources.errors import SourceError
from ai_stp_sources.local import resolve_local
from ai_stp_sources.models import PathIntent, SourceSnapshot

AUTHORED_VERSION: Final[str] = versions.FIRST_VERSION
PRIVATE_LICENSE: Final[str] = "LicenseRef-AI-STP-Private"


@dataclass(frozen=True)
class AuthoredSetup:
    setup_id: str
    setup_version: str
    component_id: str
    component_version: str
    minted: bool


def kinds_for(harness_id: str) -> tuple[str, ...]:
    """Closed kinds that this harness can actually host."""
    return tuple(
        kind for kind in COMPONENT_TYPES if kind == "cli" or rule_for(kind, harness_id) is not None
    )


def authored_setup_id(
    publisher_id: str,
    harness_id: str,
    component_type: str,
    files_digest: str,
    *,
    native_paths: tuple[str, ...] = (),
) -> str:
    material = f"{publisher_id}\0{harness_id}\0{component_type}\0{files_digest}".encode()
    if native_paths:
        material += ("\0native_paths\0" + "\0".join(native_paths)).encode()
    return f"setup_{ULID.from_bytes(hashlib.sha256(material).digest()[:16])}"


def snapshot_of(directory: Path) -> tuple[Path, SourceSnapshot]:
    """Read the directory through the shared path adapter. Never records an absolute path."""
    resolved = directory.expanduser()
    if not resolved.is_absolute():
        resolved = Path.cwd() / resolved
    try:
        resolved = resolved.resolve()
    except OSError as error:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "that directory does not exist",
            details={"directory": str(directory)},
        ) from error
    if not resolved.is_dir():
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "that directory does not exist",
            details={"directory": str(resolved)},
        )
    if not resolved.name:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the directory must have a name",
            details={"directory": str(resolved)},
        )
    try:
        snapshot = resolve_local(
            PathIntent(relative_path=resolved.name),
            local_root=resolved.parent,
        )
    except SourceError as error:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            error.message,
            details={"source_code": error.code, "directory": str(resolved)},
        ) from error
    return resolved, snapshot


def record(
    connection: sqlite3.Connection,
    *,
    directory: Path,
    harness_id: str,
    component_type: str,
    name: str,
    license_spdx: str,
    publisher_id: str,
    device_id: str,
    at: str,
) -> AuthoredSetup:
    """Persist one embedded component plus one setup, or reuse the same bytes."""
    kinds = kinds_for(harness_id)
    if component_type not in kinds:
        raise CliFailure(
            "AI_STP_CONFLICT",
            "this harness has no native surface for that component type",
            details={"harness_id": harness_id, "component_type": component_type},
        )
    place, snapshot = snapshot_of(directory)
    files_digest = str(snapshot.component_digest or snapshot.exact_identity)
    managed = _managed_files(snapshot, component_type, harness_id, name)
    # A corrected native document must not replay an immutable nested projection.
    native_paths = managed if _named_document(component_type, harness_id) else ()
    setup_id = authored_setup_id(
        publisher_id, harness_id, component_type, files_digest, native_paths=native_paths
    )
    held = versions.held(connection, setup_id, AUTHORED_VERSION)
    if held is not None:
        return _held_setup(connection, held, minted=False)
    description = f"Local {component_type} {name}."
    component = setup_compose.ComposeComponent(
        source={"kind": "path", "relative_path": place.name},
        component_type=cast(ComponentType, component_type),
        name=name,
        description=description,
        license_spdx=license_spdx,
        redistribution_allowed=False,
        managed_paths=managed,
    )
    manifest = setup_compose.ComposeManifest(
        name=name[:160],
        description=description[:4000],
        harness_id=harness_id,
        version=AUTHORED_VERSION,
        tags=("authored",),
        components=(component,),
    )
    try:
        composed = setup_compose.compose(
            manifest=manifest,
            setup_id=setup_id,
            publisher_id=publisher_id,
            created_at=at,
            snapshots=((component, snapshot),),
            catalog=(),
            # The component must fork with its projection, as well as the setup.
            embedded_identity_scope=setup_id if native_paths else "",
        )
    except SourceError as error:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR", error.message, details={"source_code": error.code}
        ) from error
    setup_compose.apply(
        connection,
        composed,
        expected_plan_digest=composed.plan_digest,
        device_id=device_id,
        publisher_id=publisher_id,
        at=at,
    )
    member = composed.frozen.components[0]
    return AuthoredSetup(
        setup_id=setup_id,
        setup_version=AUTHORED_VERSION,
        component_id=member.stable_id,
        component_version=member.version,
        minted=True,
    )


def _managed_files(
    snapshot: SourceSnapshot, component_type: str, harness_id: str, name: str
) -> tuple[str, ...]:
    """Map source files to native members, not to directory ownership claims."""
    if not name or name in {".", ".."} or any(char in name for char in "/\\\0"):
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR", "the component name must be one native path segment"
        )
    files = sorted(path for path in snapshot.files if path.rsplit("/", 1)[-1] != "GENERATED.md")
    rule = rule_for(component_type, harness_id)
    if rule is not None and _named_document(component_type, harness_id):
        if len(files) != 1 or not files[0].endswith(".md"):
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                "this native document surface requires exactly one Markdown file",
                details={"harness_id": harness_id, "component_type": component_type},
            )
        return (f"{rule.relative}/{name}.md",)
    if rule is not None and rule.shape == "directory":
        return tuple(f"{rule.relative}/{name}/{path}" for path in files)
    if len(files) != 1:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "this native surface requires exactly one source file",
            details={"harness_id": harness_id, "component_type": component_type},
        )
    return (rule.relative if rule is not None else f"bin/{name}",)


def _named_document(component_type: str, harness_id: str) -> bool:
    return harness_id == "antigravity" and component_type in {"instruction", "command"}


def _held_setup(
    connection: sqlite3.Connection, held: versions.Recorded, *, minted: bool
) -> AuthoredSetup:
    stored = revisions.get(connection, held.revision_id)
    if stored is None:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "the authored setup points to a missing passport",
            details={"stable_id": held.stable_id},
        )
    passport = SetupVersionPassport.model_validate(stored.envelope.model_dump(mode="json"))
    setup_compose.retain_embedded(
        connection,
        content.get(connection, passport.artifact.digest),
        device_id=stored.device_id,
        at=stored.created_at,
    )
    member = passport.components[0]
    return AuthoredSetup(
        setup_id=held.stable_id,
        setup_version=held.version,
        component_id=member.stable_id,
        component_version=member.version,
        minted=minted,
    )
