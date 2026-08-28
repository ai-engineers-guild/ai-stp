"""Exact consumer validation for provider protocol v3 plan/apply/status."""

from __future__ import annotations

import platform
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import cast

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.provider import bundle_protocol, protocol, protocol_v3
from ai_stp_foundation.canonical import JsonValue, from_json_bytes
from ai_stp_foundation.digests import digest_canonical, is_digest


@dataclass(frozen=True)
class ProviderPlan:
    artifact: dict[str, JsonValue]
    digest: str
    effects: tuple[str, ...]


#: Operations whose subject is a program rather than the configuration in the
#: target. They are the only ones that take `--prefix`, and they require it:
#: a provider asked to install a program without being told where would be
#: guessing a path.
SOFTWARE_OPERATIONS: frozenset[protocol_v3.Operation] = frozenset(
    {
        protocol_v3.Operation.SOFTWARE_INSTALL,
        protocol_v3.Operation.SOFTWARE_UPDATE,
        protocol_v3.Operation.SOFTWARE_REMOVE,
    }
)


@dataclass(frozen=True)
class SoftwareArtifact:
    """One program archive, named completely enough to fetch without asking again.

    `entry_point` is relative to `--prefix` and is the path the provider will
    expose there — not a path inside the archive. The archive's own shape never
    crosses the wire, which is what lets a harness whose archive has no wrapper
    directory work without a special case.
    """

    platform: str
    url: str
    sha256: str
    byte_length: int
    entry_point: str


#: Program operations that fetch bytes. `software_remove` is deliberately absent:
#: it deletes what is already there and needs no artifact.
_FETCHING_OPERATIONS: frozenset[protocol_v3.Operation] = frozenset(
    {protocol_v3.Operation.SOFTWARE_INSTALL, protocol_v3.Operation.SOFTWARE_UPDATE}
)

_ARTIFACT_FIELDS: tuple[str, ...] = (
    "platform",
    "url",
    "sha256",
    "byte_length",
    "entry_point",
)


def require_software_artifacts(
    plan: dict[str, JsonValue],
    *,
    operation: protocol_v3.Operation,
) -> tuple[SoftwareArtifact, ...]:
    """Read the artifact identities a program plan must state before any fetch.

    The consumer downloads and the provider never does — `download` is not one of
    the kit's commands, and both commands that could have carried it are
    `network_requirement: none`. So this plan is the only place the identity of
    those bytes is ever stated, and it is stated offline, before the network is
    touched. Every refusal here is a refusal to fetch something whose identity
    was left open.

    The digest is the anchor and the URL is only a hint: bytes that do not match
    are refused whatever host served them.
    """
    raw = plan.get("software_artifacts")
    if operation not in _FETCHING_OPERATIONS:
        if raw:
            raise _refused(
                "a plan that fetches nothing offered software artifacts",
                fields=operation.value,
            )
        return ()
    if not isinstance(raw, list) or not raw:
        raise _refused(
            "the program plan names no software artifact to fetch",
            fields=operation.value,
        )
    artifacts: list[SoftwareArtifact] = []
    for index, entry in enumerate(cast(list[JsonValue], raw)):
        if not isinstance(entry, dict):
            raise _refused("a software artifact is not an object", fields=str(index))
        item = cast(dict[str, JsonValue], entry)
        missing = [name for name in _ARTIFACT_FIELDS if item.get(name) is None]
        if missing:
            raise _refused(
                "a software artifact does not state its identity",
                fields=", ".join(missing),
            )
        digest = item["sha256"]
        if not isinstance(digest, str) or not is_digest(digest):
            raise _refused("a software artifact has no exact sha256", fields="sha256")
        length = item["byte_length"]
        # `bool` is an `int` in Python and `True` would pass a naive check.
        if not isinstance(length, int) or isinstance(length, bool) or length <= 0:
            raise _refused("a software artifact has no checkable byte_length", fields="byte_length")
        url = item["url"]
        if not isinstance(url, str) or not url.startswith("https://"):
            raise _refused("a software artifact is not fetched over https", fields="url")
        entry_point = item["entry_point"]
        if not isinstance(entry_point, str) or not _within_prefix(entry_point):
            raise _refused(
                "a software artifact entry point leaves the prefix", fields="entry_point"
            )
        platform_name = item["platform"]
        if not isinstance(platform_name, str) or "/" not in platform_name:
            raise _refused("a software artifact names no platform", fields="platform")
        artifacts.append(
            SoftwareArtifact(
                platform=platform_name,
                url=url,
                sha256=digest,
                byte_length=length,
                entry_point=entry_point,
            )
        )
    return tuple(artifacts)


