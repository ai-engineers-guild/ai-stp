"""Qualification prerequisites and retained attempts are independent of model answers."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import yaml

from ai_stp_cli import agy_qualify as qualify


@pytest.mark.skipif(os.name == "nt", reason="the fixture wrapper uses a POSIX shell")
def test_change_seed_authors_a_real_additive_component_without_model_calls(tmp_path: Path) -> None:
    workspace = qualify.prepare_workspace(tmp_path, scenario=qualify.CHANGE_ADD)
    source = workspace.project / "demo-skill" / "SKILL.md"
    metadata = yaml.safe_load(source.read_text().split("---", 2)[1])
    assert metadata["name"] == "demo"
    assert metadata["description"]
    assert metadata["license"] == "MIT"
    qualify.seed_for_scenario(workspace, qualify.CHANGE_ADD)
    pin = qualify.change_component_ref(workspace)
    assert pin.startswith("component_")
    assert pin != qualify.extra_cursor_ref()
    assert qualify.author_minted(workspace.home)
    assert qualify.logged_invocations(workspace) == ""
    assert "task start --intent author" in (workspace.root / "fixture-cli.log").read_text()


@pytest.mark.parametrize("docker_image", [None, "test-image"])
def test_host_and_docker_require_seed_before_the_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, docker_image: str | None
) -> None:
    seen: list[str] = []
    original = qualify.prepare_workspace

    def prepare(root: Path, **kwargs: object) -> qualify.Workspace:
        # This unit test exercises fixture dispatch without a Docker dependency.
        return original(root, scenario=str(kwargs["scenario"]))

    def seed(_workspace: qualify.Workspace, scenario: str) -> None:
        seen.append(scenario)
        raise qualify.CliUnavailable("fixture provider unavailable")

    def drive(*_args: object, **_kwargs: object) -> int:
        pytest.fail("a missing prerequisite must not spend model capacity")

    monkeypatch.setattr(qualify, "prepare_workspace", prepare)
    monkeypatch.setattr(qualify, "seed_for_scenario", seed)
    monkeypatch.setattr(qualify, "run_agy", drive)
    measured = tmp_path / "measured.json"
    assert (
        qualify.qualify_one(
            root=tmp_path / "cell",
            scenario=qualify.CHANGE_ADD,
            run=0,
            measured=measured,
            agy=Path("agy"),
            timeout=5,
            probe=False,
            docker_image=docker_image,
        )
        == 1
    )
    assert seen == [qualify.CHANGE_ADD]
    assert not measured.exists()
    assert (tmp_path / "cell" / "fixture-failure.json").is_file()


def test_repeated_fill_retains_prior_unavailable_attempts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    measured = tmp_path / "measured.json"
    roots: list[Path] = []

    def attempt(*, root: Path, **_kwargs: object) -> int:
        roots.append(root)
        root.mkdir(parents=True, exist_ok=True)
        (root / "evidence.txt").write_text(f"attempt {len(roots)}", encoding="utf-8")
        return 1

    monkeypatch.setattr(qualify, "qualify_one", attempt)
    for _ in range(2):
        assert (
            qualify.fill_unrun(
                tmp_path / "cells",
                measured=measured,
                agy=Path("agy"),
                timeout=5,
                max_attempts=1,
                gap_seconds=0,
            )
            == 1
        )
    assert roots[0] != roots[1]
    assert (roots[0] / "evidence.txt").read_text() == "attempt 1"
    assert (roots[1] / "evidence.txt").read_text() == "attempt 2"


@pytest.mark.parametrize("run", [-1, 5])
def test_bad_run_is_rejected_before_workspace_or_model_effects(tmp_path: Path, run: int) -> None:
    root = tmp_path / "cell"
    with pytest.raises(ValueError, match="run from 0 through 4"):
        qualify.qualify_one(
            root=root,
            scenario=qualify.NO_REINIT,
            run=run,
            measured=None,
            agy=Path("absent-driver"),
            timeout=5,
            probe=False,
        )
    assert not root.exists()


def test_direct_attempt_refuses_to_reuse_prior_state(tmp_path: Path) -> None:
    evidence = tmp_path / "agy.stdout"
    evidence.write_text(json.dumps({"original": True}), encoding="utf-8")
    before = evidence.read_bytes()
    with pytest.raises(ValueError, match="new empty workspace"):
        qualify.qualify_one(
            root=tmp_path,
            scenario=qualify.NO_REINIT,
            run=0,
            measured=None,
            agy=Path("absent-driver"),
            timeout=5,
            probe=False,
        )
    assert evidence.read_bytes() == before
