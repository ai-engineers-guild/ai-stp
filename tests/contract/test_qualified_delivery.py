"""Delivery refuses stale authority and reuses genuine bytes across external API failures."""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from release_scripts._github_delivery import PromotionRefused
from release_scripts.cli_artifacts import PLATFORMS, names
from release_scripts.cli_artifacts import seal as seal_cli
from release_scripts.cli_artifacts import verify as verify_cli
from release_scripts.code_scanning import LANGUAGES, admitted_payloads, seal
from release_scripts.source_admission import POLICIES, ROOT
from tests.contract.test_source_qualification import script

# Only the external GitHub executable is replaced. Production admission,
# serialization, filesystem verification and ref mutation code run unchanged.
GITHUB = r"""
import json, os, sys
from pathlib import Path

path = Path(os.environ["DELIVERY_STATE"])
state = json.loads(path.read_text())
args = sys.argv[1:]
method = args[args.index("--method") + 1] if "--method" in args else "GET"
route = (
    next(arg for arg in args if arg.startswith("repos/example/project"))
    .removeprefix("repos/example/project")
    .lstrip("/")
)
body = json.load(sys.stdin) if "--input" in args else None
entry = {"method": method, "route": route, "body": body}
state["trace"].append(entry)
status, result = 200, None
head = state["head"]
if method != "GET":
    if method == "PATCH" and route == "git/refs/heads/main":
        status = state.get("main_write_status", 200)
        if status == 200 and not state.get("lose_main_ack"):
            state["main"] = body["sha"]
        result = {"object": {"sha": state["main"]}}
    elif method == "PATCH" and route == "git/refs/heads/deploy/prod":
        state["deployment"] = body["sha"]
        state["deployment_status"] = 200
        result = {"object": {"sha": state["deployment"]}}
    elif method == "POST" and route == "git/tags":
        status = 201
        state["tagged_source"] = body["object"]
        result = {"sha": "annotated-desktop"}
    elif method == "POST" and route == "git/refs" and body["ref"].startswith("refs/tags/"):
        status = 201
        state["tag_exists"] = True
        result = {"object": {"sha": "annotated-desktop", "type": "tag"}}
    elif method == "POST" and route == "git/refs":
        status = 201
        state["deployment"] = body["sha"]
        state["deployment_status"] = 200
        result = {"object": {"sha": state["deployment"]}}
    elif method == "POST" and route == "code-scanning/sarifs":
        status = state.get("upload_status", 202)
        result = {"id": "accepted-payload"}
    elif method == "POST" and route == "actions/workflows/deploy.yml/dispatches":
        status = state.get("dispatch_status", 204)
    else:
        status, result = 500, {"unexpected_write": route}
elif not route:
    result = {
        "default_branch": state.get("default_branch", "dev"),
        "permissions": {"admin": state.get("operator_admin", True)},
    }
elif route.startswith("rulesets?"):
    result = [{"id": index, "name": item["name"]} for index, item in enumerate(state["policies"])]
elif route.startswith("rulesets/"):
    result = state["policies"][int(route.split("/")[-1])]
elif route == "actions/runs/41":
    result = state["run"]
elif route.startswith("actions/runs?"):
    result = {"total_count": 1, "workflow_runs": [state["run"]]}
elif route == "actions/runs/41/attempts/1/jobs?per_page=100":
    result = {
        "total_count": 1,
        "jobs": [{"name": "full-qualification", "status": "completed", "conclusion": "success"}],
    }
elif route.startswith("code-scanning/alerts?"):
    result = state.get(
        "main_findings" if "heads%2Fmain" in route else "findings", []
    )
elif route.startswith("code-scanning/analyses?sarif_id="):
    language = route.split("=", 1)[1].removeprefix("original-")
    result = [
        {
            "id": state.get("original_id", 41),
            "category": "/language:" + language,
            "commit_sha": state.get("original_head", head),
            "ref": "refs/heads/dev",
            "error": "",
            "tool": {"name": "CodeQL"},
        }
    ]
elif route.startswith("code-scanning/analyses?"):
    result = [
        {
            "id": index,
            "category": "/language:" + language,
            "commit_sha": state.get("main_analysis_head", head),
            "ref": "refs/heads/main",
            "error": state.get("main_analysis_error", ""),
            "tool": {"name": "CodeQL"},
            "results_count": 2,
        }
        for index, language in enumerate(["actions", "python", "javascript-typescript"])
    ]
elif route.startswith("code-scanning/sarifs/"):
    result = {
        "analyses_url": "https://api.github.com/repos/example/project/"
        "code-scanning/analyses?sarif_id=" + route.rsplit("/", 1)[1],
        "processing_status": state.get("processing_status", "complete"),
        "errors": state.get("processing_errors", []),
    }
elif route == "git/ref/heads/dev":
    result = {"object": {"sha": state.get("dev", head)}}
elif route == "git/ref/heads/main":
    result = {"object": {"sha": state["main"]}}
elif route == "git/ref/heads/deploy/prod":
    status = state.get("deployment_status", 200)
    result = {"object": {"sha": state["deployment"]}}
elif route.startswith("compare/"):
    result = {"status": state.get("comparison", "ahead")}
elif route.startswith("git/ref/tags/desktop-v"):
    status = 200 if state.get("tag_exists", True) else 404
    result = {"object": {"type": "tag", "sha": "annotated-desktop"}}
elif route == "git/tags/annotated-desktop":
    result = {
        "tag": "desktop-v" + state["version"],
        "object": {"type": "commit", "sha": state.get("tagged_source", "d" * 40)},
    }
elif route.startswith("releases/tags/desktop-v"):
    status = state.get("release_status", 200)
    version = state["version"]
    result = {
        "tag_name": "desktop-v" + version,
        "draft": False,
        "prerelease": False,
        "published_at": "2026-11-08T00:00:00Z",
        "assets": [
            {"name": name, "size": 123, "state": "uploaded", "digest": "sha256:" + "a" * 64}
            for name in ["SHA256SUMS"]
            + [
                "ai-stp_" + version + "_native." + ext
                for ext in ["deb", "rpm", "AppImage", "dmg", "msi", "exe"]
            ]
        ],
    }
else:
    status, result = 500, {"unexpected_read": route}
path.write_text(json.dumps(state))
if "--include" in args:
    print("HTTP/2.0 " + str(status) + " Contract\nContent-Type: application/json\n")
if "--jq" in args:
    assert args[args.index("--jq") + 1] == ".object.sha"
    print(result["object"]["sha"])
else:
    print(json.dumps(result))
sys.exit(0 if status < 400 else 1)
"""


