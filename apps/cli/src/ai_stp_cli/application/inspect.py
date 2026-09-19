"""Cheap local inspection. Expert commands and the inspect task share this."""

import shutil
import sqlite3
import sys
from collections.abc import Sequence
from contextlib import closing
from pathlib import Path
from typing import Final

from ai_stp_cli import config, identity, paths, secrets
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import components, database, journal, passports, revisions
from ai_stp_cli.runtime import cli_version, installation
from ai_stp_contracts.machine_help import (
    Capabilities,
    DoctorCheck,
    DoctorReport,
    SetupState,
    TaskIntentDescriptor,
    TaskIntentsCatalog,
    TaskOrientation,
)
from ai_stp_foundation.harnesses import HARNESS_IDS

SHIPPED_INTENT_NAMES: Final[tuple[str, ...]] = (
    "inspect",
    "initialize",
    "install",
    "change",
    "author",
    "switch",
    "account",
    "publish",
)
INSPECT_WHEN: Final[str] = (
    "Call when the user asks what is wrong or what this CLI can do. "
    "Do not call as a prelude to every mutation."
)
INSPECT_INPUT_SCHEMA: Final[str] = "urn:ai-stp:schema:v1:cli-task-input-inspect"
INITIALIZE_WHEN: Final[str] = (
    "Call on first run, or when the user says ai-stp is missing from this harness. "
    "Do not call as a prelude to every coding request. "
    "provider-too-old is not login: report it and stop; do not start account."
)
INITIALIZE_INPUT_SCHEMA: Final[str] = "urn:ai-stp:schema:v1:cli-task-input-initialize"
INSTALL_WHEN: Final[str] = (
    "Call when the user wants a catalog or local setup on a target. "
    "Do not choreograph plan, approve, or apply yourself."
)
INSTALL_INPUT_SCHEMA: Final[str] = "urn:ai-stp:schema:v1:cli-task-input-install"
CHANGE_WHEN: Final[str] = (
    "Call when the user wants to add or remove a member of a saved setup. "
    "Do not compose in place and do not type setup compose plan or apply."
)
CHANGE_INPUT_SCHEMA: Final[str] = "urn:ai-stp:schema:v1:cli-task-input-change"
AUTHOR_WHEN: Final[str] = (
    "Call when the user wants to register a local directory as a component. "
    "Do not type component adopt, component scaffold, or setup compose apply."
)
AUTHOR_INPUT_SCHEMA: Final[str] = "urn:ai-stp:schema:v1:cli-task-input-author"
SWITCH_WHEN: Final[str] = (
    "Call when the user wants the last working user config back. "
    "Do not type setup restore plan or setup preserve plan, and do not kill the caller."
)
SWITCH_INPUT_SCHEMA: Final[str] = "urn:ai-stp:schema:v1:cli-task-input-switch"
ACCOUNT_WHEN: Final[str] = (
    "Call when the user says sign in, sign out, or explicitly sync. "
    "Login never uploads. Do not type auth login or auth complete. "
    "Do not call for provider-too-old."
)
ACCOUNT_INPUT_SCHEMA: Final[str] = "urn:ai-stp:schema:v1:cli-task-input-account"
PUBLISH_WHEN: Final[str] = (
    "Call when the user wants to publish a local object. "
    "Do not type publication plan or publication confirm, and do not invent git provenance."
)
PUBLISH_INPUT_SCHEMA: Final[str] = "urn:ai-stp:schema:v1:cli-task-input-publish"


def capabilities() -> Capabilities:
    """What this process can do right now, without a registry dump."""
    from ai_stp_cli.application.inventory import classified_paths, classify, expert_reason
    from ai_stp_cli.application.qualify import report
    from ai_stp_cli.registry import command_paths, registry_digest

    classified_paths()
    for path in (tuple(item.split()) for item in command_paths()):
        if classify(path) == "expert":
            expert_reason(path)
    report()
    catalog_enabled, sync_enabled = config.catalog_and_sync_enabled()
    return Capabilities(
        cli_version=cli_version(),
        installation=installation(),
        registry_digest=registry_digest(),
        local_schema_version=database.SCHEMA_VERSION,
        supported_harnesses=sorted(HARNESS_IDS),
        catalog_enabled=catalog_enabled,
        sync_enabled=sync_enabled,
        command_paths=command_paths(),
    )