def _within_prefix(candidate: str) -> bool:
    """Whether a relative path stays under the directory it is joined to."""
    path = PurePosixPath(candidate)
    if path.is_absolute() or not candidate:
        return False
    return ".." not in path.parts


def plan_operation_arguments(
    *,
    operation: protocol_v3.Operation,
    release_digest: str,
    operation_id: str,
    expires_at: str,
    prefix: Path | None = None,
    backup_ref: str | None = None,
    permission_profile: str | None = None,
    bundle: bundle_protocol.Binding | None = None,
) -> tuple[str, ...]:
    """Build the `plan-operation` argv once, for every caller that needs one.

    This existed twice before it existed here: the installation path built it
    and the conformance run built it again, and the copies agreed until one of
    them had to grow `--prefix` for the program lifecycle. The one that did not
    grow it asked six providers to install a program without saying where, and
    every one of them refused — which read as six provider defects rather than
    one argv defect, because the case that broke was the case testing them.

    A third copy for the harness commands would be the same bet a third time.

    `--prefix` is required for a software operation and refused for every other
    one, so the shape cannot be assembled wrongly by a caller that passes the
    wrong pair: getting it wrong raises here rather than at a provider.
    """
    software = operation in SOFTWARE_OPERATIONS
    if software and prefix is None:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a program operation needs the prefix the program goes under",
            details={"operation": operation.value},
        )
    if prefix is not None and not software:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "only a program operation takes a prefix",
            details={"operation": operation.value},
        )
    arguments: tuple[str, ...] = (
        "--operation",
        operation.value,
        "--provider-release-digest",
        release_digest,
        "--operation-id",
        operation_id,
        "--expires-at",
        expires_at,
    )
    if prefix is not None:
        # Absolute, because the provider resolves it against nothing: a relative
        # prefix would land wherever the provider happened to be started from.
        arguments = (*arguments, "--prefix", str(prefix.resolve()))
    if backup_ref is not None:
        arguments = (*arguments, "--backup-ref", backup_ref)
    if permission_profile is not None:
        arguments = (*arguments, "--permission-profile", permission_profile)
    if bundle is not None:
        arguments = (*arguments, *bundle.common_arguments())
    return arguments


def load_plan(path: Path, expected_digest: str) -> ProviderPlan:
    """Load the consumer cache artifact and re-check its logical identity."""
    try:
        raw = from_json_bytes(path.read_bytes())
    except (OSError, ValueError) as error:
        raise _refused("the approved provider plan artifact is unreadable") from error
    if not isinstance(raw, dict):
        raise _refused("the approved provider plan artifact is not an object")
    artifact = cast(dict[str, JsonValue], raw)
    if digest_canonical(protocol_v3.PLAN_DOMAIN, artifact) != expected_digest:
        raise _refused("the approved provider plan artifact has another digest")
    return ProviderPlan(
        artifact=artifact,
        digest=expected_digest,
        effects=_strings(artifact.get("effects"), "provider plan effects"),
    )