@dataclass
class Delivery:
    directory: Path
    state: dict[str, Any]

    def run(self, module: str, *arguments: str) -> subprocess.CompletedProcess[str]:
        return self.execute([sys.executable, "-m", f"release_scripts.{module}", *arguments])

    def execute(self, command: list[str], **values: str) -> subprocess.CompletedProcess[str]:
        path = self.directory / "state.json"
        path.write_text(json.dumps(self.state))
        result = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
            env={
                "PATH": str(self.directory) + os.pathsep + os.environ.get("PATH", os.defpath),
                "DELIVERY_STATE": str(path),
                "REPOSITORY": "example/project",
                "HEAD_SHA": self.state["head"],
                "SOURCE_RUN_ID": "41",
                "SOURCE_ATTEMPT": "1",
                "GITHUB_ACTIONS": "true",
                "RUNNER_ENVIRONMENT": "github-hosted",
                "GITHUB_SHA": self.state["head"],
                "OBSERVED_ATTEMPT": "1",
                "GITHUB_OUTPUT": str(self.directory / "outputs"),
                **values,
            },
        )
        self.state = json.loads(path.read_text())
        return result

    def writes(self) -> list[dict[str, Any]]:
        return [item for item in self.state["trace"] if item["method"] != "GET"]


@pytest.fixture
def delivery(tmp_path: Path) -> Delivery:
    executable = tmp_path / "gh"
    executable.write_text(f"#!{sys.executable}\n" + GITHUB)
    executable.chmod(0o755)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    run = {
        "id": 41,
        "repository": {"full_name": "example/project"},
        "head_repository": {"full_name": "example/project"},
        "head_sha": head,
        "event": "push",
        "head_branch": "dev",
        "path": ".github/workflows/check.yml",
        "status": "completed",
        "conclusion": "success",
        "run_attempt": 1,
    }
    return Delivery(
        tmp_path,
        {
            "head": head,
            "main": "b" * 40,
            "deployment": "b" * 40,
            "run": run,
            "trace": [],
            "version": json.loads((ROOT / "apps/desktop/package.json").read_text())["version"],
            "policies": [
                json.loads((ROOT / f".github/{name}.ruleset.json").read_text()) for name in POLICIES
            ],
        },
    )


