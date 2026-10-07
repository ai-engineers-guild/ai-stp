"""A publication may approve only the run created by its own dispatch."""

import json
import subprocess
import sys
from collections.abc import Sequence

import pytest
from release_scripts import publish_pypi


def test_a_newer_publication_does_not_receive_this_dispatch_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    approved: list[str] = []
    reads: list[str] = []
    publication = iter((False, True))

    def github(path: str, *arguments: str, check: bool = True) -> object:
        del check
        reads.append(path)
        if path.endswith("/actions/runs/17"):
            return {
                "conclusion": "success",
                "head_sha": "release-sha",
                "path": ".github/workflows/release-candidate.yml",
                "event": "workflow_dispatch",
                "head_branch": "v1.2.3",
                "head_repository": {"full_name": publish_pypi.REPO},
            }
        if path.endswith("/actions/runs/17/jobs"):
            return {"jobs": [{"name": "attest-public-candidate", "conclusion": "success"}]}
        if path.endswith("/git/ref/tags/v1.2.3"):
            return {"object": {"type": "commit", "sha": "release-sha"}}
        if path.endswith("/dispatches"):
            assert "POST" in arguments
            assert "X-GitHub-Api-Version: 2026-03-10" in arguments
            assert {
                "ref=main",
                "inputs[version]=1.2.3",
                "inputs[run_id]=17",
                "inputs[package]=cli",
            } <= set(arguments)
            return {"workflow_run_id": 41}
        if path.endswith("/workflows/publish-pypi.yml/runs"):
            # Another operator dispatches after our request has returned.
            return 42
        if path.endswith("/pending_deployments"):
            return [
                {"environment": {"id": 9, "name": "pypi-cli"}, "current_user_can_approve": True}
            ]
        if path.endswith(("/actions/runs/41", "/actions/runs/42")):
            return {"status": "completed", "conclusion": "success"}
        raise AssertionError(f"unexpected GitHub request: {path}")

    def review(
        arguments: Sequence[str],
        *,
        input: str,
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        del capture_output, text, check
        assert json.loads(input)["environment_ids"] == [9]
        approved.append(arguments[4])
        return subprocess.CompletedProcess(arguments, 0, "", "")

    def publication_status(_project: str, _version: str) -> bool:
        return next(publication)

    def sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(sys, "argv", ["publish_pypi", "--version", "1.2.3", "--run-id", "17"])
    monkeypatch.setattr(publish_pypi, "api", github)
    monkeypatch.setattr(publish_pypi, "published", publication_status)
    monkeypatch.setattr(publish_pypi.subprocess, "run", review)
    monkeypatch.setattr(publish_pypi.time, "sleep", sleep)

    assert publish_pypi.main() == 0
    assert approved == [f"repos/{publish_pypi.REPO}/actions/runs/41/pending_deployments"]
    assert not any(path.endswith("/workflows/publish-pypi.yml/runs") for path in reads)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("path", ".github/workflows/check.yml"),
        ("event", "pull_request"),
        ("head_branch", "main"),
        ("head_repository", {"full_name": "another-owner/ai-stp"}),
    ],
)
def test_an_unrelated_successful_run_cannot_stand_in_for_a_candidate(
    monkeypatch: pytest.MonkeyPatch, field: str, value: object
) -> None:
    run: dict[str, object] = {
        "conclusion": "success",
        "head_sha": "release-sha",
        "path": ".github/workflows/release-candidate.yml",
        "event": "workflow_dispatch",
        "head_branch": "v1.2.3",
        "head_repository": {"full_name": publish_pypi.REPO},
        field: value,
    }

    def github(path: str, *_arguments: str) -> object:
        assert path.endswith("/actions/runs/17")
        return run

    monkeypatch.setattr(publish_pypi, "api", github)
    with pytest.raises(SystemExit, match="not this repository's candidate"):
        publish_pypi.candidate_head("17", "1.2.3")


@pytest.mark.parametrize("conclusion", ["skipped", "failure", None])
def test_a_candidate_without_successful_attestation_is_refused(
    monkeypatch: pytest.MonkeyPatch, conclusion: str | None
) -> None:
    def github(path: str, *_arguments: str) -> object:
        if path.endswith("/jobs"):
            return {"jobs": [{"name": "attest-public-candidate", "conclusion": conclusion}]}
        return {
            "conclusion": "success",
            "head_sha": "release-sha",
            "path": ".github/workflows/release-candidate.yml",
            "event": "workflow_dispatch",
            "head_branch": "v1.2.3",
            "head_repository": {"full_name": publish_pypi.REPO},
        }

    monkeypatch.setattr(publish_pypi, "api", github)
    with pytest.raises(SystemExit, match="no successful public attestation job"):
        publish_pypi.candidate_head("17", "1.2.3")


@pytest.mark.parametrize(
    "receipt",
    [
        None,
        {},
        {"workflow_run_id": 0},
        {"workflow_run_id": -1},
        {"workflow_run_id": True},
        {"workflow_run_id": "41"},
    ],
)
def test_missing_or_invalid_dispatch_identity_refuses_to_guess(
    monkeypatch: pytest.MonkeyPatch, receipt: object
) -> None:
    def github(*_arguments: str) -> object:
        return receipt

    monkeypatch.setattr(publish_pypi, "api", github)
    with pytest.raises(SystemExit, match="no run was approved"):
        publish_pypi.dispatch("1.2.3", "17", "cli")


def test_an_approval_http_failure_is_not_silently_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def github(*_arguments: str) -> object:
        return [{"environment": {"id": 9, "name": "pypi-cli"}, "current_user_can_approve": True}]

    monkeypatch.setattr(publish_pypi, "api", github)

    def rejected(
        arguments: Sequence[str],
        *,
        input: str,
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        del input, capture_output, text
        if check:
            raise subprocess.CalledProcessError(1, arguments, stderr="HTTP 403")
        return subprocess.CompletedProcess(arguments, 1, "", "HTTP 403")

    monkeypatch.setattr(publish_pypi.subprocess, "run", rejected)
    with pytest.raises(subprocess.CalledProcessError):
        publish_pypi.approve("41")
