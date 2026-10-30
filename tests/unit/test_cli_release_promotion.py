"""Promotion cannot expose a missing or incomplete native CLI download."""

from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path

import pytest
import yaml

REPOSITORY = "ai-engineers-guild/ai-stp"
HEAD = "a" * 40
TAG_OBJECT = "b" * 40
RELEASE_SOURCE = "c" * 40
TAG = "cli-v0.2.3"
SOURCE_PATH = "contents/packages/contracts/src/ai_stp_contracts/cli_copy.py?ref=" + HEAD


def _step() -> tuple[str, list[str]]:
    workflow = yaml.safe_load(Path(".github/workflows/deploy.yml").read_text())
    steps = workflow["jobs"]["promote"]["steps"]
    names = [step["name"] for step in steps]
    step = next(
        step
        for step in steps
        if step["name"] == "Require the published CLI download before promotion"
    )
    return step["run"].split("<<'PY'\n", 1)[1].rsplit("\nPY", 1)[0], names


def _document(source: str) -> dict[str, str]:
    return {
        "encoding": "base64",
        "content": base64.b64encode(source.encode()).decode(),
    }


def _responses() -> dict[str, object]:
    assets = []
    for target, extension, platform in [
        ("x86_64-unknown-linux-gnu", "tar.gz", "manylinux_2_39_x86_64"),
        ("aarch64-apple-darwin", "tar.gz", "macosx_15_0_arm64"),
        ("x86_64-pc-windows-msvc", "zip", "win_amd64"),
    ]:
        assets.extend(
            [
                f"ai-stp-cli-0.2.3-{target}.{extension}",
                f"ai_stp-0.2.3-py3-none-{platform}.whl",
            ]
        )
    assets.append("ai-stp-cli-0.2.3.crate")
    assets += [name + ".sha256" for name in assets]
    return {
        SOURCE_PATH: _document(
            'CLI_RELEASES_URL: str = "https://github.com/'
            + REPOSITORY
            + '/releases/tag/cli-v0.2.3"\n'
            'raise RuntimeError("candidate source must never execute")\n'
        ),
        "releases/tags/" + TAG: {
            "tag_name": TAG,
            "draft": False,
            "prerelease": False,
            "published_at": "2026-10-30T00:00:00Z",
            "assets": [
                {
                    "name": name,
                    "state": "uploaded",
                    "size": 100,
                    "digest": "sha256:" + "d" * 64,
                }
                for name in assets
            ],
        },
        "git/ref/tags/" + TAG: {"object": {"type": "tag", "sha": TAG_OBJECT}},
        "git/tags/" + TAG_OBJECT: {
            "tag": TAG,
            "object": {"type": "commit", "sha": RELEASE_SOURCE},
        },
        "compare/" + RELEASE_SOURCE + "..." + HEAD: {"status": "ahead"},
    }


def _execute(monkeypatch: pytest.MonkeyPatch, responses: dict[str, object]) -> list[str]:
    monkeypatch.setenv("REPOSITORY", REPOSITORY)
    monkeypatch.setenv("HEAD_SHA", HEAD)
    calls: list[str] = []

    def read(
        args: list[str], *, check: bool, capture_output: bool, text: bool, timeout: int
    ) -> subprocess.CompletedProcess[str]:
        assert args[:2] == ["gh", "api"]
        assert check and capture_output and text and timeout == 30
        prefix = f"repos/{REPOSITORY}/"
        assert args[2].startswith(prefix) and len(args) == 3
        path = args[2].removeprefix(prefix)
        calls.append(path)
        if path not in responses:
            raise subprocess.CalledProcessError(1, args, stderr="HTTP 404")
        return subprocess.CompletedProcess(args, 0, stdout=json.dumps(responses[path]))

    monkeypatch.setattr(subprocess, "run", read)
    source, _ = _step()
    exec(compile(source, "<published-cli-promotion>", "exec"), {})
    return calls


@pytest.mark.parametrize("status", ["ahead", "identical"])
def test_promotion_accepts_a_complete_published_ancestor_without_executing_source(
    monkeypatch: pytest.MonkeyPatch, status: str
) -> None:
    responses = _responses()
    responses["compare/" + RELEASE_SOURCE + "..." + HEAD] = {"status": status}
    calls = _execute(monkeypatch, responses)
    assert calls == list(responses)


@pytest.mark.parametrize(
    "case",
    [
        "missing",
        "draft",
        "prerelease",
        "unpublished",
        "wrong-tag",
        "missing-asset",
        "duplicate-asset",
        "unuploaded",
        "empty-asset",
        "missing-digest",
        "invalid-digest",
        "lightweight-tag",
        "wrong-annotation",
        "noncommit-tag",
        "diverged",
        "behind",
        "nonliteral-source",
        "wrong-origin",
        "unstable-version",
        "duplicate-source",
    ],
)
def test_promotion_refuses_unpublished_incomplete_or_unrelated_downloads(
    monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    # JSON fixtures model the API boundary, including malformed responses.
    responses = json.loads(json.dumps(_responses()))
    release = responses["releases/tags/" + TAG]
    asset = release["assets"][0]
    if case == "missing":
        del responses["releases/tags/" + TAG]
    elif case == "draft":
        release["draft"] = True
    elif case == "prerelease":
        release["prerelease"] = True
    elif case == "unpublished":
        release["published_at"] = None
    elif case == "wrong-tag":
        release["tag_name"] = "desktop-v0.1.3"
    elif case == "missing-asset":
        release["assets"].pop()
    elif case == "duplicate-asset":
        release["assets"][-1] = asset
    elif case == "unuploaded":
        asset["state"] = "starter"
    elif case == "empty-asset":
        asset["size"] = 0
    elif case == "missing-digest":
        asset["digest"] = None
    elif case == "invalid-digest":
        asset["digest"] = "sha256:not-a-digest"
    elif case == "lightweight-tag":
        responses["git/ref/tags/" + TAG]["object"]["type"] = "commit"
    elif case == "wrong-annotation":
        responses["git/tags/" + TAG_OBJECT]["tag"] = "other"
    elif case == "noncommit-tag":
        responses["git/tags/" + TAG_OBJECT]["object"]["type"] = "tree"
    elif case in ("diverged", "behind"):
        responses["compare/" + RELEASE_SOURCE + "..." + HEAD]["status"] = case
    else:
        literal = (
            'CLI_RELEASES_URL: str = "https://github.com/'
            + REPOSITORY
            + '/releases/tag/cli-v0.2.3"\n'
        )
        source = {
            "nonliteral-source": 'CLI_RELEASES_URL: str = str("do not execute")\n',
            "wrong-origin": literal.replace("github.com", "example.invalid"),
            "unstable-version": literal.replace("0.2.3", "0.2.3-rc.1"),
            "duplicate-source": literal + literal,
        }[case]
        responses[SOURCE_PATH] = _document(source)

    with pytest.raises((AssertionError, subprocess.CalledProcessError)):
        _execute(monkeypatch, responses)


def test_publication_is_checked_after_main_admission_and_before_ref_mutation() -> None:
    _, names = _step()
    assert (
        names.index("Admit only the current successful main qualification attempt")
        < names.index("Require the published CLI download before promotion")
        < names.index("Verify the source of this promotion and advance the ref")
    )
