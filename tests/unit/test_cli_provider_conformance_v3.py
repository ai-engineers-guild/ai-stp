"""Executable protocol-v3 conformance and exact operation binding."""

from __future__ import annotations

import platform
import stat
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest

from ai_stp_cli.commands import select
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.provider import (
    bundle_corpus,
    bundle_protocol,
    conformance,
    conformance_v3,
    operation_v3,
    protocol_v2,
    protocol_v3,
)
from ai_stp_foundation.canonical import JsonValue, canonize
from ai_stp_foundation.digests import digest_canonical


def _digest(character: str) -> str:
    return "sha256:" + character * 64


def _platform() -> dict[str, JsonValue]:
    system = platform.system().casefold()
    os_name = "macos" if system == "darwin" else system
    machine = platform.machine().casefold()
    architecture = {"amd64": "x86_64", "aarch64": "arm64"}.get(machine, machine)
    return {"os": os_name, "arch": architecture}


def _info(
    *,
    harness_id: str = "claude-code",
    component_kind: str = "instruction",
    native_namespace: str = "CLAUDE.md",
) -> dict[str, JsonValue]:
    current = _platform()
    profile: dict[str, JsonValue] = {
        "profile_id": f"{harness_id}/test",
        "component_kinds": cast(list[JsonValue], [component_kind]),
        "projection_kinds": cast(list[JsonValue], ["native_files"]),
        "native_namespaces": cast(list[JsonValue], [native_namespace]),
        "bundle_formats": cast(list[JsonValue], ["ai-stp-bundle/1"]),
        "max_files": 2000,
        "max_bytes": 64 * 1024 * 1024,
    }
    return {
        "protocol_version": protocol_v3.VERSION,
        "provider_id": f"nddev-{harness_id}-app",
        "harness_id": harness_id,
        "provider_version": "3.0.0",
        "provider_build_digest": _digest("b"),
        "supported_commands": cast(list[JsonValue], list(protocol_v3.CORE_COMMANDS)),
        "supported_operations": cast(
            list[JsonValue], sorted(item.value for item in protocol_v3.CORE_OPERATIONS)
        ),
        "supported_os": cast(list[JsonValue], [str(current["os"])]),
        "supported_arch": cast(list[JsonValue], [str(current["arch"])]),
        "permission_profiles": cast(list[JsonValue], []),
        "projection_profile": {
            **profile,
            "digest": digest_canonical(protocol_v3.PROJECTION_DOMAIN, profile),
        },
    }


def _arguments(values: Sequence[str]) -> dict[str, str]:
    return dict(zip(values[0::2], values[1::2], strict=True))


