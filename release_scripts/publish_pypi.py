#!/usr/bin/env python3
"""Publish an attested candidate to PyPI, unattended.

`0.0.17` publishes one distribution. Historical six-package runs still must not
overlap: they share one `concurrency` group, so a second dispatch while another
is pending does not queue politely — it takes the group and the earlier one
dies. This waits for each requested run to finish before starting the next.

Nothing here uploads anything. The upload is `publish-pypi.yml` using PyPI
Trusted Publishing, which mints an OIDC identity naming this repository, that
workflow file and the environment. There is no API token to hold, and this
script could not publish without GitHub even if it wanted to.

What it does hold is the one input a human cannot check by eye: `run_id`. Several
attested candidates can carry the same version — the `v0.0.4` tag moved three
times, leaving three successful candidates for one version — so the run id, not
the version, decides which bytes reach PyPI. It is required, and it is verified
against the tag before anything is dispatched.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

REPO = "ai-engineers-guild/ai-stp"

#: The public install is one distribution (`ADR-0146`). Historical names remain
#: rejected by the `--packages` parser rather than dispatched.
PACKAGES: tuple[str, ...] = ("cli",)

POLL_SECONDS = 10
RUN_TIMEOUT_SECONDS = 1200


def say(message: str) -> None:
    """Print so a redirected log shows progress while the run is still going."""
    print(message, flush=True)


def gh(*arguments: str, check: bool = True) -> str:
    finished = subprocess.run(["gh", *arguments], capture_output=True, text=True, check=False)
    if check and finished.returncode != 0:
        raise SystemExit(f"gh {' '.join(arguments)} failed: {finished.stderr.strip()}")
    return finished.stdout.strip()


def api(path: str, *arguments: str, check: bool = True) -> object:
    raw = gh("api", path, *arguments, check=check)
    return json.loads(raw) if raw else None


def published(project: str, version: str) -> bool:
    """Ask PyPI, not GitHub. A green run is not the same claim as a live file."""
    try:
        with urllib.request.urlopen(f"https://pypi.org/pypi/{project}/json", timeout=30) as answer:
            document = json.load(answer)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return False
    releases = document.get("releases", {})
    return bool(releases.get(version))


def candidate_head(run_id: str) -> str:
    run = api(f"repos/{REPO}/actions/runs/{run_id}")
    if not isinstance(run, dict):
        raise SystemExit(f"run {run_id} is unreadable")
    if run.get("conclusion") != "success":
        raise SystemExit(f"run {run_id} did not succeed: {run.get('conclusion')}")
    return str(run.get("head_sha", ""))


def tag_head(version: str) -> str:
    """Resolve `v<version>`, following an annotated tag to the commit it names."""
    reference = api(f"repos/{REPO}/git/ref/tags/v{version}", check=False)
    if not isinstance(reference, dict) or "object" not in reference:
        raise SystemExit(f"no tag v{version}")
    obj = reference["object"]
    if not isinstance(obj, dict):
        raise SystemExit(f"tag v{version} is unreadable")
    if obj.get("type") == "commit":
        return str(obj.get("sha", ""))
    annotated = api(f"repos/{REPO}/git/tags/{obj.get('sha')}")
    if not isinstance(annotated, dict):
        raise SystemExit(f"tag object for v{version} is unreadable")
    inner = annotated.get("object")
    return str(inner.get("sha", "")) if isinstance(inner, dict) else ""


def latest_run_id() -> str:
    runs = api(
        f"repos/{REPO}/actions/workflows/publish-pypi.yml/runs",
        "--jq",
        ".workflow_runs[0].id",
    )
    return str(runs)


def approve(run_id: str) -> None:
    """Approve the one environment this run is waiting on."""
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        pending = api(f"repos/{REPO}/actions/runs/{run_id}/pending_deployments")
        if isinstance(pending, list) and pending:
            entry = pending[0]
            environment = entry.get("environment", {})
            if not entry.get("current_user_can_approve"):
                raise SystemExit(
                    f"this account cannot approve {environment.get('name')}; "
                    "add it to the environment reviewers or have a reviewer approve"
                )
            body = json.dumps(
                {
                    "environment_ids": [environment.get("id")],
                    "state": "approved",
                    "comment": f"unattended publish from attested candidate, run {run_id}",
                }
            )
            subprocess.run(
                [
                    "gh",
                    "api",
                    "-X",
                    "POST",
                    f"repos/{REPO}/actions/runs/{run_id}/pending_deployments",
                    "--input",
                    "-",
                ],
                input=body,
                capture_output=True,
                text=True,
                check=False,
            )
            return
        run = api(f"repos/{REPO}/actions/runs/{run_id}")
        if isinstance(run, dict) and run.get("status") == "completed":
            return
        time.sleep(POLL_SECONDS)
    raise SystemExit(f"run {run_id} never asked for approval")


def await_run(run_id: str) -> str:
    deadline = time.monotonic() + RUN_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        run = api(f"repos/{REPO}/actions/runs/{run_id}")
        if isinstance(run, dict) and run.get("status") == "completed":
            return str(run.get("conclusion"))
        time.sleep(POLL_SECONDS)
    raise SystemExit(f"run {run_id} did not finish within {RUN_TIMEOUT_SECONDS}s")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help="exact version, no leading v")
    parser.add_argument(
        "--run-id",
        required=True,
        help="release-candidate run whose attested artifact is published",
    )
    parser.add_argument(
        "--packages",
        default=",".join(PACKAGES),
        help="comma-separated subset, in dependency order",
    )
    parser.add_argument("--dry-run", action="store_true", help="check the inputs and stop")
    options = parser.parse_args()

    head = candidate_head(options.run_id)
    tagged = tag_head(options.version)
    if head != tagged:
        raise SystemExit(
            f"candidate {options.run_id} was built at {head[:8]} but tag "
            f"v{options.version} names {tagged[:8]}; several attested candidates can "
            "carry one version, so this mismatch is the whole reason run_id is required"
        )
    say(f"candidate {options.run_id} == tag v{options.version} == {head[:8]}")

    wanted = [name for name in options.packages.split(",") if name]
    unknown = [name for name in wanted if name not in PACKAGES]
    if unknown:
        raise SystemExit(f"unknown package(s): {', '.join(unknown)}")
    if options.dry_run:
        say("dry run: would publish " + " → ".join(wanted))
        return 0

    for name in wanted:
        project = f"ai-stp-{name}"
        if published(project, options.version):
            say(f"{project} {options.version} already on PyPI, skipping")
            continue
        say(f"dispatching {project} {options.version}")
        gh(
            "workflow",
            "run",
            "publish-pypi.yml",
            "-R",
            REPO,
            "-f",
            f"version={options.version}",
            "-f",
            f"run_id={options.run_id}",
            "-f",
            f"package={name}",
        )
        time.sleep(POLL_SECONDS)
        run_id = latest_run_id()
        approve(run_id)
        conclusion = await_run(run_id)
        if conclusion != "success":
            raise SystemExit(f"{project} run {run_id} concluded {conclusion}")
        # PyPI is the authority on whether it is published, not the workflow.
        for _ in range(12):
            if published(project, options.version):
                break
            time.sleep(POLL_SECONDS)
        else:
            raise SystemExit(f"{project} run succeeded but PyPI does not serve it")
        say(f"{project} {options.version} published")

    say("all requested packages are on PyPI")
    return 0


if __name__ == "__main__":
    sys.exit(main())
