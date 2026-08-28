"""Importing existing native configuration, safely (`#174`, `SPEC-008` REQ-813).

Somebody already has a working harness. Importing it must not break it, must not
carry their secrets into a registry, and must not pretend the result is more
trustworthy than what it was made from.

**Inspection changes nothing.** `REQ-813` puts inspection first and in
inspection order, and this module reads: it opens files, hashes them and reports.
Nothing here writes to a harness target, and there is no argument shape that
lets it. The backup belongs to the provider; `ai_stp` holds a reference to it and
never the bytes.

**Secret values never enter the registry, and the inventory says only names.**
`REQ-815` allows an imported setup to carry the *names* of mandatory environment
variables and nothing else. So scrubbing replaces a value in place and records
the key it sat under — a redacted document plus a list of names, never a list of
what was redacted.

**The inventory reports what was scanned, not that nothing was missed.**
Detection is by key name, because the alternative — guessing from the shape of a
string — calls a project identifier a secret and misses a password stored under
`value`. An honest partial answer beats a confident wrong one, so the report
names the rule it used and the caller decides.

**A `BackupRef` is not an identity.** `REQ-814` keeps them separate objects: a
backup says where the old bytes are, an imported setup says what was made from
them. Conflating the two would make deleting a backup delete a setup's identity.
"""

import json
import re
import sqlite3
from base64 import b64encode
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final, cast

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import content, harness_catalog, journal, revisions
from ai_stp_cli.local.database import transaction
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_canonical
from ai_stp_foundation.ids import new_id

#: Key names whose value is a credential. Matched case-insensitively against the
#: whole key and against its last dotted segment, so `auth.token` is caught as
#: readily as `token`.
SECRET_KEYS: Final[frozenset[str]] = frozenset(
    {
        "api_key",
        "apikey",
        "access_key",
        "access_token",
        "auth_token",
        "authorization",
        "client_secret",
        "credential",
        "credentials",
        "key",
        "password",
        "passwd",
        "private_key",
        "refresh_token",
        "secret",
        "secret_key",
        "session_token",
        "token",
    }
)

#: What replaces a value that was removed. A fixed marker rather than a blank:
#: an empty string reads as "this setting is off", and the whole point is that
#: the setting exists and its value was not carried.
REDACTED: Final[str] = "<redacted-on-import>"

#: What the inventory says it did. Named so a caller can tell a complete answer
#: from this one, which is not complete and does not claim to be.
DETECTION_RULE: Final[str] = "key-name"

#: Files that are configuration worth importing. A binary or an artifact is not
#: configuration, and importing one would carry bytes nobody reviewed.
IMPORTABLE_SUFFIXES: Final[frozenset[str]] = frozenset(
    {".json", ".toml", ".yaml", ".yml", ".md", ".txt"}
)

#: Bound on one imported file. A harness configuration is text somebody wrote;
#: anything larger is not the thing this is for.
MAX_FILE_BYTES: Final[int] = 1024 * 1024


@dataclass(frozen=True)
class Finding:
    """One file the inspection read, and what it holds."""

    path: str
    byte_length: int
    digest: str

    #: Key names whose value was removed. Names only — `REQ-815` allows the name
    #: of a mandatory variable into a passport and nothing else, and a list of
    #: what was redacted would be the list of secrets.
    redacted_keys: tuple[str, ...] = ()

    #: Set when the file could not be read at all. Kept apart from "no secrets
    #: found": one is a clean file and the other is a file nobody looked at.
    unreadable: str = ""

    #: Set when the file was read and hashed but exceeds `MAX_FILE_BYTES`. That
    #: is a declared exclusion policy, not a failure to see the file, so it must
    #: not reach `unreadable`: the two need different remedies and only one of
    #: them means the configuration was not fully described.
    oversized: bool = False


@dataclass(frozen=True)
class Inspection:
    """What one native configuration looks like, read and nothing more."""

    root: str
    harness_id: str
    findings: tuple[Finding, ...]

    #: The rule detection used. A report that does not say how it looked cannot
    #: be told apart from one that looked properly.
    detection_rule: str = DETECTION_RULE

    @property
    def redacted_keys(self) -> tuple[str, ...]:
        return tuple(sorted({name for item in self.findings for name in item.redacted_keys}))

    @property
    def unreadable(self) -> tuple[str, ...]:
        return tuple(item.path for item in self.findings if item.unreadable)

    @property
    def oversized(self) -> tuple[str, ...]:
        return tuple(item.path for item in self.findings if item.oversized)

    @property
    def skipped(self) -> tuple[str, ...]:
        """Every path that contributes to no component, for either reason."""
        return tuple(sorted({*self.unreadable, *self.oversized}))


