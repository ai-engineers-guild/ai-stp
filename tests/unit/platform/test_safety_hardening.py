# pyright: reportUnknownLambdaType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnusedFunction=false, reportUnusedImport=false, reportUnusedVariable=false
"""Unit tests for safety sandbox, metrics, and OSV offline health."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from ai_stp_platform.safety.metrics import record_cli_result, record_scan, reset_metrics, snapshot
from ai_stp_platform.safety.osv_health import osv_db_ready, osv_db_status
from ai_stp_platform.safety.sandbox import (
    detect_sandbox_mode,
    plan_cli_argv,
    reset_sandbox_cache,
    sandbox_status,
)
from ai_stp_platform.safety.types import CheckOutcome, Finding

pytestmark = pytest.mark.platform


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_metrics()
    reset_sandbox_cache()


def test_sandbox_disabled_by_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_STP_SAFETY_SANDBOX", "off")
    reset_sandbox_cache()
    assert detect_sandbox_mode() == "disabled"
    plan = plan_cli_argv(["echo", "hi"], cwd=Path())
    assert plan.mode == "disabled"
    assert plan.argv == ["echo", "hi"]


def test_sandbox_env_only_on_non_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_STP_SAFETY_SANDBOX", "auto")
    monkeypatch.setattr(
        "ai_stp_platform.safety.sandbox.platform.system",
        lambda: "Windows",
    )
    monkeypatch.setattr("ai_stp_platform.safety.sandbox.shutil.which", lambda _n: None)
    reset_sandbox_cache()
    assert detect_sandbox_mode() == "env_only"
    plan = plan_cli_argv(["bandit", "-r", "."], cwd=Path())
    assert plan.mode == "env_only"
    assert plan.argv[0] == "bandit"
    status = sandbox_status()
    assert status["mode"] == "env_only"


def test_sandbox_bwrap_wraps_argv(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AI_STP_SAFETY_SANDBOX", "auto")
    monkeypatch.setattr(
        "ai_stp_platform.safety.sandbox.platform.system",
        lambda: "Linux",
    )
    bwrap = tmp_path / "bwrap"
    bwrap.write_text("", encoding="utf-8")
    tool = tmp_path / "gitleaks"
    tool.write_text("", encoding="utf-8")

    def _which(name: str) -> str | None:
        if name == "bwrap":
            return str(bwrap)
        if name == "gitleaks":
            return str(tool)
        if name == "true":
            return "/bin/true"
        return None

    monkeypatch.setattr("ai_stp_platform.safety.sandbox.shutil.which", _which)
    monkeypatch.setattr(
        "ai_stp_platform.safety.sandbox._probe_bwrap",
        lambda _path: (True, "ok"),
    )
    reset_sandbox_cache()
    cwd = tmp_path / "tree"
    cwd.mkdir()
    plan = plan_cli_argv(["gitleaks", "detect"], cwd=cwd)
    assert plan.mode == "bwrap"
    assert plan.argv[0] == str(bwrap)
    assert "--unshare-net" in plan.argv
    assert str(cwd.resolve()) in plan.argv
    assert str(tool) in plan.argv


def test_sandbox_bwrap_probe_failure_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_STP_SAFETY_SANDBOX", "auto")
    monkeypatch.setattr(
        "ai_stp_platform.safety.sandbox.platform.system",
        lambda: "Linux",
    )
    monkeypatch.setattr(
        "ai_stp_platform.safety.sandbox.shutil.which",
        lambda name: "/usr/bin/bwrap" if name == "bwrap" else None,
    )
    monkeypatch.setattr(
        "ai_stp_platform.safety.sandbox._probe_bwrap",
        lambda _path: (False, "No permissions to create new namespace"),
    )
    reset_sandbox_cache()
    assert detect_sandbox_mode() == "env_only"
    status = sandbox_status()
    assert status["mode"] == "env_only"
    assert "permission" in status["probe"].lower() or "namespace" in status["probe"].lower()


def test_metrics_record_scan_and_cli() -> None:
    reset_metrics()
    outcome = CheckOutcome(
        check_id="secrets_heuristic",
        family="secrets",
        result="failed",
        findings=[
            Finding(
                check_id="secrets_heuristic",
                family="secrets",
                rule_id="x",
                severity="critical",
                title="t",
            )
        ],
    )
    record_scan(profile="standard", wall_ms=12, cache_hit=False, outcomes=[outcome])
    record_scan(profile="standard", wall_ms=0, cache_hit=True, outcomes=[outcome])
    record_cli_result(code=124, duration_ms=25000, sandbox_mode="env_only")
    record_cli_result(code=127, duration_ms=0, sandbox_mode="n/a")
    snap = snapshot()
    assert snap["safety_scan_total"] == 2
    assert snap["safety_scan_cache_hit_total"] == 1
    assert snap["safety_scan_duration_ms_max"] == 12
    assert snap["safety_check_result_total"]["failed"] == 2
    assert snap["safety_finding_total"]["secrets:critical"] == 2
    assert snap["safety_cli_timeout_total"] == 1
    assert snap["safety_cli_missing_total"] == 1
    assert snap["safety_sandbox_mode_total"]["env_only"] == 1


def test_osv_missing_dir_optional(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    missing = tmp_path / "nope"
    monkeypatch.setenv("AI_STP_OSV_OFFLINE_DIR", str(missing))
    monkeypatch.delenv("AI_STP_OSV_REQUIRE_FRESH", raising=False)
    status = osv_db_status()
    assert status["present"] is False
    assert status["reason"] == "directory_missing"
    assert osv_db_ready() is True
    monkeypatch.setenv("AI_STP_OSV_REQUIRE_FRESH", "1")
    assert osv_db_ready() is False


def test_osv_readme_placeholder_not_fresh(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AI_STP_OSV_OFFLINE_DIR", str(tmp_path))
    monkeypatch.delenv("AI_STP_OSV_REQUIRE_FRESH", raising=False)
    (tmp_path / "README").write_text("placeholder\n", encoding="utf-8")
    status = osv_db_status()
    assert status["fresh"] is False
    assert status["reason"] in {"no_files", "no_stamp"}
    monkeypatch.setenv("AI_STP_OSV_REQUIRE_FRESH", "1")
    assert osv_db_ready() is False


def test_osv_fresh_stamp(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AI_STP_OSV_OFFLINE_DIR", str(tmp_path))
    monkeypatch.setenv("AI_STP_OSV_MAX_AGE_HOURS", "36")
    monkeypatch.setenv("AI_STP_OSV_REQUIRE_FRESH", "1")
    pack = tmp_path / "osv-scanner" / "PyPI"
    pack.mkdir(parents=True)
    (pack / "all.zip").write_bytes(b"data")
    stamp = tmp_path / ".ai_stp_osv_refreshed_at"
    stamp.write_text("2026-08-12T00:00:00Z\n", encoding="utf-8")
    status = osv_db_status()
    assert status["present"] is True
    assert status["fresh"] is True
    assert status["reason"] == "ok"
    assert status["file_count"] >= 1
    assert osv_db_ready() is True


def test_osv_invalid_max_age_and_stale_or_empty_stamp_fail_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("AI_STP_OSV_OFFLINE_DIR", str(tmp_path))
    monkeypatch.setenv("AI_STP_OSV_MAX_AGE_HOURS", "not-a-number")
    monkeypatch.setenv("AI_STP_OSV_REQUIRE_FRESH", "yes")
    stamp = tmp_path / ".ai_stp_osv_refreshed_at"
    stamp.write_text("refreshed", encoding="utf-8")

    empty = osv_db_status()
    assert empty["reason"] == "no_files"
    assert empty["fresh"] is False

    pack = tmp_path / "osv-scanner" / "Go"
    pack.mkdir(parents=True)
    (pack / "all.zip").write_bytes(b"zip")
    stale_time = time.time() - (48 * 3600)
    os.utime(stamp, (stale_time, stale_time))
    stale = osv_db_status()
    assert stale["reason"] == "stale"
    assert stale["max_age_hours"] > 0
    assert osv_db_ready() is False
