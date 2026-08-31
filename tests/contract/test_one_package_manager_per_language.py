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

import pytest

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / ".gds" / "compiled-policy.json"

#: The package managers this repository must not invoke. Declared here so
#: the check runs in every tree, and pinned against the policy above by
#: `test_the_policy_still_says_what_this_test_enforces` where it exists.
#: `mise` and `asdf` are version managers rather than package managers.
WATCHED = ("npm", "npx", "pip", "pipx", "pnpm", "poetry", "yarn")


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
    """A test that reads a policy is worth only as much as the policy it read.

    Skipped where the policy is not present. `.gds` is withheld from the
    published tree by `release_scripts/public_manifest.toml` — it belongs to
    another system — and the gate runs there. Which is why the check below
    names the tools itself instead of reading them from a file that may be
    absent: an enforcement that disappears in the tree where the gate runs is
    not an enforcement.
    """
    if not POLICY.is_file():
        pytest.skip("this tree does not carry the compiled policy")
    forbidden, allowed = _policy_names()
    assert allowed == {"uv", "bun"}
    assert set(WATCHED) <= forbidden


def test_the_toolchain_invokes_only_uv_and_bun() -> None:
    """No `pip`, `npm`, `npx`, `pnpm` or `yarn` in what the repository runs.

    `uv pip` is uv, not pip: it is uv's own pip-compatible interface and the
    binary invoked is `uv`. It is joined into one token before the search
    rather than excluded by a lookbehind, because the pattern has to consume
    the separator before the command word and a lookbehind then sees the wrong
    position — which is how the first version of this test reported
    `clean_install_regress.sh` for calling `uv pip install`.
    """
    pattern = re.compile(
        r"(?:^|[\s;&|(`\"']|\$\()(" + "|".join(WATCHED) + r")(?:\.exe)?\s",
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


def test_windows_arm_bootstraps_the_native_uv_binary() -> None:
    """The six-platform evidence matrix must not prove x64 emulation on ARM.

    uv publishes an ``aarch64-pc-windows-msvc`` asset for the pinned version.
    The bootstrap used to overwrite the architecture detected by ``uname``
    with ``x86_64`` for every Windows runner, so a green Windows ARM job would
    still have executed the x64 toolchain. The archive suffix differs by OS;
    the machine selected above it must survive unchanged.
    """
    script = (ROOT / ".github" / "scripts" / "install-uv.sh").read_text(encoding="utf-8")
    assert 'machine_name="${RUNNER_ARCH:-$(uname -m)}"' in script
    assert "ARM64 | arm64 | aarch64" in script
    windows = script.split('if [ "${system}" = "pc-windows-msvc" ]; then', maxsplit=1)[1].split(
        "else", maxsplit=1
    )[0]
    assert 'machine="x86_64"' not in windows
    assert 'archive="uv-${machine}-${system}.zip"' in windows


def test_every_bun_lockfile_is_readable_by_the_pinned_bun() -> None:
    """A lockfile written by a newer bun is unreadable by the pinned one.

    Found the hard way: this machine had bun 1.4.0 while the gate pinned
    1.3.14, so a plain `bun install` rewrote `docs_scripts/bun.lock` at
    `lockfileVersion: 2` and the docs job died with `Unknown lockfile version`
    before running a single check.

    Asserted on the artefact rather than on the developer's installed bun,
    which would break a working machine over a file that is fine. The pair
    moves together: raising `BUN_VERSION` means regenerating both lockfiles
    with the bun being pinned, and this is what refuses to let one happen
    without the other.
    """
    workflow = ROOT / "release_scripts" / "public_overlay" / ".github" / "workflows" / "check.yml"
    if not workflow.is_file():
        workflow = ROOT / ".github" / "workflows" / "check.yml"
    pinned = re.search(r'BUN_VERSION:\s*"([0-9][^"]*)"', workflow.read_text(encoding="utf-8"))
    assert pinned, "the gate no longer pins a bun version"

    #: What the pinned bun writes and reads: 1.3.x wrote 1, 1.4 writes 2 and
    #: refuses to read nothing. Raise this together with `BUN_VERSION`, after
    #: regenerating every lockfile with the bun being pinned.
    readable = 2
    lockfiles = sorted(ROOT.glob("*/bun.lock")) + sorted(ROOT.glob("*/*/bun.lock"))
    lockfiles = [path for path in lockfiles if "node_modules" not in path.parts]
    assert lockfiles, "no bun lockfile found"
    for path in lockfiles:
        # Read with a pattern, not a JSON parser: `bun.lock` is JSONC and
        # carries trailing commas that `json.loads` refuses.
        match = re.search(r'"lockfileVersion"\s*:\s*([0-9]+)', path.read_text(encoding="utf-8"))
        assert match, f"{path.relative_to(ROOT)} declares no lockfileVersion"
        declared = int(match.group(1))
        assert declared == readable, (
            f"{path.relative_to(ROOT)} is lockfileVersion {declared}; "
            f"bun {pinned.group(1)} reads {readable}"
        )


def test_the_local_and_gate_bun_pins_are_the_same_version() -> None:
    """`.bun-version` and `BUN_VERSION` name one version, or neither is a pin.

    The recipes check the developer's bun against `.bun-version` before running
    it, because a `bun install` from another line rewrites `bun.lock` into a
    format the gate cannot read — and the error then surfaces in CI rather than
    on the machine that caused it. That check is only worth anything while the
    file it reads agrees with what CI installs.
    """
    declared = (ROOT / ".bun-version").read_text(encoding="utf-8").strip()
    assert declared, ".bun-version is empty"
    workflow = ROOT / "release_scripts" / "public_overlay" / ".github" / "workflows" / "check.yml"
    if not workflow.is_file():
        workflow = ROOT / ".github" / "workflows" / "check.yml"
    pinned = re.search(r'BUN_VERSION:\s*"([0-9][^"]*)"', workflow.read_text(encoding="utf-8"))
    assert pinned, "the gate no longer pins a bun version"
    assert declared == pinned.group(1), (
        f".bun-version says {declared}, the gate installs {pinned.group(1)}"
    )
    recipes = (ROOT / "justfile").read_text(encoding="utf-8")
    assert ".bun-version" in recipes, "no recipe checks the developer's bun against the pin"


def test_the_local_and_gate_uv_pins_are_the_same_version() -> None:
    """`.uv-version` and `UV_VERSION` name one version, or the candidate drifts.

    uv stamps its own version into `dist-info/WHEEL`, so a candidate built by a
    different uv differs from the one that ships — while every shipped module is
    byte-identical. That is a worse failure than an outright difference: ten
    mismatched digests read as substituted bytes, and it cost an investigation
    on 2026-08-26 before the cause turned out to be one `Generator:` line.

    With the pin held, a clean worktree at the tag reproduces exactly what PyPI
    serves — measured for all ten distributions of `0.0.5`. So this is not a
    style rule about pinning things; it is the only reason the local candidate
    means what the runbook says it means.
    """
    declared = (ROOT / ".uv-version").read_text(encoding="utf-8").strip()
    assert declared, ".uv-version is empty"
    workflow = ROOT / "release_scripts" / "public_overlay" / ".github" / "workflows" / "check.yml"
    if not workflow.is_file():
        workflow = ROOT / ".github" / "workflows" / "check.yml"
    pinned = re.search(r'UV_VERSION:\s*"([0-9][^"]*)"', workflow.read_text(encoding="utf-8"))
    assert pinned, "the gate no longer pins a uv version"
    assert declared == pinned.group(1), (
        f".uv-version says {declared}, the gate installs {pinned.group(1)}"
    )
    recipes = (ROOT / "justfile").read_text(encoding="utf-8")
    assert ".uv-version" in recipes, "no recipe checks the developer's uv against the pin"


def test_every_bun_base_image_is_the_pinned_bun() -> None:
    """The image that builds the site must read the lockfile the gate writes.

    The test above binds `.bun-version`, `BUN_VERSION` and the lockfiles, and
    its docstring names the exact failure — `Unknown lockfile version`. It then
    happened anyway, in the one place it did not look: `apps/web/Dockerfile.*`
    pinned `oven/bun:1.2.19-alpine`, which cannot read `lockfileVersion: 2`. The
    gate stayed green because the gate never builds that image; production
    retried the build every minute for twelve hours and kept serving the
    previous release.

    A pinned base image is right — this asserts it is pinned to the version the
    lockfiles were written by, not that it is unpinned.
    """
    declared = (ROOT / ".bun-version").read_text(encoding="utf-8").strip()
    #: `public/build` is a generated copy of this tree and carries its own
    #: `.bun-version`; checking it from here would read one tree's pin against
    #: another tree's image. It runs this same test on itself.
    ignored = {".venv", "node_modules", "public", "dist", ".site", ".site-user-docs"}
    seen = False
    for path in sorted(ROOT.glob("**/Dockerfile*")):
        if ignored.intersection(path.relative_to(ROOT).parts):
            continue
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"^FROM\s+oven/bun:(\S+)", text, re.MULTILINE):
            seen = True
            version = match.group(1).split("-", 1)[0]
            assert version == declared, (
                f"{path.relative_to(ROOT)} builds on bun {version}, "
                f"the lockfiles are written by {declared}"
            )
    assert seen, "no image builds on bun; drop this check or restore the pin"
