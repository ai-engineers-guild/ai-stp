"""The lifecycle of the setup-system provider serving each harness (`#452`).

A provider is the only thing that writes a harness target, so which copy of it
runs, what version it is, and whether a newer one exists are facts a user has to
be able to see. `provider fetch` could already download and verify one; nothing
could say what was already on the machine.

Nothing here changes a harness target. Replacing a provider replaces one
executable; what that provider then does to a harness is still its own
operation, planned and confirmed separately.
"""

import shutil
import sqlite3
import stat
import tempfile
from collections.abc import Mapping
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, cast

from ai_stp_cli.answer import Answer
from ai_stp_cli.config import effective_config
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import provider_installations as installations
from ai_stp_cli.local.database import configured_path, open_readonly, open_registry
from ai_stp_cli.local.passports import moment
from ai_stp_cli.paths import redact_home
from ai_stp_cli.provider import attested_bind, release
from ai_stp_contracts.machine_help import (
    ProviderInstallationCheck,
    ProviderInstallationReport,
    ProviderReplacementPlan,
    ProviderReplacementResult,
)
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_canonical
from ai_stp_foundation.harnesses import HARNESS_IDS

#: Statuses that are outcomes rather than answers, and why each is not a
#: failure: a machine with no provider for a harness it does not use is
#: correct, and an unreachable release source is a fact about the network.
STATUS_UP_TO_DATE: Final[str] = "up_to_date"
STATUS_UPDATE_AVAILABLE: Final[str] = "update_available"
STATUS_UNKNOWN_VERSION: Final[str] = "unknown_version"
STATUS_SOURCE_UNAVAILABLE: Final[str] = "source_unavailable"
STATUS_MISSING: Final[str] = "missing"

#: Bytes on disk that no release manifest here covers: a path someone configured
#: by hand, a provider installed by other means, or a managed one that has been
#: replaced since. Distinct from `unknown_version`, which used to absorb all
#: three *after* running them to ask.
STATUS_UNMANAGED: Final[str] = "unmanaged"
STATUS_AMBIGUOUS: Final[str] = "ambiguous"


#: A well-formed digest standing in while the plan that will carry the real one
#: is built. The model requires the shape, and the value is replaced before the
#: plan is returned; a plan that ever escaped with this in it would fail its own
#: `apply` comparison, which is the safe direction.
DIGEST_PLACEHOLDER: Final[str] = "sha256:" + "0" * 64


@dataclass(frozen=True)
class Identity:
    """What is at a path now: its version if it will say, and its exact bytes."""

    version: str
    digest: str


def check(parameters: Mapping[str, object]) -> Answer[ProviderInstallationReport]:
    """Report each harness's provider installation against its pinned source.

    Read-only in every direction, which is the whole of what it promises. It
    hashes what is on disk and reads the release manifest beside it, asks GitHub
    for the newest exact tag, and writes nothing anywhere — not the registry,
    not the data directory, and not a remembered choice. `--offline` stops it
    asking at all rather than letting a failed request look like "no update".

    It runs no provider. `provider-info` is a program, and an executable whose
    identity is in question is exactly the one not to start; the manifest
    already carries the answer for every provider this installation placed.
    """
    named = parameters.get("harness")
    requested = _requested(named)
    offline = bool(parameters.get("offline"))
    # `values` is the ordered list the report renders, not a mapping. Reading
    # it as one silently returned nothing for every harness, which would have
    # made a configured path look like an absent one.
    configured = {item.path: item.value for item in effective_config().values}
    at = moment()

    registry = configured_path()
    checks: list[ProviderInstallationCheck] = []
    consulted = False

    # Read-only in the literal sense, which this was not. It opened the registry
    # with `create=True`, so a diagnostic created the database and its parent,
    # switched it to WAL, ran pending migrations and set permissions — and then
    # wrote an observation back as a remembered installation. A command declared
    # `read` was answering its own question by writing, and failed outright on a
    # read-only data directory it could simply have queried.
    #
    # A registry that does not exist is a history with nothing in it, and
    # `resolve` already accepts `None` for exactly that.
    connection = open_readonly(registry) if registry.exists() else None
    try:
        client = attested_bind.GithubReleases()
        for harness_id in requested:
            found = installations.resolve(
                connection,
                harness_id,
                configured=str(configured.get(f"provider.paths.{harness_id}") or ""),
            )
            outcome, asked = _check_one(found, client, offline=offline, at=at)
            consulted = consulted or asked
            checks.append(outcome)
    finally:
        if connection is not None:
            connection.close()

    return Answer(ProviderInstallationReport(installations=checks, source_consulted=consulted))


