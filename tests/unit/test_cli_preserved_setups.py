"""Preserved setups keep stable identities and require real recovery evidence."""

import os
import subprocess
import sys
from collections.abc import Sequence
from contextlib import closing
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

from ai_stp_cli.commands import install
from ai_stp_cli.commands import preserved_setups as commands
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import installation, passports, preserved_setups, project_passport
from ai_stp_cli.local.database import configured_path, open_registry
from ai_stp_cli.local.passports import moment
from ai_stp_cli.provider import conformance, invocation
from ai_stp_cli.provider.status import BackupObservation, NativeSnapshotObservation
from ai_stp_contracts.machine_help import InstallationView
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.ids import new_id


def _capture(target: Path) -> tuple[installation.Plan, dict[str, JsonValue], BackupObservation]:
    captured_at = moment()
    identity = "sha256:" + sha256(b"original").hexdigest()
    with closing(open_registry(configured_path())) as connection:
        plan = installation.propose(
            connection,
            action="backup",
            author=new_id("account"),
            target_id=f"{new_id('project')}:claude-code",
            expected_target_digest=identity,
            provider_version="1.0.0",
            effects=("preserve the complete native setup",),
            recovery_action="restore the captured setup",
            idempotency_key=new_id("operation"),
            at=captured_at,
            expires_at="2099-01-01T00:00:00.000Z",
            provider_target=str(target),
        )
    snapshot = NativeSnapshotObservation(
        identity, plan.operation_id, ("skills",), (), "verified", "matches"
    )
    artifact: dict[str, JsonValue] = {
        "native_capture": {
            "roots": ["skills"],
            "excluded": [],
            "current_digest": identity,
            "restore_digest": None,
        }
    }
    observed = BackupObservation("slot-000000000001", True, "preserved native setup", snapshot)
    return plan, artifact, observed


def test_preserved_identity_survives_reopening_and_retry(tmp_path: Path) -> None:
    plan, artifact, observed = _capture(tmp_path)
    with closing(open_registry(configured_path())) as connection:
        saved = preserved_setups.register(
            connection,
            plan=plan,
            artifact=artifact,
            observed=observed,
            provider_id="claude-code",
            at=moment(),
        )
    with closing(open_registry(configured_path())) as connection:
        repeated = preserved_setups.register(
            connection,
            plan=plan,
            artifact=artifact,
            observed=observed,
            provider_id="claude-code",
            at=moment(),
        )
        assert repeated == saved
        assert preserved_setups.held(connection, saved.stable_id) == saved
        assert len(preserved_setups.all_saved(connection)) == 1
    listed = commands.list_saved({}).payload.setups
    assert [item.stable_id for item in listed] == [saved.stable_id]
    assert listed[0].verification == "recorded_verified"
    assert listed[0].target_state == "not_observed"


@pytest.mark.parametrize(
    "defect", ["missing", "unheld", "corrupt", "wrong_operation", "wrong_digest", "wrong_base"]
)
def test_unproven_backup_cannot_become_a_preserved_setup(tmp_path: Path, defect: str) -> None:
    plan, artifact, observed = _capture(tmp_path)
    snapshot = observed.native_snapshot
    assert snapshot is not None
    if defect == "missing":
        observed = replace(observed, native_snapshot=None)
    elif defect == "unheld":
        observed = replace(observed, held=False)
    elif defect == "corrupt":
        observed = replace(observed, native_snapshot=replace(snapshot, verification="unavailable"))
    elif defect == "wrong_base":
        observed = replace(observed, native_snapshot=replace(snapshot, base_root="parent"))
    elif defect == "wrong_operation":
        observed = replace(
            observed, native_snapshot=replace(snapshot, operation_id=new_id("operation"))
        )
    else:
        observed = replace(
            observed,
            native_snapshot=replace(snapshot, digest="sha256:" + sha256(b"other").hexdigest()),
        )
    with closing(open_registry(configured_path())) as connection:
        with pytest.raises(CliFailure, match="recovery evidence"):
            preserved_setups.register(
                connection,
                plan=plan,
                artifact=artifact,
                observed=observed,
                provider_id="claude-code",
                at=moment(),
            )
        assert preserved_setups.all_saved(connection) == ()


