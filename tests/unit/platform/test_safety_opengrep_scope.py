# pyright: reportUnknownLambdaType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnusedFunction=false, reportUnusedImport=false, reportUnusedVariable=false
"""Opengrep rule scoping: MCP packs must not bulk-fire on pure skills."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from ai_stp_foundation.digests import digest_bytes
from ai_stp_platform.safety.adapters import opengrep as opengrep_adapter
from ai_stp_platform.safety.orchestrator import clear_safety_cache, run_safety_suite
from ai_stp_platform.safety.policy import CheckSpec, SafetyProfile
from ai_stp_platform.safety.policy_pack import (
    MCP_ONLY_RULE_FILES,
    select_opengrep_rule_files,
)
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


def test_select_rules_excludes_mcp_pack_for_skill() -> None:
    m = ArtifactManifest(component_type="skill", flags={"skill_md"})
    names = {p.name for p in select_opengrep_rule_files(m)}
    assert names
    assert MCP_ONLY_RULE_FILES.isdisjoint(names)
    assert "python-dangerous-code.yml" in names or "ai-agent-dangerous-patterns.yml" in names


def test_select_rules_includes_mcp_pack_for_mcp() -> None:
    m = ArtifactManifest(component_type="mcp", flags={"mcp"})
    names = {p.name for p in select_opengrep_rule_files(m)}
    assert "mcp-config-security.yml" in names


def test_markdown_only_skill_has_no_applicable_opengrep_files() -> None:
    manifest = ArtifactManifest(
        component_type="skill",
        flags={"skill_md"},
        text_files=["SKILL.md"],
    )

    assert opengrep_adapter.has_applicable_files(manifest) is False


@pytest.mark.asyncio
async def test_clean_skill_suite_has_no_mcp_overprivileged_findings() -> None:
    clear_safety_cache()
    # Text that historically matched mcp-overprivileged-scope when MCP pack applied.
    skill_body = (
        "# Clean skill\n\n"
        "Review full admin write delete all scopes for hiring managers.\n"
        "Use permissions carefully when ranking candidates.\n"
    )
    payload = _zip({"SKILL.md": skill_body, "README.md": "docs\n"})
    digest = _digest(payload)
    result = await run_safety_suite(
        passport={"component_type": "skill", "artifact": {"digest": digest}},
        content_digest=digest,
        artifact_bytes=payload,
        use_cache=False,
    )
    opengrep = next(o for o in result.outcomes if o.check_id == "sast_opengrep")
    mcp_hits = [
        f
        for f in opengrep.findings
        if "mcp-overprivileged" in f.rule_id
        or "mcp-config" in f.rule_id
        or "overprivileged" in f.rule_id
    ]
    assert mcp_hits == [], [f.rule_id for f in mcp_hits]
    assert opengrep.detail.get("rule_files") is not None
    assert "mcp-config-security.yml" not in (opengrep.detail.get("rule_files") or [])


def test_mcp_adapter_still_matches_overprivileged_scope(tmp_path: Path) -> None:
    tree = tmp_path / "tree"
    tree.mkdir()
    cfg = tree / ".mcp.json"
    # Pattern from mcp-config-security.yml (write/delete/admin/full/all/* scopes).
    cfg.write_text(
        '{\n  "mcpServers": {\n    "x": {\n'
        '      "command": "node",\n'
        '      "args": ["./s.js"],\n'
        '      "scopes": ["write", "delete", "admin"]\n'
        "    }\n  }\n}\n",
        encoding="utf-8",
    )
    (tree / "s.js").write_text("ok\n", encoding="utf-8")
    manifest = ArtifactManifest(
        component_type="mcp",
        flags={"mcp"},
        text_files=[".mcp.json", "s.js"],
    )
    spec = CheckSpec(
        check_id="sast_opengrep",
        family="sast",
        mandatory=False,
        timeout_seconds=10,
        stage=3,
        kinds=frozenset({"component"}),
        languages=frozenset(),
        requires_any_flag=frozenset(),
        profiles=frozenset({SafetyProfile.STANDARD, SafetyProfile.STRICT}),
    )
    outcome = opengrep_adapter.run(tree, manifest, spec)
    assert "mcp-config-security.yml" in (outcome.detail.get("rule_files") or [])
    # Vendored regex for scopes write/delete/admin must fire on this fixture.
    assert any("overprivileged" in f.rule_id or "mcp-" in f.rule_id for f in outcome.findings)
    assert outcome.result == "failed"