@dataclass(frozen=True)
class _ManifestIdentity:
    """A provider's identity taken from its manifest rather than from itself."""

    provider_id: str
    provider_version: str


def _manifest_identity(executable: Path) -> _ManifestIdentity | None:
    """Who this executable is, proved by bytes and read from disk. Runs nothing.

    `provider fetch` writes `release.json` beside every provider it installs,
    and that manifest names the exact artifact digest it covers. So the question
    "are these the bytes we installed, and what are they" is answerable by
    hashing the file and reading the file next to it — which is what a read-only
    command is entitled to do.

    `None` is the honest answer for everything else: a path with no manifest, a
    manifest that does not parse, and — most importantly — a manifest whose
    digest does not match the file. That last one is a managed provider that has
    been replaced, and it is precisely the case where running the executable to
    ask what it is would be running the substitute.
    """
    manifest_path = executable.parent / attested_bind.MANIFEST_NAME
    try:
        manifest = release.parse_manifest(manifest_path.read_text("utf-8"))
    except (OSError, CliFailure):
        return None
    try:
        observed, _ = release.artifact_identity(executable)
    except CliFailure:
        return None
    if observed != manifest.artifact_digest:
        return None
    return _ManifestIdentity(
        provider_id=manifest.provider_id, provider_version=manifest.provider_version
    )


def _check_one(
    found: installations.Resolution,
    client: attested_bind.ReleaseClient,
    *,
    offline: bool,
    at: str,
) -> tuple[ProviderInstallationCheck, bool]:
    """One harness. Returns the check and whether the release source was asked."""
    if found.state == installations.STATE_AMBIGUOUS:
        return (
            ProviderInstallationCheck(
                harness_id=found.harness_id,
                status=cast(Any, STATUS_AMBIGUOUS),
                reason=found.reason,
                candidates=[redact_home(Path(item)) for item in found.candidates],
                checked_at=at,
            ),
            False,
        )
    if not found.path:
        return (
            ProviderInstallationCheck(
                harness_id=found.harness_id,
                status=cast(Any, STATUS_MISSING),
                reason=found.reason or "no provider for this harness is installed here",
                checked_at=at,
            ),
            False,
        )

    # Identity is read, never asked for. This ran the executable — `provider-info`
    # is a program, and running it is running it — on bytes whose trust had not
    # been established, outside the isolation boundary, from a command declared
    # `read`. A configured path can name any file on the machine, and a
    # discovered one is an ordinary file that may have been replaced since it was
    # installed. The trusted fetch path verifies attestation *before* it inspects;
    # this did the reverse.
    #
    # Nothing is lost by not asking. A provider this installation placed has its
    # release manifest beside it, and the manifest states the provider id and
    # version — so for every candidate whose bytes match what was installed, the
    # answer this command needs is already on disk without a spawn.
    identity = _manifest_identity(Path(found.path))
    if identity is None:
        return (
            ProviderInstallationCheck(
                harness_id=found.harness_id,
                status=cast(Any, STATUS_UNMANAGED),
                path=found.path,
                source=cast(Any, found.source),
                reason=(
                    "these bytes are not the ones any release manifest here covers, so "
                    "their identity is unknown and they were not run to ask"
                ),
                checked_at=at,
            ),
            False,
        )
    capabilities = identity

    def described(
        status: str,
        reason: str,
        *,
        repository: str = "",
        latest_tag: str = "",
        latest_commit: str = "",
    ) -> ProviderInstallationCheck:
        """This harness's check, with the facts every branch shares."""
        return ProviderInstallationCheck(
            harness_id=found.harness_id,
            path=found.path,
            source=cast(Any, found.source),
            provider_id=capabilities.provider_id,
            provider_version=capabilities.provider_version,
            checked_at=at,
            status=cast(Any, status),
            reason=reason,
            repository=repository,
            latest_tag=latest_tag,
            latest_commit=latest_commit,
        )

    if offline:
        return (
            described(
                STATUS_UNKNOWN_VERSION,
                "the release source was not consulted, so nothing newer can be shown",
            ),
            False,
        )

    repository = attested_bind.repository_for_harness(found.harness_id)
    try:
        tag = client.resolve_tag(repository, None)
        facts = client.facts(repository, tag)
    except CliFailure as error:
        return (
            described(
                STATUS_SOURCE_UNAVAILABLE,
                f"the release source could not be asked: {error}",
                repository=repository,
            ),
            False,
        )

    behind = installations.newer(tag, capabilities.provider_version)
    return (
        described(
            STATUS_UPDATE_AVAILABLE if behind else STATUS_UP_TO_DATE,
            f"{capabilities.provider_version} is installed and {tag} is released"
            if behind
            else f"{capabilities.provider_version} is the newest released version",
            repository=repository,
            latest_tag=tag,
            latest_commit=facts.commit,
        ),
        True,
    )


