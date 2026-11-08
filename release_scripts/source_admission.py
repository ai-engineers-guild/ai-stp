"""Read-only admission of the exact qualified source and reviewed live repository policy."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, cast

from release_scripts._github_delivery import GitHub, require

ROOT = Path(__file__).resolve().parents[1]
POLICIES = ("permanent-branches", "dev-integration", "main-promotion", "main-admin-updates")


def admit_source(
    repository: str,
    head: str,
    run_id: int,
    attempt: int,
    run: dict[str, Any],
    inventory: dict[str, Any],
    jobs: dict[str, Any],
    current_dev: str,
) -> None:
    require(bool(re.fullmatch(r"[0-9a-f]{40}", head)), "Exact source SHA required")
    require(run_id > 0 and attempt > 0, "Exact source run and attempt required")
    require(
        run.get("id") == run_id
        and run.get("repository", {}).get("full_name") == repository
        and run.get("head_repository", {}).get("full_name") == repository
        and run.get("head_sha") == head
        and run.get("event") == "push"
        and run.get("head_branch") == "dev"
        and run.get("path") == ".github/workflows/check.yml"
        and run.get("status") == "completed"
        and run.get("conclusion") == "success"
        and run.get("run_attempt") == attempt,
        "The source is not this successful Dev qualification attempt",
    )
    runs = inventory.get("workflow_runs")
    require(
        isinstance(runs, list) and inventory.get("total_count") == len(runs),
        "Truncated source runs",
    )
    candidates = [
        item
        for item in cast(list[dict[str, Any]], runs)
        if item.get("path") == ".github/workflows/check.yml"
        and item.get("head_sha") == head
        and item.get("head_branch") == "dev"
        and item.get("event") == "push"
    ]
    require(
        bool(candidates) and max(item["id"] for item in candidates) == run_id,
        "Superseded source run",
    )
    rows = jobs.get("jobs")
    require(
        isinstance(rows, list) and jobs.get("total_count") == len(rows), "Truncated source jobs"
    )
    qualifications = [
        item
        for item in cast(list[dict[str, Any]], rows)
        if item.get("name") == "full-qualification"
    ]
    require(
        len(qualifications) == 1
        and qualifications[0].get("status") == "completed"
        and qualifications[0].get("conclusion") == "success",
        "Full source and installed qualification did not complete",
    )
    require(current_dev == head, "Dev advanced after qualification")


def policy_document(value: dict[str, Any]) -> dict[str, Any]:
    document = {
        key: value.get(key)
        for key in ["name", "target", "enforcement", "conditions", "bypass_actors", "rules"]
    }
    for key in ["bypass_actors", "rules"]:
        items = document[key]
        if isinstance(items, list):
            document[key] = sorted(items, key=lambda item: json.dumps(item, sort_keys=True))
    return document


def require_policy(api: GitHub) -> None:
    require(
        api.read("")["default_branch"] == "dev", "The reviewed Dev delivery policy is not active"
    )
    expected = {
        document["name"]: document
        for name in POLICIES
        for document in [json.loads((ROOT / f".github/{name}.ruleset.json").read_text())]
    }
    live = api.read("rulesets?includes_parents=true&per_page=100")
    require(
        isinstance(live, list) and len(live) == len(expected),
        "Repository policy differs from the review",
    )
    observed: set[str] = set()
    for summary in live:
        name = summary.get("name")
        require(name in expected and name not in observed, "Unknown or duplicate repository policy")
        observed.add(name)
        document = api.read(f"rulesets/{summary['id']}")
        actual, intended = policy_document(document), policy_document(expected[name])
        if "bypass_actors" not in document:
            # GitHub withholds actor lists from tokens without ruleset-write
            # authority. GitHub still authorizes the actual ref update; this
            # controller never receives administration or ruleset-write scope.
            actual.pop("bypass_actors")
            intended.pop("bypass_actors")
        require(
            actual == intended,
            f"Reviewed policy is not active: {name}",
        )


def source(api: GitHub, head: str, run_id: int, attempt: int) -> None:
    path = f"actions/runs/{run_id}"
    admit_source(
        api.repository,
        head,
        run_id,
        attempt,
        api.read(path),
        api.read(f"actions/runs?head_sha={head}&event=push&branch=dev&per_page=100"),
        api.read(f"{path}/attempts/{attempt}/jobs?per_page=100"),
        api.read("git/ref/heads/dev")["object"]["sha"],
    )
    findings = api.read("code-scanning/alerts?state=open&ref=refs%2Fheads%2Fdev&per_page=1")
    require(findings == [], "Processed Dev code scanning has open findings")
