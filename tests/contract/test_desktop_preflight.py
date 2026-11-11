"""Diagnostic packages cannot satisfy installed application or release admission."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any, cast

import pytest
import yaml


def workflow(name: str) -> dict[str | bool, Any]:
    return cast(
        dict[str | bool, Any], yaml.safe_load(Path(f".github/workflows/{name}.yml").read_text())
    )


@pytest.mark.parametrize(
    ("event", "owner", "accepted"),
    [
        ("workflow_dispatch", "desktop", True),
        ("push", "desktop", False),
        ("pull_request", "desktop", False),
        ("workflow_dispatch", "desktop-release", False),
        ("workflow_dispatch", "check", False),
    ],
)
def test_package_diagnosis_refuses_to_replace_an_owning_release_or_main_run(
    event: str, owner: str, accepted: bool
) -> None:
    steps = workflow("desktop")["jobs"]["desktop"]["steps"]
    gate = next(step for step in steps if step["name"].startswith("Confine package-only"))
    result = subprocess.run(
        ["bash", "-c", gate["run"]],
        env={**os.environ, "GITHUB_EVENT_NAME": event, "GITHUB_WORKFLOW": owner},
        check=False,
        capture_output=True,
        timeout=5,
    )
    assert (result.returncode == 0) is accepted


def test_reusable_release_keeps_mandatory_application_acceptance() -> None:
    desktop = workflow("desktop")
    events = cast(dict[str, Any], desktop.get("on", desktop.get(True)))
    assert events["workflow_dispatch"]["inputs"]["packages_only"]["default"] is False
    reusable = cast(dict[str, Any], events["workflow_call"] or {})
    reusable_inputs = cast(dict[str, Any], reusable.get("inputs") or {})
    assert "packages_only" not in reusable_inputs
    release = workflow("desktop-release")
    assert "bundle" not in release["jobs"]
    check = workflow("source")
    assert check["jobs"]["desktop"]["uses"] == "./.github/workflows/desktop.yml"
    assert "packages_only" not in check["jobs"]["desktop"].get("with", {})
    assert "desktop" in check["jobs"]["qualification"]["needs"]
    steps = {step.get("name"): step for step in desktop["jobs"]["desktop"]["steps"]}
    for name in (
        "Install the release package on the disposable Linux runner",
        "Three installed Linux Desktop journeys with bundled CLI and native vault",
        "Installed corporate onboarding, lost reply and original binding recovery",
        "Retain the public installed corporate checkout result",
        "Retain public installed Desktop results",
        "Prepare the exact installed performance baseline",
        "Compare installed startup and repeated navigation on the same worker",
        "Retain the exact same-worker performance observations",
    ):
        assert steps[name]["if"] == "runner.os == 'Linux' && !inputs.packages_only"
    assert "preflight-" in steps["Upload bundles"]["with"]["name"]
    assert steps["Seal the exact platform installers"]["if"] == "${{ !inputs.packages_only }}"
    order = list(steps)
    assert order.index("Seal the exact platform installers") > order.index(
        "Installed corporate onboarding, lost reply and original binding recovery"
    )
    assert order.index("Seal the exact platform installers") > order.index(
        "Retain the exact same-worker performance observations"
    )
    personal = "Qualify personal workspace on installed macOS and Windows"
    retained = "Retain installed macOS and Windows personal results"
    condition = "(runner.os == 'macOS' || runner.os == 'Windows') && !inputs.packages_only"
    assert steps[personal]["if"] == steps[retained]["if"] == condition
    assert steps[personal]["with"]["recipe"] == "ci-desktop-installed-personal-workspace"
    assert order.index("Seal the exact platform installers") < order.index(personal)
    assert order.index(personal) < order.index(retained) < order.index("Upload bundles")
    assert steps["Upload bundles"]["with"]["if-no-files-found"] == "error"
    assert (
        '"application_acceptance":false'
        in steps["Record that diagnostic packages have no application acceptance"]["run"]
    )


@pytest.mark.parametrize("existing", ["new", "draft", "published", "conflict"])
def test_desktop_publication_reconciles_by_release_id(tmp_path: Path, existing: str) -> None:
    repo = "example/project"
    tag = "desktop-v0.5.2"
    source = "a" * 40
    assets = tmp_path / "assets"
    assets.mkdir()
    names = ["SHA256SUMS"] + [
        f"candidate.{suffix}" for suffix in ("deb", "rpm", "AppImage", "dmg", "msi", "exe")
    ]
    for name in names:
        (assets / name).write_text(name, encoding="utf-8")
    available = [
        {
            "name": name,
            "state": "uploaded",
            "digest": "sha256:" + hashlib.sha256(name.encode()).hexdigest(),
        }
        for name in names
    ]
    selected = available if existing == "published" else available[:1]
    if existing == "conflict":
        selected[0]["digest"] = "sha256:" + "0" * 64
    state = tmp_path / "release.json"
    state.write_text(
        json.dumps(
            None
            if existing == "new"
            else {
                "id": 42,
                "tag_name": tag,
                "draft": existing != "published",
                "prerelease": False,
                "published_at": "2026-11-11" if existing == "published" else None,
                "assets": selected,
            }
        )
    )
    fake = tmp_path / "gh"
    fake.write_text(
        f"#!{sys.executable}\n"
        + textwrap.dedent(r"""
        import hashlib
        import json
        import os
        import sys
        from pathlib import Path

        state = Path(os.environ["RELEASE_STATE"])
        release = json.loads(state.read_text())
        args = sys.argv[1:]
        if args[:3] == ["api", "--paginate", "--slurp"]:
            assert args[3] == "repos/example/project/releases?per_page=100"
            print(json.dumps([[release] if release else []]))
        elif args[:2] == ["api", "repos/example/project/git/ref/heads/main"]:
            print(os.environ["SOURCE_SHA"])
        elif args == ["api", "repos/example/project/releases/42"]:
            print(json.dumps(release))
        elif args == ["api", "repos/example/project/releases/tags/desktop-v0.5.2"]:
            if release is None or release["draft"]:
                sys.exit(1)
            print(json.dumps(release))
        elif args[0] == "release":
            operation = args[1]
            assert args[2] == "desktop-v0.5.2"
            if operation == "create":
                assert release is None and "--draft" in args and "--verify-tag" in args
                release = {
                    "id": 42, "tag_name": args[2], "draft": True, "prerelease": False,
                    "published_at": None, "assets": [],
                }
            elif operation == "upload":
                assert release["draft"] and "--clobber" not in args
                for filename in args[args.index("--") + 1:]:
                    assert filename not in {item["name"] for item in release["assets"]}
                    digest = hashlib.sha256(Path(filename).read_bytes()).hexdigest()
                    release["assets"].append(
                        {"name": filename, "state": "uploaded", "digest": "sha256:" + digest}
                    )
            elif operation == "edit":
                assert release["draft"] and "--draft=false" in args and len(release["assets"]) == 7
                release.update(draft=False, published_at="2026-11-11")
            else:
                raise AssertionError(operation)
            state.write_text(json.dumps(release))
            with Path(os.environ["WRITES"]).open("a") as log:
                log.write(operation + "\n")
        else:
            raise AssertionError(args)
    """)
    )
    fake.chmod(0o700)
    body = next(
        step["run"]
        for job in workflow("desktop-release")["jobs"].values()
        for step in job["steps"]
        if "# No checkout or repository program" in step.get("run", "")
    )
    writes = tmp_path / "writes"
    run = subprocess.run(
        ["bash", "-c", body.replace("${{ github.repository }}", repo)],
        cwd=assets,
        env={
            "PATH": f"{tmp_path}{os.pathsep}{os.environ.get('PATH', os.defpath)}",
            "RELEASE_STATE": str(state),
            "REPOSITORY": repo,
            "RUNNER_TEMP": str(tmp_path),
            "SOURCE_RUN_ID": "41",
            "SOURCE_SHA": source,
            "VERSION": "0.5.2",
            "WRITES": str(writes),
        },
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert (run.returncode == 0) is (existing != "conflict"), run.stderr
    expected_writes = {
        "new": ["create", "upload", "edit"],
        "draft": ["upload", "edit"],
        "published": [],
        "conflict": [],
    }
    assert (writes.read_text().splitlines() if writes.exists() else []) == expected_writes[existing]