def _requested(named: object) -> tuple[str, ...]:
    """The harnesses to ask about: those named, or every supported one."""
    # A repeatable option that was not given arrives as an empty tuple, not as
    # `None`, and both mean the same thing here: ask about every harness.
    if not named:
        return tuple(sorted(HARNESS_IDS))
    supplied: tuple[object, ...] = (
        tuple(cast(list[object] | tuple[object, ...], named))
        if isinstance(named, list | tuple)
        else (named,)
    )
    wanted = tuple(str(item) for item in supplied)
    unknown = sorted(set(wanted) - set(HARNESS_IDS))
    if unknown:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a supported harness identifier is required",
            details={"unknown": ", ".join(unknown), "supported": ", ".join(sorted(HARNESS_IDS))},
            next_actions=["toolchain harnesses --json"],
        )
    return tuple(sorted(set(wanted)))


#: Plans are digested in the same domain as every other plan this CLI makes.
#: A separate domain would let a digest computed for one kind of decision be
#: presented as confirmation of another.
PLAN_DOMAIN: Final[str] = "ai-stp:plan:v1"


def update_plan(parameters: Mapping[str, object]) -> Answer[ProviderReplacementPlan]:
    """Describe replacing a harness's provider with the newest released version.

    Changes nothing, including on disk: the bytes it needs to state an exact
    digest are fetched to a temporary directory, never to the one discovery
    reads.
    """
    return cast(
        Answer[ProviderReplacementPlan], _replace(parameters, operation="update", confirmed=False)
    )


def update_apply(parameters: Mapping[str, object]) -> Answer[ProviderReplacementResult]:
    """Carry out exactly the replacement a plan described, and nothing else.

    Replacing a provider replaces one executable. What that provider then does
    to a harness target is still its own operation, planned and confirmed on
    its own.
    """
    return cast(
        Answer[ProviderReplacementResult], _replace(parameters, operation="update", confirmed=True)
    )


def reinstall_plan(parameters: Mapping[str, object]) -> Answer[ProviderReplacementPlan]:
    """Describe re-installing one exact provider version into the same path.

    Without `--version` this is the version already there. Moving to the newest
    is `provider update`, deliberately: `#452` keeps "install exactly this
    again" and "take whatever is newest" apart, because only one of them can
    surprise the person running it.
    """
    return cast(
        Answer[ProviderReplacementPlan],
        _replace(parameters, operation="reinstall", confirmed=False),
    )


def reinstall_apply(parameters: Mapping[str, object]) -> Answer[ProviderReplacementResult]:
    """Carry out exactly the reinstallation a plan described."""
    return cast(
        Answer[ProviderReplacementResult],
        _replace(parameters, operation="reinstall", confirmed=True),
    )


def forget(parameters: Mapping[str, object]) -> Answer[ProviderInstallationReport]:
    """Drop the recorded provider choice, returning to config and discovery.

    Without `--harness`, every harness. `#452` requires the choice be
    reversible: an update records a decision, and a decision nobody can undo
    leaves a machine pinned to a path it has outgrown.
    """
    requested = _requested(parameters.get("harness"))
    at = moment()
    dropped: list[ProviderInstallationCheck] = []
    with closing(open_registry(configured_path(), create=True)) as connection:
        held = {item.harness_id: item for item in installations.all_remembered(connection)}
        for harness_id in requested:
            record = held.get(harness_id)
            if record is None or not installations.forget(connection, harness_id):
                continue
            dropped.append(
                ProviderInstallationCheck(
                    harness_id=harness_id,
                    status=cast(Any, STATUS_MISSING),
                    path=record.path,
                    source=cast(Any, record.source),
                    provider_id=record.provider_id,
                    provider_version=record.provider_version,
                    reason="the recorded choice was dropped; discovery decides again",
                    checked_at=at,
                )
            )
        connection.commit()
    return Answer(ProviderInstallationReport(installations=dropped, source_consulted=False))


