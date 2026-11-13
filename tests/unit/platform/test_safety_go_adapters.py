"""Native Go report semantics, module coverage and offline prerequisites."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from ai_stp_platform.safety.adapters import gosec, govulncheck
from ai_stp_platform.safety.policy import CHECK_REGISTRY, CheckSpec
from ai_stp_platform.safety.types import ArtifactManifest

pytestmark = pytest.mark.platform


def _spec(name: str) -> CheckSpec:
    return next(spec for spec in CHECK_REGISTRY if spec.check_id == name)


def _module(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "go.mod").write_text("module example.invalid/qualification\n\ngo 1.27.0\n")
    return root


def _database(root: Path) -> Path:
    database = root / "govulncheck"
    (database / "index").mkdir(parents=True)
    for name in ("db.json", "modules.json", "vulns.json"):
        (database / "index" / name).write_text("{}" if name == "db.json" else "[]")
    (database / ".ai_stp_osv_refreshed_at").write_text("fixture")
    return database


def _report(*, files: object = 1, errors: object = None, issues: object = None) -> str:
    return json.dumps({"Golang errors": errors or {}, "Issues": issues, "Stats": {"files": files}})


@pytest.mark.parametrize(
    ("code", "report", "expected", "reason"),
    [
        (0, _report(), "passed", None),
        (
            1,
            _report(errors={"main.go": [{"error": "export data version unsupported"}]}),
            "degraded",
            "analysis_incomplete",
        ),
        (0, _report(files=0), "degraded", "analysis_incomplete"),
        (0, _report(files=True), "degraded", "invalid_report"),
        (0, _report(issues={}), "degraded", "invalid_report"),
        (1, _report(), "degraded", "analysis_incomplete"),
        (0, "not a report", "degraded", "invalid_report"),
    ],
)
def test_gosec_requires_real_analysis(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    code: int,
    report: str,
    expected: str,
    reason: str | None,
) -> None:
    _module(tmp_path)

    def execute(argv: list[str], *, cwd: Path, timeout: float) -> tuple[int, str, str, int]:
        return code, report, "", 7

    monkeypatch.setattr(gosec, "run_cli", execute)
    result = gosec.run(
        tmp_path, ArtifactManifest(component_type="skill", languages={"go"}), _spec("sast_gosec")
    )
    assert result.result == expected
    assert result.findings == []
    assert result.duration_ms == 7
    if reason:
        assert result.detail["reason"] == reason


def test_gosec_retains_findings_when_another_module_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    first = _module(tmp_path / "files" / "a")
    second = _module(tmp_path / "files" / "b")
    visited: list[Path] = []

    def execute(argv: list[str], *, cwd: Path, timeout: float) -> tuple[int, str, str, int]:
        assert argv == ["gosec", "-fmt", "json", "./..."]
        assert 0 < timeout <= _spec("sast_gosec").timeout_seconds
        visited.append(cwd)
        if cwd == second:
            return 1, _report(errors={"main.go": [{"error": "compilation failed"}]}), "", 3
        return (
            1,
            _report(
                issues=[
                    {
                        "rule_id": "G702",
                        "severity": "HIGH",
                        "file": str(first / "main.go"),
                        "code": "PRIVATE_SOURCE",
                        "details": "PRIVATE_SOURCE",
                    }
                ]
            ),
            "",
            2,
        )

    monkeypatch.setattr(gosec, "run_cli", execute)
    result = gosec.run(
        tmp_path, ArtifactManifest(component_type="skill", languages={"go"}), _spec("sast_gosec")
    )
    assert visited == [first, second]
    assert result.result == "degraded"
    assert result.detail["reason"] == "analysis_incomplete"
    assert result.findings[0].rule_id == "g702"
    assert result.findings[0].path == "files/a/main.go"
    assert result.severity_max == "high"
    assert result.duration_ms == 5
    assert "PRIVATE_SOURCE" not in repr(result)


@pytest.mark.parametrize("adapter_name", ["gosec", "govulncheck"])
def test_go_without_module_is_unknown(
    adapter_name: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        pytest.fail("A missing module must not start an analyser.")

    adapter = gosec if adapter_name == "gosec" else govulncheck
    monkeypatch.setattr(adapter, "run_cli", refuse)
    name = "sast_gosec" if adapter is gosec else "sca_govulncheck"
    result = adapter.run(
        tmp_path, ArtifactManifest(component_type="skill", languages={"go"}), _spec(name)
    )
    assert result.result == "not_run"
    assert result.detail["reason"] == "module_manifest_missing"


@pytest.mark.parametrize(
    ("code", "expected", "reason"),
    [
        (0, "passed", None),
        (3, "warning", None),
        (1, "degraded", "tool_error"),
        (124, "degraded", "timeout"),
        (127, "not_run", "tool_missing"),
    ],
)
def test_govulncheck_exit_contract_and_local_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    code: int,
    expected: str,
    reason: str | None,
) -> None:
    root = tmp_path / "cache"
    database = _database(root)
    module = _module(tmp_path / "artifact" / "files")
    monkeypatch.setenv("AI_STP_OSV_OFFLINE_DIR", str(root))
    visited: list[Path] = []

    def execute(argv: list[str], *, cwd: Path, timeout: float) -> tuple[int, str, str, int]:
        assert argv == ["govulncheck", "-db", database.as_uri(), "./..."]
        visited.append(cwd)
        return code, "native output", "compiler diagnostic", 4

    monkeypatch.setattr(govulncheck, "run_cli", execute)
    result = govulncheck.run(
        module.parent,
        ArtifactManifest(component_type="skill", languages={"go"}),
        _spec("sca_govulncheck"),
    )
    assert visited == [module]
    assert result.result == expected
    assert result.severity_max == ("medium" if code == 3 else "info")
    if reason:
        assert result.detail["reason"] == reason
    if code == 1:
        assert result.detail["stderr"] == "compiler diagnostic"


@pytest.mark.parametrize(
    ("state", "reason"),
    [
        ("missing", "offline_db_missing"),
        ("unstamped", "offline_db_unavailable"),
        ("stale", "offline_db_stale"),
    ],
)
def test_govulncheck_never_falls_back_to_network(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    state: str,
    reason: str,
) -> None:
    module = _module(tmp_path / "artifact")
    root = tmp_path / "cache"
    if state != "missing":
        database = _database(root)
        stamp = database / ".ai_stp_osv_refreshed_at"
        if state == "unstamped":
            stamp.unlink()
        else:
            os.utime(stamp, (1, 1))
    monkeypatch.setenv("AI_STP_OSV_OFFLINE_DIR", str(root))

    def refuse(*args: object, **kwargs: object) -> None:
        pytest.fail("An unavailable local database must not start govulncheck.")

    monkeypatch.setattr(govulncheck, "run_cli", refuse)
    result = govulncheck.run(
        module, ArtifactManifest(component_type="skill", languages={"go"}), _spec("sca_govulncheck")
    )
    assert result.result == "not_run"
    assert result.detail["reason"] == reason