def _conforming(target: Path) -> tuple[conformance.Invoker, list[str]]:
    info = _info()
    calls: list[str] = []
    target_digest = _digest("a")
    # Derived, not restated. This map was a hand-kept copy of `CASE_REASONS`,
    # and a copy of a closed vocabulary agrees with it exactly until somebody
    # adds a case — at which point the conforming stub silently stops
    # conforming and the failure points at the run rather than at the copy.
    refusals = {
        name: ("unsupported_native_surface" if name == "unknown_native_surface" else refusal)
        for name, refusal in bundle_corpus.CASE_REASONS_V3
    }

    def invoke(command: str, arguments: Sequence[str]) -> JsonValue:
        calls.append(command)
        if command == "provider-info":
            return info
        if command == "status":
            return {"state": "missing", "target_digest": target_digest}
        supplied = _arguments(arguments)
        # A program operation carries no bundle: its subject is the program
        # under `--prefix`, not a setup projected into the target. The stub has
        # to answer that shape too, or the only request without bundle
        # arguments is one it cannot serve.
        bound: dict[str, JsonValue] = (
            {
                "bundle_format": supplied["--bundle-format"],
                "bundle_digest": supplied["--bundle-digest"],
                "artifact_digest": supplied["--artifact-digest"],
                "bundle_size": int(supplied["--bundle-size"]),
            }
            if "--bundle" in supplied
            else {}
        )
        case = Path(supplied["--bundle"]).parent.name if "--bundle" in supplied else ""
        if command == "validate-bundle":
            reason = refusals.get(case)
            return (
                {**bound, "rejected": True, "reason": reason}
                if reason is not None
                else {**bound, "valid": True}
            )
        if command == "plan-operation":
            # A conforming provider refuses an operation it never declared, and
            # says which class of refusal it is. Planning it anyway would be the
            # defect the case exists to find.
            asked = supplied["--operation"]
            if asked not in {item.value for item in protocol_v3.CORE_OPERATIONS}:
                return {
                    **bound,
                    "rejected": True,
                    "reason": protocol_v3.UnsupportedReason.OPERATION.value,
                }
            profile = supplied.get("--permission-profile")
            raw_profiles = info["permission_profiles"]
            declared_profiles = (
                {item for item in raw_profiles if isinstance(item, str)}
                if isinstance(raw_profiles, list)
                else set[str]()
            )
            if profile is not None and profile not in declared_profiles:
                return {
                    **bound,
                    "rejected": True,
                    "reason": protocol_v3.UnsupportedReason.PERMISSION_PROFILE.value,
                }
            artifact: dict[str, JsonValue] = {
                "format": "ai-stp-provider-plan/3",
                "protocol_version": protocol_v3.VERSION,
                "provider_id": info["provider_id"],
                "provider_version": info["provider_version"],
                "provider_build_digest": info["provider_build_digest"],
                "provider_release_digest": supplied["--provider-release-digest"],
                "operation_id": supplied["--operation-id"],
                "operation": supplied["--operation"],
                "canonical_target": str(target.resolve()),
                "expected_target_digest": target_digest,
                "projection_profile_digest": cast(dict[str, JsonValue], info["projection_profile"])[
                    "digest"
                ],
                "bundle": bound,
                "backup_ref": None,
                "permission_profile": None,
                "platform": _platform(),
                "expires_at": supplied["--expires-at"],
                "effects": cast(list[JsonValue], ["write exact projection"]),
            }
            plan_digest = digest_canonical(protocol_v3.PLAN_DOMAIN, artifact)
            return {
                "state": "planned",
                "plan": artifact,
                "plan_digest": plan_digest,
                "expected_target_digest": target_digest,
                "effects": artifact["effects"],
                **bound,
            }
        raise AssertionError(command)

    return invoke, calls


def test_v3_conformance_exercises_only_repeatable_pure_commands(tmp_path: Path) -> None:
    invoke, calls = _conforming(tmp_path)

    report = conformance_v3.run(invoke, harness_id="claude-code", target=tmp_path)

    assert report.conforms
    assert {case.name for case in report.cases} >= {
        "provider_info_v3_closed",
        "valid_v3_bundle_accepted",
        "pure_v3_plan_is_exact",
        "pure_v3_validation_is_repeatable",
        "rejects_v3_digest_mismatch",
    }
    assert "apply-operation" not in calls
    assert "launch" not in calls
    assert calls.count("status") == 2


def test_v3_conformance_closes_invalid_provider_info_without_other_calls(tmp_path: Path) -> None:
    calls: list[str] = []

    def invoke(command: str, arguments: Sequence[str]) -> JsonValue:
        del arguments
        calls.append(command)
        return {"protocol_version": 3}

    report = conformance_v3.run(invoke, harness_id="claude-code", target=tmp_path)

    assert not report.conforms
    assert [case.name for case in report.cases] == ["provider_info_v3_closed"]
    assert calls == ["provider-info"]


def test_v3_conformance_refuses_a_profile_without_a_compiler_native_route(
    tmp_path: Path,
) -> None:
    info = _info(harness_id="codex", component_kind="plugin", native_namespace="plugins")

    def invoke(command: str, arguments: Sequence[str]) -> JsonValue:
        del arguments
        if command == "provider-info":
            return info
        if command == "status":
            return {"state": "missing", "target_digest": _digest("a")}
        raise AssertionError(command)

    report = conformance_v3.run(invoke, harness_id="codex", target=tmp_path)

    assert not report.conforms
    failed = {case.name for case in report.failures}
    assert failed == {"declared_native_route_is_compilable"}


