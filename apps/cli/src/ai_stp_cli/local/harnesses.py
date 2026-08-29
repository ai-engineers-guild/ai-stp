"""Detecting harnesses without changing anything (`SPEC-014` REQ-1414 to REQ-1418).

`REQ-1414` bounds this to a declared set: known executable names resolved to a
verified absolute path, a safe version query, and known user configuration
roots. There is no search — the home directory is never walked, the disk is
never scanned, and an executable this table does not name is not looked for.
That is a stronger guarantee than a limit, because it makes the whole surface
readable in one place.

Every root here was read from the harness's own documentation rather than
recalled, and the seven disagree with each other in ways that would have been
easy to get wrong: `~/.claude`, `~/.codex` overridable by `CODEX_HOME`,
`~/.pi/agent`, XDG-based `~/.config/opencode`, `~/.grok`, `~/.cursor`
overridable by `CURSOR_CONFIG_DIR`, and `~/.gemini` for Antigravity. Assuming
one convention would have produced six confident wrong answers.

Nothing here writes. `REQ-1416` asks for a filesystem that is byte-identical
afterwards, and the way to get that is to never open a file for writing rather
than to remember not to.
"""

import json
import os
import platform
import re
import shutil
import stat
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

from ai_stp_cli.local import harness_catalog

#: How long a version query may take before it is abandoned (`REQ-1409`). A
#: harness that does not answer in this is not a harness this can report on.
VERSION_TIMEOUT_SECONDS: Final[float] = 5.0

