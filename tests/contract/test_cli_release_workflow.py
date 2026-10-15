"""The native archive lane is the CLI release entrypoint."""

from pathlib import Path


def test_only_the_native_cli_release_workflow_is_present() -> None:
    workflows = Path(".github/workflows")
    assert (workflows / "cli-release.yml").is_file()
    assert not (workflows / "publish-pypi.yml").exists()
    assert not (workflows / "release-candidate.yml").exists()
