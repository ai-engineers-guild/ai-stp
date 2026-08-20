# pyright: reportUnknownLambdaType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnusedFunction=false, reportUnusedImport=false, reportUnusedVariable=false
"""OSV adapter uses local cache env and honest offline-db missing reasons."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from ai_stp_platform.safety.adapters import osv as osv_adapter
from ai_stp_platform.safety.policy import CheckSpec, SafetyProfile
from ai_stp_platform.safety.types import ArtifactManifest

pytestmark = pytest.mark.platform


def _spec() -> CheckSpec:
    return CheckSpec(
        check_id="sca_osv",
        family="sca",
        mandatory=False,
        timeout_seconds=10,
        stage=4,
        kinds=frozenset({"component"}),
        languages=frozenset(),
        requires_any_flag=frozenset({"manifests"}),
        profiles=frozenset({SafetyProfile.STANDARD, SafetyProfile.STRICT}),
    )


def _manifest() -> ArtifactManifest:
    return ArtifactManifest(component_type="mcp", flags={"manifests"}, text_files=[])


def test_offline_db_has_data_detects_all_zip(tmp_path: Path) -> None:
    pack = tmp_path / "osv-scanner" / "PyPI"
    pack.mkdir(parents=True)
    (pack / "all.zip").write_bytes(b"zip")
    assert osv_adapter.offline_db_has_data(tmp_path) is True
    empty = tmp_path / "empty"
    empty.mkdir()
    (empty / "README").write_text("x", encoding="utf-8")
    assert osv_adapter.offline_db_has_data(empty) is False

    legacy = tmp_path / "legacy" / "osv-scanner" / "Go"
    legacy.mkdir(parents=True)
    (legacy / "vulns.zip").write_bytes(b"zip")
    assert osv_adapter.offline_db_has_data(tmp_path / "legacy") is True


def test_resolve_offline_cache_uses_configured_then_existing_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    configured = tmp_path / "configured"
    monkeypatch.setenv("AI_STP_OSV_OFFLINE_DIR", str(configured))
    assert osv_adapter.resolve_offline_cache_dir() == configured

    monkeypatch.delenv("AI_STP_OSV_OFFLINE_DIR")
    default = tmp_path / "default"
    default.mkdir()
    monkeypatch.setattr(osv_adapter, "_DEFAULT_OFFLINE", default)
    assert osv_adapter.resolve_offline_cache_dir() == default

    monkeypatch.setattr(osv_adapter, "_DEFAULT_OFFLINE", tmp_path / "absent")
    assert osv_adapter.resolve_offline_cache_dir() is None


def test_artifact_without_manifests_is_not_applicable(tmp_path: Path) -> None:
    manifest = ArtifactManifest(component_type="skill", flags=set(), text_files=[])
    out = osv_adapter.run(tmp_path, manifest, _spec())
    assert out.result == "not_applicable"


def test_missing_tool_is_tool_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AI_STP_OSV_OFFLINE_DIR", str(tmp_path))
    monkeypatch.setattr(osv_adapter, "which", lambda _n: None)
    out = osv_adapter.run(tmp_path, _manifest(), _spec())
    assert out.result == "not_run"
    assert out.detail.get("reason") == "tool_missing"


def test_present_tool_empty_offline_dir_is_offline_db_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("AI_STP_OSV_OFFLINE_DIR", str(tmp_path))
    (tmp_path / "README").write_text("placeholder\n", encoding="utf-8")
    monkeypatch.setattr(osv_adapter, "which", lambda _n: "/opt/safety-bin/osv-scanner")
    out = osv_adapter.run(tmp_path, _manifest(), _spec())
    assert out.result == "not_run"
    assert out.detail.get("reason") == "offline_db_missing"
    assert out.detail.get("cache_env_name") == "OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY"
    assert out.detail.get("offline_dir") == str(tmp_path)


def test_offline_scan_sets_cache_env_and_does_not_pass_dir_as_scan_target(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pack = tmp_path / "osv-scanner" / "npm"
    pack.mkdir(parents=True)
    (pack / "all.zip").write_bytes(b"zip")
    monkeypatch.setenv("AI_STP_OSV_OFFLINE_DIR", str(tmp_path))
    monkeypatch.setattr(osv_adapter, "which", lambda _n: "/opt/safety-bin/osv-scanner")

    captured: list[list[str]] = []

    def fake_run_cli(argv: list[str], *, cwd: Path, timeout: float) -> tuple[int, str, str, int]:
        del cwd, timeout
        captured.append(list(argv))
        return 0, "", "", 12

    monkeypatch.setattr(osv_adapter, "run_cli", fake_run_cli)
    tree = tmp_path / "tree"
    tree.mkdir()
    out = osv_adapter.run(tree, _manifest(), _spec())
    assert out.result == "passed"
    assert captured, "expected run_cli invocation"
    argv = captured[0]
    # Offline dir must not appear as a scan path after --offline-vulnerabilities.
    assert str(tmp_path) not in argv or argv[-1] == str(tree) or "-r" in argv
    if "--offline-vulnerabilities" in argv:
        idx = argv.index("--offline-vulnerabilities")
        # Next token must not be the offline dir path
        if idx + 1 < len(argv):
            assert argv[idx + 1] != str(tmp_path)
            assert argv[idx + 1] != str(tmp_path.resolve())
    assert os.environ.get("OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY") == str(tmp_path.resolve())
    assert out.detail.get("offline") is True
    assert out.detail.get("cache_env_name") == "OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY"


@pytest.mark.parametrize(
    ("responses", "expected_result", "expected_reason"),
    [
        ([(127, "", "missing", 1), (127, "", "missing", 2)], "not_run", "tool_missing"),
        (
            [(1, "", "no offline database found", 3)],
            "not_run",
            "offline_db_unavailable",
        ),
        ([(1, "", "vulnerability GHSA-test", 4)], "warning", None),
    ],
)
def test_offline_scan_failure_semantics_are_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    responses: list[tuple[int, str, str, int]],
    expected_result: str,
    expected_reason: str | None,
) -> None:
    pack = tmp_path / "osv-scanner" / "PyPI"
    pack.mkdir(parents=True)
    (pack / "all.zip").write_bytes(b"zip")
    tree = tmp_path / "tree"
    tree.mkdir()
    monkeypatch.setenv("AI_STP_OSV_OFFLINE_DIR", str(tmp_path))
    monkeypatch.setattr(osv_adapter, "which", lambda _name: "/opt/safety-bin/osv-scanner")

    remaining = list(responses)

    def fake_run_cli(argv: list[str], *, cwd: Path, timeout: float) -> tuple[int, str, str, int]:
        del argv, cwd, timeout
        return remaining.pop(0)

    monkeypatch.setattr(osv_adapter, "run_cli", fake_run_cli)
    out = osv_adapter.run(tree, _manifest(), _spec())

    assert out.result == expected_result
    if expected_reason is None:
        assert out.findings and out.findings[0].rule_id == "osv"
    else:
        assert out.detail["reason"] == expected_reason