@dataclass(frozen=True)
class BackupRef:
    """Where the provider put the old bytes. Not a setup, and not an identity."""

    backup_id: str
    harness_id: str
    target_id: str

    #: The provider's own reference. `ai_stp` never holds backup bytes: they are
    #: the provider's, and copying them would make two owners of one recovery.
    provider_ref: str
    created_at: str


@dataclass(frozen=True)
class Imported:
    """One imported setup and the backup it was taken alongside.

    Two fields rather than one object, because they are two objects. Deleting a
    backup must not delete a setup's identity, and it cannot when the identity
    was never the backup's.
    """

    stable_id: str
    revision_id: str
    backup_id: str
    plan_digest: str = ""
    component_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProposedComponent:
    """One natural native component boundary found inside an inspection."""

    candidate_id: str
    component_type: str
    native_role: str
    paths: tuple[str, ...]
    file_set_digest: str
    byte_length: int


@dataclass(frozen=True)
class Plan:
    """A content-addressed, read-only proposal for registering one setup graph."""

    root: str
    harness_id: str
    inspection_digest: str
    plan_digest: str
    components: tuple[ProposedComponent, ...]
    excluded: tuple[str, ...]
    blocked_by: tuple[str, ...]
    effects: tuple[str, ...]


def plan(inspection: Inspection) -> Plan:
    """Decompose an inspection without creating identities or storing bytes."""
    inspection_document: dict[str, JsonValue] = {
        "root": inspection.root,
        "harness_id": inspection.harness_id,
        "detection_rule": inspection.detection_rule,
        "files": [
            {
                "path": item.path,
                "byte_length": item.byte_length,
                "digest": item.digest,
                "redacted_keys": list(item.redacted_keys),
                "unreadable": item.unreadable,
                "oversized": item.oversized,
            }
            for item in inspection.findings
        ],
    }
    inspection_digest = digest_canonical("ai-stp:native-discovery:v1", inspection_document)
    grouped: dict[tuple[str, str], list[Finding]] = {}
    excluded: list[str] = []
    for item in inspection.findings:
        if item.unreadable or item.oversized:
            excluded.append(item.path)
            continue
        component_type, native_role, boundary = _component_boundary(item.path)
        grouped.setdefault((component_type, f"{native_role}:{boundary}"), []).append(item)

    proposed: list[ProposedComponent] = []
    for (component_type, identity), findings in sorted(grouped.items()):
        native_role, _, _boundary = identity.partition(":")
        paths = tuple(sorted(item.path for item in findings))
        material: dict[str, JsonValue] = {
            "harness_id": inspection.harness_id,
            "component_type": component_type,
            "native_role": native_role,
            "files": [
                {"path": item.path, "digest": item.digest, "byte_length": item.byte_length}
                for item in sorted(findings, key=lambda found: found.path)
            ],
        }
        file_set_digest = digest_canonical("ai-stp:plan:v1", material)
        candidate_id = digest_canonical("ai-stp:native-discovery:v1", material)
        proposed.append(
            ProposedComponent(
                candidate_id=candidate_id,
                component_type=component_type,
                native_role=native_role,
                paths=paths,
                file_set_digest=file_set_digest,
                byte_length=sum(item.byte_length for item in findings),
            )
        )

    # Only a file nobody could read blocks. An oversized one is already in
    # `excluded`, and listing the same path as both "left out" and "in your way"
    # is a contradiction the caller cannot act on.
    blocked = tuple(f"unreadable:{path}" for path in sorted(inspection.unreadable))
    effects = (
        f"register {len(proposed)} component draft(s)",
        "register one private setup draft with exact component references",
    )
    plan_document: dict[str, JsonValue] = {
        "inspection_digest": inspection_digest,
        "harness_id": inspection.harness_id,
        "components": [
            {
                "candidate_id": item.candidate_id,
                "component_type": item.component_type,
                "native_role": item.native_role,
                "paths": list(item.paths),
                "file_set_digest": item.file_set_digest,
                "byte_length": item.byte_length,
            }
            for item in proposed
        ],
        "excluded": cast(list[JsonValue], sorted(excluded)),
        "blocked_by": cast(list[JsonValue], list(blocked)),
        "effects": cast(list[JsonValue], list(effects)),
    }
    return Plan(
        root=inspection.root,
        harness_id=inspection.harness_id,
        inspection_digest=inspection_digest,
        plan_digest=digest_canonical("ai-stp:plan:v1", plan_document),
        components=tuple(proposed),
        excluded=tuple(sorted(excluded)),
        blocked_by=blocked,
        effects=effects,
    )


