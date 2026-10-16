"""PyPI delivers native release bytes; it cannot rebuild a Python CLI."""

from pathlib import Path


def test_pypi_delivery_uses_verified_native_release_artifacts() -> None:
    workflows = Path(".github/workflows")
    assert (workflows / "cli-release.yml").is_file()
    assert not (workflows / "release-candidate.yml").exists()
    publisher = (workflows / "publish-pypi.yml").read_text()
    assert "gh attestation verify" in publisher
    assert "--source-digest" in publisher
    assert "actions/checkout@" not in publisher
    assert "uv build" not in publisher
    assert "pip install" not in publisher
