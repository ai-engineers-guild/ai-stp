"""One package manager per language, and the repository's own policy says which.

`.gds/compiled-policy.json` names `uv` and `bun` as the only
`language_dependency_managers` and forbids the npm family on a managed PATH. It
is written by another system and enforced by none, which is how the gate came
to bootstrap `uv` with `pip` on twenty-one jobs and install documentation tools
with `npm ci`.

What this checks is our own toolchain: what the gate runs, what the recipes
run, what our scripts run. It deliberately does not touch the safety adapters —
`npm audit` and `pip-audit` are the right tools to run *against a scanned
artefact*, and forbidding them there would confuse the product with the
workshop.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / ".gds" / "compiled-policy.json"


#: Files that make up the toolchain: what CI runs and what a developer runs.
def _toolchain() -> dict[str, str]:
    paths: list[Path] = [ROOT / "justfile"]
    overlay = ROOT / "release_scripts" / "public_overlay" / ".github"
    for directory in (overlay / "workflows", overlay / "scripts", ROOT / ".github" / "scripts"):
        if directory.is_dir():
            paths.extend(sorted(directory.rglob("*")))
    paths.extend(sorted((ROOT / "release_scripts").glob("*.sh")))
    paths.extend(sorted((ROOT / "docs_scripts").glob("*.py")))
    return {
        str(path.relative_to(ROOT)): path.read_text(encoding="utf-8")
        for path in paths
        if path.is_file()
    }


def _commands(text: str, suffix: str) -> str:
    """Blank out comments, so prose about a banned tool is not an invocation.

    Blanked rather than dropped: every one of these files explains in a comment
    why it does not use the tool it replaced, and the line numbers in a failure
    are only useful if they still point at the real file.
    """
    marker = "//" if suffix in {".json", ".mjs", ".ts"} else "#"
    return "\n".join("" if line.strip().startswith(marker) else line for line in text.split("\n"))


def _policy_names() -> tuple[frozenset[str], frozenset[str]]:
    """Read the two lists out of the policy at their documented location.

    Addressed rather than searched for: if the policy moves them, this should
    fail loudly and be re-read, not quietly find something similar elsewhere.
    """
    policy = cast(dict[str, object], json.loads(POLICY.read_text(encoding="utf-8")))
    effective = policy.get("effective")
    assert isinstance(effective, dict), f"{POLICY.name}: `effective` is absent"
    section = cast(dict[str, object], effective).get("package_management")
    assert isinstance(section, dict), f"{POLICY.name}: `package_management` is absent"
    managed = cast(dict[str, object], section)

    def names(key: str) -> frozenset[str]:
        value = managed.get(key)
        assert isinstance(value, list) and value, f"{POLICY.name}: {key} is absent or empty"
        return frozenset(str(item) for item in cast(list[object], value))

    return names("forbidden_executables"), names("language_dependency_managers")


def test_the_policy_still_says_what_this_test_enforces() -> None:
    """A test that reads a policy is worth only as much as the policy it read."""
    forbidden, allowed = _policy_names()
    assert allowed == {"uv", "bun"}
    assert {"pip", "npm", "npx", "pnpm", "yarn"} <= forbidden


def test_the_toolchain_invokes_only_uv_and_bun() -> None:
    """No `pip`, `npm`, `npx`, `pnpm` or `yarn` in what the repository runs.

    `uv pip` is uv, not pip: it is uv's own pip-compatible interface and the
    binary invoked is `uv`. It is joined into one token before the search
    rather than excluded by a lookbehind, because the pattern has to consume
    the separator before the command word and a lookbehind then sees the wrong
    position — which is how the first version of this test reported
    `clean_install_regress.sh` for calling `uv pip install`.
    """
    forbidden, _allowed = _policy_names()
    # `mise`, `asdf` and friends are version managers rather than package
    # managers; the ones this repository could plausibly reach for are these.
    watched = sorted(forbidden & {"pip", "pipx", "poetry", "npm", "npx", "pnpm", "yarn"})
    pattern = re.compile(
        r"(?:^|[\s;&|(`\"']|\$\()(" + "|".join(watched) + r")(?:\.exe)?\s",
        re.MULTILINE,
    )
    offences: list[str] = []
    for name, text in _toolchain().items():
        commands = _commands(text, Path(name).suffix).replace("uv pip ", "uv-pip ")
        for match in pattern.finditer(commands):
            line = commands[: match.start()].count("\n") + 1
            offences.append(f"{name}:{line}: {match.group(1)}")
    assert not offences, "the toolchain invokes a forbidden package manager: " + repr(offences)


def test_both_managers_are_installed_from_a_pinned_verified_archive() -> None:
    """`remote_stream_to_shell` is forbidden, and a pinned version is required.

    Which rules out both shapes the vendors' own instructions suggest: piping
    an installer into a shell, and asking a package manager for "latest".
    """
    for name in ("install-uv.sh", "install-bun.sh"):
        script = (ROOT / ".github" / "scripts" / name).read_text(encoding="utf-8")
        commands = _commands(script, ".sh")
        assert "sha256" in commands.lower(), f"{name} does not verify a checksum"
        assert not re.search(r"curl[^\n|]*\|\s*(?:ba)?sh", commands), f"{name} pipes to a shell"
        assert '"${1:?' in script or "version=" in commands, f"{name} takes no pinned version"