def test_cli_v3_conformance_fails_before_spawn_without_network_isolation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = tmp_path / "spawned"
    provider = tmp_path / "provider"
    provider.write_text(
        f"#!/usr/bin/env python3\nopen({str(marker)!r}, 'w').write('yes')\n",
        encoding="utf-8",
    )
    provider.chmod(provider.stat().st_mode | stat.S_IXUSR)
    unavailable = protocol_v2.NetworkCapability(
        enforcement=protocol_v2.NetworkEnforcement.UNAVAILABLE,
        os_name="linux",
        launcher_id=None,
        evidence=("no launcher",),
    )
    monkeypatch.setattr(
        "ai_stp_cli.commands.select.network_launcher.discover_bubblewrap",
        lambda: (None, unavailable),
    )

    with pytest.raises(CliFailure) as caught:
        select.provider_conformance(
            {
                "harness": "claude-code",
                "executable": str(provider),
                "target": str(tmp_path),
                "protocol-version": 3,
            }
        )

    assert caught.value.code == "AI_STP_DEPENDENCY_UNAVAILABLE"
    assert not marker.exists()


def _capabilities() -> protocol_v3.ProviderCapabilities:
    return protocol_v3.parse_capabilities(cast(dict[str, object], _info()))


def _binding(tmp_path: Path) -> bundle_protocol.Binding:
    artifact = tmp_path / "bundle.zip"
    artifact.write_bytes(b"bundle")
    return bundle_protocol.binding(
        artifact,
        bundle_format="ai-stp-bundle/1",
        bundle_digest=_digest("1"),
        artifact_digest=_digest("2"),
        bundle_size=artifact.stat().st_size,
    )


def _plan_answer(
    tmp_path: Path,
    *,
    operation: protocol_v3.Operation = protocol_v3.Operation.INSTALL,
) -> tuple[dict[str, JsonValue], bundle_protocol.Binding, str, str]:
    capabilities = _capabilities()
    bound = _binding(tmp_path)
    expiry = (
        (datetime.now(UTC) + timedelta(minutes=10))
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )
    target_digest = _digest("a")
    bundle_echo: dict[str, JsonValue] = {
        "bundle_format": bound.bundle_format,
        "bundle_digest": bound.bundle_digest,
        "artifact_digest": bound.artifact_digest,
        "bundle_size": bound.bundle_size,
    }
    artifact: dict[str, JsonValue] = {
        "format": "ai-stp-provider-plan/3",
        "protocol_version": protocol_v3.VERSION,
        "provider_id": capabilities.provider_id,
        "provider_version": capabilities.provider_version,
        "provider_build_digest": capabilities.provider_build_digest,
        "provider_release_digest": _digest("d"),
        "operation_id": "operation_test_v3",
        "operation": operation.value,
        "canonical_target": str(tmp_path.resolve()),
        "expected_target_digest": target_digest,
        "projection_profile_digest": capabilities.projection.digest,
        "bundle": bundle_echo,
        "backup_ref": None,
        "permission_profile": None,
        "platform": _platform(),
        "expires_at": expiry,
        "effects": cast(list[JsonValue], ["write exact projection"]),
    }
    digest = digest_canonical(protocol_v3.PLAN_DOMAIN, artifact)
    answer: dict[str, JsonValue] = {
        "state": "planned",
        "plan": artifact,
        "plan_digest": digest,
        "expected_target_digest": target_digest,
        "effects": artifact["effects"],
        **bundle_echo,
    }
    return answer, bound, expiry, digest


