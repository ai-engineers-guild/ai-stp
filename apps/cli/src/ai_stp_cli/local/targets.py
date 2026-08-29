"""The daily state of one project-and-harness pair (`#177`, `SPEC-008`).

Four situations that look alike from a distance and need completely different
answers. `REQ-818` names local drift and forbids fixing it automatically;
`REQ-816` and `REQ-820` make a missing variable or an unfinished authorization
a readiness state rather than a failure; `selection-proposal.md` makes the window
between selected and installed ordinary.

**Every applicable state is reported, not the first one found.** A target can be
waiting to install *and* missing a variable, and answering only the first would
send somebody to fix one thing and meet the other immediately afterwards.

**Nothing updates by itself.** `catalog_drift` is a fact about the catalogue, and
this module reports it and stops. `REQ-817` gives the harness lifecycle to the
provider and `#177` says in as many words that there is no automatic update — so
there is no function here that installs anything, and the update path is an
ordinary plan with an ordinary approval.

**Rollback names an exact previous version or refuses.** It is read from the
operation log, which records which setup version was verified on which target,
in order. "Previous" means the state verified immediately before the current;
undoing a rollback can therefore raise a version number without changing the
direction of history.
"""

import sqlite3
from dataclasses import dataclass
from typing import Final, Literal, cast

from pydantic import ValidationError

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import cache, installation, revisions, selection, versions
from ai_stp_cli.provider.status import AuthorizationEvidence
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.versioning import VersionError, compare_versions
from ai_stp_passports import SetupVersionPassport

#: A version is selected and the provider has not verified it yet. Ordinary, and
#: explicitly not a drift.
STATE_PENDING_INSTALL: Final[str] = "pending_install"

#: The target changed outside the provider's lifecycle (`REQ-818`). Never fixed
#: automatically: whatever changed it may have had a reason.
STATE_LOCAL_DRIFT: Final[str] = "local_drift"

#: A newer version exists than the one selected. A fact, never an instruction.
STATE_CATALOG_DRIFT: Final[str] = "catalog_drift"

#: Something must be configured before this can run (`REQ-816`, `REQ-820`).
STATE_NEEDS_CONFIGURATION: Final[str] = "needs_configuration"

#: Nothing to say: selected, verified, unchanged and configured.
STATE_INSTALLED: Final[str] = "installed"

#: Nothing has been chosen for this pair, so there is no target to have a state.
#: Named rather than answered with an empty list: an empty list reads as "no
#: problems", and "no target" is a different thing entirely.
STATE_NOT_SELECTED: Final[str] = "not_selected"

STATES: Final[frozenset[str]] = frozenset(
    {
        STATE_PENDING_INSTALL,
        STATE_LOCAL_DRIFT,
        STATE_CATALOG_DRIFT,
        STATE_NEEDS_CONFIGURATION,
        STATE_INSTALLED,
        STATE_NOT_SELECTED,
    }
)


@dataclass(frozen=True)
class Verified:
    """One setup version that a provider verified on this target."""

    operation_id: str
    setup_stable_id: str
    setup_version: str
    target_digest: str
    at: str


@dataclass(frozen=True)
class Backup:
    """One provider-owned copy of a target, named by the reference that restores it."""

    backup_ref: str
    operation_id: str
    setup_stable_id: str
    setup_version: str
    provider_target: str
    created_at: str


