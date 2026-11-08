"""Retain actual accepted CodeQL payloads and register them for the release reference."""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from release_scripts._github_delivery import GitHub, PromotionRefused, require
from release_scripts.source_admission import require_policy, source

LANGUAGES = ("actions", "javascript-typescript", "python")
TARGET = "refs/heads/main"
MAX_PAYLOAD = 64 * 1024 * 1024


def payload(path: Path, head: str, language: str, repository: str) -> tuple[bytes, str]:
    require(path.is_file() and not path.is_symlink(), "SARIF must be a regular file")
    require(0 < path.stat().st_size <= MAX_PAYLOAD, "SARIF exceeds the payload boundary")
    data = path.read_bytes()
    document = json.loads(data)
    require(document.get("version") == "2.1.0", "A real SARIF 2.1.0 payload is required")
    runs = document.get("runs")
    require(isinstance(runs, list) and 0 < len(runs) <= 20, "Missing or excessive analysis runs")
    refs: set[str] = set()
    for run in runs:
        require(
            run.get("tool", {}).get("driver", {}).get("name") == "CodeQL",
            "Unexpected analysis tool",
        )
        require(
            run.get("automationDetails", {}).get("id", "").rstrip("/") == f"/language:{language}",
            "The retained payload changed analysis category",
        )
        provenance = run.get("versionControlProvenance")
        require(
            isinstance(provenance, list) and len(provenance) == 1,
            "Exact source provenance required",
        )
        origin = provenance[0]
        require(origin.get("revisionId") == head, "SARIF belongs to another source commit")
        require(
            origin.get("repositoryUri")
            in {f"https://github.com/{repository}", f"https://github.com/{repository}.git"},
            "SARIF belongs to another repository",
        )
        require(isinstance(origin.get("branch"), str), "Original analysis reference is missing")
        refs.add(origin["branch"])
    require(len(refs) == 1, "The payload combines different source references")
    return data, refs.pop()


def seal(directory: Path, output: Path, language: str, sarif_id: str) -> None:
    require(language in LANGUAGES, "Unknown CodeQL language")
    require(
        bool(re.fullmatch(r"[A-Za-z0-9_-]{1,128}", sarif_id)), "Accepted original SARIF ID required"
    )
    repository, head = os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_SHA"]
    files = sorted(directory.glob("*.sarif"))
    require(len(files) == 1, "One complete language payload is required")
    data, analysis_ref = payload(files[0], head, language, repository)
    require(not output.exists(), "The evidence directory must be new")
    output.mkdir(parents=True, mode=0o700)
    with (output / "analysis.sarif").open("xb") as stream:
        stream.write(data)
    proof = {
        "schema_version": 1,
        "repository": repository,
        "source_sha": head,
        "source_run_id": int(os.environ["GITHUB_RUN_ID"]),
        "source_run_attempt": int(os.environ["GITHUB_RUN_ATTEMPT"]),
        "source_event": os.environ["GITHUB_EVENT_NAME"],
        "source_ref": os.environ["GITHUB_REF"],
        "analysis_ref": analysis_ref,
        "language": language,
        "sarif_id": sarif_id,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
    }
    with (output / "manifest.json").open("x") as stream:
        json.dump(proof, stream, sort_keys=True)


def admitted_payloads(
    directory: Path, repository: str, head: str, run_id: int, attempt: int
) -> dict[str, tuple[bytes, dict[str, Any]]]:
    manifests = sorted(directory.glob("*/manifest.json"))
    require(0 < len(manifests) <= 100, "Missing or excessive retained analysis inventories")
    selected: dict[str, tuple[bytes, dict[str, Any]]] = {}
    seen: set[tuple[str, int]] = set()
    for path in manifests:
        require(
            not path.is_symlink() and path.stat().st_size <= 16 * 1024, "Invalid analysis inventory"
        )
        require(
            path.resolve().is_relative_to(directory.resolve()),
            "Analysis inventory escaped its input",
        )
        proof = json.loads(path.read_bytes())
        language = proof.get("language")
        require(language in LANGUAGES, "Unexpected retained language")
        source_attempt = proof.get("source_run_attempt")
        require(
            type(source_attempt) is int and 0 < source_attempt <= attempt, "Invalid source attempt"
        )
        require(
            (language, source_attempt) not in seen, "Duplicate language inventory for one attempt"
        )
        seen.add((language, source_attempt))
        require(
            proof.get("schema_version") == 1
            and proof.get("repository") == repository
            and proof.get("source_sha") == head
            and proof.get("source_run_id") == run_id
            and proof.get("source_event") == "push"
            and proof.get("source_ref") == "refs/heads/dev"
            and proof.get("analysis_ref") == "refs/heads/dev",
            "The retained analysis is not this qualified Dev source",
        )
        require(
            isinstance(proof.get("sarif_id"), str)
            and bool(re.fullmatch(r"[A-Za-z0-9_-]{1,128}", proof["sarif_id"])),
            "The retained payload has no original acceptance identifier",
        )
        require(
            {item.name for item in path.parent.iterdir()} == {"analysis.sarif", "manifest.json"},
            "Unexpected content in the retained analysis",
        )
        data, analysis_ref = payload(path.parent / "analysis.sarif", head, language, repository)
        require(
            analysis_ref == proof["analysis_ref"]
            and len(data) == proof.get("size_bytes")
            and hashlib.sha256(data).hexdigest() == proof.get("sha256"),
            "Retained analysis bytes differ from the accepted source payload",
        )
        current = selected.get(language)
        if current is None or current[1]["source_run_attempt"] < source_attempt:
            selected[language] = (data, proof)
    require(set(selected) == set(LANGUAGES), "Every original analysis language is required")
    return selected