def _replace(
    parameters: Mapping[str, object], *, operation: str, confirmed: bool
) -> Answer[ProviderReplacementPlan] | Answer[ProviderReplacementResult]:
    harness_id = str(parameters.get("harness") or "")
    if harness_id not in HARNESS_IDS:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a supported harness identifier is required",
            details={"supported": ", ".join(sorted(HARNESS_IDS))},
            next_actions=["provider check --json"],
        )
    wanted_tag = str(parameters.get("version") or "")
    executable = str(parameters.get("executable") or "")
    expected = str(parameters.get("expected-plan-digest") or "")
    if confirmed and parameters.get("confirm") is not True:
        raise CliFailure(
            "AI_STP_USER_DECISION_REQUIRED",
            "replacing a provider requires explicit confirmation",
            next_actions=[
                f"provider {operation} apply --harness {harness_id} "
                "--expected-plan-digest <digest> --confirm --json"
            ],
        )
    adopt = bool(parameters.get("adopt"))

    configured = {item.path: item.value for item in effective_config().values}
    registry = configured_path()
    with closing(open_registry(registry, create=True)) as connection:
        found = installations.resolve(
            connection,
            harness_id,
            argument=executable,
            configured=str(configured.get(f"provider.paths.{harness_id}") or ""),
        )
        if found.state == installations.STATE_AMBIGUOUS:
            raise CliFailure(
                "AI_STP_USER_DECISION_REQUIRED",
                "more than one provider is installed for this harness; name the one to replace",
                details={
                    "harness": harness_id,
                    "candidates": ", ".join(redact_home(Path(c)) for c in found.candidates),
                },
                next_actions=[
                    f"provider {operation} plan --harness {harness_id} --executable <path>"
                ],
            )
        if not found.path:
            raise CliFailure(
                "AI_STP_NOT_FOUND",
                "no provider for this harness is installed here",
                details={"harness": harness_id},
                next_actions=[f"provider fetch --harness {harness_id} --json"],
            )

        target = Path(found.path)
        current = _identity(target)
        foreign = not _is_managed(connection, target)
        if foreign and not adopt:
            # A file this tool did not place is not silently overwritten
            # (`#452`). The refusal names the flag rather than the impossibility
            # so the user can decide, which is the whole point of the branch.
            raise CliFailure(
                "AI_STP_USER_DECISION_REQUIRED",
                "that provider was not installed by ai-stp; adopting it must be explicit",
                details={"harness": harness_id, "path": redact_home(target)},
                next_actions=[
                    f"provider {operation} plan --harness {harness_id} --adopt --json",
                ],
            )

        tag = wanted_tag or (current.version if operation == "reinstall" else "")
        # Into a temporary directory, never the managed root. `provider fetch`
        # writes there on purpose and a fetched provider is meant to be found;
        # a replacement's download is staging, and putting it there made the
        # *plan* create a second installation — after which the machine was
        # ambiguous and the update it had just planned refused to run.
        with tempfile.TemporaryDirectory(prefix="ai-stp-provider-") as staging:
            bound = attested_bind.fetch(
                harness=harness_id, tag=tag or None, directory=Path(staging)
            )
            return _planned_or_applied(
                connection,
                bound=bound,
                operation=operation,
                harness_id=harness_id,
                target=target,
                current=current,
                foreign=foreign,
                confirmed=confirmed,
                expected=expected,
            )