def test_read_only_admission_never_mutates_refs(delivery: Delivery) -> None:
    outcome = delivery.run("source_promotion")
    assert outcome.returncode == 0, outcome.stderr
    assert delivery.writes() == []


@pytest.mark.parametrize("change", [None, "source"])
def test_dispatcher_admits_only_its_own_qualified_sha_before_checkout(
    delivery: Delivery,
    change: str | None,
) -> None:
    values = {"GITHUB_SHA": "c" * 40} if change == "source" else {}
    outcome = delivery.execute(["bash", "-c", script("deploy.yml", "promote")], **values)
    assert (outcome.returncode == 0) == (change is None), outcome.stderr
    output = delivery.directory / "outputs"
    if change:
        assert not output.exists()
    else:
        assert output.read_text() == (
            f"head_sha={delivery.state['head']}\nsource_run_id=41\nsource_attempt=1\n"
        )
    assert delivery.writes() == []


@pytest.mark.parametrize(
    "failure", ["stale", "pr", "manual", "policy", "actors", "findings", "diverged"]
)
@pytest.mark.parametrize("operator", [False, True])
def test_invalid_authority_cannot_reach_any_write(
    delivery: Delivery, failure: str, operator: bool
) -> None:
    if failure == "stale":
        delivery.state["dev"] = "c" * 40
    elif failure == "pr":
        delivery.state["run"]["event"] = "pull_request"
    elif failure == "manual":
        delivery.state["run"]["event"] = "workflow_dispatch"
    elif failure == "policy":
        delivery.state["default_branch"] = "main"
    elif failure == "actors":
        delivery.state["policies"][3]["bypass_actors"].append(
            {"actor_id": 99, "actor_type": "Integration", "bypass_mode": "always"}
        )
    elif failure == "findings":
        delivery.state["findings"] = [{"number": 7}]
    else:
        delivery.state["comparison"] = "diverged"
    outcome = delivery.execute(
        [
            sys.executable,
            "-m",
            "release_scripts.source_promotion",
            "--advance-main" if operator else "--apply",
        ],
        GITHUB_ACTIONS="false" if operator else "true",
    )
    assert outcome.returncode != 0
    assert delivery.writes() == []


def test_ff_refusal_has_one_attempt_and_no_alternate_authority(delivery: Delivery) -> None:
    delivery.state["main_write_status"] = 403
    outcome = delivery.execute(
        [sys.executable, "-m", "release_scripts.source_promotion", "--advance-main"],
        GITHUB_ACTIONS="false",
    )
    assert outcome.returncode != 0
    assert [(item["method"], item["route"], item["body"]) for item in delivery.writes()] == [
        ("PATCH", "git/refs/heads/main", {"sha": delivery.state["head"], "force": False})
    ]
    assert delivery.state["deployment"] == "b" * 40


def test_hosted_preparation_never_attempts_main_or_claims_deployment(delivery: Delivery) -> None:
    delivery.state["main_write_status"] = 403
    outcome = delivery.run("source_promotion", "--apply")
    assert outcome.returncode == 0, outcome.stderr
    assert delivery.writes() == []
    assert (delivery.directory / "outputs").read_text() == "deployed=false\n"
    assert delivery.state["main"] == delivery.state["deployment"] == "b" * 40