def orientation() -> TaskOrientation:
    """Inspect-sized orientation: no command_paths."""
    from ai_stp_cli.registry import registry_digest

    catalog_enabled, sync_enabled = config.catalog_and_sync_enabled()
    return TaskOrientation(
        cli_version=cli_version(),
        installation=installation(),
        registry_digest=registry_digest(),
        local_schema_version=database.SCHEMA_VERSION,
        supported_harnesses=sorted(HARNESS_IDS),
        catalog_enabled=catalog_enabled,
        sync_enabled=sync_enabled,
        intents=list(SHIPPED_INTENT_NAMES),
    )


def intent_catalog() -> TaskIntentsCatalog:
    """Shipped intents only. Unknown names are not advertised."""
    from ai_stp_cli.registry import registry_digest

    return TaskIntentsCatalog(
        cli_version=cli_version(),
        registry_digest=registry_digest(),
        intents=[
            TaskIntentDescriptor(
                name="inspect",
                when=INSPECT_WHEN,
                input_schema=INSPECT_INPUT_SCHEMA,
            ),
            TaskIntentDescriptor(
                name="initialize",
                when=INITIALIZE_WHEN,
                input_schema=INITIALIZE_INPUT_SCHEMA,
            ),
            TaskIntentDescriptor(
                name="install",
                when=INSTALL_WHEN,
                input_schema=INSTALL_INPUT_SCHEMA,
            ),
            TaskIntentDescriptor(
                name="change",
                when=CHANGE_WHEN,
                input_schema=CHANGE_INPUT_SCHEMA,
            ),
            TaskIntentDescriptor(
                name="author",
                when=AUTHOR_WHEN,
                input_schema=AUTHOR_INPUT_SCHEMA,
            ),
            TaskIntentDescriptor(
                name="switch",
                when=SWITCH_WHEN,
                input_schema=SWITCH_INPUT_SCHEMA,
            ),
            TaskIntentDescriptor(
                name="account",
                when=ACCOUNT_WHEN,
                input_schema=ACCOUNT_INPUT_SCHEMA,
            ),
            TaskIntentDescriptor(
                name="publish",
                when=PUBLISH_WHEN,
                input_schema=PUBLISH_INPUT_SCHEMA,
            ),
        ],
    )


#: Worst-first, so the overall state is the worst individual one. A report whose
#: summary said `ready` while a check said `failed` would be read by exactly the
#: callers who only read the summary.
_SEVERITY: Final[tuple[SetupState, ...]] = ("failed", "partial", "needs_user_action", "ready")

MINIMUM_PYTHON: Final[tuple[int, int]] = (3, 12)


def _python_check() -> DoctorCheck:
    current = sys.version_info[:2]
    if current < MINIMUM_PYTHON:
        return DoctorCheck(
            name="python_runtime",
            state="failed",
            detail=f"needs {MINIMUM_PYTHON[0]}.{MINIMUM_PYTHON[1]} or newer",
        )
    return DoctorCheck(name="python_runtime", state="ready", detail=f"{current[0]}.{current[1]}")


def _config_check() -> DoctorCheck:
    path = config.config_path()
    if path.exists():
        # Reading it is the check: a file that cannot be parsed is a real
        # problem, and reporting "present" without looking would hide it.
        config.effective_config()
        return DoctorCheck(name="configuration", state="ready", detail="read from file")
    return DoctorCheck(
        name="configuration",
        state="ready",
        detail="no file; defaults are a complete configuration",
    )


