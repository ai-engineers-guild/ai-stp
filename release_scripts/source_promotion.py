"""Prepare qualified delivery, explicitly advance Main, then reconcile deployment."""

from __future__ import annotations

import argparse
import os
import subprocess
import time
from pathlib import Path

from release_scripts._github_delivery import GitHub, PromotionRefused, require
from release_scripts.cli_artifacts import require_published
from release_scripts.code_scanning import require_registered
from release_scripts.desktop_publication import reconcile
from release_scripts.desktop_version import version
from release_scripts.source_admission import ROOT, require_policy, source


def read_back(api: GitHub, ref: str, head: str) -> None:
    for attempt in range(5):
        if api.read(f"git/ref/heads/{ref}")["object"]["sha"] == head:
            return
        if attempt < 4:
            time.sleep(2)
    raise PromotionRefused(f"{ref} did not retain the acknowledged source")


def promote(
    api: GitHub, head: str, run_id: int, attempt: int, *, apply: bool, advance_main: bool = False
) -> None:
    require(not (apply and advance_main), "Choose one delivery authority")
    if apply:
        require(
            os.environ.get("GITHUB_ACTIONS") == "true"
            and os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted",
            "Deployment reconciliation belongs to the hosted qualification owner",
        )
    if advance_main:
        require(
            os.environ.get("GITHUB_ACTIONS") != "true",
            "Main promotion uses the existing operator principal outside Actions",
        )
        require(
            api.read("").get("permissions", {}).get("admin") is True,
            "The existing Main administrator principal is required",
        )
    checkout = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    require(checkout.stdout.strip() == head, "Promotion code must be the qualified source")
    source(api, head, run_id, attempt)
    require_policy(api, require_actors=advance_main)
    previous = api.read("git/ref/heads/main")["object"]["sha"]
    comparison = api.read(f"compare/{previous}...{head}")
    require(
        comparison.get("status") in {"ahead", "identical"},
        "Main cannot fast-forward to this source",
    )
    if not (apply or advance_main):
        print("Qualified Dev source and reviewed delivery policy admitted; no references changed.")
        return
    require_registered(api, head)
    # The operator path is explicit, never a fallback after an Actions refusal.
    # A refused write ends the operation; no token replacement or force retry.
    source(api, head, run_id, attempt)
    if advance_main:
        if previous != head:
            api.write("git/refs/heads/main", {"sha": head, "force": False})
        read_back(api, "main", head)
        source(api, head, run_id, attempt)
        status, _ = api.request(
            "actions/workflows/deploy.yml/dispatches",
            method="POST",
            body={"ref": "dev", "inputs": {"source_run_id": str(run_id)}},
        )
        require(status == 204, f"Delivery dispatch refused ({status}); Main is already advanced")
        print(f"Main retained qualified Dev {head}; delivery reconciliation dispatched.")
        return
    if previous != head:
        output_values(deployed=False)
        print(
            f"Qualified source {head} is ready for the existing Main operator; "
            "no references changed and no deployment claimed."
        )
        return
    read_back(api, "main", head)
    require_published(api, head)
    source(api, head, run_id, attempt)
    require(
        api.read("git/ref/heads/main")["object"]["sha"] == head, "Main changed before deployment"
    )
    status, _ = api.request("git/ref/heads/deploy/prod")
    if status == 404:
        api.write("git/refs", {"ref": "refs/heads/deploy/prod", "sha": head}, create=True)
    else:
        require(status == 200, f"Deployment reference could not be read ({status})")
        api.write("git/refs/heads/deploy/prod", {"sha": head, "force": False})
    read_back(api, "deploy/prod", head)
    desktop_version = version(ROOT)
    publish_desktop = reconcile(api, head, desktop_version, run_id)
    output_values(
        deployed=True,
        publish_desktop=str(publish_desktop).lower(),
        desktop_version=desktop_version,
    )
    print(f"Promoted qualified Dev {head}; source run {run_id} attempt {attempt}.")


def output_values(*, deployed: bool, **values: str) -> None:
    if output := os.environ.get("GITHUB_OUTPUT"):
        with Path(output).open("a", encoding="utf-8") as stream:
            stream.write(f"deployed={str(deployed).lower()}\n")
            for name, value in values.items():
                stream.write(f"{name}={value}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    authority = parser.add_mutually_exclusive_group()
    authority.add_argument(
        "--apply", action="store_true", help="prepare delivery or reconcile already promoted Main"
    )
    authority.add_argument(
        "--advance-main", action="store_true", help="use the existing Main operator and dispatch CI"
    )
    arguments = parser.parse_args()
    try:
        promote(
            GitHub(os.environ["REPOSITORY"]),
            os.environ["HEAD_SHA"],
            int(os.environ["SOURCE_RUN_ID"]),
            int(os.environ["SOURCE_ATTEMPT"]),
            apply=arguments.apply,
            advance_main=arguments.advance_main,
        )
    except (PromotionRefused, KeyError, ValueError, OSError, subprocess.SubprocessError) as error:
        raise SystemExit(f"Promotion refused: {error}") from None


if __name__ == "__main__":
    main()