def require_registered(api: GitHub, head: str) -> None:
    analyses = api.read(
        "code-scanning/analyses?ref=refs%2Fheads%2Fmain&tool_name=CodeQL&per_page=100"
    )
    require(isinstance(analyses, list), "Release analysis inventory is unavailable")
    for language in LANGUAGES:
        category = f"/language:{language}"
        candidates = [item for item in analyses if item.get("category", "").rstrip("/") == category]
        require(bool(candidates), f"Release analysis is missing: {language}")
        latest = max(candidates, key=lambda item: item["id"])
        require(
            latest.get("commit_sha") == head
            and latest.get("ref") == TARGET
            and latest.get("error") == ""
            and latest.get("tool", {}).get("name") == "CodeQL",
            f"Release analysis does not match the qualified source: {language}",
        )
    require(
        api.read("code-scanning/alerts?state=open&ref=refs%2Fheads%2Fmain&per_page=1") == [],
        "The release reference has open processed findings",
    )


def register(directory: Path) -> None:
    require(
        os.environ.get("GITHUB_ACTIONS") == "true"
        and os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted",
        "Release analysis registration belongs to the hosted qualification owner",
    )
    api = GitHub(os.environ["REPOSITORY"])
    head = os.environ["HEAD_SHA"]
    run_id, attempt = int(os.environ["SOURCE_RUN_ID"]), int(os.environ["SOURCE_ATTEMPT"])
    source(api, head, run_id, attempt)
    require_policy(api)
    selected = admitted_payloads(directory, api.repository, head, run_id, attempt)
    for language, (data, proof) in sorted(selected.items()):
        source(api, head, run_id, attempt)
        # Preserve every original finding, disposition, fingerprint, category
        # and Dev provenance byte. Only the API's destination reference changes.
        encoded = base64.b64encode(gzip.compress(data, mtime=0)).decode("ascii")
        require(len(encoded) <= 10_000_000, "Compressed analysis exceeds the API limit")
        status, result = api.request(
            "code-scanning/sarifs",
            method="POST",
            body={"commit_sha": head, "ref": TARGET, "sarif": encoded, "tool_name": "CodeQL"},
        )
        require(status == 202, f"Release analysis registration was refused ({status})")
        identifier = result.get("id")
        require(
            isinstance(identifier, str) and bool(re.fullmatch(r"[A-Za-z0-9_-]{1,128}", identifier)),
            "GitHub did not acknowledge the registered payload",
        )
        deadline, delay = time.monotonic() + 180, 2
        while time.monotonic() < deadline:
            status, processing = api.request(f"code-scanning/sarifs/{identifier}")
            if status == 200 and processing.get("processing_status") == "complete":
                require(not processing.get("errors"), "Registered analysis has processing errors")
                break
            require(
                status == 404
                or (status == 200 and processing.get("processing_status") == "pending"),
                "GitHub refused processing of the original analysis",
            )
            time.sleep(min(delay, max(0, deadline - time.monotonic())))
            delay = min(delay * 2, 10)
        else:
            raise PromotionRefused("Registered analysis did not finish processing")
        print(
            json.dumps(
                {
                    "language": language,
                    "source_sha": head,
                    "original_sarif_id": proof["sarif_id"],
                    "sha256": proof["sha256"],
                    "registered_ref": TARGET,
                }
            )
        )
    require_registered(api, head)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    seal_parser = commands.add_parser("seal")
    seal_parser.add_argument("--directory", type=Path, required=True)
    seal_parser.add_argument("--output", type=Path, required=True)
    seal_parser.add_argument("--language", choices=LANGUAGES, required=True)
    seal_parser.add_argument("--sarif-id", required=True)
    register_parser = commands.add_parser("register")
    register_parser.add_argument("--directory", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        if arguments.command == "seal":
            seal(arguments.directory, arguments.output, arguments.language, arguments.sarif_id)
        else:
            register(arguments.directory)
    except (PromotionRefused, KeyError, ValueError, OSError, subprocess.SubprocessError) as error:
        raise SystemExit(f"Source analysis refused: {error}") from None


if __name__ == "__main__":
    main()
