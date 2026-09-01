"""`ai-stp doctor` — the setup state, reported rather than judged (issue #72).

`doctor` exits `0` even when the installation is not ready. An installation that
has merely not been set up yet is the normal state right after `uv tool install`,
and answering non-zero would make the first run look broken and break any caller
running under `set -e`. The state is in the body, where a reader can act on it;
`SPEC-011` names the four values.

A non-zero exit is reserved for `doctor` itself failing — the difference between
"I looked and you are not ready" and "I could not look".
"""

import shutil
import sqlite3
import sys
from collections.abc import Mapping, Sequence
from contextlib import closing
from pathlib import Path
from typing import Final

from ai_stp_cli import config, identity, paths, secrets
from ai_stp_cli.answer import Answer
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import components, database, journal, passports, revisions
from ai_stp_contracts.machine_help import DoctorCheck, DoctorReport, SetupState

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
            state="needs_user_action",
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
    """Name the tool `provider fetch` shells out to, before it is needed.

    Installing a published setup goes through `provider fetch`, which binds an
    attested OpenNetwork release by running `gh attestation verify`. The shipped
    policy pins no bytes and allows no publisher, so that binding is the only
    path an install takes — and `gh` is not a dependency of this package. On a
    machine installed from PyPI there is no reason for it to be present.

    The refusal when it is absent is honest (`AI_STP_DEPENDENCY_UNAVAILABLE`
    with `dependency: gh`), but it arrives after an agent has already chosen to
    install. This is the same shape as `composition_passports`, and it takes the
    same answer: an installation without `gh` is still sound, and somebody who
    only searches the catalogue never needs it, so the state stays `ready` and
    the detail carries the fact (`SPEC-011` `REQ-1124`).

    Presence only. Running `gh` to ask its version would make a command declared
    `read` execute a third-party binary, and diagnostics do not do that.
    """
    found = shutil.which("gh")
    if found is None:
        return DoctorCheck(
            name="provider_binding",
            state="ready",
            detail="`gh` is not on PATH; `provider fetch` needs it to verify an "
            "attested provider release before binding it",
        )
    return DoctorCheck(
        name="provider_binding",
        state="ready",
        detail=f"`gh` at {paths.redact_home(Path(found))}; `provider fetch` uses it to verify "
        "an attested provider release",
    )


def run(_parameters: Mapping[str, object]) -> Answer[DoctorReport]:
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
        _provider_binding_check(),
    ]
    return Answer(DoctorReport(state=worst([check.state for check in checks]), checks=checks))
