"""Reuse exact qualified installers for native-owner diagnosis without release authority."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

from release_scripts._github_delivery import GitHub, require
from release_scripts.source_admission import source


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["admit", "retain"])
    arguments = parser.parse_args()
    require(
        os.environ.get("GITHUB_ACTIONS") == "true"
        and os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted"
        and os.environ.get("RUNNER_OS") in {"macOS", "Windows"}
        and os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
        and os.environ.get("GITHUB_WORKFLOW") == "desktop",
        "Native diagnosis requires its explicit disposable hosted workflow",
    )
    app_source = os.environ["AI_STP_DESKTOP_DIAGNOSTIC_SOURCE"]
    fixture_source = os.environ["GITHUB_SHA"]
    run = os.environ["AI_STP_DESKTOP_DIAGNOSTIC_RUN"]
    attempt = os.environ["AI_STP_DESKTOP_DIAGNOSTIC_ATTEMPT"]
    require(
        all(re.fullmatch(r"[0-9a-f]{40}", value) for value in [app_source, fixture_source])
        and all(re.fullmatch(r"[1-9][0-9]{0,19}", value) for value in [run, attempt]),
        "Exact application/fixture source and producer attempt required",
    )
    if arguments.action == "admit":
        source(GitHub(os.environ["GITHUB_REPOSITORY"]), app_source, int(run), int(attempt))
        return
    path = Path(os.environ["RUNNER_TEMP"]) / "installed-personal-desktop.json"
    proof = json.loads(path.read_text(encoding="utf-8"))
    require(
        proof["schema_version"] == 2
        and proof["source_sha"] == app_source
        and proof["release_authorized"] is False,
        "Native diagnostic proof differs from the admitted application",
    )
    proof.update(
        fixture_source_sha=fixture_source,
        source_run_id=run,
        source_run_attempt=int(attempt),
        diagnostic_only=True,
    )
    path.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