def test_v3_plan_load_apply_and_status_require_the_same_exact_identity(tmp_path: Path) -> None:
    answer, bound, expiry, digest = _plan_answer(tmp_path)
    capabilities = _capabilities()
    plan = operation_v3.require_plan(
        answer,
        capabilities=capabilities,
        release_digest=_digest("d"),
        operation_id="operation_test_v3",
        operation=protocol_v3.Operation.INSTALL,
        target=tmp_path,
        expected_target_digest=_digest("a"),
        bundle=bound,
        backup_ref=None,
        permission_profile=None,
        expires_at=expiry,
    )
    plan_path = tmp_path / "plan.json"
    plan_path.write_bytes(canonize(plan.artifact))
    assert operation_v3.load_plan(plan_path, digest) == plan
    applied: dict[str, JsonValue] = {
        "state": "verified",
        "plan_digest": digest,
        "expected_target_digest": _digest("a"),
        "bundle_format": bound.bundle_format,
        "bundle_digest": bound.bundle_digest,
        "artifact_digest": bound.artifact_digest,
        "bundle_size": bound.bundle_size,
    }
    assert operation_v3.require_applied(applied, plan=plan, bundle=bound) == "verified"
    without_echoes: dict[str, JsonValue] = {
        "state": "verified",
        "plan_digest": digest,
        "expected_target_digest": _digest("a"),
        "target_identity_digest": _digest("e"),
        "backup_ref": "slot-000000000001",
    }
    assert operation_v3.require_applied(without_echoes, plan=plan, bundle=bound) == "verified"
    stale: dict[str, JsonValue] = {
        "state": "refused",
        "rejected": True,
        "reason": "stale",
        "detail": "moved",
    }
    assert operation_v3.require_applied(stale, plan=plan, bundle=bound) == "stale"
    status: dict[str, JsonValue] = {
        "state": "managed",
        "target_digest": _digest("e"),
        "drift_state": "verified",
        "protocol_version": 3,
        "provider_id": capabilities.provider_id,
        "provider_version": capabilities.provider_version,
        "provider_build_digest": capabilities.provider_build_digest,
        "provider_release_digest": _digest("d"),
        "provider_plan_digest": digest,
        "projection_profile_digest": capabilities.projection.digest,
        "bundle_digest": bound.bundle_digest,
        "artifact_digest": bound.artifact_digest,
    }
    assert operation_v3.require_verified_status(
        status,
        capabilities=capabilities,
        release_digest=_digest("d"),
        plan=plan,
        bundle=bound,
        operation=protocol_v3.Operation.INSTALL,
    ) == _digest("e")
    nested_status: dict[str, JsonValue] = {
        "state": "managed",
        "target_digest": _digest("e"),
        "protocol_version": protocol_v3.VERSION,
        "provider_id": capabilities.provider_id,
        "harness_id": "claude-code",
        "provider_state": {
            "present": True,
            "readable": True,
            "operation_id": "operation_test_v3",
            "drift_state": "clean",
            "backup_ref": "slot-000000000001",
        },
    }
    assert operation_v3.require_verified_status(
        nested_status,
        capabilities=capabilities,
        release_digest=_digest("d"),
        plan=plan,
        bundle=bound,
        operation=protocol_v3.Operation.INSTALL,
    ) == _digest("e")


def test_every_drift_statement_a_status_carries_has_to_hold(tmp_path: Path) -> None:
    """One fact recorded twice, checked once, is a fail-open (`#431`).

    A v3 status may state drift at the top level and again inside
    `provider_state`. Reading whichever came first meant a release reporting a
    clean top level beside a nested `drifted` verified on the strength of the
    half that happened to be read — and nothing would ever have said so.

    Both spellings of no-drift stay admissible on both, so a release that mixes
    the legacy `verified` with the current `clean` is not caught in a vocabulary
    difference that means nothing. `#431` reported the opposite failure against
    a build predating `c7844cd`, where only `verified` was accepted at all.
    """
    answer, bound, expiry, digest = _plan_answer(tmp_path)
    capabilities = _capabilities()
    plan = operation_v3.require_plan(
        answer,
        capabilities=capabilities,
        release_digest=_digest("d"),
        operation_id="operation_test_v3",
        operation=protocol_v3.Operation.INSTALL,
        target=tmp_path,
        expected_target_digest=_digest("a"),
        bundle=bound,
        backup_ref=None,
        permission_profile=None,
        expires_at=expiry,
    )

    def status(top: str | None, nested: str | None) -> dict[str, JsonValue]:
        held: dict[str, JsonValue] = {
            "state": "managed",
            "target_digest": _digest("e"),
            "protocol_version": protocol_v3.VERSION,
            "provider_id": capabilities.provider_id,
            "provider_plan_digest": digest,
        }
        if top is not None:
            held["drift_state"] = top
        if nested is not None:
            held["provider_state"] = {"drift_state": nested}
        return held

    def verify(held: dict[str, JsonValue]) -> str:
        return operation_v3.require_verified_status(
            held,
            capabilities=capabilities,
            release_digest=_digest("d"),
            plan=plan,
            bundle=bound,
            operation=protocol_v3.Operation.INSTALL,
        )

    for top, nested in (("clean", "clean"), ("verified", "clean"), ("clean", None)):
        assert verify(status(top, nested)) == _digest("e"), (top, nested)

    # The one this exists for: the read half says clean, the other does not.
    for top, nested in (("clean", "drifted"), ("verified", "unknown")):
        with pytest.raises(CliFailure, match="clean managed target"):
            verify(status(top, nested))

    with pytest.raises(CliFailure, match="clean managed target"):
        verify(status(None, None))


