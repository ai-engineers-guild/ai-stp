"""Exact consumer validation for provider protocol v3 plan/apply/status."""

from __future__ import annotations

import platform
from dataclasses import dataclass
from pathlib import Path
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
    """Require an apply result bound to one exact v3 plan and optional bundle."""
    state = str(answer.get("state", ""))
    if state not in protocol.STATE_MAP:
        raise _refused("the provider returned an unknown operation state", state=state)
    if answer.get("plan_digest") != plan.digest:
        raise _refused("the provider apply result names a different v3 plan")
    if answer.get("expected_target_digest") != plan.artifact["expected_target_digest"]:
        raise _refused("the provider apply result names a different target snapshot")
    if state == protocol.SUCCESS_STATE and bundle is not None:
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
        if answer.get("state") not in {"missing", "unmanaged"}:
            raise _refused("provider status does not prove managed-state removal")
        return target_digest
    if operation is protocol_v3.Operation.RESTORE:
        expected_restore = str(plan.artifact.get("restore_target_digest", ""))
        if target_digest != expected_restore:
            raise _refused("provider restore status differs from the exact BackupRef identity")
    expected: dict[str, JsonValue] = {"state": "managed", "drift_state": "verified"}
    if operation in {protocol_v3.Operation.INSTALL, protocol_v3.Operation.REPLACE}:
        expected.update(
            {
                "protocol_version": protocol_v3.VERSION,
                "provider_id": capabilities.provider_id,
                "provider_version": capabilities.provider_version,
                "provider_build_digest": capabilities.provider_build_digest,
                "provider_release_digest": release_digest,
                "provider_plan_digest": plan.digest,
                "projection_profile_digest": capabilities.projection.digest,
            }
        )
    if bundle is not None:
        expected.update(
            {
                "bundle_digest": bundle.bundle_digest,
                "artifact_digest": bundle.artifact_digest,
                "drift_state": "verified",
            }
        )
    mismatches = [name for name, value in expected.items() if answer.get(name) != value]
    if mismatches:
        raise _refused(
            "provider status does not prove the approved v3 installation",
            fields=", ".join(mismatches),
        )
    return target_digest


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