def _registry_check() -> DoctorCheck:
    """Look at the registry without opening it read-write.

    `doctor` is declared `read`, and opening the registry applies pending
    migrations — a write. So this reports what can be seen from the file itself,
    and the schema version comes from the header rather than from a connection
    that would upgrade it.
    """
    report = config.effective_config()
    location = next(value for value in report.values if value.path == "registry.path")
    path = Path(str(location.value))
    if not path.exists():
        return DoctorCheck(
            name="local_registry",
            state="needs_user_action",
            detail="not created yet",
        )
    if not paths.is_private(path):
        return DoctorCheck(
            name="local_registry",
            state="failed",
            detail="readable by more than its owner",
        )
    try:
        found = database.file_schema_version(path)
    except sqlite3.Error as error:
        # `#74`: a corrupt database fails typed and is left intact. A diagnostic
        # that crashes on the thing it is diagnosing is the least useful moment
        # to crash.
        return DoctorCheck(
            name="local_registry",
            state="failed",
            detail=f"present but unreadable: {type(error).__name__}",
        )
    if found > database.SCHEMA_VERSION:
        return DoctorCheck(
            name="local_registry",
            state="failed",
            detail=f"written by a newer build: schema {found}, this build supports "
            f"{database.SCHEMA_VERSION}",
        )
    if found < database.SCHEMA_VERSION:
        return DoctorCheck(
            name="local_registry",
            state="ready",
            detail=f"schema {found}; the next write migrates it to {database.SCHEMA_VERSION}",
        )
    return DoctorCheck(name="local_registry", state="ready", detail="present")


def _catalog_check() -> DoctorCheck:
    enabled, _sync = config.catalog_and_sync_enabled()
    if not enabled:
        return DoctorCheck(
            name="catalog",
            state="ready",
            detail="disabled; offline operation is a supported configuration",
        )
    return DoctorCheck(name="catalog", state="ready", detail="enabled")


def _credential_store_check() -> DoctorCheck:
    """Name the tier secrets actually use, never assume the preferred one.

    `ADR-0058` makes the tier part of the answer rather than a log line. The
    file tier is `ready`, not a degradation to complain about: it is a supported
    configuration and the only one available over SSH or in a container. What
    would be wrong is not saying which one is in use.
    """
    # `open_store` runs the same ephemeral read/write/delete probe as every
    # command that stores a secret; backend selection alone misses a keyring
    # that can read but cannot write, which is the failure this check exists to
    # expose.
    store, _warning = secrets.open_store()
    return DoctorCheck(name="credential_store", state="ready", detail=store.detail)


def _device_identity_check() -> DoctorCheck:
    """Report the identity without creating one.

    `doctor` observes; creating an identity here would make a diagnostic command
    change state, and `#72` fixed its mutability class as `read`.
    """
    if not paths.device_file().exists():
        return DoctorCheck(
            name="device_identity",
            state="needs_user_action",
            detail="not created yet; the first device command creates it",
        )
    try:
        current, _warning = identity.load_or_create()
    except CliFailure as failure:
        return DoctorCheck(name="device_identity", state="failed", detail=failure.message)
    if current.state == "revoked":
        return DoctorCheck(
            name="device_identity",
            state="needs_user_action",
            detail="revoked; cloud work needs a new identity",
        )
    return DoctorCheck(name="device_identity", state="ready", detail=current.device_id)


def _permissions_check() -> DoctorCheck:
    """Every file this installation owns must be readable only by its owner.

    A file whose mode widened after it was written is the failure this catches;
    `paths.write_private` makes it impossible to create one, but not impossible
    for someone to `chmod` it later.
    """
    if not paths.POSIX:  # pragma: no cover - the coverage leg is Linux; Windows asserts this
        return DoctorCheck(
            name="file_permissions",
            state="ready",
            detail="access is governed by the platform ACL, not by POSIX modes",
        )
    exposed = [
        paths.redact_home(path)
        for path in (paths.device_file(), *sorted(paths.secrets_dir().glob("*.secret")))
        if path.exists() and not paths.is_private(path)
    ]
    if exposed:
        return DoctorCheck(
            name="file_permissions",
            state="failed",
            detail=f"readable by more than the owner: {', '.join(exposed)}",
        )
    return DoctorCheck(name="file_permissions", state="ready", detail="owner-only")