def test_v3_plan_and_apply_reject_tamper_and_unknown_state(tmp_path: Path) -> None:
    answer, bound, expiry, _digest_value = _plan_answer(tmp_path)
    capabilities = _capabilities()
    changed = dict(answer)
    changed["plan_digest"] = _digest("0")
    with pytest.raises(CliFailure, match="does not bind"):
        operation_v3.require_plan(
            changed,
            capabilities=capabilities,
            release_digest=_digest("d"),
            operation_id="operation_test_v3",
            operation=protocol_v3.Operation.INSTALL,
            target=tmp_path,
            expected_target_digest=_digest("a"),
            bundle=bound,
            backup_ref=None,
            permission_profile=None,
            expires_at=expiry,
        )
    valid = operation_v3.require_plan(
        answer,
        capabilities=capabilities,
        release_digest=_digest("d"),
        operation_id="operation_test_v3",
        operation=protocol_v3.Operation.INSTALL,
        target=tmp_path,
        expected_target_digest=_digest("a"),
        bundle=bound,
        backup_ref=None,
        permission_profile=None,
        expires_at=expiry,
    )
    with pytest.raises(CliFailure, match="unknown operation state"):
        operation_v3.require_applied(
            {
                "state": "success-ish",
                "plan_digest": valid.digest,
                "expected_target_digest": _digest("a"),
            },
            plan=valid,
            bundle=None,
        )


def test_v3_cached_plan_and_response_validation_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(CliFailure, match="unreadable"):
        operation_v3.load_plan(tmp_path / "missing.json", _digest("1"))
    scalar = tmp_path / "scalar.json"
    scalar.write_text('"not-an-object"', encoding="utf-8")
    with pytest.raises(CliFailure, match="not an object"):
        operation_v3.load_plan(scalar, _digest("1"))

    answer, bound, expiry, _digest_value = _plan_answer(tmp_path)
    capabilities = _capabilities()
    valid = operation_v3.require_plan(
        answer,
        capabilities=capabilities,
        release_digest=_digest("d"),
        operation_id="operation_test_v3",
        operation=protocol_v3.Operation.INSTALL,
        target=tmp_path,
        expected_target_digest=_digest("a"),
        bundle=bound,
        backup_ref=None,
        permission_profile=None,
        expires_at=expiry,
    )
    plan_path = tmp_path / "plan.json"
    plan_path.write_bytes(canonize(valid.artifact))
    with pytest.raises(CliFailure, match="another digest"):
        operation_v3.load_plan(plan_path, _digest("0"))

    for changed, message in (
        ({**answer, "state": "ready"}, "did not return a planned"),
        ({**answer, "plan": None}, "did not return a v3 plan"),
        ({**answer, "effects": []}, "does not enumerate"),
        ({**answer, "expected_target_digest": _digest("0")}, "different target snapshot"),
    ):
        with pytest.raises(CliFailure, match=message):
            operation_v3.require_plan(
                changed,
                capabilities=capabilities,
                release_digest=_digest("d"),
                operation_id="operation_test_v3",
                operation=protocol_v3.Operation.INSTALL,
                target=tmp_path,
                expected_target_digest=_digest("a"),
                bundle=bound,
                backup_ref=None,
                permission_profile=None,
                expires_at=expiry,
            )
    for changed, message in (
        ({"state": "verified", "plan_digest": _digest("0")}, "different v3 plan"),
        (
            {
                "state": "verified",
                "plan_digest": valid.digest,
                "expected_target_digest": _digest("0"),
            },
            "different target snapshot",
        ),
    ):
        with pytest.raises(CliFailure, match=message):
            operation_v3.require_applied(
                cast(dict[str, JsonValue], changed), plan=valid, bundle=None
            )
    with pytest.raises(CliFailure, match="no exact target digest"):
        operation_v3.require_verified_status(
            {"state": "missing", "target_digest": "main"},
            capabilities=capabilities,
            release_digest=_digest("d"),
            plan=valid,
            bundle=None,
            operation=protocol_v3.Operation.REMOVE,
        )