def _planned_or_applied(
    connection: sqlite3.Connection,
    *,
    bound: attested_bind.BoundRelease,
    operation: str,
    harness_id: str,
    target: Path,
    current: Identity,
    foreign: bool,
    confirmed: bool,
    expected: str,
) -> Answer[ProviderReplacementPlan] | Answer[ProviderReplacementResult]:
    """Describe the replacement, and carry it out when it was confirmed exactly."""
    plan = ProviderReplacementPlan(
        harness_id=harness_id,
        operation=operation,  # pyright: ignore[reportArgumentType]
        path=str(target),
        current_version=current.version,
        current_digest=current.digest,
        repository=bound.repository,
        tag=bound.tag,
        commit=bound.commit,
        provider_id=bound.provider_id,
        provider_version=bound.provider_version,
        artifact_url=bound.artifact_url,
        artifact_digest=bound.artifact_digest,
        artifact_bytes=bound.artifact.stat().st_size,
        trust_level=bound.trust_level,
        backup=redact_home(_backup_path(target, current.digest)),
        foreign=foreign,
        plan_digest=DIGEST_PLACEHOLDER,
        idempotency_key=f"provider:{operation}:{harness_id}:{bound.artifact_digest}",
    )
    plan = plan.model_copy(update={"plan_digest": _digest(plan)})

    if not confirmed:
        return Answer(plan)
    if expected != plan.plan_digest:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the plan digest does not match what would be installed now",
            details={"expected": expected, "current": plan.plan_digest},
            next_actions=[f"provider {operation} plan --harness {harness_id} --json"],
        )

    outcome = _install(bound.artifact, target, current)
    installations.remember(
        connection,
        installations.Installation(
            harness_id=harness_id,
            path=str(target),
            # An update is a decision, so the row it writes settles the
            # question that discovery only observed.
            source=installations.SOURCE_CHOSEN,
            state=installations.STATE_INSTALLED,
            provider_id=bound.provider_id,
            provider_version=bound.provider_version,
            tag=bound.tag,
            commit=bound.commit,
            artifact_digest=bound.artifact_digest,
            checked_at=moment(),
            source_checked_at=moment(),
        ),
    )
    connection.commit()

    return Answer(
        ProviderReplacementResult(
            harness_id=harness_id,
            operation=operation,  # pyright: ignore[reportArgumentType]
            outcome=outcome,  # pyright: ignore[reportArgumentType]
            path=str(target),
            previous_version=current.version,
            provider_version=bound.provider_version,
            tag=bound.tag,
            artifact_digest=bound.artifact_digest,
            backup=(
                redact_home(_backup_path(target, current.digest)) if outcome == "replaced" else ""
            ),
            plan_digest=plan.plan_digest,
        )
    )


def _identity(executable: Path) -> Identity:
    """Read the installed provider's version and digest, tolerating silence.

    A provider that will not answer `provider-info` is still replaceable — that
    is often *why* it is being replaced — so an unreadable version is empty
    rather than fatal. The digest is read from the file and always available.
    """
    digest, _size = release.artifact_identity(executable)
    try:
        capabilities = attested_bind.inspect_provider(executable)
    except CliFailure:
        return Identity("", digest)
    return Identity(capabilities.provider_version, digest)


def _is_managed(connection: sqlite3.Connection, executable: Path) -> bool:
    """Whether ai-stp itself placed these exact bytes at this path.

    Two ways that is true. The file sits in the store `provider fetch` owns —
    location is the proof. Or the registry remembers this path as the chosen
    installation — the row an adopted `update apply` writes — and the file
    still hashes to the digest that row recorded. Bound to bytes, not to the
    path alone: a file someone replaced afterwards is foreign again, and the
    adoption question returns exactly when its premise does. Before the second
    half existed, an adopted replacement was re-asked for adoption on its very
    next operation, with a premise the previous apply had already made false.
    """
    try:
        resolved = executable.resolve()
        if resolved.is_relative_to(installations.managed_root().resolve()):
            return True
    except OSError:  # pragma: no cover - resolve on a vanished path
        return False
    for held in installations.all_remembered(connection):
        if held.source != installations.SOURCE_CHOSEN or not held.artifact_digest:
            continue
        if Path(held.path) != resolved and Path(held.path).resolve() != resolved:
            continue
        digest, _size = release.artifact_identity(resolved)
        return digest == held.artifact_digest
    return False


def _backup_path(executable: Path, digest: str) -> Path:
    """Where the replaced bytes are kept, named by what they were.

    Named by digest rather than by time: two runs that replace the same bytes
    write the same backup, so repeating an update cannot bury the copy that
    would be restored.
    """
    return executable.with_name(f"{executable.name}.{digest.split(':')[-1][:16]}.backup")


def _install(source: Path, target: Path, current: Identity) -> str:
    """Put the fetched bytes at the target path, atomically, keeping a backup.

    Idempotent by digest: if the bytes already there are the bytes wanted, this
    changes nothing and says so. That is what makes an interrupted run safe to
    repeat — the second attempt is not a second installation.

    The replacement is a rename onto the target, which is atomic on one
    filesystem, so an interruption leaves either the old executable or the new
    one and never a half-written file that would run.
    """
    fetched, _size = release.artifact_identity(source)
    if fetched == current.digest:
        return "unchanged"

    backup = _backup_path(target, current.digest)
    shutil.copy2(target, backup)
    staged = target.with_name(f"{target.name}.incoming")
    shutil.copy2(source, staged)
    staged.chmod(staged.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    staged.replace(target)
    return "replaced"


def _digest(plan: ProviderReplacementPlan) -> str:
    """The plan's digest over everything in it except the digest field itself."""
    document = plan.model_dump(mode="json")
    document.pop("plan_digest", None)
    return digest_canonical(PLAN_DOMAIN, cast(JsonValue, document))