def _component_boundary(path: str) -> tuple[str, str, str]:
    """Map a native relative path onto a stable component family boundary."""
    parts = Path(path).parts
    folded = tuple(part.casefold() for part in parts)
    families = {
        "skills": ("skill", "skill"),
        "commands": ("command", "command"),
        "agents": ("agent", "agent"),
        "hooks": ("hook", "hook"),
        "plugins": ("plugin", "plugin"),
    }
    for index, part in enumerate(folded[:-1]):
        if part in families:
            component_type, role = families[part]
            boundary = parts[index + 1]
            return component_type, role, f"{part}/{boundary}"
    name = folded[-1]
    if "mcp" in name:
        return "mcp", "mcp_server", path
    if name in {"agents.md", "claude.md"} or name.endswith("instructions.md"):
        return "instruction", "instruction", path
    return "setting", "configuration", path


def _state_paths(harness_id: str) -> tuple[str, ...]:
    """Subtrees this harness writes state into, from the catalog that owns them."""
    definition = harness_catalog.BY_ID.get(harness_id)
    return () if definition is None else definition.state_paths


def _is_state(relative: str, state_paths: tuple[str, ...]) -> bool:
    """Whether a path inside the configuration root is runtime state.

    Matched on whole path segments so a declared `cache` never swallows a
    sibling named `cache-policy.toml`, and so an undeclared harness keeps
    every file it has today.
    """
    parts = PurePosixPath(relative.replace("\\", "/")).parts
    for declared in state_paths:
        prefix = PurePosixPath(declared).parts
        if parts[: len(prefix)] == prefix:
            return True
    return False


def inspect(root: Path, *, harness_id: str) -> Inspection:
    """Read one native configuration. Writes nothing, anywhere.

    Files are visited in sorted order so two inspections of one tree produce one
    report. A file that cannot be read is reported as unreadable rather than
    skipped: "there were no secrets" and "nobody looked" must not be the same
    answer.

    Subtrees the harness writes state into are not read at all. A configuration
    root is also where a harness keeps session transcripts, job records and
    caches, and a real `~/.claude` offers 3800 job records against roughly 58
    files a person authored. A setup built from those would pin one machine's
    history as if it were shareable, and would read as drifted the moment the
    harness ran again. Which subtrees those are belongs to `harness_catalog`,
    the same owner the layouts come from.
    """
    resolved = root.resolve()
    if not resolved.is_dir():
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "there is no configuration directory at that path",
            details={"root": str(root)},
        )

    state_paths = _state_paths(harness_id)
    findings: list[Finding] = []
    for place in sorted(resolved.rglob("*")):
        if not place.is_file() or place.suffix.casefold() not in IMPORTABLE_SUFFIXES:
            continue
        relative = place.relative_to(resolved).as_posix()
        if _is_state(relative, state_paths):
            continue
        # Ask how big it is before reading it. `REQ-841` requires an oversized
        # file to be read and hashed, and it still is — but "read" used to mean
        # "read into one `bytes` object", so a multi-gigabyte cache blob in a
        # harness root was allocated whole in order to discover that it would be
        # excluded. A real `~/.codex` holds exactly that shape of file.
        #
        # The evidence is unchanged: same digest, same length, same exclusion.
        # Only the memory is bounded.
        try:
            oversized_by_stat = place.stat().st_size > MAX_FILE_BYTES
            if oversized_by_stat:
                digest, length = content.address_of_file(place)
                findings.append(
                    Finding(path=relative, byte_length=length, digest=digest, oversized=True)
                )
                continue
            raw = place.read_bytes()
        except OSError as error:
            findings.append(
                Finding(path=relative, byte_length=0, digest="", unreadable=type(error).__name__)
            )
            continue
        # A file that grew past the bound between the stat and the read is
        # still oversized, and this is the branch that says so.
        if len(raw) > MAX_FILE_BYTES:
            # Read and hashed, so it is not unreadable. Harness roots carry
            # caches — a real `~/.codex` holds multi-megabyte catalogue blobs —
            # and calling those unreadable made every such root unimportable
            # while pointing the reader at a permission problem that does not
            # exist.
            findings.append(
                Finding(
                    path=relative,
                    byte_length=len(raw),
                    digest=content.address_of(raw),
                    oversized=True,
                )
            )
            continue

        _, names = scrub(raw)
        findings.append(
            Finding(
                path=relative,
                byte_length=len(raw),
                digest=content.address_of(raw),
                redacted_keys=names,
            )
        )
    return Inspection(root=str(resolved), harness_id=harness_id, findings=tuple(findings))