def test_v3_remove_status_requires_managed_state_to_be_gone(tmp_path: Path) -> None:
    answer, bound, expiry, _digest_value = _plan_answer(
        tmp_path, operation=protocol_v3.Operation.REMOVE
    )
    capabilities = _capabilities()
    plan = operation_v3.require_plan(
        answer,
        capabilities=capabilities,
        release_digest=_digest("d"),
        operation_id="operation_test_v3",
        operation=protocol_v3.Operation.REMOVE,
        target=tmp_path,
        expected_target_digest=_digest("a"),
        bundle=bound,
        backup_ref=None,
        permission_profile=None,
        expires_at=expiry,
    )
    assert operation_v3.require_verified_status(
        {"state": "missing", "target_digest": _digest("f")},
        capabilities=capabilities,
        release_digest=_digest("d"),
        plan=plan,
        bundle=None,
        operation=protocol_v3.Operation.REMOVE,
    ) == _digest("f")
    with pytest.raises(CliFailure, match="does not prove managed-state removal"):
        operation_v3.require_verified_status(
            {"state": "managed", "target_digest": _digest("f")},
            capabilities=capabilities,
            release_digest=_digest("d"),
            plan=plan,
            bundle=None,
            operation=protocol_v3.Operation.REMOVE,
        )


def _restore_plan(tmp_path: Path) -> operation_v3.ProviderPlan:
    capabilities = _capabilities()
    expiry = (
        (datetime.now(UTC) + timedelta(minutes=10))
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )
    restore_digest = _digest("e")
    backup_ref = "backup:v3:" + "a" * 32
    artifact: dict[str, JsonValue] = {
        "format": "ai-stp-provider-plan/3",
        "protocol_version": protocol_v3.VERSION,
        "provider_id": capabilities.provider_id,
        "provider_version": capabilities.provider_version,
        "provider_build_digest": capabilities.provider_build_digest,
        "provider_release_digest": _digest("d"),
        "operation_id": "operation_test_v3_restore",
        "operation": protocol_v3.Operation.RESTORE.value,
        "canonical_target": str(tmp_path.resolve()),
        "expected_target_digest": _digest("a"),
        "projection_profile_digest": capabilities.projection.digest,
        "bundle": None,
        "backup_ref": backup_ref,
        "restore_target_digest": restore_digest,
        "permission_profile": None,
        "platform": _platform(),
        "expires_at": expiry,
        "effects": cast(list[JsonValue], ["restore exact BackupRef identity"]),
    }
    digest = digest_canonical(protocol_v3.PLAN_DOMAIN, artifact)
    answer: dict[str, JsonValue] = {
        "state": "planned",
        "plan": artifact,
        "plan_digest": digest,
        "expected_target_digest": _digest("a"),
        "effects": artifact["effects"],
    }
    return operation_v3.require_plan(
        answer,
        capabilities=capabilities,
        release_digest=_digest("d"),
        operation_id="operation_test_v3_restore",
        operation=protocol_v3.Operation.RESTORE,
        target=tmp_path,
        expected_target_digest=_digest("a"),
        bundle=None,
        backup_ref=backup_ref,
        permission_profile=None,
        expires_at=expiry,
    )


def test_v3_restore_status_accepts_exact_backup_identity_without_managed_drift(
    tmp_path: Path,
) -> None:
    capabilities = _capabilities()
    plan = _restore_plan(tmp_path)
    restore_digest = str(plan.artifact["restore_target_digest"])
    unmanaged: dict[str, JsonValue] = {"state": "unmanaged", "target_digest": restore_digest}
    assert (
        operation_v3.require_verified_status(
            unmanaged,
            capabilities=capabilities,
            release_digest=_digest("d"),
            plan=plan,
            bundle=None,
            operation=protocol_v3.Operation.RESTORE,
        )
        == restore_digest
    )
    with pytest.raises(CliFailure, match="exact BackupRef identity"):
        operation_v3.require_verified_status(
            {"state": "unmanaged", "target_digest": _digest("0")},
            capabilities=capabilities,
            release_digest=_digest("d"),
            plan=plan,
            bundle=None,
            operation=protocol_v3.Operation.RESTORE,
        )
    install_answer, bound, expiry, _digest_value = _plan_answer(tmp_path)
    install_plan = operation_v3.require_plan(
        install_answer,
        capabilities=capabilities,
        release_digest=_digest("d"),
        operation_id="operation_test_v3",
        operation=protocol_v3.Operation.INSTALL,
        target=tmp_path,
        expected_target_digest=_digest("a"),
        bundle=bound,
        backup_ref=None,
        permission_profile=None,
        expires_at=expiry,
    )
    with pytest.raises(CliFailure, match="managed installation"):
        operation_v3.require_verified_status(
            unmanaged,
            capabilities=capabilities,
            release_digest=_digest("d"),
            plan=install_plan,
            bundle=bound,
            operation=protocol_v3.Operation.INSTALL,
        )