@pytest.mark.parametrize("failure", ["stale-analysis", "processing-error", "main-findings"])
def test_operator_requires_processed_clean_main_analysis_before_any_write(
    delivery: Delivery, failure: str
) -> None:
    if failure == "stale-analysis":
        delivery.state["main_analysis_head"] = "c" * 40
    elif failure == "processing-error":
        delivery.state["main_analysis_error"] = "Analysis was not processed"
    else:
        delivery.state["main_findings"] = [{"number": 8}]
    outcome = delivery.execute(
        [sys.executable, "-m", "release_scripts.source_promotion", "--advance-main"],
        GITHUB_ACTIONS="false",
    )
    assert outcome.returncode != 0
    assert delivery.writes() == []


@pytest.mark.parametrize("failure", [None, "actions", "principal", "hidden-actors", "dispatch"])
def test_explicit_operator_verifies_authority_advances_only_main_and_dispatches(
    delivery: Delivery, failure: str | None
) -> None:
    if failure == "principal":
        delivery.state["operator_admin"] = False
    elif failure == "hidden-actors":
        delivery.state["policies"][3].pop("bypass_actors")
    elif failure == "dispatch":
        delivery.state["dispatch_status"] = 403
    outcome = delivery.execute(
        [sys.executable, "-m", "release_scripts.source_promotion", "--advance-main"],
        GITHUB_ACTIONS="true" if failure == "actions" else "false",
    )
    assert (outcome.returncode == 0) == (failure is None), outcome.stderr
    if failure in {"actions", "principal", "hidden-actors"}:
        assert delivery.writes() == []
        return
    assert [(item["method"], item["route"], item["body"]) for item in delivery.writes()] == [
        ("PATCH", "git/refs/heads/main", {"sha": delivery.state["head"], "force": False}),
        (
            "POST",
            "actions/workflows/deploy.yml/dispatches",
            {"ref": "dev", "inputs": {"source_run_id": "41"}},
        ),
    ]
    assert delivery.state["main"] == delivery.state["head"]
    assert delivery.state["deployment"] == "b" * 40
    assert not (delivery.directory / "outputs").exists()
    # A repair reuses Main, dispatching reconciliation without another ref write.
    delivery.state["dispatch_status"] = 204
    again = delivery.execute(
        [sys.executable, "-m", "release_scripts.source_promotion", "--advance-main"],
        GITHUB_ACTIONS="false",
    )
    assert again.returncode == 0, again.stderr
    assert sum(item["route"] == "git/refs/heads/main" for item in delivery.writes()) == 1


@pytest.mark.parametrize("status", [200, 403, 404])
def test_deployment_creation_requires_actual_missing_ref(delivery: Delivery, status: int) -> None:
    delivery.state["main"] = delivery.state["head"]
    delivery.state["deployment_status"] = status
    outcome = delivery.run("source_promotion", "--apply")
    writes = delivery.writes()
    if status == 403:
        assert outcome.returncode != 0
        assert writes == []
    else:
        assert outcome.returncode == 0, outcome.stderr
        assert writes[0]["method"] == ("POST" if status == 404 else "PATCH")
        if status == 200:
            assert writes[0]["body"]["force"] is False
        assert delivery.state["main"] == delivery.state["deployment"] == delivery.state["head"]
        again = delivery.run("source_promotion", "--apply")
        assert again.returncode == 0, again.stderr
        assert all(item["route"] != "git/refs/heads/main" for item in delivery.writes())


