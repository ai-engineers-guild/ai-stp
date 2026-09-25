# pyright: reportPrivateUsage=false, reportPrivateImportUsage=false, reportUnknownLambdaType=false, reportUnknownArgumentType=false
"""OS wakeups must invoke the existing, opt-in due sender safely."""

import plistlib
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_stp_cli.application import heartbeat as heartbeat_app
from ai_stp_cli.application import heartbeat_schedule as schedule
from ai_stp_cli.application import heartbeat_wakeup
from ai_stp_cli.commands import heartbeat as heartbeat_commands
from ai_stp_cli.errors import CliFailure
from ai_stp_contracts.heartbeat import (
    InstallationHeartbeatPolicy,
    InstallationHeartbeatSubscription,
)
from ai_stp_foundation.ids import new_id


def test_tick_claims_only_its_organization(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "registry.sqlite"
    first, second = new_id("organization"), new_id("organization")
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE heartbeat_subscription ("
            "organization_id TEXT PRIMARY KEY, account_id TEXT NOT NULL, "
            "device_id TEXT NOT NULL, next_attempt_at TEXT NOT NULL, "
            "attempts INTEGER NOT NULL DEFAULT 0, last_attempt_at TEXT, "
            "last_success_at TEXT, attempt_token TEXT)"
        )
        for organization in (first, second):
            connection.execute(
                "INSERT INTO heartbeat_subscription "
                "(organization_id, account_id, device_id, next_attempt_at) "
                "VALUES (?, ?, ?, ?)",
                (organization, new_id("account"), new_id("device"), "2026-01-01T00:00:00.000Z"),
            )
    monkeypatch.setattr(heartbeat_app, "configured_path", lambda: path)
    claimed = heartbeat_app._claim_due_subscription(
        datetime(2026, 9, 25, tzinfo=UTC), organization_id=second
    )
    assert claimed is not None and claimed[0] == second
    with sqlite3.connect(path) as connection:
        assert (
            connection.execute(
                "SELECT attempt_token FROM heartbeat_subscription WHERE organization_id = ?",
                (first,),
            ).fetchone()[0]
            is None
        )


def test_windows_task_uses_user_session_and_catch_up(monkeypatch: pytest.MonkeyPatch) -> None:
    organization = new_id("organization")
    scripts: list[str] = []
    monkeypatch.setattr(
        schedule,
        "_target",
        lambda _org: (r"C:\Program Files\Python\python.exe", ["-m", "ai_stp_cli"]),
    )
    monkeypatch.setattr(schedule, "_powershell", scripts.append)
    schedule._windows_install("ai-stp-test", organization)
    assert "-LogonType Interactive -RunLevel Limited" in scripts[0]
    assert "-StartWhenAvailable" in scripts[0]
    assert "-RepetitionInterval (New-TimeSpan -Minutes 1)" in scripts[0]
    assert "@(0, 30)" in scripts[0]
    assert "-MultipleInstances IgnoreNew" in scripts[0]
    assert "C:\\Program Files\\Python\\python.exe" in scripts[0]


def test_windows_target_uses_windowless_python(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(schedule.sys, "platform", "win32")
    monkeypatch.setattr(schedule.sys, "executable", str(tmp_path / "python.exe"))
    with pytest.raises(CliFailure):
        schedule._target(new_id("organization"))
    (tmp_path / "pythonw.exe").touch()
    executable, _args = schedule._target(new_id("organization"))
    assert executable == str(tmp_path / "pythonw.exe")


def test_wsl_task_uses_windowless_host_launcher(monkeypatch: pytest.MonkeyPatch) -> None:
    scripts: list[str] = []
    monkeypatch.setattr(
        schedule,
        "_target",
        lambda _org: ("wsl.exe", ["-d", "Ubuntu-24.04", "--", "/usr/bin/python3"]),
    )
    monkeypatch.setattr(schedule, "_powershell", scripts.append)
    schedule._windows_install("ai-stp-test", new_id("organization"))
    assert "wscript.exe" in scripts[0]
    assert "WScript.Shell" in scripts[0]
    assert "Run" in scripts[0]
    assert ".vbs" in scripts[0]
    schedule._windows_remove("ai-stp-test")
    assert "Remove-Item -LiteralPath $launcher" in scripts[1]


def test_mac_launch_agent_checks_twice_per_minute_and_at_login(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    organization = new_id("organization")
    path = tmp_path / "heartbeat.plist"
    calls: list[list[str]] = []
    monkeypatch.setattr(schedule, "_mac_path", lambda _name: path)
    monkeypatch.setattr(schedule, "_mac_domain", lambda: "gui/1000")
    monkeypatch.setattr(schedule, "_mac_loaded", lambda _name: False)
    monkeypatch.setattr(
        schedule, "_target", lambda _org: ("/usr/bin/python3", ["-m", "ai_stp_cli"])
    )
    monkeypatch.setattr(schedule, "_run", calls.append)
    schedule._mac_install("ai-stp-test", organization)
    payload = plistlib.loads(path.read_bytes())
    assert payload["StartInterval"] == 30
    assert payload["RunAtLoad"] is True
    assert calls == [["launchctl", "bootstrap", "gui/1000", str(path)]]


def test_linux_timer_catches_up_and_runs_as_user(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    organization = new_id("organization")
    service, timer = tmp_path / "heartbeat.service", tmp_path / "heartbeat.timer"
    calls: list[list[str]] = []
    monkeypatch.setattr(schedule, "_linux_paths", lambda _name: (service, timer))
    monkeypatch.setattr(
        schedule, "_target", lambda _org: ("/usr/bin/python3", ["-m", "ai_stp_cli"])
    )
    monkeypatch.setattr(schedule, "_run", calls.append)
    schedule._linux_install("ai-stp-test", organization)
    assert "OnCalendar=*-*-* *:*:00,30" in timer.read_text()
    assert "Persistent=true" in timer.read_text()
    assert "ExecStart=/usr/bin/python3 -m ai_stp_cli" in service.read_text()
    assert calls[-1] == ["systemctl", "--user", "enable", "--now", "heartbeat.timer"]


def test_wsl_uses_host_scheduler_and_named_distro(monkeypatch: pytest.MonkeyPatch) -> None:
    organization = new_id("organization")
    monkeypatch.setattr(schedule, "_wsl", lambda: True)
    monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu-24.04")
    monkeypatch.setattr(schedule.getpass, "getuser", lambda: "alice")
    executable, args = schedule._target(organization)
    assert executable == "wsl.exe"
    assert args[:6] == ["-d", "Ubuntu-24.04", "-u", "alice", "--", schedule.sys.executable]
    assert args[6:9] == ["-m", "ai_stp_cli.application.heartbeat_wakeup", organization]


def test_wakeup_restores_enrolled_xdg_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    from ai_stp_cli import app

    seen: list[list[str]] = []
    monkeypatch.setattr(app, "main", lambda args: seen.append(args) or 0)
    monkeypatch.setenv("XDG_CONFIG_HOME", "/prior/config")
    monkeypatch.setenv("XDG_DATA_HOME", "/prior/data")
    monkeypatch.delenv("AI_STP_FORCE_FILE_CREDENTIAL_STORE", raising=False)
    organization = new_id("organization")
    assert heartbeat_wakeup.run([organization, "/private/config", "/private/data", "1"]) == 0
    assert schedule.os.environ["XDG_CONFIG_HOME"] == "/private/config"
    assert schedule.os.environ["XDG_DATA_HOME"] == "/private/data"
    assert schedule.os.environ["AI_STP_FORCE_FILE_CREDENTIAL_STORE"] == "1"
    assert seen == [["heartbeat", "tick", "--organization", organization, "--json"]]


def test_enable_registers_before_opt_in_and_disable_opts_out_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization = new_id("organization")
    events: list[str] = []
    held = SimpleNamespace(account_id=new_id("account"), device_id=new_id("device"))
    monkeypatch.setattr(heartbeat_commands.cloud_auth, "required", lambda _reason: held)
    monkeypatch.setattr(heartbeat_commands, "endpoint", lambda: object())
    monkeypatch.setattr(
        heartbeat_commands.heartbeat,
        "policy",
        lambda *_args: InstallationHeartbeatPolicy(organization_id=organization),
    )
    monkeypatch.setattr(schedule, "install", lambda _org: events.append("install"))
    monkeypatch.setattr(schedule, "remove", lambda _org: events.append("remove"))
    monkeypatch.setattr(
        heartbeat_commands.heartbeat,
        "enable_subscription",
        lambda *_args, **_kwargs: (
            events.append("opt-in")
            or InstallationHeartbeatSubscription(organization_id=organization, enabled=True)
        ),
    )
    monkeypatch.setattr(
        heartbeat_commands.heartbeat,
        "disable_subscription",
        lambda *_args: events.append("opt-out"),
    )
    monkeypatch.setattr(
        heartbeat_commands.heartbeat,
        "subscription_status",
        lambda *_args: InstallationHeartbeatSubscription(
            organization_id=organization, enabled=False, scheduler_registered=False
        ),
    )
    heartbeat_commands.enable({"organization": organization})
    heartbeat_commands.disable({"organization": organization})
    assert events == ["install", "opt-in", "opt-out", "remove"]