def test_an_empty_target_says_what_it_did_not_exercise(tmp_path: Path) -> None:
    """A conforming report from an empty directory is a narrower claim.

    Two defect classes only appear against material already in the home: a
    provider that mishandles what is there, and one that refuses a symbolic
    link outside every namespace it declared. Both were found on live homes by
    an implementation that passed every other case here, so a run that cannot
    reach them has to say so rather than report the same `conforms` as a run
    that could.
    """
    empty = tmp_path / "empty-target"
    empty.mkdir()
    invoke, _calls = _conforming(empty)

    report = conformance_v3.run(invoke, harness_id="claude-code", target=empty)

    case = next(item for item in report.cases if item.name == "target_was_populated")
    assert case.passed, case.detail
    assert "target was empty" in case.detail
    # It narrows the claim; it does not fail the provider for the operator's
    # choice of directory.
    assert report.conforms


def test_a_populated_target_requires_status_to_notice(tmp_path: Path) -> None:
    """Existing material must move status off `missing`, or the read is wrong."""
    populated = tmp_path / "populated-target"
    populated.mkdir()
    (populated / "CLAUDE.md").write_text("# already here\n", encoding="utf-8")
    invoke, _calls = _conforming(populated)

    report = conformance_v3.run(invoke, harness_id="claude-code", target=populated)

    case = next(item for item in report.cases if item.name == "target_was_populated")
    # The stub reports `missing` unconditionally, which is exactly the answer a
    # provider must not give for a target that holds something.
    assert not case.passed, case.detail
    assert "still reported" in case.detail


def _declares_software(
    target: Path,
    *,
    artifacts: list[JsonValue] | None,
) -> conformance.Invoker:
    """A provider that declares the program lifecycle, wrapping the conforming stub.

    `artifacts` is what its `software_install` plan puts on the wire. `None`
    stands for the defect this case exists to find: a provider that declares the
    operation and then does not say what bytes it means, leaving the consumer to
    ask the network what the plan should already have named.
    """
    inner, _calls = _conforming(target)
    declared = sorted(
        {item.value for item in protocol_v3.CORE_OPERATIONS}
        | {protocol_v3.Operation.SOFTWARE_INSTALL.value}
    )

    def invoke(command: str, arguments: Sequence[str]) -> JsonValue:
        if command == "provider-info":
            info = cast(dict[str, JsonValue], inner(command, arguments))
            return {**info, "supported_operations": cast(list[JsonValue], declared)}
        if command == "plan-operation":
            supplied = _arguments(arguments)
            if supplied["--operation"] == protocol_v3.Operation.SOFTWARE_INSTALL.value:
                # Route through `install` so the stub builds a well-formed plan,
                # then say it is the software operation it was asked for.
                rerouted = list(arguments)
                rerouted[rerouted.index("--operation") + 1] = protocol_v3.Operation.INSTALL.value
                answer = cast(dict[str, JsonValue], inner(command, rerouted))
                plan = dict(cast(dict[str, JsonValue], answer["plan"]))
                plan["operation"] = protocol_v3.Operation.SOFTWARE_INSTALL.value
                if artifacts is not None:
                    plan["software_artifacts"] = artifacts
                return {
                    **answer,
                    "plan": plan,
                    "plan_digest": digest_canonical(protocol_v3.PLAN_DOMAIN, plan),
                }
        return inner(command, arguments)

    return invoke


def _artifact(**overrides: JsonValue) -> JsonValue:
    complete: dict[str, JsonValue] = {
        "platform": "linux/x86_64",
        "url": "https://registry.example.invalid/opencode-1.18.23.tgz",
        "sha256": _digest("b"),
        "byte_length": 60167326,
        "entry_point": "bin/opencode",
    }
    return {**complete, **overrides}