def retain(
    directory: Path, head: str, language: str, attempt: int = 1, *, provenance: bool = True
) -> bytes:
    source = directory / f"input-{language}-{attempt}"
    source.mkdir()
    data = json.dumps(
        {
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {"driver": {"name": "CodeQL"}},
                    "automationDetails": {"id": f"/language:{language}/"},
                    "versionControlProvenance": [
                        {
                            "revisionId": head,
                            "repositoryUri": "https://github.com/example/project",
                            "branch": "refs/heads/dev",
                        }
                    ],
                    "results": [
                        {
                            "ruleId": "retained-disposition",
                            "message": {"text": "Preserve this genuine result."},
                            "suppressions": [{"kind": "external", "status": "accepted"}],
                        }
                    ],
                }
            ],
        },
        indent=2,
    ).encode()
    if not provenance:
        document = json.loads(data)
        del document["runs"][0]["versionControlProvenance"]
        data = json.dumps(document, indent=2).encode()
    (source / "upload.sarif").write_bytes(data)
    env = {
        "GITHUB_REPOSITORY": "example/project",
        "GITHUB_SHA": head,
        "GITHUB_RUN_ID": "41",
        "GITHUB_RUN_ATTEMPT": str(attempt),
        "GITHUB_EVENT_NAME": "push",
        "GITHUB_REF": "refs/heads/dev",
    }
    # seal is a source-job filesystem operation; environment is its real public input.
    previous = {key: os.environ.get(key) for key in env}
    try:
        os.environ.update(env)
        seal(
            source,
            directory / "retained" / f"{language}-{attempt}",
            language,
            f"original-{language}",
            41,
        )
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return data


def test_new_desktop_tag_is_annotated_immutable_and_repairable(delivery: Delivery) -> None:
    delivery.state.update(main=delivery.state["head"], tag_exists=False, release_status=404)
    outcome = delivery.run("source_promotion", "--apply")
    assert outcome.returncode == 0, outcome.stderr
    tagging = [item for item in delivery.writes() if item["route"] == "git/tags"]
    assert len(tagging) == 1
    assert tagging[0]["body"]["type"] == "commit"
    assert tagging[0]["body"]["object"] == delivery.state["head"]
    references = [item for item in delivery.writes() if item["route"] == "git/refs"]
    assert len(references) == 1
    assert references[0]["body"] == {
        "ref": "refs/tags/desktop-v" + delivery.state["version"],
        "sha": "annotated-desktop",
    }
    repaired = delivery.run("source_promotion", "--apply")
    assert repaired.returncode == 0, repaired.stderr
    assert len([item for item in delivery.writes() if item["route"] == "git/tags"]) == 1
    assert all(
        item["method"] != "PATCH" or "/tags/" not in item["route"] for item in delivery.writes()
    )


def test_complete_desktop_release_needs_no_republication(delivery: Delivery) -> None:
    delivery.state["main"] = delivery.state["head"]
    delivery.state["tagged_source"] = delivery.state["head"]
    outcome = delivery.run("source_promotion", "--apply")
    assert outcome.returncode == 0, outcome.stderr
    assert "publish_desktop=false\n" in (delivery.directory / "outputs").read_text()
    assert all(item["route"] not in {"git/tags", "git/refs"} for item in delivery.writes())


@pytest.mark.parametrize("provenance", [False, True])
def test_registered_analysis_preserves_every_original_byte_and_disposition(
    delivery: Delivery,
    provenance: bool,
) -> None:
    original = {
        language: retain(
            delivery.directory, delivery.state["head"], language, provenance=provenance
        )
        for language in LANGUAGES
    }
    outcome = delivery.run(
        "code_scanning", "register", "--directory", str(delivery.directory / "retained")
    )
    assert outcome.returncode == 0, outcome.stderr
    writes = delivery.writes()
    assert len(writes) == 3
    actual: set[bytes] = set()
    for item in writes:
        assert item["route"] == "code-scanning/sarifs"
        assert item["body"]["ref"] == "refs/heads/main"
        assert item["body"]["commit_sha"] == delivery.state["head"]
        decoded = gzip.decompress(base64.b64decode(item["body"]["sarif"], validate=True))
        actual.add(decoded)
    assert actual == set(original.values())
    assert delivery.state["main"] == "b" * 40


