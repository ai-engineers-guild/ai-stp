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


def test_the_pypi_runbook_describes_the_live_per_package_upload() -> None:
    """The overlay uploads. A runbook that still calls that an activation
    contract is a second source of truth that disagrees with production.
    """
    runbook = Path("docs/operations/runbooks/pypi-release.md").read_text(encoding="utf-8")
    assert "activation contract" not in runbook
    assert "не содержит PyPI upload" not in runbook
    assert "publish-pypi" in runbook
    assert "pypi-{package}" in runbook or "pypi-passports" in runbook
    assert "id-token: write" in runbook


def test_the_public_overlay_pypi_runbook_is_not_a_stub() -> None:
    """The public tree reads the overlay at this path. A stub there fails CI."""
    overlay = Path("release_scripts/public_overlay/docs/operations/runbooks/pypi-release.md")
    if not overlay.is_file():
        return
    text = overlay.read_text(encoding="utf-8")
    assert "Заглушка" not in text
    assert "activation contract" not in text
    assert "publish-pypi" in text
    assert "pypi-{package}" in text or "pypi-passports" in text
    assert "id-token: write" in text