def _interrupted_operations_check() -> DoctorCheck:
    """Report local mutations that started and never said how they ended.

    This is what the operation journal is for. Writing entries nobody surfaces
    would make it write-only, and after an interrupted run these are exactly the
    entries worth looking at — `applied_unverified` most of all, because it
    means the effect may have landed and the check never ran.
    """
    path = database.configured_path()
    if not path.exists():
        return DoctorCheck(
            name="interrupted_operations", state="ready", detail="no local registry yet"
        )
    try:
        # Read-only on purpose: opening the registry the normal way applies
        # pending migrations, and `doctor` is declared `read`. Getting this
        # wrong once was enough.
        with closing(database.open_readonly(path)) as connection:
            pending = journal.unsettled(connection)
    except (CliFailure, sqlite3.Error) as failure:
        return DoctorCheck(
            name="interrupted_operations", state="failed", detail=type(failure).__name__
        )
    if not pending:
        return DoctorCheck(name="interrupted_operations", state="ready", detail="none")
    return DoctorCheck(
        name="interrupted_operations",
        state="needs_user_action",
        detail=f"{len(pending)} unfinished: " + ", ".join(f"{i.kind} ({i.state})" for i in pending),
    )


def _needed(kinds: Sequence[str]) -> str:
    """Name the creating commands, read from their single owner."""
    return ", ".join(f"`{passports.CREATES_PASSPORT[kind]}`" for kind in kinds)


def _composition_passports_check() -> DoctorCheck:
    """Say what composing would additionally need, without narrowing `ready`.

    `#356`: `doctor` answered `ready` on an installation where `select propose`
    had just refused, because the composition anchors — the developer and device
    passports — were absent. Nine green checks, and nothing named the thing that
    would refuse.

    The obvious patch is a check that turns the report
    `needs_user_action` while they are missing. That is rejected, and the reason
    is recorded rather than left to be rediscovered: somebody who only searches
    the catalogue and installs never needs either passport, and reporting every
    such installation as needing action would make the state word useless for
    the callers who read only the summary. `ready` continues to mean the
    installation is sound.

    So the state stays `ready` in both cases and the detail carries the fact.
    A machine caller that branches on `state` is unaffected; one that wants to
    know before composing can read this line instead of discovering it from a
    refusal. `SPEC-011` `REQ-1119` owns that distinction.
    """
    path = database.configured_path()
    if not path.exists():
        return DoctorCheck(
            name="composition_passports",
            state="ready",
            detail="no local registry yet; composing needs "
            + _needed(passports.COMPOSITION_PASSPORT_KINDS),
        )
    try:
        with closing(database.open_readonly(path)) as connection:
            missing = [
                kind
                for kind, stable_id in (
                    ("developer", passports.developer_stable_id(connection)),
                    ("device", passports.device_stable_id(connection)),
                )
                if stable_id is None or revisions.head(connection, stable_id) is None
            ]
    except (CliFailure, sqlite3.Error) as failure:
        return DoctorCheck(
            name="composition_passports", state="failed", detail=type(failure).__name__
        )
    if not missing:
        return DoctorCheck(
            name="composition_passports",
            state="ready",
            detail="developer and device passports recorded",
        )
    return DoctorCheck(
        name="composition_passports",
        state="ready",
        detail=f"installing and searching are unaffected; composing needs {_needed(missing)}",
    )


def worst(states: list[SetupState]) -> SetupState:
    """The worst state present, or `ready` when nothing is wrong."""
    for candidate in _SEVERITY:
        if candidate in states:
            return candidate
    return "ready"


def _component_layout_check() -> DoctorCheck:
    """Whether the declared native-component layouts are internally sound.

    A build-time fact rather than a machine one, and it is here because a broken
    table is invisible everywhere else: a rule naming a harness no detector
    knows would simply never match, and discovery would report one fewer kind
    without anything saying why.
    """
    problems = components.declared_consistently()
    if not problems:
        return DoctorCheck(
            name="component_layouts",
            state="ready",
            detail=f"{len(components.GLOBAL_RULES) + len(components.PROJECT_RULES)} declared",
        )
    return DoctorCheck(name="component_layouts", state="failed", detail="; ".join(problems))


def _provider_binding_check() -> DoctorCheck:
    """Describe default index acquisition and the optional GitHub transport."""
    found = shutil.which("gh")
    github = "not on PATH" if found is None else f"at {paths.redact_home(Path(found))}"
    return DoctorCheck(
        name="provider_binding",
        state="ready",
        detail="`provider fetch` defaults to PyPI with the CLI-managed uv verifier; "
        f"no standalone verifier is required. Explicit GitHub acquisition uses `gh` ({github})",
    )


