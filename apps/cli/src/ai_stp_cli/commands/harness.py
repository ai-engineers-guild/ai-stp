"""Install, update and remove the harness program itself (`ADR-0122`).

The subject here is the program under `--prefix`, not the configuration in
`--target`. That is the whole reason this is a separate noun: `install` owns a
setup and carries a bundle, a stable id and a version, and a program install has
none of those.

The consumer downloads and the provider never does. `download` is not one of the
kit's seven commands, and both commands that could have carried it declare
`network_requirement: none`, so the plan states the identity of the bytes
offline and this module fetches them against that statement.

Three constraints here are not obvious and were established by running a real
provider rather than by reading the contract:

- `expected_target_digest` is **not** enforced for a program operation. A file
  written into the target between plan and apply does not invalidate the plan,
  and a configuration edit is never a reason to re-plan or retry. Adding a
  re-check here for symmetry with setups would break a 167 MB download because
  someone edited their own instructions.
- `--target` is still required, and is injected by the invoker rather than by
  the argv builder.
- `software_remove` on a prefix this program never wrote answers `removed:
  false` rather than refusing. That is idempotence, not a failure.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Final

from ai_stp_cli.answer import Answer
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import cache, installation, journal
from ai_stp_cli.local.database import configured_path, open_readonly, open_registry
from ai_stp_cli.local.passports import moment
from ai_stp_cli.provider import (
    conformance,
    invocation,
    operation_v3,
    protocol,
    protocol_v3,
    software_fetch,
    trust,
)
from ai_stp_contracts.machine_help import (
    HarnessProgram,
    HarnessProgramArtifact,
    HarnessProgramOperation,
    HarnessProgramStatus,
)
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.ids import new_id

#: How long a program plan stays applicable. The same short window a setup plan
#: gets, and for the same reason: a plan is a statement about a moment.
PLAN_TTL_SECONDS: Final[int] = 900

#: Journal action per command, and the provider operation it maps to. This is
#: the second of the two action maps `ADR-0122` describes; the first belongs to
#: setup installation and refuses everything here.
_OPERATIONS: Final[dict[str, protocol_v3.Operation]] = {
    "install": protocol_v3.Operation.SOFTWARE_INSTALL,
    "update": protocol_v3.Operation.SOFTWARE_UPDATE,
    "remove": protocol_v3.Operation.SOFTWARE_REMOVE,
}


def _required(parameters: Mapping[str, object], name: str) -> str:
    value = str(parameters.get(name) or "")
    if not value:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            f"--{name} is required",
            details={"parameter": name},
        )
    return value


def _directory(parameters: Mapping[str, object], name: str) -> Path:
    """An absolute directory, resolved.

    Absolute because the provider resolves it against nothing: a relative path
    would land wherever the provider happened to be started from. Rooted is not
    absolute on Windows, and `Path.is_absolute` knows the difference.
    """
    place = Path(_required(parameters, name)).expanduser()
    if not place.is_absolute():
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            f"--{name} must be an absolute path",
            details={name: str(place)},
        )
    return place


def install(parameters: Mapping[str, object]) -> Answer[HarnessProgram]:
    """Install the harness program under an exact prefix."""
    return _perform("install", parameters)


def update(parameters: Mapping[str, object]) -> Answer[HarnessProgram]:
    """Move the exposed program to the version this provider pins."""
    return _perform("update", parameters)


def remove(parameters: Mapping[str, object]) -> Answer[HarnessProgram]:
    """Remove what this program installed, and nothing it did not.

    The confirmation is read here rather than assumed from the declaration. A
    flag a handler never reads is a confirmation that does not exist, and this
    is the one command in the group whose effect cannot be undone by running it
    again.
    """
    if parameters.get("confirm") is not True:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "removing a harness program requires explicit confirmation",
            details={"prefix": str(parameters.get("prefix") or "")},
            next_actions=["harness remove --confirm --json"],
        )
    return _perform("remove", parameters)


def status(parameters: Mapping[str, object]) -> Answer[HarnessProgramStatus]:
    """What stands under one prefix (`ADR-0122`).

    Two sources on purpose. The journal says what this installation did; the
    filesystem says what is there now. Only the second can tell that a verified
    operation left nothing behind, and that is not hypothetical — a provider
    once unpacked into a sandbox's own tmpfs, verified it where every check was
    true, and reported success for files that died with the namespace. `lost`
    is that case, named rather than left to be inferred from two fields.

    No provider is invoked. The kit's `status` describes the *target*, and its
    seven commands include nothing that describes a prefix; asking the program
    its own version would run a foreign executable from a command declared
    `read`, which `doctor` already refuses to do for `gh`.
    """
    harness_id = _required(parameters, "harness")
    prefix = _directory(parameters, "prefix")

    # Read-only, as the command declares itself. This opened the registry with
    # `open_registry`, which creates the database and its parent on a fresh
    # installation, switches it to WAL, applies pending migrations and sets
    # filesystem permissions — a diagnostic with durable side effects, and one
    # that fails outright on a read-only data directory it could have queried.
    #
    # A registry that does not exist is a history with nothing in it, which is
    # exactly what `never_installed` means. Creating one to say so was the
    # command answering its own question by writing.
    registry = configured_path()
    if registry.exists():
        with closing(open_readonly(registry)) as connection:
            history = installation.program_history(connection, str(prefix))
    else:
        history = ()

    stopped = tuple(item for item in history if item.state not in installation.REPLANNABLE_STATES)
    settled = next((item for item in history if item.state == installation.STATE_VERIFIED), None)

    entry_point = settled.entry_point if settled else ""
    executable = prefix / entry_point if entry_point else None
    on_disk = executable is not None and executable.exists()

    state, reason = _standing(
        settled=settled, stopped=stopped, on_disk=on_disk, prefix=prefix, history=history
    )
    return Answer(
        HarnessProgramStatus(
            harness_id=harness_id,
            prefix=str(prefix),
            state=state,  # pyright: ignore[reportArgumentType]
            reason=reason,
            executable=str(executable) if on_disk and executable is not None else "",
            entry_point=entry_point,
            version=settled.version if settled else "",
            operation_id=settled.operation_id if settled else "",
            recorded_operation=settled.action if settled else "",
            recorded_state=settled.state if settled else "",
            recorded_at=settled.at if settled else "",
            stopped=[
                HarnessProgramOperation(
                    operation_id=item.operation_id,
                    operation=item.action,  # pyright: ignore[reportArgumentType]
                    state=item.state,
                    at=item.at,
                )
                for item in stopped
            ],
        )
    )


def _standing(
    *,
    settled: installation.ProgramRecord | None,
    stopped: tuple[installation.ProgramRecord, ...],
    on_disk: bool,
    prefix: Path,
    history: tuple[installation.ProgramRecord, ...],
) -> tuple[str, str]:
    """One of six answers, and the sentence that says why.

    Order matters in one place: an unsettled operation outranks everything,
    because it is the answer that asks for an action rather than a reading, and
    it is usually also the explanation for whatever the other fields show.
    """
    if stopped:
        return (
            "interrupted",
            f"{len(stopped)} program operation(s) here stopped without settling; "
            "recover before planning another",
        )
    if settled is None:
        if _occupied(prefix):
            return (
                "foreign",
                "something is installed under this prefix that this installation did not put "
                "there; a program operation here would refuse rather than adopt it",
            )
        return ("never_installed", "this installation has never put a program under this prefix")
    if settled.action == "software_remove":
        if on_disk:
            # The marker first, because it is written by the side that does the
            # exposing. The journal can only infer, and it infers from
            # operations this installation drove — a person running the
            # provider's own `rollback` against this prefix leaves a version
            # standing that no record here names.
            marked = _exposed_version(prefix=prefix, entry_point=settled.entry_point)
            if marked and marked != settled.version:
                return (
                    "present",
                    f"{marked} exposed at {settled.entry_point}, read from the provider's "
                    f"version marker; {settled.version or 'another build'} was taken off by "
                    f"{settled.operation_id} and did not hold the exposure",
                )
            standing = _survivor(settled=settled, history=history)
            if not marked and standing is not None:
                return (
                    "present",
                    f"{standing.version or 'a build'} exposed at {standing.entry_point}, "
                    f"inferred from the journal because this prefix carries no version "
                    f"marker; {settled.version or 'another build'} was taken off by "
                    f"{settled.operation_id} and did not hold the exposure",
                )
            return (
                "foreign",
                "this installation removed what it owned and a program is still exposed here; "
                "the provider removes only what it installed",
            )
        return ("removed", f"removed by {settled.operation_id}, and nothing is exposed here")
    if not on_disk:
        return (
            "lost",
            f"{settled.operation_id} verified {settled.version or 'a build'} here and "
            f"{settled.entry_point or 'the entry point'} is not on disk; ask what bound the "
            "prefix before asking the provider",
        )
    return (
        "present",
        f"{settled.version or 'a build'} exposed at {settled.entry_point}, "
        f"verified by {settled.operation_id}",
    )


#: Where the provider records which version `bin/<command>` points into. Written
#: by the same code that does the exposing and deleted with the command it
#: described, so it cannot disagree with the disk the way a separate ledger can.
_VERSION_MARKER: Final[str] = ".{command}.version"

#: Suffixes the exposed file may carry that the marker's name does not. The
#: provider exposes `<command>.cmd` for a JavaScript member on Windows while
#: still writing `.<command>.version`, so the marker is found from the stem
#: rather than from the file that is actually there.
#:
#: Only `.cmd` has a subject: cursor exposes `agent.cmd` on Windows because its
#: member is JavaScript. No harness exposes a `.exe` — codex ships `codex.exe`
#: as its member and exposes it as `codex`, because `CreateProcess` on an
#: explicit path reads the PE header rather than the name. `.exe` and `.bat`
#: are breadth, not coverage, and are named here so this set is not later read
#: as evidence that such an exposure exists.
_EXPOSED_SUFFIXES: Final[frozenset[str]] = frozenset({".cmd", ".exe", ".bat"})


def _exposed_version(*, prefix: Path, entry_point: str) -> str:
    """The version standing at this prefix, read from the provider's own marker.

    `<prefix>/bin/.<command>.version` is written after the command is in place
    and removed with it, by the provider rather than by us. Reading it answers
    what the journal can only infer, and answers it for exposures this
    installation did not make: a person can run the provider's own `rollback`
    against a prefix we manage, which puts a version in place through a path
    `program_history` never sees.

    Two guards, both taken from the provider's own reader rather than invented
    here. The marker is believed only where the command it describes is
    actually there, and only when it names a version directory that exists —
    a hand-edited or half-written marker must not name a version that is not.

    An empty answer means unknown, not absent: a prefix written before markers
    existed reads the same as one nothing installed into, and neither is a
    version. The caller decides what unknown is worth.

    The existence filter does not catch every bad marker, and the reason it is
    not asked to is worth keeping. The provider used to write the marker with a
    plain, non-atomic write, so an interrupted install could truncate it.
    Measured against a prefix holding both `1.18` and `1.18.23`: `1.18.2` and
    an empty string are rejected, and `1.18` was *accepted* — truncation only
    has to stop somewhere that is itself a real version directory, which a
    prefix-sibling version provides for free.

    Nothing here distinguishes that from a genuine `1.18` exposure; the filter
    is true either way. The one reading-side mitigation available — distrusting
    the marker where the journal disagrees — would fire exactly on the
    hand-rollback case this reading exists to answer, and a guard that is wrong
    where the mechanism is right is worse than the hole.

    So it was fixed where it could be. From provider `0.0.42` the marker is
    staged to a sibling and renamed, which is atomic within a directory, so a
    reader meets the old marker or the new one and never a third thing. Read
    from the tag rather than taken on report: `setup-core/src/software.rs` at
    `0.0.42` carries the staged write, and codex's tree for it is `71dc0c5a`.

    The filter stays regardless. Every prefix written by a provider before
    `0.0.42` keeps the shape above, and this reads prefixes it did not write.
    """
    command = PurePosixPath(entry_point).name
    stem = Path(command)
    if stem.suffix.casefold() in _EXPOSED_SUFFIXES:
        command = stem.stem
    marker = prefix / "bin" / _VERSION_MARKER.format(command=command)
    try:
        held = marker.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    return held if held and (prefix / held).is_dir() else ""


def _survivor(
    *,
    settled: installation.ProgramRecord,
    history: tuple[installation.ProgramRecord, ...],
) -> installation.ProgramRecord | None:
    """The version still exposed after a removal that did not name it.

    A removal takes `bin/<command>` only when it names the version that holds
    it. Removing a build that is merely present — the one a rollback stepped
    off — leaves the running command alone, and that is the whole point of
    being able to remove it.

    This reading could not see the difference. `entry_point` is a command name
    rather than a version, so it is the same string for every build under the
    prefix; the file was still there and the branch above called it `foreign`,
    which says *this installation did not put it there*. It did.

    Reported by the side that owns the kernel, after it fixed a removal that
    used to take the exposure unconditionally: install, update, roll back,
    remove the bad one, and the command running the good build was deleted. So
    the old `foreign` was accurate only because the state it described could
    not occur.

    The journal can tell them apart because a rollback is a `software_update`
    to the earlier version — the operation vocabulary has three verbs and no
    fourth — so the newest settled install or update before the removal names
    the build that stands. A different version there is the survivor; the same
    version is a genuine stranger, and keeps the old answer.
    """
    # By position rather than by timestamp: `program_history` orders on
    # `created_at DESC, operation_id DESC`, so two operations recorded in the
    # same second are separated by the second key and not by the first. A
    # comparison on `at` alone would put them in either order.
    try:
        start = history.index(settled)
    except ValueError:  # pragma: no cover - `settled` is taken from `history`
        return None
    for record in history[start + 1 :]:
        if record.state != installation.STATE_VERIFIED:
            continue
        if record.action == "software_remove":
            return None
        return record if record.version and record.version != settled.version else None
    return None


def _occupied(prefix: Path) -> bool:
    """Whether anything is exposed under this prefix.

    `bin/` and nothing deeper: that is where a provider exposes a command, and
    it is the one place a sibling copy of the program would be visible. Walking
    the whole prefix would call a leftover download an installation.
    """
    exposed = prefix / "bin"
    return exposed.is_dir() and any(exposed.iterdir())


def _perform(action: str, parameters: Mapping[str, object]) -> Answer[HarnessProgram]:
    operation = _OPERATIONS[action]
    harness_id = _required(parameters, "harness")
    executable = conformance.resolve_executable(_required(parameters, "provider"))
    prefix = _directory(parameters, "prefix")
    target = _directory(parameters, "target")

    # Trust before the first spawn, exactly as the setup path establishes it.
    #
    # This ran `provider-info` on a caller-supplied executable and only then
    # read the caller-supplied `--provider-release-digest`, so a string copied
    # from a real release stood in for proof that these were its bytes. The
    # sandbox binds the target and the prefix writable for every command,
    # including that first one, so an unverified executable had somewhere to
    # write before any durable plan existed.
    #
    # It also passed no unisolated reason, and macOS and Windows have no
    # launcher — so this refused there before the provider spawned at all, for
    # the whole command family. The reason is not new authority: it reads which
    # of two things the caller already established, a verified release or a
    # deliberate `--unverified-provider`.
    with open_registry(configured_path()) as connection:
        evidence = trust.trusted_manifest(
            connection, parameters, executable, recovery_requested=False
        )
        trusted_release = evidence.manifest
        trust.release_required(parameters, protocol_v3.VERSION, trusted_release)

        # The prefix is where the program goes, and the sandbox binds only the
        # target unless told otherwise. Without this the provider writes into
        # the namespace's own tmpfs and reports success for files that do not
        # survive it.
        invoke = invocation.provider_invoker(
            executable,
            str(target),
            protocol_v3.VERSION,
            writable=(prefix,),
            unisolated_reason=trust.unisolated_reason(trusted_release, parameters),
        )
        info = _object(invoke("provider-info", ()))
        capabilities = protocol_v3.parse_capabilities(dict(info))
        if capabilities.harness_id != harness_id:
            raise CliFailure(
                "AI_STP_PRECONDITION_FAILED",
                "that provider is for a different harness",
                details={"asked": harness_id, "provider": capabilities.harness_id},
            )
        # Asking a provider that never declared the operation is how an agent finds
        # out, so the refusal is left to the provider rather than pre-empted here:
        # its detail says why, and ours would only guess.
        capabilities.require(operation)

        # What the target is now, read from the provider before anything is
        # planned against it. The setup path does the same; this path used to
        # take the number out of the plan it was about to validate.
        observed_target_digest = str(_object(invoke("status", ())).get("target_digest", ""))
        if not observed_target_digest:
            raise CliFailure(
                "AI_STP_PRECONDITION_FAILED",
                "the provider does not report a target digest, so a plan cannot be bound to one",
                details={"harness": harness_id},
            )

        operation_id = new_id("operation")
        expires_at = (
            (datetime.now(UTC) + timedelta(seconds=PLAN_TTL_SECONDS))
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )
        release_digest = _required(parameters, "provider-release-digest")
        arguments = operation_v3.plan_operation_arguments(
            operation=operation,
            release_digest=release_digest,
            operation_id=operation_id,
            expires_at=expires_at,
            prefix=prefix,
        )
        answer = _object(invoke("plan-operation", arguments))
        if answer.get("rejected") is True:
            raise CliFailure(
                "AI_STP_PRECONDITION_FAILED",
                "the provider refused to plan this program operation",
                details={"reason": str(answer.get("reason", "")), "harness": harness_id},
            )
        # The canonical binder, not a hand-read of four keys.
        #
        # This used to take `plan`, `plan_digest` and `effects` out of the
        # answer and check none of them against what was asked. A provider
        # returning a correctly hashed plan for a *different* operation, prefix,
        # release or operation id was accepted, its artifacts downloaded, and it
        # applied. `require_plan` binds all of that, and it needed no widening
        # for programs: measured against the released provider, a
        # `software_install` plan carries the same keys as any other and its
        # `canonical_target` is the target, not the prefix.
        #
        # `expected_target_digest` is the consumer's own observation rather than
        # the plan's echo of itself. Taking it from the plan made the binding
        # circular — the provider would have been agreeing with a number it had
        # just invented.
        bound = operation_v3.require_plan(
            answer,
            capabilities=capabilities,
            release_digest=release_digest,
            operation_id=operation_id,
            operation=operation,
            target=target,
            expected_target_digest=observed_target_digest,
            bundle=None,
            backup_ref=None,
            permission_profile=None,
            expires_at=expires_at,
        )
        plan = bound.artifact
        plan_digest = bound.digest
        effects = bound.effects
        artifacts = operation_v3.require_software_artifacts(dict(plan), operation=operation)

        held = installation.propose(
            connection,
            action=f"software_{action}",
            author=str(parameters.get("author") or "agent"),
            target_id=str(prefix),
            expected_target_digest=observed_target_digest,
            provider_version=capabilities.provider_version,
            effects=effects,
            recovery_action="remove" if action != "remove" else "install",
            idempotency_key=f"harness:{harness_id}:{action}:{prefix}",
            at=moment(),
            expires_at=expires_at,
            provider_protocol_version=protocol_v3.VERSION,
            provider_target=str(target),
            provider_plan_digest=plan_digest,
            operation_id=operation_id,
        )
        return Answer(
            _apply(
                connection,
                held,
                invoke=invoke,
                operation=operation,
                harness_id=harness_id,
                prefix=prefix,
                target=target,
                release_digest=release_digest,
                plan=dict(plan),
                plan_digest=plan_digest,
                bound=bound,
                effects=effects,
                artifacts=artifacts,
            )
        )


def _apply(
    connection: sqlite3.Connection,
    held: installation.Plan,
    *,
    invoke: conformance.Invoker,
    operation: protocol_v3.Operation,
    harness_id: str,
    prefix: Path,
    target: Path,
    release_digest: str,
    plan: dict[str, JsonValue],
    plan_digest: str,
    bound: operation_v3.ProviderPlan,
    effects: tuple[str, ...],
    artifacts: tuple[operation_v3.SoftwareArtifact, ...],
) -> HarnessProgram:
    """Fetch what the plan named, then let the provider apply it."""
    # The journal's own plan digest, not the provider's. They are different
    # statements about different objects — the journal's covers the decision it
    # recorded, the provider's covers the artifact it will re-read — and the
    # journal keeps the second in `provider_plan_digest` precisely so approving
    # cannot be satisfied by the wrong one.
    installation.approve(connection, held.operation_id, plan_digest=held.digest, at=moment())
    fetched = [software_fetch.fetch(artifact) for artifact in artifacts]
    # The observed digest is the plan's own: for a program action `begin` does
    # not compare it at all, and passing anything else would suggest it did.
    installation.begin(
        connection,
        held.operation_id,
        observed_target_digest=held.expected_target_digest,
        at=moment(),
    )

    # The cache owns this: it writes the canonical bytes privately and
    # re-checks the digest on the way back out. A second writer here would
    # be a second opinion about what a stored plan is.
    plan_path = cache.store_provider_plan(plan, plan_digest)
    arguments: tuple[str, ...] = (
        "--plan",
        str(plan_path),
        "--plan-digest",
        plan_digest,
        "--provider-release-digest",
        release_digest,
        "--prefix",
        str(prefix),
    )
    for place in fetched:
        arguments = (*arguments, "--software-artifact", str(place))
    # A timeout or a malformed answer here is not a failure — the provider was
    # called and may have finished. `applied_unverified` is the state that says
    # so, and the operation stays resumable from it. Recording `failed` after a
    # possible effect is the one thing the state machine forbids, and it is what
    # this path did for every outcome that was not the literal word `verified`.
    try:
        answer = _object(invoke("apply-operation", arguments))
    except CliFailure:
        installation.applied(connection, held.operation_id, at=moment())
        installation.interrupted(
            connection,
            held.operation_id,
            at=moment(),
            reason="the provider did not answer after a program operation may have landed",
        )
        raise
    installation.applied(connection, held.operation_id, at=moment())

    # The canonical binder, which also refuses an apply result that names a
    # different plan or snapshot. It returns the provider's own state word, and
    # `stale` is a settled no-effect outcome rather than a failure.
    state = operation_v3.require_applied(answer, plan=bound, bundle=None)
    mapped = protocol.operation_state(state)
    if mapped != installation.STATE_VERIFIED:
        # Each outcome recorded as itself, the way the setup path records them.
        # `stale` is the provider having locked the target and refused a plan
        # that no longer describes it — settled, and no effect. `rolled_back` is
        # the provider having undone its own change. `partial` is an effect
        # nobody has confirmed, which stays resumable. Collapsing all three into
        # `failed`, as this did, made a retry look safer than it was.
        recorder = {
            installation.STATE_STALE: (
                installation.stale,
                "the provider locked the prefix and refused a stale plan",
            ),
            installation.STATE_ROLLED_BACK: (
                installation.roll_back,
                "the provider undid its own change",
            ),
            installation.STATE_PARTIAL: (
                installation.interrupted,
                f"the provider reported {state}",
            ),
        }.get(mapped, (installation.fail, f"the provider reported {state!r}"))
        recorder[0](connection, held.operation_id, at=moment(), reason=recorder[1])
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the provider did not verify this program operation",
            details={"state": state, "harness": harness_id, "operation": operation.value},
        )
    installation.verify(
        connection,
        held.operation_id,
        postconditions_met=True,
        at=moment(),
        evidence=str(answer.get("executable", "")),
    )
    # What this operation exposed, in columns rather than in the effect prose,
    # so `harness status` can name the exact build without parsing a sentence
    # or running the program.
    installation.record_program(
        connection,
        held.operation_id,
        version=str(answer.get("version", "")),
        entry_point=artifacts[0].entry_point if artifacts else "",
    )
    return HarnessProgram(
        harness_id=harness_id,
        operation=operation.value,  # pyright: ignore[reportArgumentType]
        state=state,
        operation_id=held.operation_id,
        prefix=str(prefix),
        plan_digest=plan_digest,
        effects=list(effects),
        artifacts=[
            HarnessProgramArtifact(
                platform=item.platform,
                url=item.url,
                sha256=item.sha256,
                byte_length=item.byte_length,
                entry_point=item.entry_point,
            )
            for item in artifacts
        ],
        executable=str(answer.get("executable", "")),
        version=str(answer.get("version", "")),
        removed=(
            bool(answer.get("removed"))
            if operation is protocol_v3.Operation.SOFTWARE_REMOVE
            else None
        ),
        recovered=_recovered(answer),
    )


def _recovered(answer: Mapping[str, JsonValue]) -> list[str]:
    """What the provider resolved from an interrupted earlier operation.

    Absent from every released provider at the time this was written, and that
    is the normal answer rather than a problem: the key is new, and a prefix
    nothing interrupted has nothing to report either way.

    Read defensively for the same reason. A provider that sends something other
    than a list of strings is not worth failing a completed operation over —
    the effect has already landed — so anything unreadable is reported as
    nothing recovered rather than raised. The operation's own outcome is
    carried by `state`, and this field must not be able to change it.
    """
    raw = answer.get("recovered")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, str) and item]


def _object(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the provider answered with something other than one object",
        )
    return value


#: Where a program operation can still be settled by looking rather than by
#: doing it again. Both mean the provider was called; only the second admits it.
_UNSETTLED: Final[frozenset[str]] = frozenset(
    {installation.STATE_APPLYING, installation.STATE_APPLIED_UNVERIFIED}
)

#: Cleanup the provider says it still owes. Any of these is durable work, so
#: `recover-operation` is the command that settles it, never a second apply.


def resume(parameters: Mapping[str, object]) -> Answer[HarnessProgram]:
    """Settle a program operation that stopped, without repeating its effect.

    The program lifecycle had no way back. A process killed after
    `apply-operation` left the operation in `applying`; `install resume` refuses
    a program action by design, because its subject is a setup, and it pointed
    at `harness install` — which would run the whole operation again. So the
    only offered route out of "the provider was called and nobody has looked"
    was to do it a second time.

    This looks instead. It reads the provider's own state, calls
    `recover-operation` when the provider says durable recovery is owed, and
    never calls `apply-operation`. Nothing here sends an artifact.

    A provider that still does not settle leaves the operation `partial` rather
    than `failed`: after the call was made, "nothing was done" is a claim nobody
    is in a position to make.
    """
    operation_id = _required(parameters, "operation")
    executable = conformance.resolve_executable(_required(parameters, "provider"))
    prefix = _directory(parameters, "prefix")
    target = _directory(parameters, "target")

    with open_registry(configured_path()) as connection:
        current = journal.get(connection, operation_id)
        state = "" if current is None else current.state
        if state not in _UNSETTLED:
            raise CliFailure(
                "AI_STP_PRECONDITION_FAILED",
                "that program operation is not waiting on a postcondition",
                details={"operation": operation_id, "state": state},
                next_actions=["harness status --harness <id> --prefix <dir> --json"],
            )

        evidence = trust.trusted_manifest(
            connection, parameters, executable, recovery_requested=False
        )
        trusted_release = evidence.manifest
        trust.release_required(parameters, protocol_v3.VERSION, trusted_release)
        invoke = invocation.provider_invoker(
            executable,
            str(target),
            protocol_v3.VERSION,
            writable=(prefix,),
            unisolated_reason=trust.unisolated_reason(trusted_release, parameters),
        )

        # `applying` means the provider was called and nobody has looked since.
        # Acknowledging that first is not a guess that the effect landed — it is
        # the honest name for the situation, and the state the journal requires
        # before any verdict about it.
        if state == installation.STATE_APPLYING:
            installation.applied(connection, operation_id, at=moment())

        answer = _object(invoke("status", ()))
        reported = str(answer.get("state", ""))
        cleanup = str(answer.get("cleanup_state", ""))
        if reported == "recovery_required" or cleanup in protocol_v3.CLEANUP_NEEDS_RECOVERY:
            invoke("recover-operation", ())
            answer = _object(invoke("status", ()))
            reported = str(answer.get("state", ""))

        if reported in {"managed", "missing", "unmanaged"}:
            installation.verify(
                connection,
                operation_id,
                postconditions_met=True,
                at=moment(),
                observed_target_digest=str(answer.get("target_digest", "")),
            )
        else:
            installation.interrupted(
                connection,
                operation_id,
                at=moment(),
                reason=f"the provider still reports {reported!r} for this program operation",
            )
        settled = journal.get(connection, operation_id)
        # The durable plan, which is what recorded the action. `journal.get`
        # answers where the operation stopped; it does not carry what it was.
        held = installation._require(connection, operation_id)  # pyright: ignore[reportPrivateUsage]
        return Answer(
            HarnessProgram(
                harness_id=_required(parameters, "harness"),  # pyright: ignore[reportArgumentType]
                operation=held.action.removeprefix("software_"),  # pyright: ignore[reportArgumentType]
                state="" if settled is None else settled.state,
                operation_id=operation_id,
                prefix=str(prefix),
                plan_digest=str(answer.get("provider_plan_digest", "")),
                effects=[],
                artifacts=[],
            )
        )
