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
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final

from ai_stp_cli.answer import Answer
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import cache, installation
from ai_stp_cli.local.database import configured_path, open_registry
from ai_stp_cli.local.passports import moment
from ai_stp_cli.provider import (
    conformance,
    invocation,
    operation_v3,
    protocol_v3,
    software_fetch,
)
from ai_stp_contracts.machine_help import HarnessProgram, HarnessProgramArtifact
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


def _perform(action: str, parameters: Mapping[str, object]) -> Answer[HarnessProgram]:
    operation = _OPERATIONS[action]
    harness_id = _required(parameters, "harness")
    executable = conformance.resolve_executable(_required(parameters, "provider"))
    prefix = _directory(parameters, "prefix")
    target = _directory(parameters, "target")

    # The prefix is where the program goes, and the sandbox binds only the
    # target unless told otherwise. Without this the provider writes into the
    # namespace's own tmpfs and reports success for files that do not survive it.
    invoke = invocation.provider_invoker(
        executable, str(target), protocol_v3.VERSION, writable=(prefix,)
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
    plan = answer.get("plan")
    if not isinstance(plan, dict):
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the provider returned no program plan artifact",
            details={"harness": harness_id},
        )
    plan_digest = str(answer.get("plan_digest", ""))
    raw_effects = answer.get("effects")
    effects = tuple(str(item) for item in raw_effects) if isinstance(raw_effects, list) else ()
    artifacts = operation_v3.require_software_artifacts(dict(plan), operation=operation)

    with open_registry(configured_path()) as connection:
        held = installation.propose(
            connection,
            action=f"software_{action}",
            author=str(parameters.get("author") or "agent"),
            target_id=str(prefix),
            expected_target_digest=str(plan.get("expected_target_digest", "")),
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
    answer = _object(invoke("apply-operation", arguments))
    installation.applied(connection, held.operation_id, at=moment())

    state = str(answer.get("state", ""))
    if state != "verified":
        installation.fail(
            connection,
            held.operation_id,
            at=moment(),
            reason=f"the provider reported {state!r} rather than verified",
        )
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
    )


def _object(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the provider answered with something other than one object",
        )
    return value