def require_plan(
    answer: dict[str, JsonValue],
    *,
    capabilities: protocol_v3.ProviderCapabilities,
    release_digest: str,
    operation_id: str,
    operation: protocol_v3.Operation,
    target: Path,
    expected_target_digest: str,
    bundle: bundle_protocol.Binding | None,
    backup_ref: str | None,
    permission_profile: str | None,
    expires_at: str,
) -> ProviderPlan:
    """Require the provider's exact canonical plan and its redundant echoes."""
    if answer.get("state") != "planned":
        raise _refused("the provider did not return a planned v3 operation")
    raw = answer.get("plan")
    if not isinstance(raw, dict):
        raise _refused("the provider did not return a v3 plan artifact")
    artifact = cast(dict[str, JsonValue], raw)
    digest = str(answer.get("plan_digest", ""))
    if not is_digest(digest) or digest_canonical(protocol_v3.PLAN_DOMAIN, artifact) != digest:
        raise _refused("the provider plan digest does not bind its exact artifact")
    restore_target_digest = artifact.get("restore_target_digest")
    if operation is protocol_v3.Operation.RESTORE:
        if not isinstance(restore_target_digest, str) or not is_digest(restore_target_digest):
            raise _refused("the provider restore plan has no exact result target digest")
    elif restore_target_digest is not None:
        raise _refused("a non-restore provider plan binds a restored target digest")
    expected: dict[str, JsonValue] = {
        "format": "ai-stp-provider-plan/3",
        "protocol_version": protocol_v3.VERSION,
        "provider_id": capabilities.provider_id,
        "provider_version": capabilities.provider_version,
        "provider_build_digest": capabilities.provider_build_digest,
        "provider_release_digest": release_digest,
        "operation_id": operation_id,
        "operation": operation.value,
        "canonical_target": str(target.resolve()),
        "expected_target_digest": expected_target_digest,
        "projection_profile_digest": capabilities.projection.digest,
        "bundle": None if bundle is None else _bundle_echo(bundle),
        "backup_ref": backup_ref,
        "restore_target_digest": restore_target_digest,
        "permission_profile": permission_profile,
        "platform": _platform(),
        "expires_at": expires_at,
    }
    mismatches = [name for name, value in expected.items() if artifact.get(name) != value]
    if mismatches:
        raise _refused(
            "the provider plan differs from exact consumer inputs",
            fields=", ".join(mismatches),
        )
    effects = _strings(artifact.get("effects"), "provider plan effects")
    if not effects or answer.get("effects") != list(effects):
        raise _refused("the provider plan does not enumerate exact effects")
    if answer.get("expected_target_digest") != expected_target_digest:
        raise _refused("the provider plan echo names a different target snapshot")
    if bundle is not None:
        bundle_protocol.require_validated({**answer, "valid": True}, bundle)
    return ProviderPlan(artifact=artifact, digest=digest, effects=effects)


def require_applied(
    answer: dict[str, JsonValue],
    *,
    plan: ProviderPlan,
    bundle: bundle_protocol.Binding | None,
) -> str:
    """Require an apply result bound to one exact v3 plan.

    Bundle identity is sealed into the plan artifact at `plan-operation`.
    `apply-operation` echoes that plan, not the four validate-bundle fields.
    A typed refusal uses `state=refused` with `reason=stale` to mean no effect
    after the lock.
    """
    state = _reported_operation_state(answer)
    if state not in protocol.STATE_MAP:
        raise _refused("the provider returned an unknown operation state", state=state)
    if state == "stale":
        return state
    if answer.get("plan_digest") != plan.digest:
        raise _refused("the provider apply result names a different v3 plan")
    if answer.get("expected_target_digest") != plan.artifact["expected_target_digest"]:
        raise _refused("the provider apply result names a different target snapshot")
    echoed = ("bundle_format", "bundle_digest", "artifact_digest", "bundle_size")
    if bundle is not None and any(name in answer for name in echoed):
        bundle_protocol.require_validated({**answer, "valid": True}, bundle)
    return state