def test_a_declared_program_lifecycle_names_its_artifact_offline(tmp_path: Path) -> None:
    """Declaring `software_install` obliges the plan to name exact bytes.

    The whole reason the consumer may download without asking anyone is that
    the offline plan already carries `platform`, `url`, `sha256`, `byte_length`
    and `entry_point`. A provider that declares the operation and returns a plan
    without them has moved the identity decision to download time, where no
    plan digest covers it.
    """
    target = tmp_path / "declares"
    target.mkdir()

    report = conformance_v3.run(
        _declares_software(target, artifacts=[_artifact()]),
        harness_id="claude-code",
        target=target,
    )

    case = next(
        item for item in report.cases if item.name == "software_lifecycle_matches_its_declaration"
    )
    assert case.passed, case.detail


def test_a_declared_program_lifecycle_without_artifacts_fails(tmp_path: Path) -> None:
    """The defect: declared, planned, and silent about which bytes it meant."""
    target = tmp_path / "silent"
    target.mkdir()

    report = conformance_v3.run(
        _declares_software(target, artifacts=None),
        harness_id="claude-code",
        target=target,
    )

    case = next(
        item for item in report.cases if item.name == "software_lifecycle_matches_its_declaration"
    )
    assert not case.passed, case.detail
    assert not report.conforms


def test_an_incomplete_software_artifact_is_not_an_identity(tmp_path: Path) -> None:
    """Four of five fields is not an identity: without `sha256` nothing is bound."""
    target = tmp_path / "partial"
    target.mkdir()
    partial = dict(cast(dict[str, JsonValue], _artifact()))
    del partial["sha256"]

    report = conformance_v3.run(
        _declares_software(target, artifacts=[cast(JsonValue, partial)]),
        harness_id="claude-code",
        target=target,
    )

    case = next(
        item for item in report.cases if item.name == "software_lifecycle_matches_its_declaration"
    )
    assert not case.passed, case.detail
    assert "sha256" in case.detail


def test_a_provider_without_the_lifecycle_must_refuse_rather_than_be_skipped(
    tmp_path: Path,
) -> None:
    """Not declaring it is an assertion here, not a pass by default.

    Measured against the shipped `pi-setup-system` 0.0.4: npm resolves the
    dependency closure at install time, so no single artifact has a digest a
    plan could pin ahead of time. Pi therefore declares none of the three and
    refuses with `unsupported_operation`, and that refusal is what this case
    requires. Scoring "did not declare it" as passed is how a case becomes a
    permanent green that reads as coverage.
    """
    target = tmp_path / "core-only"
    target.mkdir()
    invoke, _calls = _conforming(target)

    report = conformance_v3.run(invoke, harness_id="claude-code", target=target)

    case = next(
        item for item in report.cases if item.name == "software_lifecycle_matches_its_declaration"
    )
    assert case.passed, case.detail
    assert "unsupported_operation" in case.detail


def test_the_software_plan_request_names_a_prefix(tmp_path: Path) -> None:
    """The request must carry `--prefix`, or every refusal means the wrong thing.

    A program lives under `--prefix`, not under `--target`. Sending the core
    operation's argv unchanged asks a provider to install a program without
    saying where, and every provider that implements the lifecycle correctly
    refuses that as malformed. Shipped once without this: all six providers that
    declare the lifecycle went red and Pi, the only one without it, went green —
    the case inverted. This pins the argument so the inversion cannot come back
    silently.
    """
    target = tmp_path / "argv"
    target.mkdir()
    seen: list[Sequence[str]] = []
    inner = _declares_software(target, artifacts=[_artifact()])

    def invoke(command: str, arguments: Sequence[str]) -> JsonValue:
        if command == "plan-operation":
            seen.append(tuple(arguments))
        return inner(command, arguments)

    conformance_v3.run(invoke, harness_id="claude-code", target=target)

    software = [call for call in seen if protocol_v3.Operation.SOFTWARE_INSTALL.value in call]
    assert software, "the software plan was never requested"
    for call in software:
        assert "--prefix" in call, f"software plan request without --prefix: {call}"
        prefix = Path(call[call.index("--prefix") + 1])
        assert prefix.is_absolute(), f"--prefix must be absolute, got {prefix}"
        # Named, never created: `plan-operation` is pure, and a directory made
        # here would be one the run has to remove again.
        assert not prefix.exists(), f"conformance created {prefix}"
