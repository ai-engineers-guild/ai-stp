"""PyPI publication uses one OIDC identity per project."""

from pathlib import Path

OVERLAY = Path("release_scripts/public_overlay/.github/workflows/publish-pypi.yml")
WORKFLOW = OVERLAY if OVERLAY.is_file() else Path(".github/workflows/publish-pypi.yml")


def test_each_distribution_has_a_distinct_trusted_publisher_identity() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    projects = ("foundation", "passports", "assurance", "contracts", "cli")
    assert all(f"          - {project}" in workflow for project in projects)

    assert "inputs.package == 'foundation'" in workflow
    assert "format('pypi-{0}', inputs.package)" in workflow
    assert "DISTRIBUTION: ai_stp_${{ inputs.package }}" in workflow
    assert "expected 2 distributions" in workflow
    assert "id-token: write" in workflow
    assert "actions/checkout@" not in workflow
