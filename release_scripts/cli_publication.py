"""Reconcile the CLI release before dispatching its existing publication owner."""

from __future__ import annotations

from typing import Literal

from release_scripts._github_delivery import GitHub, require
from release_scripts.cli_artifacts import release_version, require_published


def prepare(
    api: GitHub, head: str, run_id: int
) -> tuple[str, Literal["start", "running", "complete"]]:
    """Return whether publication must start, is running, or has completed."""
    version = release_version(api, head)
    tag = f"cli-v{version}"
    status, reference = api.request(f"git/ref/tags/{tag}")
    if status == 404:
        require(
            api.read("git/ref/heads/main")["object"]["sha"] == head
            and api.read("git/ref/heads/dev")["object"]["sha"] == head,
            "CLI tagging requires current qualified Main and Dev",
        )
        annotated = api.write(
            "git/tags",
            {
                "tag": tag,
                "message": f"CLI {version}; qualified source {head}; Dev run {run_id}",
                "object": head,
                "type": "commit",
            },
            create=True,
        )
        api.write("git/refs", {"ref": f"refs/tags/{tag}", "sha": annotated["sha"]}, create=True)
        reference = api.read(f"git/ref/tags/{tag}")
    else:
        require(status == 200, f"CLI tag could not be read ({status})")
    require(reference.get("object", {}).get("type") == "tag", "Annotated CLI tag required")
    annotated = api.read("git/tags/" + reference["object"]["sha"])
    require(
        annotated.get("tag") == tag and annotated.get("object", {}).get("type") == "commit",
        "CLI tag identity differs",
    )
    tagged_source = annotated["object"]["sha"]
    require(
        api.read(f"compare/{tagged_source}...{head}").get("status") in {"ahead", "identical"},
        "CLI version belongs to a different source history",
    )
    if tagged_source != head:
        require_published(api, head)
        return version, "complete"
    runs = api.read(
        "actions/workflows/cli-release.yml/runs"
        f"?event=workflow_dispatch&head_sha={head}&branch={tag}&per_page=100"
    )
    require(
        runs["total_count"] == len(runs["workflow_runs"]),
        "Complete CLI publication run inventory required",
    )
    candidates = [
        run
        for run in runs["workflow_runs"]
        if run.get("head_sha") == head
        and run.get("head_branch") == tag
        and run.get("event") == "workflow_dispatch"
        and run.get("path") == ".github/workflows/cli-release.yml"
        and run.get("repository", {}).get("full_name") == api.repository
        and run.get("head_repository", {}).get("full_name") == api.repository
    ]
    require(len(candidates) == len(runs["workflow_runs"]), "CLI publication run identity differs")
    if not candidates:
        return version, "start"
    latest = max(candidates, key=lambda run: run["id"])
    require(
        latest.get("status")
        in {"completed", "queued", "in_progress", "requested", "waiting", "pending"},
        "CLI publication status is unknown",
    )
    if latest["status"] != "completed":
        print(f"CLI publication {latest['id']} is still running; no duplicate dispatch.")
        return version, "running"
    require(
        latest.get("conclusion") == "success",
        f"CLI publication {latest['id']} failed; inspect its original receipt before resuming",
    )
    require_published(api, head)
    return version, "complete"