def scrub(raw: bytes) -> tuple[bytes, tuple[str, ...]]:
    """Remove credential values, returning the clean bytes and the key names.

    Structured documents are walked and rewritten; anything else is returned
    untouched with nothing claimed about it. Guessing at the shape of an
    unstructured file would either miss a secret or mangle a document, and both
    are worse than saying the file was not rewritten.
    """
    try:
        decoded: object = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return raw, ()

    names: set[str] = set()
    cleaned = _walk(decoded, names)
    return json.dumps(cleaned, ensure_ascii=False, sort_keys=True).encode("utf-8"), tuple(
        sorted(names)
    )


_CAMEL_BOUNDARY: Final = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def _fold_key(name: str) -> str:
    """One spelling for a key name, so an exact comparison can be exact.

    `accessToken`, `access-token` and `Access_Token` are the same name written
    three ways, and a set membership test sees three different strings unless
    they are folded first.
    """
    return _CAMEL_BOUNDARY.sub("_", name).casefold().replace("-", "_")


def is_secret_key(name: str) -> bool:
    """Whether a key's *name* says its value is a credential.

    By name, and the report says so. The alternative is guessing from the shape
    of the value, which calls a project identifier a secret and misses a
    password stored under `value` — a confident wrong answer where an honest
    partial one was available.

    The comparison is exact against `SECRET_KEYS`, so the name has to be folded
    into the same shape first. `-` and camel case are both word boundaries in
    the wild: Claude Code stores its OAuth tokens as `accessToken` and
    `refreshToken`, which matched nothing while the set held `access_token`.
    """
    folded = _fold_key(name)
    return folded in SECRET_KEYS or folded.rsplit(".", 1)[-1] in SECRET_KEYS