@dataclass(frozen=True)
class Survey:
    """What one pair looks like today, and every reason it is not simply fine."""

    project_id: str
    harness_id: str

    selected_stable_id: str = ""
    selected_version: str = ""
    installed_stable_id: str = ""
    installed_version: str = ""

    #: What the target read at the last verified install, and what it reads now.
    #: Both, because a difference is the whole of what local drift means and one
    #: of them alone cannot express it.
    verified_target_digest: str = ""
    observed_target_digest: str = ""

    #: Names only. `REQ-1108` keeps values out of every path an agent reaches.
    missing_env: tuple[str, ...] = ()
    pending_authorization: str = ""

    #: The newest version the catalogue knows of, when anything is known. Empty
    #: means nobody asked, which is not the same as "there is nothing newer".
    catalog_version: str = ""

    @property
    def states(self) -> tuple[str, ...]:
        """Every applicable state, in the order `#177` names them.

        A tuple rather than one value: a pair can be waiting to install *and*
        missing a variable, and picking one would send somebody to fix a thing
        and meet the other immediately after.
        """
        if not self.selected_version and not self.installed_version:
            return (STATE_NOT_SELECTED,)

        found: list[str] = []
        if self.selected_version and (
            self.selected_version != self.installed_version
            or self.selected_stable_id != self.installed_stable_id
        ):
            found.append(STATE_PENDING_INSTALL)
        if (
            self.verified_target_digest
            and self.observed_target_digest
            and self.verified_target_digest != self.observed_target_digest
        ):
            found.append(STATE_LOCAL_DRIFT)
        if _catalog_is_newer(self.catalog_version, self.selected_version):
            found.append(STATE_CATALOG_DRIFT)
        if self.missing_env or self.pending_authorization:
            found.append(STATE_NEEDS_CONFIGURATION)
        return tuple(found) if found else (STATE_INSTALLED,)


@dataclass(frozen=True)
class SetupRequirements:
    """Readiness requirements from one exact immutable SetupVersion."""

    required_env: tuple[str, ...] = ()
    requires_authorization: Literal["none", "user_account", "external_service"] = "none"

    #: What the setup says it does, in its own words. Carried to the approval
    #: point because a plan enumerates the *files* a provider will write and
    #: never what changing them means — and for at least one published setup
    #: that meaning is the whole content. `full-auto` turns off a product's
    #: sandbox and its prompting, and 690 characters of its description say
    #: which parts of that claim hold on which platform. The listing card
    #: clamps to two lines and cannot install from there; the CLI, which is the
    #: primary consumer, showed none of it at all.
    name: str = ""
    description: str = ""


def survey(
    connection: sqlite3.Connection,
    *,
    project_id: str,
    harness_id: str,
    observed_target_digest: str = "",
    present_env: frozenset[str] = frozenset(),
    additional_required_env: tuple[str, ...] = (),
    authorization_evidence: AuthorizationEvidence | None = None,
    catalog_version: str = "",
) -> Survey:
    """Read the pair's state. Reads, and changes nothing at all.

    The observed digest is passed in rather than fetched: only the provider can
    say what its target is, and asking it from here would put a subprocess call
    inside a status read.
    """
    pinned = selection.selected(connection, project_id=project_id, harness_id=harness_id)
    history = verified(connection, project_id=project_id, harness_id=harness_id)
    last = history[-1] if history else None
    requirements = _selected_requirements(connection, pinned, harness_id=harness_id)

    return Survey(
        project_id=project_id,
        harness_id=harness_id,
        selected_stable_id="" if pinned is None else pinned[0],
        selected_version="" if pinned is None else pinned[1],
        installed_stable_id="" if last is None else last.setup_stable_id,
        installed_version="" if last is None else last.setup_version,
        verified_target_digest="" if last is None else last.target_digest,
        observed_target_digest=observed_target_digest,
        missing_env=tuple(
            sorted(set(requirements.required_env).union(additional_required_env) - present_env)
        ),
        pending_authorization=_pending_authorization(
            requirements.requires_authorization, authorization_evidence
        ),
        catalog_version=catalog_version,
    )


def _selected_requirements(
    connection: sqlite3.Connection,
    pinned: tuple[str, str, str] | None,
    *,
    harness_id: str,
) -> SetupRequirements:
    """Read requirements from the exact selected SetupVersion, never its head.

    Selection freezes one immutable version. Reading the mutable head here
    would let a later local revision change readiness without a new selection;
    reading no passport at all lets an omitted CLI flag hide a requirement.
    """
    if pinned is None:
        return SetupRequirements()
    stable_id, version, _state = pinned
    return setup_requirements(
        connection,
        stable_id=stable_id,
        version=version,
        harness_id=harness_id,
    )