@pytest.mark.parametrize("initially_empty", [False, True])
@pytest.mark.parametrize("lost_response", [False, True])
def test_real_provider_preserved_setup_returns_by_identity_after_restart(
    tmp_path: Path,
    initially_empty: bool,
    lost_response: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = os.environ.get("AI_STP_CLAUDE_PROVIDER_V3")
    if executable is None:
        pytest.skip("set AI_STP_CLAUDE_PROVIDER_V3 for complete native lifecycle evidence")
    target = tmp_path / "native-target"
    target.mkdir()
    if not initially_empty:
        (target / "skills" / "empty").mkdir(parents=True)
        (target / "skills" / "own.py").write_bytes(b"print('original')\n")
        (target / "CLAUDE.md").write_bytes(b"# original\n")
        (target / "plugins" / "cache" / "own").mkdir(parents=True)
        (target / "plugins" / "cache" / "own" / "tool.js").write_bytes(b"original plugin\n")
        (target / "plugins" / "installed_plugins.json").write_bytes(b'{"plugins":{}}\n')
        (target / "hooks").mkdir()
        (target / "hooks" / "before.sh").write_bytes(b"echo original hook\n")
    with closing(open_registry(configured_path())) as connection:
        device_id = new_id("device")
        passports.init_developer(connection, device_id=device_id)
        passports.ensure_device(connection, device_id=device_id)
        project = project_passport.scan(connection, tmp_path)
        project_passport.record(connection, project, device_id=device_id)
    parameters: dict[str, object] = {
        "project": project.stable_id,
        "harness": "claude-code",
        "target": str(target),
        "provider": executable,
        "unverified-provider": True,
    }

    def apply_plan(planned: InstallationView) -> InstallationView:
        install.approve({"operation": planned.operation_id, "plan-digest": planned.plan_digest})
        result = install.apply({"operation": planned.operation_id, "provider": executable}).payload
        assert result.state == "verified"
        return result

    planned = commands.preserve_plan(parameters).payload
    if lost_response:
        real_invoker = invocation.provider_invoker
        calls: list[str] = []

        def interrupted_invoker(
            executable: str,
            target: str,
            version: int,
            *,
            unisolated_reason: str | None = None,
            writable: tuple[Path, ...] = (),
        ) -> conformance.Invoker:
            invoke = real_invoker(
                executable, target, version, unisolated_reason=unisolated_reason, writable=writable
            )

            def interrupted(command: str, arguments: Sequence[str]) -> JsonValue:
                answer = invoke(command, arguments)
                calls.append(command)
                if command == "apply-operation":
                    raise TimeoutError("the effect completed but its response was lost")
                return answer

            return interrupted

        with monkeypatch.context() as fault:
            fault.setattr(invocation, "provider_invoker", interrupted_invoker)
            with pytest.raises(CliFailure) as failed:
                apply_plan(planned)
            assert failed.value.code == "AI_STP_TIMEOUT_UNCONFIRMED"
            original = install.recover_preserved(
                {"operation": planned.operation_id, "provider": executable}
            ).payload
            repeated = install.recover_preserved(
                {"operation": planned.operation_id, "provider": executable}
            ).payload
        assert calls.count("apply-operation") == 1
        assert "recover-operation" not in calls
        assert original.state == "partial"
        assert repeated.preserved_setup_id == original.preserved_setup_id
    else:
        original = apply_plan(planned)
    assert original.preserved_setup_id is not None
    fresh = subprocess.run(
        [sys.executable, "-m", "ai_stp_cli", "setup", "preserved", "list", "--json"],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    assert original.preserved_setup_id in fresh.stdout
    (target / "skills").mkdir(exist_ok=True)
    (target / "skills" / "new.sh").write_bytes(b"echo current\n")
    (target / "CLAUDE.md").write_bytes(b"# current\n")
    (target / "plugins" / "cache" / "new").mkdir(parents=True)
    (target / "plugins" / "cache" / "new" / "tool.js").write_bytes(b"new plugin\n")
    (target / "plugins" / "data").mkdir(parents=True)
    (target / "plugins" / "data" / "session.txt").write_bytes(b"latest plugin runtime\n")
    restored = apply_plan(
        commands.restore_plan(
            {
                "preserved-setup": original.preserved_setup_id,
                "provider": executable,
                "unverified-provider": True,
            }
        ).payload
    )
    assert isinstance(restored, InstallationView)
    assert restored.preserved_setup_id is not None
    assert not (target / "skills" / "new.sh").exists()
    assert not (target / "plugins" / "cache" / "new").exists()
    assert (target / "plugins" / "data" / "session.txt").read_bytes() == b"latest plugin runtime\n"
    if initially_empty:
        assert not (target / "CLAUDE.md").exists()
        assert not (target / "skills").exists()
    else:
        assert (target / "CLAUDE.md").read_bytes() == b"# original\n"
        assert (target / "skills" / "empty").is_dir()
        assert (
            target / "plugins" / "cache" / "own" / "tool.js"
        ).read_bytes() == b"original plugin\n"
        assert (target / "hooks" / "before.sh").read_bytes() == b"echo original hook\n"
    observed = commands.show(
        {"setup": original.preserved_setup_id, "provider": executable, "unverified-provider": True}
    ).payload
    assert observed.verification == "verified"
    assert observed.target_state == "matches"
    apply_plan(
        commands.restore_plan(
            {
                "preserved-setup": restored.preserved_setup_id,
                "provider": executable,
                "unverified-provider": True,
            }
        ).payload
    )
    assert (target / "skills" / "new.sh").read_bytes() == b"echo current\n"


@pytest.mark.parametrize(
    ("harness", "provider_env", "paths", "companion"),
    [
        (
            "claude-code",
            "AI_STP_CLAUDE_PROVIDER_V3",
            ("plugins/installed_plugins.json", ".claude.json", "keybindings.json"),
            False,
        ),
        (
            "claude-code",
            "AI_STP_CLAUDE_PROVIDER_V3",
            ("plugins/installed_plugins.json", ".claude.json"),
            True,
        ),
        (
            "codex",
            "AI_STP_CODEX_PROVIDER_V3",
            ("AGENTS.override.md", "skills/custom/SKILL.md", "plugins/cache/custom/plugin.json"),
            False,
        ),
        (
            "grok-build",
            "AI_STP_GROK_BUILD_PROVIDER_V3",
            ("plugins/known_marketplaces.json", "installed-plugins/custom/plugin.json", "lsp.json"),
            False,
        ),
        (
            "opencode",
            "AI_STP_OPENCODE_PROVIDER_V3",
            ("opencode.jsonc", "plugin/custom.js", "skill/custom/SKILL.md", "tui.jsonc"),
            False,
        ),
        (
            "pi",
            "AI_STP_PI_PROVIDER_V3",
            ("models.json", "keybindings.json", "npm/custom/package.json"),
            False,
        ),
        (
            "cursor",
            "AI_STP_CURSOR_PROVIDER_V3",
            ("plugins/registry.json", "plugins/cache/custom/plugin.json", "sandbox.json"),
            False,
        ),
        (
            "antigravity",
            "AI_STP_ANTIGRAVITY_PROVIDER_V3",
            ("config/config.json", "config/import_manifest.json", "config/workflows/custom.md"),
            False,
        ),
    ],
)
def test_real_estate_returns_configuration_outside_installation_ownership(
    tmp_path: Path,
    harness: str,
    provider_env: str,
    paths: tuple[str, ...],
    companion: bool,
) -> None:
    executable = os.environ.get(provider_env)
    if executable is None:
        pytest.skip(f"set {provider_env} for native preservation evidence")
    target = tmp_path / (".claude" if companion else "native-target")
    target.mkdir()
    members = [target / name for name in paths]
    if companion:
        members.append(tmp_path / ".claude.json")
    for member in members:
        member.parent.mkdir(parents=True, exist_ok=True)
        member.write_bytes(b'{"original":true}\n')
        if os.name != "nt":
            member.chmod(0o640)
    native_directory = (
        target
        / {
            "claude-code": "plugins",
            "codex": "plugins",
            "grok-build": "installed-plugins",
            "opencode": "plugin",
            "pi": "npm",
            "cursor": "plugins",
            "antigravity": "config/workflows",
        }[harness]
    )
    extra = native_directory / "new-native-file"
    empty = native_directory / "empty-directory"
    empty.mkdir()
    unrelated = tmp_path / "unrelated.md"
    unrelated.write_bytes(b"unrelated bytes\n")
    with closing(open_registry(configured_path())) as connection:
        device_id = new_id("device")
        passports.init_developer(connection, device_id=device_id)
        passports.ensure_device(connection, device_id=device_id)
        project = project_passport.scan(connection, tmp_path)
        project_passport.record(connection, project, device_id=device_id)

    def apply(planned: InstallationView) -> InstallationView:
        install.approve({"operation": planned.operation_id, "plan-digest": planned.plan_digest})
        result = install.apply({"operation": planned.operation_id, "provider": executable}).payload
        assert result.state == "verified"
        return result

    original = apply(
        commands.preserve_plan(
            {
                "project": project.stable_id,
                "harness": harness,
                "target": str(target),
                "provider": executable,
                "unverified-provider": True,
            }
        ).payload
    )
    assert original.preserved_setup_id is not None
    for member in members:
        member.write_bytes(b'{"edited":true}\n')
        if os.name != "nt":
            member.chmod(0o600)
    empty.rmdir()
    extra.write_bytes(b"new native contribution\n")
    restored = apply(
        commands.restore_plan(
            {
                "preserved-setup": original.preserved_setup_id,
                "provider": executable,
                "unverified-provider": True,
            }
        ).payload
    )
    assert restored.preserved_setup_id != original.preserved_setup_id
    assert empty.is_dir()
    assert not extra.exists()
    assert unrelated.read_bytes() == b"unrelated bytes\n"
    for member in members:
        assert member.read_bytes() == b'{"original":true}\n'
        if os.name != "nt":
            assert member.stat().st_mode & 0o777 == 0o640
    observed = commands.show(
        {"setup": original.preserved_setup_id, "provider": executable, "unverified-provider": True}
    ).payload
    assert observed.verification == "verified" and observed.target_state == "matches"
    assert observed.base_root == ("parent" if companion else "target")
    apply(
        commands.restore_plan(
            {
                "preserved-setup": restored.preserved_setup_id,
                "provider": executable,
                "unverified-provider": True,
            }
        ).payload
    )
    assert extra.read_bytes() == b"new native contribution\n"
    assert not empty.exists()
    for member in members:
        assert member.read_bytes() == b'{"edited":true}\n'


@pytest.mark.parametrize(
    ("harness", "provider_env", "scope", "relative"),
    [
        ("codex", "AI_STP_CODEX_PROVIDER_V3", "project", "AGENTS.override.md"),
        ("grok-build", "AI_STP_GROK_BUILD_PROVIDER_V3", "user_root", "commands/custom.md"),
        (
            "antigravity",
            "AI_STP_ANTIGRAVITY_PROVIDER_V3",
            "project",
            ".agent/skills/custom/SKILL.md",
        ),
    ],
)
def test_real_scoped_capture_keeps_declined_installation_routes(
    tmp_path: Path, harness: str, provider_env: str, scope: str, relative: str
) -> None:
    executable = os.environ.get(provider_env)
    if executable is None:
        pytest.skip(f"set {provider_env} for scoped native preservation evidence")
    target = tmp_path / "scoped-target"
    target.mkdir()
    member = target / relative
    member.parent.mkdir(parents=True, exist_ok=True)
    member.write_bytes(b"original local override\n")
    with closing(open_registry(configured_path())) as db:
        device = new_id("device")
        passports.init_developer(db, device_id=device)
        passports.ensure_device(db, device_id=device)
        project = project_passport.scan(db, tmp_path)
        project_passport.record(db, project, device_id=device)

    def apply(planned: InstallationView) -> InstallationView:
        install.approve({"operation": planned.operation_id, "plan-digest": planned.plan_digest})
        result = install.apply({"operation": planned.operation_id, "provider": executable}).payload
        assert result.state == "verified"
        return result

    original = apply(
        commands.preserve_plan(
            {
                "project": project.stable_id,
                "harness": harness,
                "target": str(target),
                "scope": scope,
                "provider": executable,
                "unverified-provider": True,
            }
        ).payload
    )
    assert original.preserved_setup_id is not None
    member.write_bytes(b"edited local override\n")
    apply(
        commands.restore_plan(
            {
                "preserved-setup": original.preserved_setup_id,
                "provider": executable,
                "unverified-provider": True,
            }
        ).payload
    )
    assert member.read_bytes() == b"original local override\n"
    observed = commands.show(
        {"setup": original.preserved_setup_id, "provider": executable, "unverified-provider": True}
    ).payload
    assert observed.target_scope == scope
    assert observed.target_state == "matches"


@pytest.mark.parametrize("defect", ["sibling", "ancestor", "provider", "scope", "base_type"])
def test_companion_binding_cannot_expand_to_arbitrary_parent_state(
    tmp_path: Path, defect: str
) -> None:
    from ai_stp_cli.provider import operation_v3, protocol_v3

    native: dict[str, JsonValue] = {
        "base_root": "parent",
        "roots": [".claude/settings.json", ".claude.json"],
        "excluded": [],
        "current_digest": "sha256:" + sha256(b"snapshot").hexdigest(),
        "restore_digest": None,
    }
    artifact: dict[str, JsonValue] = {
        "native_capture": native,
        "provider_id": "claude-setup-system",
        "canonical_target": str(tmp_path / ".claude"),
        "target_scope": None,
    }
    operation_v3.require_native_capture(
        artifact, operation=protocol_v3.Operation.BACKUP, capture_mode="complete_native"
    )
    if defect == "sibling":
        native["roots"] = [".ssh"]
    elif defect == "ancestor":
        native["roots"] = ["../settings.json"]
    elif defect == "provider":
        artifact["provider_id"] = "codex-setup-system"
    elif defect == "scope":
        artifact["target_scope"] = "project"
    else:
        native["base_root"] = {}
    with pytest.raises(CliFailure) as refused:
        operation_v3.require_native_capture(
            artifact, operation=protocol_v3.Operation.BACKUP, capture_mode="complete_native"
        )
    assert refused.value.code == "AI_STP_PRECONDITION_FAILED"
