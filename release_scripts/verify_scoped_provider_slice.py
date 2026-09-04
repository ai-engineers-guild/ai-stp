"""Mutating disposable-target evidence for every non-global provider profile."""

from __future__ import annotations

import argparse
import json
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

from ai_stp_cli.local import composition
from ai_stp_cli.provider import (
    bundle_corpus,
    bundle_protocol,
    conformance,
    invocation,
    operation_v3,
    protocol_v3,
)
from ai_stp_foundation.canonical import JsonValue, canonize
from ai_stp_foundation.ids import new_id

BINARIES = {
    "antigravity": "antigravity-setup-system",
    "claude-code": "claude-setup-system",
    "codex": "codex-setup-system",
    "cursor": "cursor-setup-system",
    "grok-build": "grok-setup-system",
    "opencode": "opencode-setup-system",
    "pi": "pi-setup-system",
}
RELEASE_DIGEST = "sha256:" + "d" * 64


@dataclass
class Lifecycle:
    invoke: conformance.Invoker
    capabilities: protocol_v3.ProviderCapabilities
    profile: protocol_v3.ProjectionProfile
    target: Path
    status_arguments: tuple[str, ...]
    sequence: int = 0


def _object(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise RuntimeError("provider returned a non-object response")
    return cast(dict[str, JsonValue], value)


def _route(harness_id: str, profile: protocol_v3.ProjectionProfile) -> tuple[str, str, str]:
    for kind in sorted(profile.component_kinds, key=lambda item: item.value):
        rule = composition.rule_for(kind.value, harness_id, scope=profile.scope)
        if rule is None or rule.relative not in profile.native_namespaces:
            continue
        target_path = (
            rule.relative if rule.shape == "file" else f"{rule.relative}/ai-stp-scoped-evidence.md"
        )
        return kind.value, rule.relative, target_path
    raise RuntimeError(f"{harness_id}/{profile.scope} has no consumer route")


def _execute(
    lifecycle: Lifecycle,
    operation: protocol_v3.Operation,
    *,
    bound: bundle_protocol.Binding | None = None,
    backup_ref: str | None = None,
) -> tuple[dict[str, JsonValue], str]:
    invoke = lifecycle.invoke
    lifecycle.sequence += 1
    before = _object(invoke("status", lifecycle.status_arguments))
    expected_target_digest = str(before.get("target_digest") or "")
    expires_at = (
        (datetime.now(UTC) + timedelta(minutes=10))
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )
    operation_id = new_id("operation")
    arguments = operation_v3.plan_operation_arguments(
        operation=operation,
        release_digest=RELEASE_DIGEST,
        operation_id=operation_id,
        expires_at=expires_at,
        backup_ref=backup_ref,
        bundle=bound,
        target_scope=lifecycle.profile.scope,
        accepted_request_fields=lifecycle.capabilities.plan_request_fields,
    )
    answer = _object(invoke("plan-operation", arguments))
    plan = operation_v3.require_plan(
        answer,
        capabilities=lifecycle.capabilities,
        release_digest=RELEASE_DIGEST,
        operation_id=operation_id,
        operation=operation,
        target=lifecycle.target,
        expected_target_digest=expected_target_digest,
        bundle=bound,
        backup_ref=backup_ref,
        permission_profile=None,
        expires_at=expires_at,
        target_scope=lifecycle.profile.scope,
    )
    plan_path = lifecycle.target / f".ai-stp-evidence-plan-{lifecycle.sequence}.json"
    plan_path.write_bytes(canonize(cast(JsonValue, plan.artifact)))
    apply_arguments: tuple[str, ...] = (
        "--plan",
        str(plan_path),
        "--plan-digest",
        plan.digest,
        "--provider-release-digest",
        RELEASE_DIGEST,
    )
    if bound is not None:
        apply_arguments = (*apply_arguments, *bound.common_arguments())
    applied = _object(invoke("apply-operation", apply_arguments))
    operation_v3.require_applied(applied, plan=plan, bundle=bound)
    after = _object(invoke("status", lifecycle.status_arguments))
    observed = operation_v3.require_verified_status(
        after,
        capabilities=lifecycle.capabilities,
        release_digest=RELEASE_DIGEST,
        plan=plan,
        bundle=bound,
        operation=operation,
    )
    return applied, observed


def verify(root: Path) -> dict[str, JsonValue]:
    """Run install/status/backup/remove/restore for all declared scoped profiles."""
    results: list[JsonValue] = []
    for harness_id, binary_name in BINARIES.items():
        executable = root / "target" / "release" / binary_name
        if not executable.is_file():
            raise RuntimeError(f"provider executable is absent: {binary_name}")
        with tempfile.TemporaryDirectory(prefix=f"ai-stp-{harness_id}-scoped-") as held:
            harness_root = Path(held)
            probe = harness_root / "probe"
            probe.mkdir()
            probe_invoke = invocation.provider_invoker(str(executable), str(probe), 3)
            capabilities = protocol_v3.parse_capabilities(
                cast(dict[str, object], _object(probe_invoke("provider-info", ())))
            )
            for profile in capabilities.scoped_projections:
                target = harness_root / profile.scope
                target.mkdir()
                invoke = invocation.provider_invoker(str(executable), str(target), 3)
                component_kind, native_surface, target_path = _route(harness_id, profile)
                lifecycle = Lifecycle(
                    invoke=invoke,
                    capabilities=capabilities,
                    profile=profile,
                    target=target,
                    status_arguments=operation_v3.status_arguments(capabilities, profile.scope),
                )
                with bundle_corpus.materialized_v3(
                    harness_id=harness_id,
                    component_kind=component_kind,
                    native_surface=native_surface,
                    target_path=target_path,
                    profile_id=profile.profile_id,
                    profile_digest=profile.digest,
                    target_scope=profile.scope,
                ) as corpus:
                    bundle_protocol.require_validated(
                        _object(invoke("validate-bundle", corpus.valid.common_arguments())),
                        corpus.valid,
                    )
                    _installed, installed_digest = _execute(
                        lifecycle, protocol_v3.Operation.INSTALL, bound=corpus.valid
                    )
                    expected = b"safe provider v3 conformance literal\n"
                    if (target / target_path).read_bytes() != expected:
                        raise RuntimeError(
                            f"{harness_id}/{profile.scope} installed different bytes"
                        )
                    backup, _backup_digest = _execute(lifecycle, protocol_v3.Operation.BACKUP)
                    backup_ref = str(backup.get("backup_ref") or "")
                    if not backup_ref:
                        raise RuntimeError(f"{harness_id}/{profile.scope} returned no BackupRef")
                    _removed, removed_digest = _execute(lifecycle, protocol_v3.Operation.REMOVE)
                    if (target / target_path).exists():
                        raise RuntimeError(
                            f"{harness_id}/{profile.scope} left managed bytes after remove"
                        )
                    _restored, restored_digest = _execute(
                        lifecycle,
                        protocol_v3.Operation.RESTORE,
                        backup_ref=backup_ref,
                    )
                    if (target / target_path).read_bytes() != expected:
                        raise RuntimeError(f"{harness_id}/{profile.scope} restored different bytes")
                    results.append(
                        {
                            "harness_id": harness_id,
                            "scope": profile.scope,
                            "profile_id": profile.profile_id,
                            "profile_digest": profile.digest,
                            "installed_target_digest": installed_digest,
                            "removed_target_digest": removed_digest,
                            "restored_target_digest": restored_digest,
                            "backup_ref_present": True,
                        }
                    )
    return {
        "schema_version": 1,
        "profiles_verified": len(results),
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--setup-systems-root", type=Path, required=True)
    options = parser.parse_args()
    print(
        json.dumps(
            verify(options.setup_systems_root.resolve()),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