#: How much of its answer is read. Output is untrusted (`SPEC-014` security
#: section), and a version string is short.
VERSION_OUTPUT_LIMIT: Final[int] = 4096
METADATA_OUTPUT_LIMIT: Final[int] = 65_536
VERSION_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[0-9A-Za-z][0-9A-Za-z.+_-]{0,63}$")
WINDOWS_CODEX_PACKAGE: Final[re.Pattern[str]] = re.compile(
    r"^OpenAI\.Codex_(?P<version>[0-9]+(?:\.[0-9]+){1,3})_(?:x64|x86|arm64)__[A-Za-z0-9]+$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Detector:
    """One declared way to find one harness, and where that was established."""

    harness_id: str
    title: str

    #: `primary` or `beta`, matching `AGENTS.md`. A beta harness is detected the
    #: same way; the label describes the support, not the detection.
    support: str

    #: The command name. Resolved to an absolute path before it is trusted.
    executable: str

    #: Argument array, never a string: `REQ-1409` requires `shell=false`, and a
    #: string would have to be split by something.
    version_arguments: tuple[str, ...]

    #: Where the user's configuration lives, relative to the home directory —
    #: unless `xdg_config` is set, in which case it is relative to
    #: `XDG_CONFIG_HOME`.
    config_root: str
    xdg_config: bool = False

    #: The leaf under `XDG_CONFIG_HOME`, when a product spells it differently
    #: there than under the home directory. `None` means the same leaf in both.
    #:
    #: No harness sets it today. It was added for cursor and withdrawn the same
    #: day: cursor's config *resolver* does rename the leaf, but only one of the
    #: eight surfaces it owns is built by calling that resolver, and the rest are
    #: literal `~/.cursor`. Kept because the distinction it draws is real and the
    #: next product to need it will need exactly this, and because deleting it
    #: would lose the reason — a resolver is not a statement about a home.
    xdg_config_root: str | None = None

    #: Environment variable that moves the configuration root, where one exists.
    root_override: str | None = None

    #: The documentation this was read from. Recorded because these paths change
    #: and a future reader needs to know what to re-check rather than guess.
    source: str = ""

    #: Package-manager metadata read only after a failed process query on
    #: Windows. These are declared package identities, never a disk search.
    npm_packages: tuple[str, ...] = ()
    scoop_app: str | None = None


DETECTORS: Final[tuple[Detector, ...]] = tuple(
    Detector(
        harness_id=item.harness_id,
        title=item.title,
        support=item.support,
        executable=item.executable,
        version_arguments=item.version_arguments,
        config_root=item.config_root,
        xdg_config=item.xdg_config,
        xdg_config_root=item.xdg_config_root,
        root_override=item.root_override,
        source=item.source,
        npm_packages=item.npm_packages,
        scoop_app=item.scoop_app,
    )
    for item in harness_catalog.DEFINITIONS
    if item.executable is not None and item.config_root is not None
)


@dataclass(frozen=True)
class Installation:
    """One place a harness was found."""

    path: str
    version: str
    reason: str
    surface: str = "cli"
    version_source: str = "process"
    diagnostic: str = "version_reported"


@dataclass(frozen=True)
class Found:
    """What is known about one harness on this machine."""

    harness_id: str
    title: str
    support: str

    #: `configured`, `installed`, `unknown_version` or `available` (`REQ-1415`).
    state: str

    #: Every installation, not the first (`REQ-1417`). Two versions of one
    #: harness on one machine is a normal state, and reporting one of them would
    #: make the other invisible.
    installations: tuple[Installation, ...]

    #: The user configuration root, when it exists.
    configuration: str | None
    reason: str


def config_root(detector: Detector, environment: dict[str, str] | None = None) -> Path:
    """Where this harness keeps user configuration, on this machine.

    An override wins when the user set one: it is the whole point of the
    variable, and reading the default anyway would report a directory the
    harness is not using.
    """
    held = os.environ if environment is None else environment
    override = detector.root_override
    if override and held.get(override):
        return Path(held[override]).expanduser()
    if detector.xdg_config:
        base = held.get("XDG_CONFIG_HOME")
        if base is None and detector.xdg_config_root is None:
            # A product that is XDG all the way down uses the specification's
            # own default when the variable is unset. OpenCode is this one.
            base = str(Path(held.get("HOME", "~")).expanduser() / ".config")
        if base is not None:
            leaf = detector.xdg_config_root or detector.config_root
            return Path(base).expanduser() / leaf
        # A product that honours the variable but falls back to a dotted home
        # rather than to `~/.config`. Cursor is this one: `CURSOR_CONFIG_DIR`,
        # then `$XDG_CONFIG_HOME/cursor`, else `~/.cursor`. Defaulting the base
        # here would have answered `~/.config/cursor` on a machine with no
        # variable set — a second wrong answer introduced by fixing the first.
    return Path(held.get("HOME", "~")).expanduser() / detector.config_root


def executables(
    name: str,
    environment: dict[str, str] | None = None,
    *,
    system_name: str | None = None,
) -> tuple[Path, ...]:
    """Every absolute path this name resolves to, in `PATH` order.

    `shutil.which` answers with the first, which would hide a second
    installation that `REQ-1417` asks to be listed. Duplicates are collapsed by
    resolved path, because the same binary reached through two symlinked
    directories is one installation with two names.
    """
    held = os.environ if environment is None else environment
    search = held.get("PATH", "")
    found: list[Path] = []
    seen: set[Path] = set()
    windows = (system_name or platform.system()) == "Windows"
    separator = ";" if windows else os.pathsep
    for entry in search.split(separator):
        if not entry:
            continue
        candidate = shutil.which(name, path=entry)
        if candidate is None:
            continue
        resolved = Path(candidate).resolve()
        identity = Path(str(resolved).casefold()) if windows else resolved
        if identity in seen:
            continue
        seen.add(identity)
        found.append(Path(candidate))
    return tuple(found)


def ask_version(executable: Path, arguments: tuple[str, ...]) -> tuple[str, str]:
    """Ask a harness its version, safely. Returns the version and a reason.

    `REQ-1409` in full: an argument array, no shell, a filtered environment, a
    time limit and a bound on how much is read. The answer is untrusted input —
    it is a subprocess this CLI did not write — so only its first line is kept
    and it is never interpreted as anything but text.
    """
    try:
        # An argument array and no shell: `REQ-1409` asks for exactly this, and
        # a string command would have to be split by something that is not us.
        finished = subprocess.run(
            [str(executable), *arguments],
            capture_output=True,
            text=True,
            timeout=VERSION_TIMEOUT_SECONDS,
            check=False,
            # A version query needs nothing from the environment, and passing
            # the whole of it would hand a subprocess whatever is in it.
            env={"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", "")},
        )
    except (OSError, subprocess.SubprocessError) as error:
        return "unknown", f"the version query failed: {type(error).__name__}"

    if finished.returncode != 0:
        return "unknown", f"the version query exited {finished.returncode}"
    answer = (finished.stdout or finished.stderr)[:VERSION_OUTPUT_LIMIT].strip()
    first = answer.splitlines()[0].strip() if answer else ""
    if not first:
        return "unknown", "the version query answered with nothing"
    return first, "reported by the harness"


def _diagnostic(reason: str) -> str:
    if reason == "reported by the harness":
        return "version_reported"
    if reason.startswith("the version query exited "):
        return "version_query_exit"
    if reason.endswith("with nothing"):
        return "version_query_empty"
    return "version_query_failed"


def _surface(detector: Detector, executable: Path) -> str:
    if detector.harness_id == "codex" and any(
        part.casefold() == "windowsapps" for part in executable.parts
    ):
        return "desktop"
    return "cli"