def record_backup(
    connection: sqlite3.Connection,
    *,
    harness_id: str,
    target_id: str,
    provider_ref: str,
    at: str,
) -> BackupRef:
    """Record where the provider put the old bytes (`REQ-807`, `REQ-814`).

    A reference, never the bytes. Copying them would give one recovery two
    owners, and the provider's is the one that can actually restore.
    """
    if not provider_ref:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "an import needs the provider's backup reference before anything is registered",
            details={"harness_id": harness_id},
            # A command, not a sentence. `next_actions` is read by an agent that
            # runs what it finds there, and "run the provider's backup command"
            # is advice it has no way to follow.
            next_actions=["setup import register --backup-ref <ref from the provider> --json"],
        )
    backup_id = new_id("backup")
    connection.execute(
        """
        INSERT INTO backup_ref (backup_id, harness_id, target_id, provider_ref, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (backup_id, harness_id, target_id, provider_ref, at),
    )
    return BackupRef(backup_id, harness_id, target_id, provider_ref, at)


def backup(connection: sqlite3.Connection, backup_id: str) -> BackupRef | None:
    row = connection.execute(
        "SELECT * FROM backup_ref WHERE backup_id = ?", (backup_id,)
    ).fetchone()
    if row is None:
        return None
    return BackupRef(
        backup_id=str(row["backup_id"]),
        harness_id=str(row["harness_id"]),
        target_id=str(row["target_id"]),
        provider_ref=str(row["provider_ref"]),
        created_at=str(row["created_at"]),
    )


def register(
    connection: sqlite3.Connection,
    inspection: Inspection,
    *,
    backup_id: str,
    owner_id: str,
    device_id: str,
    at: str,
    plan_digest: str = "",
    components: list[dict[str, JsonValue]] | None = None,
    operation_id: str | None = None,
) -> Imported:
    """Register the inspected configuration as the user's own setup.

    Everything or nothing: the passport, its exact file hashes and its
    provenance are one transaction, because a setup recorded without the hashes
    it was made from is a setup nobody can verify against its source.

    The backup must already exist. `REQ-813` puts the provider's backup before
    registration, and taking a reference to something that was never made would
    record a recovery path that does not exist.
    """
    held = backup(connection, backup_id)
    if held is None:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "no backup with that identifier was recorded",
            details={"backup_id": backup_id},
        )
    if held.harness_id != inspection.harness_id:
        raise CliFailure(
            "AI_STP_CONFLICT",
            "that backup is for another harness",
            details={"backup": held.harness_id, "inspection": inspection.harness_id},
        )
    if not inspection.findings:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "there is nothing to import from an empty configuration",
            details={"root": inspection.root},
        )
    unreadable = inspection.unreadable
    if unreadable:
        # A setup registered from files nobody could read would claim to
        # describe a configuration it has not seen.
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "some files could not be read, so this configuration is not fully described",
            details={"unreadable": ", ".join(unreadable)},
        )

    own_operation = operation_id is None
    if operation_id is None:
        operation_id = journal.begin(connection, "setup.import", at)
    try:
        with transaction(connection):
            stable_id = new_id("setup")
            stored = revisions.commit(
                connection,
                _graph_content(
                    inspection,
                    stable_id,
                    held,
                    owner_id,
                    plan_digest,
                    components or [],
                    at,
                )
                if plan_digest
                else _content(inspection, stable_id, held, owner_id, at),
                device_id=device_id,
                operation_id=operation_id,
            )
    except BaseException as error:
        if own_operation:
            journal.settle(connection, operation_id, "failed", at, type(error).__name__)
        raise
    if own_operation:
        journal.settle(connection, operation_id, "verified", at)
    return Imported(stable_id=stable_id, revision_id=stored.revision_id, backup_id=backup_id)


def register_graph(
    connection: sqlite3.Connection,
    inspection: Inspection,
    *,
    expected_plan_digest: str,
    target_id: str,
    provider_ref: str,
    owner_id: str,
    device_id: str,
    at: str,
) -> Imported:
    """Atomically materialize the exact confirmed import plan.

    The plan is rebuilt from the second inspection supplied by the command.
    Confirmation therefore applies only while every observed byte still has
    the digest the user reviewed. Backup identity, component artifacts,
    component passports and the setup graph commit together or not at all.
    """
    proposed = plan(inspection)
    if proposed.plan_digest != expected_plan_digest:
        raise CliFailure(
            "AI_STP_CONFLICT",
            "the native configuration changed after the import plan was reviewed",
            details={"expected": expected_plan_digest, "found": proposed.plan_digest},
            next_actions=[
                "setup import plan "
                f"--root {inspection.root} --harness {inspection.harness_id} --json"
            ],
        )
    if proposed.blocked_by:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the confirmed import plan still has blocking files",
            details={"blocked_by": ", ".join(proposed.blocked_by)},
        )
    if not proposed.components:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "there are no component drafts in this import plan",
            details={"root": inspection.root},
        )

    operation_id = journal.begin(connection, "setup.import.graph", at)
    try:
        with transaction(connection):
            held = record_backup(
                connection,
                harness_id=inspection.harness_id,
                target_id=target_id,
                provider_ref=provider_ref,
                at=at,
            )
            components: list[dict[str, JsonValue]] = []
            component_ids: list[str] = []
            by_path = {item.path: item for item in inspection.findings}
            root = Path(inspection.root)
            for candidate in proposed.components:
                packaged: list[JsonValue] = []
                for relative in candidate.paths:
                    raw = (root / relative).read_bytes()
                    if content.address_of(raw) != by_path[relative].digest:
                        raise CliFailure(
                            "AI_STP_CONFLICT",
                            "a native file changed while the import was being registered",
                            details={"path": relative},
                        )
                    cleaned, _names = scrub(raw)
                    packaged.append(
                        {"path": relative, "content_base64": b64encode(cleaned).decode("ascii")}
                    )
                artifact_bytes = json.dumps(
                    {"format": "ai-stp-imported-component/1", "files": packaged},
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                artifact = content.put(connection, artifact_bytes, at=at)
                component_id = new_id("component")
                stored = revisions.commit(
                    connection,
                    _component_content(
                        inspection,
                        candidate,
                        component_id,
                        artifact.digest,
                        artifact.byte_length,
                        owner_id,
                        at,
                    ),
                    device_id=device_id,
                    operation_id=operation_id,
                )
                component_ids.append(component_id)
                components.append(
                    {
                        "stable_id": component_id,
                        "revision_id": stored.revision_id,
                        "candidate_id": candidate.candidate_id,
                        "artifact_digest": artifact.digest,
                    }
                )

            imported = register(
                connection,
                inspection,
                backup_id=held.backup_id,
                owner_id=owner_id,
                device_id=device_id,
                at=at,
                plan_digest=proposed.plan_digest,
                components=components,
                operation_id=operation_id,
            )
    except BaseException as error:
        journal.settle(connection, operation_id, "failed", at, type(error).__name__)
        raise
    journal.settle(connection, operation_id, "verified", at)
    return Imported(
        stable_id=imported.stable_id,
        revision_id=imported.revision_id,
        backup_id=held.backup_id,
        plan_digest=proposed.plan_digest,
        component_ids=tuple(component_ids),
    )


def _component_content(
    inspection: Inspection,
    candidate: ProposedComponent,
    stable_id: str,
    artifact_digest: str,
    artifact_size: int,
    owner_id: str,
    at: str,
) -> dict[str, JsonValue]:
    facts = {
        "component_type": _fact(candidate.component_type, at),
        "native_role": _fact(candidate.native_role, at),
        "harness_id": _fact(inspection.harness_id, at),
        "source_root": _fact(inspection.root, at),
        "source_paths": _fact(list(candidate.paths), at),
        "candidate_id": _fact(candidate.candidate_id, at),
        "file_set_digest": _fact(candidate.file_set_digest, at),
        "content_format": _fact("ai-stp-imported-component/1", at),
        "content_digest": _fact(artifact_digest, at),
        "byte_length": _fact(artifact_size, at),
    }
    return {
        "schema_version": 1,
        "kind": "component",
        "stable_id": stable_id,
        "owner_id": owner_id,
        "created_at": at,
        "visibility": "private",
        "parent_revision_ids": [],
        "facts": facts,
    }


def _graph_content(
    inspection: Inspection,
    stable_id: str,
    held: BackupRef,
    owner_id: str,
    plan_digest: str,
    components: list[dict[str, JsonValue]],
    at: str,
) -> dict[str, JsonValue]:
    document = _content(inspection, stable_id, held, owner_id, at)
    facts = cast(dict[str, JsonValue], document["facts"])
    facts["plan_digest"] = _fact(plan_digest, at)
    facts["components"] = _fact(cast(list[JsonValue], components), at)
    return document


def _content(
    inspection: Inspection,
    stable_id: str,
    held: BackupRef,
    owner_id: str,
    at: str,
) -> dict[str, JsonValue]:
    """The imported setup's passport, built by naming every field it may hold.

    A whitelist and not a filter: the one thing this passport must never carry
    is a secret value, and a filter has to be right about every field somebody
    adds later.
    """
    files: list[JsonValue] = [
        {"path": item.path, "digest": item.digest, "byte_length": item.byte_length}
        for item in inspection.findings
    ]
    facts: dict[str, JsonValue] = {
        "harness_id": _fact(inspection.harness_id, at),
        "origin": _fact("imported", at),
        # Provenance: where these bytes came from, so the setup can be checked
        # against its source rather than taken on trust.
        "source_root": _fact(inspection.root, at),
        "files": _fact(files, at),
        # A reference to a separate object (`REQ-814`), never its identity.
        "backup_id": _fact(held.backup_id, at),
        # `REQ-815`: names, and only names.
        "redacted_keys": _fact(list(inspection.redacted_keys), at),
        "detection_rule": _fact(inspection.detection_rule, at),
    }
    return {
        "schema_version": 1,
        "kind": "setup",
        "stable_id": stable_id,
        "owner_id": owner_id,
        "created_at": at,
        # Private, always. An imported setup is somebody's working machine and
        # publishing it is a separate decision nobody has made here.
        "visibility": "private",
        "parent_revision_ids": [],
        "facts": facts,
    }


def _walk(value: object, names: set[str], prefix: str = "") -> JsonValue:
    """Rewrite a decoded document, removing values under credential keys."""
    if isinstance(value, dict):
        cleaned: dict[str, JsonValue] = {}
        for key, item in cast(dict[object, object], value).items():
            name = str(key)
            path = f"{prefix}.{name}" if prefix else name
            if is_secret_key(name):
                names.add(path)
                cleaned[name] = REDACTED
                continue
            cleaned[name] = _walk(item, names, path)
        return cleaned
    if isinstance(value, list):
        held = cast(list[object], value)
        return [_walk(item, names, f"{prefix}[]") for item in held]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def _fact(value: JsonValue, at: str) -> JsonValue:
    return {"value": value, "origin": "observed", "confirmation": "none", "observed_at": at}
