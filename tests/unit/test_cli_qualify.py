"""Qualify cells stay not_run until those artifacts actually run."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from ai_stp_cli.application.qualify import (
    AGENT_RUNS,
    AGENT_SCENARIOS,
    AGY_MODEL,
    MEASURED_ENV,
    PLATFORMS,
    PROMOTION_STAGES,
    agent_cells,
    agent_from_document,
    content_digest,
    extra_status,
    isolation_from_document,
    load_measured,
    native_cells,
    native_config_root,
    native_from_document,
    native_marker_populated,
    native_platform,
    promotion_from_document,
    promotion_status,
    report,
    tree_digest,
    wheel_status,
)
from ai_stp_cli.runtime import cli_version
from ai_stp_contracts.cli_copy import INITIALIZE_PROMPT
from ai_stp_foundation.harnesses import HARNESS_ID_ORDER

ROOT = Path(__file__).resolve().parents[2]
CANONICAL_SKILL = ROOT / "skills" / "canonical" / "ai-stp"
KIT_IDENTITY = ROOT / "provider-kit" / "v3" / "KIT-IDENTITY.json"
AGENTS_MD = ROOT / "apps" / "web" / "src" / "app" / "agents.md" / "route.ts"


def test_native_and_agent_cells_are_not_run() -> None:
    native = native_cells()
    agent = agent_cells()
    assert len(native) == len(HARNESS_ID_ORDER) * len(PLATFORMS) == 21
    assert len(agent) == len(AGENT_SCENARIOS) * AGENT_RUNS == 100
    assert set(native.values()) == {"not_run"}
    assert set(agent.values()) == {"not_run"}
    assert len(AGENT_SCENARIOS) == 20
    assert len(set(AGENT_SCENARIOS)) == 20


def test_promotion_stages_are_not_run() -> None:
    status = promotion_status()
    assert tuple(status) == PROMOTION_STAGES
    assert set(status.values()) == {"not_run"}
    assert "source_merged" in status
    assert "session_loaded" in status


def test_artifact_identities_are_content_hashes_not_release_claims() -> None:
    kit = json.loads(KIT_IDENTITY.read_text(encoding="utf-8"))
    identities = {
        "skill_package": tree_digest(CANONICAL_SKILL),
        "initialize_prompt": content_digest(INITIALIZE_PROMPT.encode("utf-8")),
        "provider_kit_aggregate": kit["aggregate_digest"],
        "cli_version": cli_version(),
        "agents_md": content_digest(AGENTS_MD.read_bytes()),
    }
    assert identities["skill_package"].startswith("sha256:")
    assert identities["initialize_prompt"].startswith("sha256:")
    assert identities["provider_kit_aggregate"].startswith("sha256:")
    assert identities["agents_md"].startswith("sha256:")
    assert identities["cli_version"]
    assert "0.0.31" not in identities["cli_version"]
    assert kit["kit_version"] != ""


def test_qualify_module_does_not_start_a_process() -> None:
    source = Path("apps/cli/src/ai_stp_cli/application/qualify.py").read_text(encoding="utf-8")
    assert "Popen" not in source
    assert "subprocess" not in source
    assert "network_launcher" not in source
    assert "agy_qualify" not in source


def test_wheel_and_extra_are_not_built() -> None:
    shown = report()
    assert wheel_status() == "not_built"
    assert extra_status() == "not_built"
    assert shown["wheel"] == "not_built"
    assert shown["extra"] == "not_built"
    dist = ROOT / "dist"
    if not dist.is_dir():
        return
    names = [path.name for path in dist.iterdir()]
    assert not any("0.0.31" in name for name in names)


def test_measured_overlay_does_not_fill_unrun_cells(tmp_path: Path) -> None:
    place = tmp_path / "measured.json"
    place.write_text(
        json.dumps(
            {
                "agent": {
                    "no-reinit-on-coding:0": "pass",
                    "no-reinit-on-coding:1": "fail",
                    "unknown-scenario:0": "pass",
                    "no-reinit-on-coding:x": "pass",
                    "install-exact-pin:0": "success",
                },
                "native": {"cursor:linux-x86_64": "pass", "cursor:sparc": "pass"},
                "promotion": {"source_merged": "fail", "session_loaded": "not_run"},
            }
        ),
        encoding="utf-8",
    )
    document = load_measured(place)
    agent = agent_cells(measured=agent_from_document(document))
    native = native_cells(measured=native_from_document(document))
    promotion = promotion_status(measured=promotion_from_document(document))
    assert agent[("no-reinit-on-coding", 0)] == "pass"
    assert agent[("no-reinit-on-coding", 1)] == "fail"
    assert agent[("no-reinit-on-coding", 2)] == "not_run"
    assert agent[("install-exact-pin", 0)] == "not_run"
    assert ("unknown-scenario", 0) not in agent
    assert native[("cursor", "linux-x86_64")] == "pass"
    assert ("cursor", "sparc") not in native
    assert promotion["source_merged"] == "fail"
    assert promotion["session_loaded"] == "not_run"
    assert promotion["cli_released"] == "not_run"


def test_report_is_json_safe_and_keeps_unrun_cells() -> None:
    shown = report()
    dumped = json.dumps(shown)
    parsed = json.loads(dumped)
    assert parsed["agy_model"] == AGY_MODEL == "gpt-oss-120b-medium"
    agent = parsed["agent"]
    assert agent["no-reinit-on-coding:0"] == "not_run"
    assert len(agent) == 100
    native = parsed["native"]
    assert len(native) == 21
    assert set(native.values()) == {"not_run"}
    isolation = parsed["isolation"]
    assert isolation == {"status": "not_run"}


def test_native_bytes_oracle_matches_written_tree_and_detects_drift(
    tmp_path: Path,
) -> None:
    root = tmp_path / "native"
    (root / ".cursor" / "rules").mkdir(parents=True)
    held = root / ".cursor" / "rules" / "ai-stp.mdc"
    held.write_text("alwaysApply: true\n", encoding="utf-8")
    reported = tree_digest(root)
    assert reported.startswith("sha256:")
    held.write_text("drift\n", encoding="utf-8")
    assert tree_digest(root) != reported


def test_native_tree_digest_frames_file_boundaries(tmp_path: Path) -> None:
    one = tmp_path / "one"
    two = tmp_path / "two"
    one.mkdir()
    two.mkdir()
    (one / "first").write_bytes(b"x\nsecond\0y")
    (two / "second").write_bytes(b"y")
    (two / "first").write_bytes(b"x")
    assert tree_digest(one) != tree_digest(two)
    (one / "first").write_bytes(b"x")
    (one / "second").write_bytes(b"y")
    assert tree_digest(one) == tree_digest(two)
    (one / "second").rename(one / "renamed")
    assert tree_digest(one) != tree_digest(two)


@pytest.mark.parametrize("model", ["other-model", "gpt-oss-120b-medium", None, "", 12])
def test_report_preserves_measured_model_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, model: object
) -> None:
    place = tmp_path / "measured.json"
    place.write_text(
        json.dumps({"agy_model": model, "agent": {"no-reinit-on-coding:0": "pass"}}),
        encoding="utf-8",
    )
    monkeypatch.setenv(MEASURED_ENV, str(place))
    shown = report()
    assert shown["agy_model"] == (model if isinstance(model, str) and model else None)


def test_native_config_root_honours_opencode_xdg(tmp_path: Path) -> None:
    home = tmp_path / "home"
    xdg = tmp_path / "xdg"
    env = {"HOME": str(home), "XDG_CONFIG_HOME": str(xdg)}
    assert native_config_root("opencode", env) == xdg / "opencode"
    bare = {"HOME": str(home)}
    assert native_config_root("opencode", bare) == home / ".config" / "opencode"
    assert native_config_root("cursor", env) == home / ".cursor"
    assert native_config_root("pi", bare) == home / ".pi" / "agent"
    with pytest.raises(ValueError):
        native_config_root("not-a-harness", bare)
    assert native_platform(system="linux", machine="x86_64") == "linux-x86_64"
    assert native_platform(system="darwin", machine="arm64") == "macos-arm64"
    assert native_platform(system="win32", machine="AMD64") == "windows-x86_64"
    assert native_platform(system="linux", machine="aarch64") is None
    empty = tmp_path / "empty"
    empty.mkdir()
    assert native_marker_populated(empty) is False
    held = empty / "file.txt"
    held.write_text("x\n", encoding="utf-8")
    assert native_marker_populated(empty) is True


def test_report_reads_measured_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    place = tmp_path / "measured.json"
    place.write_text(
        json.dumps({"agent": {"no-reinit-on-coding:0": "pass"}}),
        encoding="utf-8",
    )
    monkeypatch.setenv(MEASURED_ENV, str(place))
    shown = report()
    agent = shown["agent"]
    assert isinstance(agent, dict)
    assert agent["no-reinit-on-coding:0"] == "pass"
    assert agent["no-reinit-on-coding:1"] == "not_run"
    isolation = shown["isolation"]
    assert isinstance(isolation, dict)
    assert isolation["status"] == "not_run"


def test_historical_haiku_overlay_does_not_qualify_the_agent_matrix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    place = tmp_path / "historical.json"
    place.write_text(
        json.dumps(
            {
                "agy_model": "claude-haiku-4-5",
                "haiku": {"no-reinit-on-coding:0": "pass"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(MEASURED_ENV, str(place))
    shown = report()
    agent = shown["agent"]
    assert isinstance(agent, dict)
    assert set(cast(dict[str, object], agent).values()) == {"not_run"}
    assert "haiku" not in shown
    assert shown["agy_model"] == AGY_MODEL


def test_isolation_overlay_does_not_fill_native_cells(tmp_path: Path) -> None:
    place = tmp_path / "measured.json"
    place.write_text(
        json.dumps(
            {
                "isolation": {
                    "status": "unavailable",
                    "os_name": "linux",
                    "evidence": ["bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted"],
                    "launcher_id": "",
                    "garbage": "ignored",
                }
            }
        ),
        encoding="utf-8",
    )
    document = load_measured(place)
    isolation = isolation_from_document(document)
    native = native_cells(measured=native_from_document(document))
    assert isolation["status"] == "unavailable"
    assert isolation["os_name"] == "linux"
    assert isolation["evidence"] == ["bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted"]
    assert "launcher_id" not in isolation
    assert set(native.values()) == {"not_run"}
    assert isolation_from_document({"isolation": {"status": "pass"}}) == {"status": "not_run"}
    enforced = isolation_from_document(
        {
            "isolation": {
                "status": "enforced",
                "os_name": "linux",
                "launcher_id": "bwrap",
                "evidence": ["unshare-net"],
            }
        }
    )
    assert enforced["status"] == "enforced"
    assert enforced["launcher_id"] == "bwrap"
