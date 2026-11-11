"""Repository toolchains use uv for Python and Bun for JavaScript.

Safety adapters inspect scanned artifacts with their native audit tools; they
remain separate from repository dependency preparation.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Dependency preparation follows this repository's declared toolchain.
# Version managers are checked separately from language package managers.
WATCHED = ("npm", "npx", "pip", "pipx", "pnpm", "poetry", "yarn")


#: Files that make up the toolchain: what CI runs and what a developer runs.
def _toolchain(root: Path = ROOT) -> dict[str, str]:
    paths: list[Path] = [root / "justfile"]
    paths.extend(sorted((root / ".github").glob("*.just")))
    for directory in (
        root / ".github" / "actions",
        root / ".github" / "workflows",
        root / ".github" / "scripts",
    ):
        if directory.is_dir():
            paths.extend(sorted(directory.rglob("*")))
    paths.extend(sorted((root / "release_scripts").glob("*.sh")))
    paths.extend(sorted((root / "docs_scripts").glob("*.py")))
    return {
        str(path.relative_to(root)): path.read_text(encoding="utf-8")
        for path in paths
        if path.is_file() and "__pycache__" not in path.relative_to(root).parts
    }


def test_toolchain_reads_source_without_decoding_generated_bytecode(tmp_path: Path) -> None:
    scripts = tmp_path / ".github" / "scripts"
    cache = scripts / "__pycache__"
    cache.mkdir(parents=True)
    (cache / "probe.cpython-314.pyc").write_bytes(b"\xf6\x00\xff")
    (tmp_path / "justfile").write_text("check:\n    uv run check\n")
    source = "pip install forbidden-package\n"
    (scripts / "probe.py").write_text(source)
    (scripts.parent / "ci.just").write_text("probe:\n    pip install forbidden-package\n")
    observed = _toolchain(tmp_path)
    assert set(observed) == {"justfile", ".github/scripts/probe.py", ".github/ci.just"}
    assert observed[".github/scripts/probe.py"] == source


def _commands(text: str, suffix: str) -> str:
    """Blank out comments, so prose about a banned tool is not an invocation.

    Blanked rather than dropped: every one of these files explains in a comment
    why it does not use the tool it replaced, and the line numbers in a failure
    are only useful if they still point at the real file.
    """
    marker = "//" if suffix in {".json", ".mjs", ".ts"} else "#"
    return "\n".join("" if line.strip().startswith(marker) else line for line in text.split("\n"))


def test_the_toolchain_invokes_only_uv_and_bun() -> None:
    """Repository dependencies use uv/bun; one offline pip consumer probe is allowed.

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
        if name == ".github/scripts/qualify-native-wheel.sh":
            # Consumer qualification must exercise real pip. This one isolated
            # install reads only the built wheel, without indexes or dependencies;
            # repository environments and build tools still use uv exclusively.
            consumer = '"${pip_python}" -m pip install --no-index --no-deps "${wheel}"'
            assert commands.count(consumer) == 1, "The isolated real pip consumer probe is missing"
            commands = commands.replace(consumer, "", 1)
        for match in pattern.finditer(commands):
            line = commands[: match.start()].count("\n") + 1
            offences.append(f"{name}:{line}: {match.group(1)}")
    assert not offences, "the toolchain invokes a forbidden package manager: " + repr(offences)


def test_ci_sdk_preparation_uses_one_immutable_library_revision() -> None:
    library = r"NDDev-Technocracy-OpenNetwork/nddev-ci/"
    toolchain = _toolchain()
    declarations = [
        _commands(text, Path(name).suffix)
        for name, text in toolchain.items()
        if name.startswith((".github/actions/", ".github/workflows/"))
    ]
    ci = "\n".join(declarations)
    pins = re.findall(rf"{library}[\w./-]+@([^\s]+)", ci)
    assert pins and all(re.fullmatch(r"[0-9a-f]{40}", pin) for pin in pins)
    assert len(set(pins)) == 1, f"CI uses several versions of nddev-ci: {set(pins)}"
    assert "std-0004" not in ci
    assert not re.search(
        r"actions/setup-(?:node|python)@|install-(?:uv|bun|rust-toolchain)\.sh", ci
    )
    assert f"{library}actions/hosted-sdk@" in ci
    assert "uv-version:" in ci and "bun-version:" in ci


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
    workflow = ROOT / ".github" / "workflows" / "source.yml"
    pinned = re.search(r'BUN_VERSION:\s*"([0-9][^"]*)"', workflow.read_text(encoding="utf-8"))
    assert pinned, "the gate no longer pins a bun version"

    #: Bun 1.4.4 reads its ordinary version2 lockfiles and version3 for scoped
    #: overrides. The frozen native installs also validate the actual parser;
    #: an unknown format must not pass this source-level compatibility guard.
    readable = {2, 3}
    lockfiles = (
        sorted(ROOT.glob("bun.lock"))
        + sorted(ROOT.glob("*/bun.lock"))
        + sorted(ROOT.glob("*/*/bun.lock"))
        + sorted(ROOT.glob("tests/native_vendor/*-distribution/bun.lock"))
    )
    lockfiles = [path for path in lockfiles if "node_modules" not in path.parts]
    assert lockfiles, "no bun lockfile found"
    for path in lockfiles:
        # Read with a pattern, not a JSON parser: `bun.lock` is JSONC and
        # carries trailing commas that `json.loads` refuses.
        match = re.search(r'"lockfileVersion"\s*:\s*([0-9]+)', path.read_text(encoding="utf-8"))
        assert match, f"{path.relative_to(ROOT)} declares no lockfileVersion"
        declared = int(match.group(1))
        assert declared in readable, (
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
    workflow = ROOT / ".github" / "workflows" / "source.yml"
    pinned = re.search(r'BUN_VERSION:\s*"([0-9][^"]*)"', workflow.read_text(encoding="utf-8"))
    assert pinned, "the gate no longer pins a bun version"
    assert declared == pinned.group(1), (
        f".bun-version says {declared}, the gate installs {pinned.group(1)}"
    )
    recipes = (ROOT / "justfile").read_text(encoding="utf-8")
    assert ".bun-version" in recipes, "no recipe checks the developer's bun against the pin"


def test_the_local_and_gate_node_pins_are_the_same_version() -> None:
    declared = (ROOT / ".node-version").read_text(encoding="utf-8").strip()
    workflow = ROOT / ".github" / "workflows" / "source.yml"
    pinned = re.search(r'NODE_VERSION:\s*"([0-9][^"]*)"', workflow.read_text(encoding="utf-8"))
    assert pinned, "the gate no longer pins a Node version"
    assert declared == pinned.group(1), "local Node and the source-analysis runtime differ"
    recipes = (ROOT / "justfile").read_text(encoding="utf-8")
    assert ".node-version" in recipes, "no recipe verifies the selected Node runtime"


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
    workflow = ROOT / ".github" / "workflows" / "source.yml"
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
    happened anyway, in the one place it did not look: `deploy/docker/Dockerfile.web`
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
    ignored = {
        ".venv",
        "node_modules",
        "public",
        "dist",
        ".site",
        ".site-user-docs",
        ".work",
    }
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