def _safe_json_version(path: Path) -> str | None:
    """Read one declared package manifest without following links or large files."""
    descriptor = -1
    try:
        metadata = path.lstat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_size > METADATA_OUTPUT_LIMIT
        ):
            return None
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        flags |= getattr(os, "O_NOINHERIT", 0)
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        if (
            (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino)
            or opened.st_mode != metadata.st_mode
            or opened.st_nlink != 1
            or opened.st_size != metadata.st_size
        ):
            return None
        with os.fdopen(descriptor, encoding="utf-8") as stream:
            descriptor = -1
            document = cast(object, json.load(stream))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if not isinstance(document, dict):
        return None
    held = cast(dict[str, object], document).get("version")
    if not isinstance(held, str) or not VERSION_PATTERN.fullmatch(held):
        return None
    return held


def _windows_package_version(executable: Path, detector: Detector) -> tuple[str, str] | None:
    """Return a version from one bounded, declared Windows package location."""
    if detector.harness_id == "codex":
        for part in executable.parts:
            matched = WINDOWS_CODEX_PACKAGE.fullmatch(part)
            if matched:
                return matched.group("version"), "windows_package_metadata"

    for package in detector.npm_packages:
        manifest = executable.parent / "node_modules" / Path(*package.split("/")) / "package.json"
        version = _safe_json_version(manifest)
        if version is not None:
            return version, "package_metadata"

    if detector.scoop_app and any(part.casefold() == "shims" for part in executable.parts):
        for parent in executable.parents:
            if parent.name.casefold() != "scoop":
                continue
            manifest = parent / "apps" / detector.scoop_app / "current" / "manifest.json"
            version = _safe_json_version(manifest)
            if version is not None:
                return version, "package_metadata"
            break
    return None


def detect(
    detector: Detector,
    *,
    environment: dict[str, str] | None = None,
    explicit: Path | None = None,
    system_name: str | None = None,
) -> Found:
    """Everything known about one harness, without changing anything.

    An explicit path wins over what `PATH` offers (`REQ-1417`): the user naming
    a binary is a stronger statement than the order of a search path they may
    not control.
    """
    system = system_name or platform.system()
    places = (
        (explicit,)
        if explicit is not None
        else executables(detector.executable, environment, system_name=system)
    )
    installations: list[Installation] = []
    for place in places:
        version, reason = ask_version(place, detector.version_arguments)
        source = "process" if version != "unknown" else "unavailable"
        diagnostic = _diagnostic(reason)
        if version == "unknown" and system == "Windows":
            fallback = _windows_package_version(place, detector)
            if fallback is not None:
                version, source = fallback
                reason = f"reported by {source} after {diagnostic}"
                diagnostic = "version_metadata_fallback"
        installations.append(
            Installation(
                str(place),
                version,
                reason,
                surface=_surface(detector, place),
                version_source=source,
                diagnostic=diagnostic,
            )
        )

    installations.sort(key=lambda item: (item.surface != "cli", item.path.casefold()))

    root = config_root(detector, environment)
    configured = root.is_dir()

    if not installations:
        return Found(
            detector.harness_id,
            detector.title,
            detector.support,
            "available",
            (),
            str(root) if configured else None,
            "supported by this build; no installation found on this machine",
        )
    if all(item.version == "unknown" for item in installations):
        return Found(
            detector.harness_id,
            detector.title,
            detector.support,
            "unknown_version",
            tuple(installations),
            str(root) if configured else None,
            installations[0].reason,
        )
    if configured:
        return Found(
            detector.harness_id,
            detector.title,
            detector.support,
            "configured",
            tuple(installations),
            str(root),
            "installed and holding user configuration",
        )
    return Found(
        detector.harness_id,
        detector.title,
        detector.support,
        "installed",
        tuple(installations),
        None,
        "installed; no user configuration found",
    )


def detect_all(
    environment: dict[str, str] | None = None, *, system_name: str | None = None
) -> tuple[Found, ...]:
    """Every declared harness, in declaration order. Total by construction.

    Detection is one `--version` subprocess per harness, and the seven of them
    took 1.74s of `toolchain harnesses`'s 2.29s in series (`#453`) — the
    process spent that time in `poll`, waiting, one harness at a time. They are
    independent read-only queries of different programs, so they are asked
    together.

    `ThreadPoolExecutor.map` yields in **input** order, not completion order,
    so the answer is the same tuple it always was: this changes when the waits
    happen and nothing about what is returned. Threads rather than processes
    because every one of these waits on a subprocess and holds no GIL while it
    does.
    """

    def ask(detector: Detector) -> Found:
        return detect(detector, environment=environment, system_name=system_name)

    with ThreadPoolExecutor(max_workers=len(DETECTORS)) as pool:
        return tuple(pool.map(ask, DETECTORS))


def present_installations(found: tuple[Found, ...]) -> tuple[Found, ...]:
    """Harnesses that are on this machine.

    `available` means supported by this build and not installed. Passport
    `installed_harnesses` and the toolchain survey must use this same cut:
    a supported-but-absent harness, including Pi with no binary, stays out.
    """
    return tuple(item for item in found if item.state != "available")