@pytest.mark.parametrize(
    "failure",
    [
        "changed",
        "language",
        "reference",
        "attempt",
        "rejected",
        "processing",
        "original-source",
        "original-id",
    ],
)
def test_invalid_or_unprocessed_analysis_never_changes_refs(
    delivery: Delivery, failure: str
) -> None:
    for language in LANGUAGES:
        retain(delivery.directory, delivery.state["head"], language)
    directory = delivery.directory / "retained"
    artifact = directory / "actions-1"
    if failure == "changed":
        (artifact / "analysis.sarif").write_bytes(b"{}")
    elif failure == "language":
        (artifact / "manifest.json").unlink()
    elif failure in {"reference", "attempt"}:
        path = artifact / "manifest.json"
        proof = json.loads(path.read_text())
        proof["source_ref" if failure == "reference" else "source_run_attempt"] = (
            "refs/pull/7/merge" if failure == "reference" else 2
        )
        path.write_text(json.dumps(proof))
    elif failure == "original-source":
        delivery.state["original_head"] = "c" * 40
    elif failure == "original-id":
        delivery.state["original_id"] = 42
    elif failure == "rejected":
        delivery.state["upload_status"] = 403
    else:
        delivery.state["processing_errors"] = ["Contract processing refused"]
    outcome = delivery.run("code_scanning", "register", "--directory", str(directory))
    assert outcome.returncode != 0
    assert all(item["route"] == "code-scanning/sarifs" for item in delivery.writes())
    assert len(delivery.writes()) <= 1
    assert delivery.state["main"] == delivery.state["deployment"] == "b" * 40


def test_rerun_reuses_only_latest_original_language_attempt(tmp_path: Path) -> None:
    for language in LANGUAGES:
        retain(tmp_path, "a" * 40, language)
    latest = retain(tmp_path, "a" * 40, "actions", 2)
    selected = admitted_payloads(tmp_path / "retained", "example/project", "a" * 40, 41, 2)
    assert selected["actions"] == (
        latest,
        json.loads((tmp_path / "retained/actions-2/manifest.json").read_bytes()),
    )
    assert selected["python"][1]["source_run_attempt"] == 1


@pytest.mark.parametrize("failure", [None, "changed", "extra", "source", "missing", "checksum"])
def test_cli_publication_stages_identical_complete_payloads_only(
    tmp_path: Path, failure: str | None
) -> None:
    directory = tmp_path / "qualified"
    directory.mkdir()
    for target in PLATFORMS:
        platform = tmp_path / target
        platform.mkdir()
        for name in names("0.3.0", target):
            if not name.endswith(".sha256"):
                data = f"Qualified payload {name}\n".encode()
                (platform / name).write_bytes(data)
                (platform / (name + ".sha256")).write_text(
                    f"{hashlib.sha256(data).hexdigest()}  {name}\n"
                )
        if failure == "checksum":
            checksum = next(platform.glob("*.sha256"))
            checksum.write_text("0" * 64 + "  " + checksum.name.removesuffix(".sha256") + "\n")
        seal_cli(platform, "a" * 40, "0.3.0", target)
        for path in platform.iterdir():
            (directory / path.name).write_bytes(path.read_bytes())
    output = tmp_path / "release"
    if failure == "changed":
        next(directory.glob("*.whl")).write_bytes(b"changed native bytes")
    elif failure == "extra":
        (directory / "unqualified.exe").write_bytes(b"unqualified")
    elif failure == "source":
        path = next(directory.glob("qualification-*.json"))
        proof = json.loads(path.read_bytes())
        proof["source_sha"] = "b" * 40
        path.write_text(json.dumps(proof))
    elif failure == "missing":
        next(directory.glob("*.crate")).unlink()
    if failure:
        with pytest.raises(PromotionRefused):
            verify_cli(directory, output, "a" * 40, "0.3.0")
        assert not output.exists()
    else:
        verify_cli(directory, output, "a" * 40, "0.3.0")
        assert len(list(output.iterdir())) == 14
        assert all(
            path.read_bytes() == (directory / path.name).read_bytes() for path in output.iterdir()
        )