def _cli_update_check() -> DoctorCheck:
    """Journal and check cache only. A down index is not a failed installation."""
    from ai_stp_cli.self_update import store
    from ai_stp_cli.self_update.method import current_installation

    try:
        journal = store.read_json(store.journal_path()) or {}
        state = str(journal.get("state") or "idle")
        if state in {"applying", "pending", "recovery_required", "failed"}:
            return DoctorCheck(
                name="cli_update",
                state="needs_user_action",
                detail=(
                    f"CLI update journal is {state}; run update recover --json or "
                    "update status --json"
                ),
            )
        held = current_installation()
        if held.method == "source_managed":
            return DoctorCheck(
                name="cli_update",
                state="ready",
                detail="source-managed installation; wheel replacement is refused",
            )
        cache = store.read_json(store.cache_path())
        if isinstance(cache, dict) and cache.get("state") == "available":
            version = str(cache.get("candidate_version") or "")
            return DoctorCheck(
                name="cli_update",
                state="needs_user_action",
                detail=f"a newer CLI {version} is cached; run update plan --json",
            )
        return DoctorCheck(name="cli_update", state="ready", detail="no interrupted CLI update")
    except Exception as failure:
        return DoctorCheck(
            name="cli_update",
            state="ready",
            detail=f"updater journal unread ({type(failure).__name__})",
        )


def _addressable_objects_check() -> DoctorCheck:
    """Entities with no head revision: registered, and reachable by no command.

    Every command that shows, edits, releases or forgets an object reaches it
    through its head revision, so an entity minted without one is addressable by
    nothing at all — `show` says it has no passport, `forget` says the same, and
    the row stays in the registry forever. Two producers made them before
    2026-09-01: `component fork` wrote an entity and its origin without a first
    revision, and a bundle probe that failed between the mint and the write. Both
    are closed; the rows they left are not.

    Reported rather than repaired, and `ready` rather than `partial`, for the
    reason `composition_passports` gives: the installation is sound, nothing a
    caller does is affected, and a summary word that goes yellow for a harmless
    leftover stops carrying information. Deleting them belongs to a command the
    owner runs, not to a diagnostic — `doctor` is declared `read`, and a
    read-only command that mutates local state is a defect this estate has
    already paid for.
    """
    path = database.configured_path()
    if not path.exists():
        return DoctorCheck(
            name="addressable_objects", state="ready", detail="no local registry yet"
        )
    try:
        with closing(database.open_readonly(path)) as connection:
            rows = connection.execute(
                """
                SELECT entity.stable_id, entity.kind
                FROM entity
                LEFT JOIN head ON head.stable_id = entity.stable_id
                WHERE head.stable_id IS NULL
                ORDER BY entity.created_at
                """
            ).fetchall()
    except (CliFailure, sqlite3.Error) as failure:
        return DoctorCheck(
            name="addressable_objects", state="failed", detail=type(failure).__name__
        )
    if not rows:
        return DoctorCheck(
            name="addressable_objects", state="ready", detail="every object has a head revision"
        )
    kinds = sorted({str(row[1]) for row in rows})
    return DoctorCheck(
        name="addressable_objects",
        state="ready",
        detail=(
            f"{len(rows)} object(s) hold no head revision and no command can reach them "
            f"({', '.join(kinds)}); they are inert leftovers of producers closed on 2026-09-01"
        ),
    )


def doctor() -> DoctorReport:
    """Look at everything this build can look at, and say what was found."""
    checks = [
        _python_check(),
        _config_check(),
        _registry_check(),
        _catalog_check(),
        _credential_store_check(),
        _device_identity_check(),
        _permissions_check(),
        _interrupted_operations_check(),
        _component_layout_check(),
        _composition_passports_check(),
        _addressable_objects_check(),
        _provider_binding_check(),
        _cli_update_check(),
    ]
    return DoctorReport(state=worst([check.state for check in checks]), checks=checks)
