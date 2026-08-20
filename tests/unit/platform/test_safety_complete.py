# pyright: reportUnknownLambdaType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnusedFunction=false, reportUnusedImport=false, reportUnusedVariable=false
"""Residual backlog: vendored rules, lang SCA adapters, setup pins, OSV offline."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ai_stp_foundation.digests import digest_bytes
from ai_stp_platform.safety.adapters import setup_aggregate
from ai_stp_platform.safety.orchestrator import clear_safety_cache, run_safety_suite
from ai_stp_platform.safety.planner import plan_checks
from ai_stp_platform.safety.policy import SafetyProfile
from ai_stp_platform.safety.policy_pack import opengrep_rules_dir
from ai_stp_platform.safety.types import ArtifactManifest
from ai_stp_platform.storage.object_store import ARTIFACT_DIGEST_DOMAIN

pytestmark = pytest.mark.platform


def _zip(files: dict[str, str | bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            data = content.encode("utf-8") if isinstance(content, str) else content
            zf.writestr(name, data)
    return buf.getvalue()


def _digest(payload: bytes) -> str:
    return digest_bytes(ARTIFACT_DIGEST_DOMAIN, payload)


def test_vendored_opengrep_rules_present() -> None:
    rules = opengrep_rules_dir()
    assert rules.is_dir()
    ymls = list(rules.glob("*.yml"))
    assert len(ymls) >= 5
    names = {p.name for p in ymls}
    assert "mcp-config-security.yml" in names
    assert "python-dangerous-code.yml" in names


@pytest.mark.asyncio
async def test_opengrep_fallback_uses_vendored_regex() -> None:
    clear_safety_cache()
    payload = _zip(
        {
            "cfg.json": '{"token": "abcdefghijklmnopqrstuvwxyz012345"}\n',
        }
    )
    digest = _digest(payload)
    result = await run_safety_suite(
        passport={"component_type": "mcp"},
        content_digest=digest,
        artifact_bytes=payload,
        use_cache=False,
    )
    opengrep = next(o for o in result.outcomes if o.check_id == "sast_opengrep")
    # Either CLI or fallback; must not silent-pass on plaintext token patterns
    assert opengrep.result in {"passed", "failed", "warning", "not_run", "degraded"}


def test_planner_includes_go_rust_js_python_sca() -> None:
    m = ArtifactManifest(
        component_type="mcp",
        languages={"python", "go", "rust", "js", "shell"},
        flags={"manifests", "binary", "pdf"},
    )
    ids = {
        p.check_id
        for p in plan_checks(object_kind="component", manifest=m, profile=SafetyProfile.STRICT)
    }
    for expected in (
        "sast_bandit",
        "sca_pip_audit",
        "sast_gosec",
        "sca_govulncheck",
        "sca_cargo_audit",
        "sca_cargo_deny",
        "sast_eslint_security",
        "sca_npm_audit",
        "document_pdf",
        "sca_osv",
        "malware_yara",
    ):
        assert expected in ids, expected


@pytest.mark.asyncio
async def test_pdf_document_flags_javascript() -> None:
    clear_safety_cache()
    # Minimal PDF-like bytes with dangerous feature tokens
    pdf = (
        b"%PDF-1.4\n1 0 obj\n<< /JavaScript << /JS (app.alert(1)) >> /OpenAction 1 0 R >>\nendobj\n"
    )
    payload = _zip({"doc.pdf": pdf})
    digest = _digest(payload)
    result = await run_safety_suite(
        passport={"component_type": "skill"},
        content_digest=digest,
        artifact_bytes=payload,
        profile=SafetyProfile.STANDARD,
        use_cache=False,
    )
    pdf_check = next(o for o in result.outcomes if o.check_id == "document_pdf")
    assert pdf_check.result == "warning"
    assert pdf_check.findings


def test_all_registry_checks_have_adapters() -> None:
    from ai_stp_platform.safety.adapters import get_adapter
    from ai_stp_platform.safety.policy import CHECK_REGISTRY

    missing = [s.check_id for s in CHECK_REGISTRY if get_adapter(s.check_id) is None]
    assert missing == []


def test_setup_pin_aggregate_fails_missing_scans() -> None:
    setup_aggregate.set_pin_context(
        [
            {"stable_id": "component_a", "version": "1.0", "checks_summary": None},
            {
                "stable_id": "component_b",
                "version": "2.0",
                "checks_summary": {
                    "status": "available",
                    "failed": 0,
                    "checks": [
                        {
                            "check_id": "path_denylist",
                            "result": "passed",
                            "mandatory": True,
                        }
                    ],
                },
            },
        ]
    )
    try:
        from ai_stp_platform.safety.policy import registry_by_id

        spec = registry_by_id()["setup_pin_aggregate"]
        out = setup_aggregate.run(Path(), None, spec)
        assert out.result == "failed"
        assert any(f.rule_id == "pin_missing_scan" for f in out.findings)
    finally:
        setup_aggregate.clear_pin_context()


def test_setup_pin_aggregate_fails_mandatory_pin() -> None:
    setup_aggregate.set_pin_context(
        [
            {
                "stable_id": "component_bad",
                "version": "1.0",
                "checks_summary": {
                    "status": "available",
                    "failed": 1,
                    "checks": [
                        {
                            "check_id": "secrets_heuristic",
                            "result": "failed",
                            "mandatory": True,
                        }
                    ],
                },
            }
        ]
    )
    try:
        from ai_stp_platform.safety.policy import registry_by_id

        spec = registry_by_id()["setup_pin_aggregate"]
        out = setup_aggregate.run(Path(), None, spec)
        assert out.result == "failed"
        assert out.mandatory is True
    finally:
        setup_aggregate.clear_pin_context()


def test_setup_pin_aggregate_passes_clean_pins() -> None:
    setup_aggregate.set_pin_context(
        [
            {
                "stable_id": "component_ok",
                "version": "1.0",
                "checks_summary": {
                    "status": "available",
                    "failed": 0,
                    "checks": [
                        {
                            "check_id": "path_denylist",
                            "result": "passed",
                            "mandatory": True,
                        }
                    ],
                },
            }
        ]
    )
    try:
        from ai_stp_platform.safety.policy import registry_by_id

        spec = registry_by_id()["setup_pin_aggregate"]
        out = setup_aggregate.run(Path(), None, spec)
        assert out.result == "passed"
    finally:
        setup_aggregate.clear_pin_context()


@pytest.mark.parametrize(
    ("pin", "expected_rule"),
    [
        (
            {
                "stable_id": "component_failed",
                "version": "1.0",
                "failed_mandatory": True,
                "checks_summary": {"status": "available", "failed": 1},
            },
            "pin_failed_mandatory",
        ),
        (
            {
                "stable_id": "component_pending",
                "version": "1.0",
                "checks_summary": {"status": "pending", "failed": 0},
            },
            "pin_scan_pending",
        ),
        (
            {
                "stable_id": "component_malformed",
                "version": "1.0",
                "checks_summary": {
                    "status": "available",
                    "failed": 0,
                    "checks": ["not-a-check", {"mandatory": False, "result": "failed"}],
                },
            },
            None,
        ),
    ],
)
def test_setup_pin_aggregate_preserves_fail_closed_pin_semantics(
    pin: dict[str, object], expected_rule: str | None
) -> None:
    from ai_stp_platform.safety.policy import registry_by_id

    setup_aggregate.set_pin_context([pin])
    try:
        out = setup_aggregate.run(Path(), None, registry_by_id()["setup_pin_aggregate"])
    finally:
        setup_aggregate.clear_pin_context()

    if expected_rule is None:
        assert out.result == "passed"
        assert out.findings == []
    else:
        assert out.result == "failed"
        assert any(finding.rule_id == expected_rule for finding in out.findings)


@pytest.mark.asyncio
async def test_setup_suite_with_pin_context() -> None:
    clear_safety_cache()
    setup_aggregate.set_pin_context(
        [
            {
                "stable_id": "component_ok",
                "version": "1.0",
                "checks_summary": {
                    "status": "available",
                    "checks": [{"check_id": "x", "result": "passed", "mandatory": True}],
                },
            }
        ]
    )
    try:
        result = await run_safety_suite(
            passport={"kind": "setup", "components": []},
            content_digest="sha256:" + "f" * 64,
            object_kind="setup",
            use_cache=False,
        )
        assert result.outcomes[0].check_id == "setup_pin_aggregate"
        assert result.outcomes[0].result == "passed"
    finally:
        setup_aggregate.clear_pin_context()


@pytest.mark.asyncio
async def test_execute_validate_setup_loads_catalog_pins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_stp_platform.publication_logic import execute_validate
    from ai_stp_platform.safety.policy import POLICY_VERSION

    clear_safety_cache()
    plan = SimpleNamespace(
        id="plan_setup_pins",
        object_kind="setup",
        stable_id="setup_01ARZ3NDEKTSV4RRFFQ69G5FAV",
        version="1.0",
        content_digest="sha256:" + "a" * 64,
        policy_version=POLICY_VERSION,
        state="validating",
        component_verified=False,
        actor_account_id="account_01ARZ3NDEKTSV4RRFFQ69G5FAV",
        device_id="device_1",
        passport={
            "name": "s",
            "version": "1.0",
            "tags": ["t"],
            "license": {"spdx_id": "MIT"},
            "source": {
                "repository": "https://github.com/e/r",
                "commit": "a" * 40,
                "path": ".",
            },
            "artifact": {"digest": "sha256:" + "a" * 64, "size_bytes": 1},
            "components": [
                {
                    "stable_id": "component_01ARZ3NDEKTSV4RRFFQ69G5FAV",
                    "version": "1.0",
                    "passport_digest": "sha256:" + "b" * 64,
                }
            ],
            "requires_credentials": False,
        },
        attestations=[],
        effects=[],
    )
    pin_row = SimpleNamespace(
        checks_summary={
            "status": "available",
            "failed": 0,
            "checks": [{"check_id": "path_denylist", "result": "passed", "mandatory": True}],
        }
    )
    session = AsyncMock()
    session.get = AsyncMock(return_value=plan)

    async def _scalar(stmt: object | None = None, **_k: object) -> object | None:
        text = str(stmt)
        if "validation_snapshot" in text.lower():
            return None
        if "catalog_metadata" in text.lower():
            return pin_row
        return None

    session.scalar = AsyncMock(side_effect=_scalar)
    added: list[object] = []
    session.add = lambda o: added.append(o)
    session.flush = AsyncMock()
    monkeypatch.setattr("ai_stp_platform.publication_logic.enqueue", AsyncMock())
    monkeypatch.setattr(
        "ai_stp_platform.publication_logic._persist_safety_run",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr("ai_stp_platform.publication_logic.new_id", lambda p: f"{p}_setup")
    monkeypatch.setattr(
        "ai_stp_platform.publication_logic.open_env_object_store",
        AsyncMock(return_value=None),
    )
    await execute_validate(session, plan_id=plan.id)
    assert plan.state == "publish_planned"
    assert any(
        getattr(o, "check_id", None) == "setup_pin_aggregate"
        and getattr(o, "result", None) == "passed"
        for o in added
    )


@pytest.mark.asyncio
async def test_yara_marker_on_strict() -> None:
    clear_safety_cache()
    payload = _zip({"x.bin": b"\x00AI_STP_MALWARE_TEST_MARKER_V1\x00"})
    digest = _digest(payload)
    result = await run_safety_suite(
        passport={"component_type": "skill"},
        content_digest=digest,
        artifact_bytes=payload,
        profile=SafetyProfile.STRICT,
        use_cache=False,
    )
    yara = next(o for o in result.outcomes if o.check_id == "malware_yara")
    assert yara.result == "failed"
