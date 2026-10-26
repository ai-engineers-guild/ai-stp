"""Collect authenticated installation-component observations in disposable CI state.

The native engine owns signature verification and confinement. These reports
are observations for release review, never serialized installation authority.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
REQUIRED_PROBES = {"ipv4_tcp", "ipv6_tcp", "ipv4_udp"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_report(report: dict[str, Any], harness: str, version: str, source_commit: str) -> None:
    artifact = report["artifact"]
    info = report["provider_info"]
    network = report["network"]
    require(artifact["harness_id"] == info["harness_id"] == harness, "wrong harness")
    require(artifact["version"] == info["provider_version"] == version, "wrong version")
    require(artifact["project"] == info["provider_id"], "wrong component identity")
    require(artifact["platform"] == "linux/x86_64", "wrong qualification platform")
    require(artifact["trust_level"] == "verified_publisher", "unverified publisher")
    require(artifact["source_commit"] == source_commit, "artifact and tag source differ")
    require(
        network["enforcement"] == "enforced"
        and network["isolated"] == "denied"
        and set(network["positive_control"]) >= REQUIRED_PROBES,
        "positive network separation evidence is missing",
    )
    require(report["harness_written"] is False, "inspection wrote harness state")
    require(report["installed"] is False, "inspection reported an installation")
    projects = [
        profile
        for profile in info["scoped_projection_profiles"]
        if profile["target_scope"] == "project"
    ]
    require(len(projects) == 1, "one authenticated project profile is required")
    require(bool(projects[0]["component_kinds"]), "the project profile has no kinds")
    require(bool(projects[0]["native_namespaces"]), "the project profile has no paths")


def tag_commit(repository: str, version: str) -> str:
    # The intended component family has one owner; a historical publisher
    # accepted by the engine must not silently select a different family here.
    require(
        re.fullmatch(r"NDDev-Technocracy-Archive/[a-z]+-setup-system", repository) is not None,
        "unexpected component repository",
    )
    url = f"https://api.github.com/repos/{repository}/git/ref/tags/" + urllib.parse.quote(
        version, safe=""
    )
    for _ in range(4):
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "ai-stp"}
        if token := os.environ.get("GH_TOKEN"):
            headers["Authorization"] = f"Bearer {token}"
        with urllib.request.urlopen(
            urllib.request.Request(url, headers=headers), timeout=30
        ) as reply:
            obj = json.load(reply)["object"]
        if obj["type"] == "commit":
            require(re.fullmatch(r"[0-9a-f]{40}", obj["sha"]) is not None, "invalid tag commit")
            return str(obj["sha"])
        require(obj["type"] == "tag", "tag does not resolve to a commit")
        require(re.fullmatch(r"[0-9a-f]{40}", obj["sha"]) is not None, "invalid annotated tag")
        url = f"https://api.github.com/repos/{repository}/git/tags/{obj['sha']}"
    raise ValueError("tag chain is too deep")


def invoke(binary: Path, home: Path, arguments: list[str]) -> dict[str, Any]:
    # No job token, account credentials, proxy or caller home reaches the CLI.
    environment = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / "config"),
        "XDG_DATA_HOME": str(home / "data"),
        "XDG_CACHE_HOME": str(home / "cache"),
        "LANG": "C.UTF-8",
    }
    result = subprocess.run(
        [str(binary), *arguments, "--json"],
        capture_output=True,
        check=False,
        timeout=240,
        env=environment,
    )
    if result.returncode != 0:
        try:
            error = json.loads(result.stdout)["error"]
            detail = str(error.get("message", error.get("code", "refused")))[:1000]
        except (ValueError, KeyError, TypeError):
            detail = "the native engine returned no error envelope"
        raise ValueError(f"native observation failed: {arguments}: {detail}")
    require(not result.stderr, "native observation emitted unexpected stderr")
    envelope = json.loads(result.stdout)
    require(envelope["ok"] is True, "native observation did not succeed")
    return dict(envelope["data"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--consumer-commit", required=True)
    parser.add_argument("--require-managed-default", action="store_true")
    args = parser.parse_args()
    require(
        re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", args.version)
        is not None,
        "an exact canonical component version is required",
    )
    require(
        re.fullmatch(r"[0-9a-f]{40}", args.consumer_commit) is not None,
        "an exact consumer commit is required",
    )
    binary = args.binary.resolve(strict=True)
    catalog = json.loads(
        (ROOT / "packages/foundation/src/ai_stp_foundation/provider_catalog.json").read_text()
    )
    harnesses = sorted(
        {p["harness_id"] for p in catalog["profiles"] if p["target_scope"] == "global"}
    )
    require(len(harnesses) == 7, "the selected seven-component family differs")
    reports = []
    with tempfile.TemporaryDirectory(prefix="ai-stp-provider-observation-") as temporary:
        home = Path(temporary).resolve(strict=True)
        state = home / "state"
        state.mkdir()
        if args.require_managed_default:
            capabilities = invoke(binary, home, ["capabilities"])
            require(
                capabilities["managed_provider_version"] == args.version,
                "the selected binary does not have the candidate's managed default",
            )
        for harness in harnesses:
            report = invoke(
                binary,
                home,
                [
                    "provider",
                    "inspect",
                    "--state-dir",
                    str(state),
                    "--harness",
                    harness,
                    "--version",
                    args.version,
                ],
            )
            source = tag_commit(report["artifact"]["publisher"]["repository"], args.version)
            validate_report(report, harness, args.version, source)
            reports.append(report)
            print(
                f"Authenticated project declaration: {harness} {args.version} {source}", flush=True
            )
    args.out.mkdir(parents=True, exist_ok=False)
    result = {
        "schema_version": 1,
        "evidence_type": "authenticated_provider_inspection",
        "component_version": args.version,
        "consumer_commit": args.consumer_commit,
        "installation_qualified": False,
        "reports": reports,
    }
    (args.out / "observations.json").write_text(json.dumps(result, indent=2) + "\n")
    (args.out / "provider-declarations.json").write_text(
        json.dumps([r["provider_info"] for r in reports], indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
