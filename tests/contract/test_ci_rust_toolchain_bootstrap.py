"""Transient toolchain failures retry the same pin and cannot weaken CI gates."""

from __future__ import annotations

import os
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".github/scripts/install-rust-toolchain.sh"
PIN = tomllib.loads((ROOT / "apps/cli/rust-toolchain.toml").read_text())["toolchain"]["channel"]


def environment(tmp_path: Path, failures: int) -> dict[str, str]:
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "rustup").write_text(
        "#!/bin/bash\n"
        "n=0\n"
        'if test -f "$TRACE_STATE"; then IFS= read -r n < "$TRACE_STATE"; fi\n'
        "n=$((n + 1))\n"
        'printf "%s\\n" "$n" > "$TRACE_STATE"\n'
        'printf "%s\\n" "$*" >> "$TRACE_CALLS"\n'
        'if test "$n" -le "$FAILURES"; then exit 17; fi\n'
    )
    (tools / "sleep").write_text('#!/bin/bash\nprintf "%s\\n" "$*" >> "$TRACE_SLEEPS"\n')
    for path in tools.iterdir():
        path.chmod(0o755)
    return {
        **os.environ,
        "PATH": f"{tools}:/usr/bin:/bin",
        "GITHUB_ENV": str(tmp_path / "job-env"),
        "TRACE_STATE": str(tmp_path / "attempt"),
        "TRACE_CALLS": str(tmp_path / "calls"),
        "TRACE_SLEEPS": str(tmp_path / "sleeps"),
        "FAILURES": str(failures),
    }


@pytest.mark.parametrize("failures", [0, 2, 3])
@pytest.mark.parametrize("components", [[], ["clippy", "rustfmt"]])
def test_transient_and_terminal_failures_preserve_the_exact_install(
    tmp_path: Path, failures: int, components: list[str]
) -> None:
    bash = shutil.which("bash")
    assert bash is not None
    env = environment(tmp_path, failures)
    result = subprocess.run(
        [bash, str(SCRIPT), str(ROOT / "apps/cli/rust-toolchain.toml"), *components],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    calls = (tmp_path / "calls").read_text().splitlines()
    expected = f"toolchain install {PIN} --profile minimal --no-self-update"
    expected += "".join(f" --component {component}" for component in components)
    assert calls == [expected] * min(failures + 1, 3)
    if failures < 3:
        assert result.returncode == 0
        assert (tmp_path / "job-env").read_text() == f"RUSTUP_TOOLCHAIN={PIN}\n"
    else:
        assert result.returncode == 17
        assert not (tmp_path / "job-env").exists()
    sleeps = (tmp_path / "sleeps").read_text().splitlines() if failures else []
    assert sleeps == (["2", "4"] if failures else [])


@pytest.mark.parametrize("pin", ["stable", "nightly", "1.99.1 --profile default"])
def test_moving_or_ambiguous_pins_refuse_before_any_install(tmp_path: Path, pin: str) -> None:
    bash = shutil.which("bash")
    assert bash is not None
    env = environment(tmp_path, 0)
    manifest = tmp_path / "rust-toolchain.toml"
    manifest.write_text(f'[toolchain]\nchannel = "{pin}"\n')
    result = subprocess.run(
        [bash, str(SCRIPT), str(manifest)], env=env, capture_output=True, timeout=10, check=False
    )
    assert result.returncode == 2
    assert not (tmp_path / "calls").exists()
    assert not (tmp_path / "job-env").exists()


def test_native_desktop_and_archive_jobs_use_the_shared_pinned_bootstrap() -> None:
    helper = ".github/scripts/install-rust-toolchain.sh"
    for name, job in [
        ("check.yml", "cli"),
        ("desktop.yml", "desktop"),
        ("cli-release.yml", "build"),
    ]:
        text = (ROOT / ".github/workflows" / name).read_text()
        workflow = yaml.load(text, Loader=yaml.BaseLoader)
        steps = workflow["jobs"][job]["steps"]
        installs = [step for step in steps if helper in step.get("run", "")]
        assert len(installs) == 1
        assert "apps/cli/rust-toolchain.toml" in installs[0]["run"]
        assert installs[0].get("continue-on-error") != "true"
        assert "rustup toolchain install" not in text
        if name != "check.yml":
            assert helper in workflow["on"]["pull_request"]["paths"]