def require_verified_status(
    answer: dict[str, JsonValue],
    *,
    capabilities: protocol_v3.ProviderCapabilities,
    release_digest: str,
    plan: ProviderPlan,
    bundle: bundle_protocol.Binding | None,
    operation: protocol_v3.Operation,
) -> str:
    """Verify durable provider provenance before ai_stp records success."""
    target_digest = str(answer.get("target_digest", ""))
    if not is_digest(target_digest):
        raise _refused("provider status has no exact target digest")

    if operation is protocol_v3.Operation.REMOVE:
        # The fact that proves a removal is the absent setup, not the absent
        # provider. This used to require `state ∈ {missing, unmanaged}`, and no
        # released provider has ever satisfied it: after a remove they report
        # `managed`, because they keep a control directory and the backup slot
        # the removal is undone from. Asking them for `missing` asked them to
        # claim no state while a restore was pending — the reading that invites
        # a consumer to treat a populated directory as free, which is the
        # defect the provider side narrowed `missing` to avoid.
        #
        # `state` answers *who manages this target*; `setup_stable_id` answers
        # *whether a setup is installed*, and is `null` exactly when none is.
        # Neither word was in the shared contract, so both sides had assumed
        # one — the same shape as a path with no declared root.
        #
        # A missing or malformed `provider_state` refuses. Absence is not
        # evidence here any more than it is on `held`.
        # Two answers prove it, and they are different sentences rather than a
        # loosening. A provider owning nothing owns no setup by definition; a
        # provider still owning the directory proves it by naming no setup.
        if answer.get("state") in {"missing", "unmanaged"}:
            # Bound here too. This branch returned first, so a provider under a
            # stale plan reporting an empty target verified an operation it had
            # never run — the same hole as the one below, on the path that skips
            # it. Found by a mutation that deleted the other call and changed
            # nothing, which is what a guard covering one of two identical
            # branches looks like from the outside.
            _require_belongs_here(
                answer,
                capabilities=capabilities,
                release_digest=release_digest,
                plan=plan,
                bundle=bundle,
            )
            return target_digest
        reported = answer.get("provider_state")
        if not isinstance(reported, dict) or "setup_stable_id" not in reported:
            raise _refused("provider status does not prove the setup was removed")
        if reported["setup_stable_id"] is not None:
            raise _refused("provider status does not prove the setup was removed")
        _require_belongs_here(
            answer,
            capabilities=capabilities,
            release_digest=release_digest,
            plan=plan,
            bundle=bundle,
        )
        return target_digest
    if operation is protocol_v3.Operation.RESTORE:
        expected_restore = str(plan.artifact.get("restore_target_digest", ""))
        if target_digest != expected_restore:
            raise _refused("provider restore status differs from the exact BackupRef identity")
        _require_belongs_here(
            answer,
            capabilities=capabilities,
            release_digest=release_digest,
            plan=plan,
            bundle=bundle,
        )
        return target_digest
    if answer.get("state") != "managed":
        raise _refused("provider status does not prove managed installation")
    if answer.get("protocol_version") != protocol_v3.VERSION:
        raise _refused("provider status names a different protocol version")
    if answer.get("provider_id") != capabilities.provider_id:
        raise _refused("provider status names a different provider")
    nested = _provider_state(answer)
    # Every drift statement present has to hold, not the first one found. A
    # status can carry the fact twice — at the top level and inside
    # `provider_state` — and reading one meant a provider reporting `clean`
    # beside a nested `drifted` was accepted on the strength of the half that
    # was read. Two records of one fact where only one is checked is a fail-open
    # by construction, and its silence is what would keep it alive.
    #
    # Both spellings of "no drift" stay admissible on both, so a release mixing
    # the legacy `verified` with the current `clean` is not caught in a
    # vocabulary difference that means nothing.
    stated = [
        value
        for value in (answer.get("drift_state"), nested.get("drift_state"))
        if value is not None
    ]
    if not stated or any(str(value) not in {"verified", "clean"} for value in stated):
        raise _refused("provider status does not prove a clean managed target")
    # These two are what make the status about *this* operation rather than
    # about some installation. Without them a provider answering `managed` and
    # `clean` for an entirely different, older install verifies the one being
    # applied now — and the refusal below, whose whole subject is "the approved"
    # installation, could never fire. Everything else binds content or identity
    # and is checked when stated.
    _require_operation_binding(
        answer,
        nested,
        capabilities=capabilities,
        release_digest=release_digest,
        plan=plan,
        bundle=bundle,
    )
    return target_digest


def _require_belongs_here(
    answer: dict[str, JsonValue],
    *,
    capabilities: protocol_v3.ProviderCapabilities,
    release_digest: str,
    plan: ProviderPlan,
    bundle: bundle_protocol.Binding | None,
) -> None:
    """Whose target this is, and which operation reached it.

    `remove` and `restore` proved only the destination. A target digest says
    what is there, and nothing about who put it there or under what plan — two
    different providers reach an identical digest and were indistinguishable,
    and so was the same provider under a stale plan. That is how a status
    reporting `recovery_required` with the right bytes could be recorded
    `verified`.

    Deliberately *not* hoisted above the operation branches, which is where this
    was first written. On a drifted managed target the seven publish
    `operation_id` without `provider_plan_digest` on purpose, so a binding check
    running before the drift check would refuse a drifted target for a missing
    field — a familiar refusal, accurate about the wrong thing. The install path
    keeps drift first and binds afterwards; these two have no drift to protect
    and bind here.

    Nothing new is asked of any provider: all four facts are in the state file
    after an applied operation and already reported. A new field would have been
    a seven-provider release and a version window.
    """
    if answer.get("provider_id") != capabilities.provider_id:
        raise _refused("provider status names a different provider")
    _require_operation_binding(
        answer,
        _provider_state(answer),
        capabilities=capabilities,
        release_digest=release_digest,
        plan=plan,
        bundle=bundle,
    )


