"""Advance Main and deployment only from the current fully qualified Dev source."""

from __future__ import annotations

import argparse
import os
import subprocess
import time
from pathlib import Path

from release_scripts._github_delivery import GitHub, PromotionRefused, require
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


def promote(api: GitHub, head: str, run_id: int, attempt: int, *, apply: bool) -> None:
    if apply:
        require(
            os.environ.get("GITHUB_ACTIONS") == "true"
            and os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted",
            "Reference promotion belongs to the hosted qualification owner",
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
    require_policy(api)
    previous = api.read("git/ref/heads/main")["object"]["sha"]
    comparison = api.read(f"compare/{previous}...{head}")
    require(
        comparison.get("status") in {"ahead", "identical"},
        "Main cannot fast-forward to this source",
    )
    if not apply:
        print("Qualified Dev source and reviewed delivery policy admitted; no references changed.")
        return
    require_registered(api, head)
    # Revalidate immediately before each authority change. A mechanical refusal
    # ends this run; no alternate token, force update or administrator path exists.
    source(api, head, run_id, attempt)
    if previous != head:
        api.write("git/refs/heads/main", {"sha": head, "force": False})
    read_back(api, "main", head)
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
    if output := os.environ.get("GITHUB_OUTPUT"):
        with Path(output).open("a", encoding="utf-8") as stream:
            stream.write(
                f"publish_desktop={str(publish_desktop).lower()}\n"
                f"desktop_version={desktop_version}\n"
            )
    print(f"Promoted qualified Dev {head}; source run {run_id} attempt {attempt}.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="advance refs after all admission checks"
    )
    arguments = parser.parse_args()
    try:
        promote(
            GitHub(os.environ["REPOSITORY"]),
            os.environ["HEAD_SHA"],
            int(os.environ["SOURCE_RUN_ID"]),
            int(os.environ["SOURCE_ATTEMPT"]),
            apply=arguments.apply,
        )
    except (PromotionRefused, KeyError, ValueError, OSError, subprocess.SubprocessError) as error:
        raise SystemExit(f"Promotion refused: {error}") from None


if __name__ == "__main__":
    main()