def setup_requirements(
    connection: sqlite3.Connection,
    *,
    stable_id: str,
    version: str,
    harness_id: str | None = None,
) -> SetupRequirements:
    """Validate and read one exact SetupVersion's readiness requirements."""
    recorded = versions.held(connection, stable_id, version)
    stored = None if recorded is None else revisions.get(connection, recorded.revision_id)
    if recorded is None or stored is None:
        raise _selected_setup_corrupt()

    document = stored.envelope.model_dump(mode="json")
    try:
        passport = SetupVersionPassport.model_validate(document)
    except ValidationError as error:
        raise _selected_setup_corrupt() from error
    if (
        stored.stable_id != stable_id
        or passport.stable_id != stable_id
        or passport.version != version
        or (harness_id is not None and passport.harness_id != harness_id)
        or cache.digest_of(cast(JsonValue, document)) != recorded.passport_digest
    ):
        raise _selected_setup_corrupt()
    return SetupRequirements(
        required_env=tuple(item.name for item in passport.required_env),
        requires_authorization=passport.requires_authorization,
        name=passport.name,
        description=passport.description,
    )


def _pending_authorization(
    required: Literal["none", "user_account", "external_service"],
    evidence: AuthorizationEvidence | None,
) -> str:
    """Only exact provider evidence can clear a declared authorization."""
    if required == "none":
        return ""
    if evidence is None:
        return required
    if evidence.kind != required:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the provider authorization evidence does not match the selected setup",
            details={"expected": required, "reported": evidence.kind},
            next_actions=["provider conformance --harness <id> --executable <path> --json"],
        )
    return "" if evidence.ready else required


def _selected_setup_corrupt() -> CliFailure:
    return CliFailure(
        "AI_STP_INTERNAL",
        "the selected setup version does not match its exact passport",
        next_actions=["select propose --harness <id> --json"],
    )


def verified(
    connection: sqlite3.Connection, *, project_id: str, harness_id: str
) -> tuple[Verified, ...]:
    """Every version a provider verified on this pair, oldest first.

    Read from the operation log rather than from a table of its own. The log
    already records which version was verified on which target and when, and a
    second record of the same fact is a second thing that can disagree.
    """
    rows = connection.execute(
        """
        SELECT p.operation_id, p.setup_stable_id, p.setup_version,
               p.verified_target_digest, o.finished_at
        FROM operation_plan AS p
        JOIN operation AS o ON o.operation_id = p.operation_id
        JOIN operation_event AS e
          ON e.operation_id = p.operation_id AND e.state_after = ?
        WHERE p.target_id = ? AND o.state = ?
        -- Millisecond timestamps can tie, and operation_id orders creation,
        -- not completion.  Every global_sequence is assigned under the SQLite
        -- write lock, so it is the exact durable local verification order.
        ORDER BY e.global_sequence
        """,
        (
            installation.STATE_VERIFIED,
            f"{project_id}:{harness_id}",
            installation.STATE_VERIFIED,
        ),
    ).fetchall()
    return tuple(
        Verified(
            operation_id=str(row["operation_id"]),
            setup_stable_id=str(row["setup_stable_id"] or ""),
            setup_version=str(row["setup_version"] or ""),
            target_digest=str(row["verified_target_digest"] or ""),
            at=str(row["finished_at"] or ""),
        )
        for row in rows
        if row["setup_version"]
    )


