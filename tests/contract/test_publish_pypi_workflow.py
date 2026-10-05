"""PyPI publication uses one OIDC identity per project."""

from pathlib import Path
from typing import Any, cast

import yaml

WORKFLOW = Path(".github/workflows/publish-pypi.yml")


def test_each_distribution_has_a_distinct_trusted_publisher_identity() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "          - cli" in workflow
    assert "          - foundation" not in workflow
    assert "          - sources" not in workflow
    assert "name: pypi-cli" in workflow
    assert "DISTRIBUTION: ai_stp_${{ inputs.package }}" in workflow
    assert "expected 2 distributions" in workflow
    assert "id-token: write" in workflow
    assert "actions/checkout@" not in workflow


def test_the_pypi_runbook_describes_the_live_per_package_upload() -> None:
    """A runbook that still calls publication an activation contract is a
    second source of truth that disagrees with production.
    """
    runbook = Path("docs/operations/runbooks/pypi-release.md").read_text(encoding="utf-8")
    assert "activation contract" not in runbook
    assert "does not contain PyPI upload" not in runbook
    assert "publish-pypi" in runbook
    assert "pypi-cli" in runbook
    assert "id-token: write" in runbook


def test_the_github_release_carries_the_published_candidate() -> None:
    """The GitHub Release is created by the run that uploaded, from its bytes.

    It used to be a manual step after publication and was missed for nine
    versions. The job runs only after `publish` succeeded, re-verifies the
    candidate's sums, checks nothing out, holds `contents: write` alone and
    refuses a tag that does not exist.
    """
    document = cast(dict[str, Any], yaml.safe_load(WORKFLOW.read_text(encoding="utf-8")))
    jobs = cast(dict[str, dict[str, Any]], document["jobs"])
    release = jobs["github-release"]
    assert release["needs"] == "publish"
    assert release["permissions"] == {"contents": "write"}
    assert "environment" not in release
    assert jobs["publish"]["permissions"] == {"contents": "read", "id-token": "write"}
    steps = cast(list[dict[str, Any]], release["steps"])
    assert not any(str(step.get("uses", "")).startswith("actions/checkout@") for step in steps)
    download = next(step for step in steps if "download-artifact" in str(step.get("uses", "")))
    assert download["with"]["run-id"] == "${{ inputs.run_id }}"
    scripts = "\n".join(str(step.get("run", "")) for step in steps)
    assert "sha256sum --check --strict SHA256SUMS" in scripts
    assert "gh release create" in scripts
    assert "--verify-tag" in scripts
    assert "--latest=false" in scripts
