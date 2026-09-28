"""PyPI publication uses one OIDC identity per project."""

from pathlib import Path

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