def backups(
    connection: sqlite3.Connection, *, project_id: str, harness_id: str
) -> tuple[Backup, ...]:
    """Every provider-owned copy taken of this pair, oldest first.

    Read from the operation log for the same reason `verified` is: the log
    already records which operation took a copy, of what, and when. A second
    table of the same fact is a second thing that can disagree, and `REQ-814`
    keeps the copy and the setup apart precisely so that deleting one cannot
    take the other's identity with it.

    Only settled operations. A `BackupRef` on an operation that stopped belongs
    to `install recover`, which knows what may still be done with it; offering
    it here would read as "restorable" without anything having said so.
    """
    rows = connection.execute(
        """
        SELECT p.operation_id, p.backup_ref, p.setup_stable_id, p.setup_version,
               p.provider_target, o.finished_at
        FROM operation_plan AS p
        JOIN operation AS o ON o.operation_id = p.operation_id
        JOIN operation_event AS e
          ON e.operation_id = p.operation_id AND e.state_after = ?
        WHERE p.target_id = ? AND p.backup_ref IS NOT NULL AND o.state = ?
        -- The durable local order, as in `verified`: millisecond timestamps
        -- tie, and operation_id orders creation rather than completion.
        ORDER BY e.global_sequence
        """,
        (
            installation.STATE_VERIFIED,
            f"{project_id}:{harness_id}",
            installation.STATE_VERIFIED,
        ),
    ).fetchall()
    return tuple(
        Backup(
            backup_ref=str(row["backup_ref"]),
            operation_id=str(row["operation_id"]),
            setup_stable_id=str(row["setup_stable_id"] or ""),
            setup_version=str(row["setup_version"] or ""),
            provider_target=str(row["provider_target"] or ""),
            created_at=str(row["finished_at"] or ""),
        )
        for row in rows
        if row["backup_ref"]
    )


def rollback_target(
    connection: sqlite3.Connection, *, project_id: str, harness_id: str
) -> Verified:
    """The exact previous verified version, or a refusal naming why there is none.

    "Previous" means the one before the current in the order they were verified,
    not a numeric predecessor. Undoing a rollback may therefore name a higher
    version while still moving to the immediately preceding target state.
    """
    history = verified(connection, project_id=project_id, harness_id=harness_id)
    if len(history) < 2:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "there is no earlier verified version on this target to go back to",
            details={
                "project_id": project_id,
                "harness_id": harness_id,
                "verified": str(len(history)),
            },
            next_actions=["target status --harness <id> --json"],
        )
    return history[-2]


def pending_changes(found: Survey) -> tuple[str, ...]:
    """What installing the selected version would change, named line by line.

    One survey rather than two readings: nothing stores a previous survey, and
    a comparison that needs a snapshot nobody keeps is a comparison nobody can
    make. Both sides of the interesting difference — what is installed and what
    is selected — are already in one reading.

    Named rather than counted. "Three things differ" is not something anybody
    can act on, and finding out which is the reason to ask.
    """
    moved: list[str] = []
    if found.selected_version and found.selected_version != found.installed_version:
        moved.append(
            f"version: {found.installed_version or 'none installed'} -> {found.selected_version}"
        )
    if found.selected_stable_id and found.selected_stable_id != found.installed_stable_id:
        moved.append(
            f"setup: {found.installed_stable_id or 'none installed'} -> {found.selected_stable_id}"
        )
    if (
        found.verified_target_digest
        and found.observed_target_digest
        and found.verified_target_digest != found.observed_target_digest
    ):
        # Named as drift rather than as a change to apply: `REQ-818` forbids
        # fixing it automatically, and whatever moved the target may have had a
        # reason nobody here knows.
        moved.append(
            "target changed outside the provider: "
            f"{found.verified_target_digest} -> {found.observed_target_digest}"
        )
    if _catalog_is_newer(found.catalog_version, found.selected_version):
        moved.append(
            f"catalogue has {found.catalog_version}, selected is "
            f"{found.selected_version or 'nothing'}"
        )
    moved.extend(f"must be configured: {name}" for name in found.missing_env)
    if found.pending_authorization:
        moved.append(f"authorization not completed: {found.pending_authorization}")
    return tuple(moved)


def _catalog_is_newer(catalog_version: str, selected_version: str) -> bool:
    """Compare canonical X.Y numerically; inequality alone is not drift."""
    if not catalog_version or not selected_version:
        return False
    try:
        return compare_versions(catalog_version, selected_version) > 0
    except VersionError as error:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "target versions must use canonical X.Y notation",
            details={
                "catalog_version": catalog_version,
                "selected_version": selected_version,
            },
        ) from error
