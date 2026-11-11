"""The real publisher can resume drafts without replacing previously uploaded bytes."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from tests.contract.test_source_qualification import workflow

GITHUB = r"""
import hashlib
import json
import os
import sys
from pathlib import Path

path = Path(os.environ["PUBLICATION_STATE"])
state = json.loads(path.read_text())
args = sys.argv[1:]
state["trace"].append(args)
status, result = 200, None
if args[0] == "api":
    route = next(arg for arg in args if arg.startswith("repos/"))
    if route.endswith("git/ref/heads/main"):
        result = {"object": {"sha": "a" * 40}}
    elif route == "repos/example/project/git/ref/tags/desktop-v0.5.0":
        status = 404 if state.get("missing_tag") else 200
        result = {"object": {"type": "tag", "sha": "b" * 40}}
    elif route == "repos/example/project/git/tags/" + "b" * 40:
        result = {"tag": "desktop-v0.5.0", "object": {"type": "commit", "sha": "a" * 40}}
    elif route == "repos/example/project/releases":
        assert args[args.index("--method") + 1] == "POST" and "--input" in args
        assert not state["exists"]
        payload = json.load(sys.stdin)
        assert payload["tag_name"] == "desktop-v0.5.0"
        assert payload["target_commitish"] == "a" * 40
        assert payload["draft"] is True and payload["prerelease"] is False
        assert payload["make_latest"] == "false" and payload["body"]
        state["exists"] = True
        result = state["release"]
        if state.pop("lose_create_reply", False):
            status = 503
    elif route == "repos/example/project/releases?per_page=100":
        assert "--paginate" in args and "--slurp" in args
        status = state.get("read_status", 200)
        releases = [state["release"]] if state["exists"] and not state.get("list_lag") else []
        if state.get("duplicate"):
            releases = releases + releases
        result = [releases]
    elif route == "repos/example/project/releases/42":
        status = state.get("read_status", 200 if state["exists"] else 404)
        result = state["release"]
    elif route == "repos/example/project/releases/tags/desktop-v0.5.0":
        status = 200 if state["exists"] and not state["release"]["draft"] else 404
        result = state["release"]
    else:
        raise SystemExit("Unexpected GitHub API route")
elif args[:2] == ["release", "upload"]:
    assert state["release"]["draft"] and "--clobber" not in args
    for name in args[args.index("--") + 1 :]:
        assert not any(asset["name"] == name for asset in state["release"]["assets"])
        data = Path(name).read_bytes()
        state["release"]["assets"].append(
            {
                "name": name,
                "state": "uploaded",
                "digest": "sha256:" + hashlib.sha256(data).hexdigest(),
                "size": len(data),
            }
        )
        if state.get("interrupt_upload"):
            state["interrupt_upload"] = False
            status = 503
            break
elif args[:2] == ["release", "edit"]:
    assert "--draft=false" in args
    state["release"]["draft"] = False
    state["release"]["published_at"] = "2026-11-08T00:00:00Z"
else:
    raise SystemExit("Unexpected external GitHub command")
path.write_text(json.dumps(state))
if "--include" in args:
    print("HTTP/2.0 " + str(status) + " Contract\nContent-Type: application/json\n")
if "--jq" in args:
    query = args[args.index("--jq") + 1]
    print(
        "a" * 40
        if query == ".object.sha"
        else str(
            not result["draft"] and not result["prerelease"] and bool(result["published_at"])
        ).lower()
    )
elif result is not None:
    print(json.dumps(result))
