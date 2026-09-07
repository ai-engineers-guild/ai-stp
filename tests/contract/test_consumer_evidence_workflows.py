"""Consumer evidence must execute the self-contained CLI package (ADR-0146)."""

import shlex
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[2]


@pytest.mark.parametrize("name", ["config-evidence", "software-evidence"])
def test_package_only_evidence_keeps_the_bundled_cli_installed(name: str) -> None:
    """A later uv run must not replace the working wheel with an editable CLI.

    The six native jobs used to fail before reaching a provider: package-only
    editable installation omits the first-party modules bundled by the wheel
    hook. The runtime package check lives in back-regress; this checks that
    every environment-resolving command in these workflows uses that package.
    """
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / f"{name}.yml").read_text())
    commands: list[list[str]] = []
    for step in workflow["jobs"]["consume"]["steps"]:
        script = step.get("run", "").replace("\\\n", " ")
        for line in script.splitlines():
            args = shlex.split(line, comments=True)
            if args[:2] in (["uv", "sync"], ["uv", "run"]):
                commands.append(args)

    assert {args[1] for args in commands} == {"sync", "run"}
    for args in commands:
        assert "--no-editable" in args, args
        assert "--locked" in args, args
        assert args[args.index("--package") + 1] == "ai-stp-cli", args