def _require_operation_binding(
    answer: dict[str, JsonValue],
    nested: dict[str, JsonValue],
    *,
    capabilities: protocol_v3.ProviderCapabilities,
    release_digest: str,
    plan: ProviderPlan,
    bundle: bundle_protocol.Binding | None,
) -> None:
    """Make a status about *this* operation rather than about some installation.

    Without it a provider answering for an entirely different, older install
    verifies the one being applied now. It used to run only on the install path:
    `remove` and `restore` returned from their own proof first, so a target
    digest — which says what the destination *is*, and nothing about who put it
    there or under what plan — was the whole of their evidence. Two different
    providers reach an identical digest and were indistinguishable; so was the
    same provider under a stale plan, which is how `recovery_required` with the
    right bytes could be recorded `verified`.

    Nothing new is asked of any provider. All four facts are already in the
    state file after an applied operation and already reported by `status`; the
    change is reading what was arriving. A new field would have been a
    seven-provider release and a version window.
    """
    binding: dict[str, JsonValue] = {
        "operation_id": plan.artifact.get("operation_id", ""),
        "provider_plan_digest": plan.digest,
    }
    unstated = [name for name in binding if name not in answer and name not in nested]
    if unstated:
        raise _refused(
            "provider status binds itself to no approved operation",
            fields=", ".join(sorted(unstated)),
        )
    stated_bindings: dict[str, JsonValue] = {
        "provider_version": capabilities.provider_version,
        "provider_build_digest": capabilities.provider_build_digest,
        "provider_release_digest": release_digest,
        "projection_profile_digest": capabilities.projection.digest,
        **binding,
    }
    if bundle is not None:
        stated_bindings["bundle_digest"] = bundle.bundle_digest
        stated_bindings["artifact_digest"] = bundle.artifact_digest
    mismatches = _present_mismatches(answer, nested, stated_bindings)
    if mismatches:
        raise _refused(
            "provider status does not prove the approved v3 installation",
            fields=", ".join(mismatches),
        )


def _reported_operation_state(answer: dict[str, JsonValue]) -> str:
    state = str(answer.get("state", ""))
    if state == "refused" and str(answer.get("reason", "")) == "stale":
        return "stale"
    return state


def _provider_state(answer: dict[str, JsonValue]) -> dict[str, JsonValue]:
    held = answer.get("provider_state")
    return cast(dict[str, JsonValue], held) if isinstance(held, dict) else {}


def _present_mismatches(
    answer: dict[str, JsonValue],
    nested: dict[str, JsonValue],
    expected: dict[str, JsonValue],
) -> list[str]:
    mismatches: list[str] = []
    for name, value in expected.items():
        if name in answer:
            if answer.get(name) != value:
                mismatches.append(name)
        elif name in nested and nested.get(name) != value:
            mismatches.append(name)
    return mismatches


def _bundle_echo(bound: bundle_protocol.Binding) -> dict[str, JsonValue]:
    return {
        "bundle_format": bound.bundle_format,
        "bundle_digest": bound.bundle_digest,
        "artifact_digest": bound.artifact_digest,
        "bundle_size": bound.bundle_size,
    }


def _platform() -> dict[str, JsonValue]:
    system = platform.system().casefold()
    os_name = "macos" if system == "darwin" else system
    machine = platform.machine().casefold()
    architecture = {"amd64": "x86_64", "aarch64": "arm64"}.get(machine, machine)
    return {"os": os_name, "arch": architecture}


def _strings(value: JsonValue, label: str) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or not item for item in value)
    ):
        raise _refused(f"{label} must be a non-empty string array")
    return cast(tuple[str, ...], tuple(value))


def _refused(message: str, **details: str) -> CliFailure:
    return CliFailure(
        "AI_STP_PRECONDITION_FAILED",
        message,
        details=details,
        next_actions=["provider conformance --json"],
    )
