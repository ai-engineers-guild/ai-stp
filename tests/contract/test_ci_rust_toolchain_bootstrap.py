"""Native CI jobs resolve the repository toolchain through shared SDK preparation."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_project_rust_uses_the_repository_pin_and_shared_provider() -> None:
    action = ROOT / ".github/actions/project-rust/action.yml"
    steps = yaml.safe_load(action.read_text())["runs"]["steps"]
    assert "apps/cli/rust-toolchain.toml" in steps[0]["run"]
    assert steps[1]["uses"].startswith("NDDev-Technocracy-OpenNetwork/nddev-ci/actions/hosted-sdk@")
    assert steps[1]["with"]["rust-version"] == "${{ steps.pin.outputs.version }}"


def test_native_desktop_and_archive_jobs_use_the_shared_pinned_bootstrap() -> None:
    helper = "./.github/actions/project-rust"
    for name, job in [
        ("source.yml", "cli"),
        ("source.yml", "integration-native"),
        ("desktop.yml", "desktop"),
        ("cli-archives.yml", "build"),
    ]:
        text = (ROOT / ".github/workflows" / name).read_text()
        workflow = yaml.load(text, Loader=yaml.BaseLoader)
        steps = workflow["jobs"][job]["steps"]
        installs = [step for step in steps if step.get("uses") == helper]
        assert len(installs) == 1
        assert installs[0].get("continue-on-error") != "true"
        assert "rustup toolchain install" not in text
        if name != "source.yml":
            assert "workflow_call" in workflow["on"]
            assert "pull_request" not in workflow["on"]
            caller = yaml.load(
                (ROOT / ".github/workflows/source.yml").read_text(), Loader=yaml.BaseLoader
            )
            assert any(
                item.get("uses") == f"./.github/workflows/{name}"
                for item in caller["jobs"].values()
            )