sys.exit(0 if status < 400 else 1)
"""


@dataclass
class Publisher:
    directory: Path
    release: Path
    state: dict[str, Any]

    def run(self) -> subprocess.CompletedProcess[str]:
        state = self.directory / "state.json"
        state.write_text(json.dumps(self.state))
        script = next(
            step["run"]
            for step in workflow("desktop-release.yml")["jobs"]["release"]["steps"]
            if step.get("name") == "Create the GitHub release"
        )
        script = script.replace("${{ github.repository }}", "example/project")
        result = subprocess.run(
            ["bash", "-c", script],
            cwd=self.release,
            env={
                "PATH": str(self.directory) + os.pathsep + os.environ.get("PATH", os.defpath),
                "PUBLICATION_STATE": str(state),
                "REPOSITORY": "example/project",
                "VERSION": "0.5.0",
                "SOURCE_SHA": "a" * 40,
                "SOURCE_RUN_ID": "41",
                "RUNNER_TEMP": str(self.directory),
            },
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
        self.state = json.loads(state.read_text())
        return result

    def mutations(self) -> list[list[str]]:
        return [args for args in self.state["trace"] if args[0] == "release" or "--method" in args]


@pytest.fixture
def publisher(tmp_path: Path) -> Publisher:
    program = tmp_path / "gh"
    program.write_text(f"#!{sys.executable}\n" + GITHUB)
    program.chmod(0o755)
    release = tmp_path / "release"
    release.mkdir()
    checksums: list[str] = []
    for extension in ("deb", "rpm", "AppImage", "dmg", "msi", "exe"):
        name = f"ai-stp_0.5.0_native.{extension}"
        data = f"Qualified original installer: {name}\n".encode()
        (release / name).write_bytes(data)
        checksums.append(f"{hashlib.sha256(data).hexdigest()}  {name}\n")
    (release / "SHA256SUMS").write_text("".join(checksums))
    return Publisher(
        tmp_path,
        release,
        {
            "exists": False,
            "trace": [],
            "release": {
                "id": 42,
                "tag_name": "desktop-v0.5.0",
                "draft": True,
                "prerelease": False,
                "published_at": None,
                "assets": [],
            },
        },
    )


def test_first_publication_and_repeated_delivery_preserve_every_asset(publisher: Publisher) -> None:
    result = publisher.run()
    assert result.returncode == 0, result.stderr
    assets = publisher.state["release"]["assets"]
    assert len(assets) == 7
    assert all(
        asset["digest"]
        == "sha256:" + hashlib.sha256((publisher.release / asset["name"]).read_bytes()).hexdigest()
        for asset in assets
    )
    assert [args[:2] for args in publisher.mutations()] == [
        ["api", "--method"],
        ["release", "upload"],
        ["release", "edit"],
    ]
    again = publisher.run()
    assert again.returncode == 0, again.stderr
    assert publisher.state["release"]["assets"] == assets
    assert len(publisher.mutations()) == 3


def test_partial_upload_can_finish_without_duplicate_or_replaced_assets(
    publisher: Publisher,
) -> None:
    publisher.state["interrupt_upload"] = True
    failed = publisher.run()
    assert failed.returncode != 0
    original = publisher.state["release"]["assets"].copy()
    assert len(original) == 1
    assert publisher.state["release"]["draft"] is True
    resumed = publisher.run()
    assert resumed.returncode == 0, resumed.stderr
    assert len(publisher.state["release"]["assets"]) == 7
    assert publisher.state["release"]["assets"][:1] == original
    assert sum("--method" in args for args in publisher.mutations()) == 1
    assert all("--clobber" not in args for args in publisher.mutations())


@pytest.mark.parametrize(
    "failure", ["digest", "extra", "escape", "denied", "duplicate", "published_incomplete"]
)
def test_existing_release_conflicts_refuse_before_publication_writes(
    publisher: Publisher, failure: str
) -> None:
    publisher.state["exists"] = True
    if failure == "denied":
        publisher.state["read_status"] = 403
    elif failure == "duplicate":
        publisher.state["duplicate"] = True
    elif failure == "published_incomplete":
        publisher.state["release"].update(draft=False, published_at="2026-11-11T00:00:00Z")
    else:
        name = (
            "SHA256SUMS"
            if failure == "digest"
            else ("unqualified.exe" if failure == "extra" else "../state.json")
        )
        publisher.state["release"]["assets"] = [
            {"name": name, "state": "uploaded", "size": 1, "digest": "sha256:" + "0" * 64}
        ]
    result = publisher.run()
    assert result.returncode != 0
    assert publisher.mutations() == []


def test_existing_draft_is_found_before_creating_a_release(publisher: Publisher) -> None:
    publisher.state["exists"] = True
    result = publisher.run()
    assert result.returncode == 0, result.stderr
    assert [args[:2] for args in publisher.mutations()] == [
        ["release", "upload"],
        ["release", "edit"],
    ]


def test_creation_acknowledgement_does_not_depend_on_release_list_visibility(
    publisher: Publisher,
) -> None:
    publisher.state["list_lag"] = True
    result = publisher.run()
    assert result.returncode == 0, result.stderr
    assert publisher.state["release"]["draft"] is False
    assert (
        sum(
            "repos/example/project/releases?per_page=100" in args
            for args in publisher.state["trace"]
        )
        == 1
    )


def test_lost_creation_reply_resumes_the_acknowledged_draft_without_recreation(
    publisher: Publisher,
) -> None:
    publisher.state["lose_create_reply"] = True
    result = publisher.run()
    assert result.returncode != 0
    assert publisher.state["exists"] is True
    assert publisher.state["release"]["assets"] == []
    resumed = publisher.run()
    assert resumed.returncode == 0, resumed.stderr
    assert sum("--method" in args for args in publisher.mutations()) == 1
    assert len(publisher.state["release"]["assets"]) == 7


def test_missing_tag_refuses_before_release_creation(publisher: Publisher) -> None:
    publisher.state["missing_tag"] = True
    result = publisher.run()
    assert result.returncode != 0
    assert publisher.mutations() == []
