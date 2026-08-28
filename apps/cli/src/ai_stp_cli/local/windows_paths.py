"""The one path bound that cannot be decided where the bundle is built.

`bundle.py` refuses paths Windows cannot name at all — reserved stems, trailing
dots, `<>"|?*`. Those are decidable from the relative path alone. The length
limit is not: `MAX_PATH` counts the **whole** path, and a bundle knows only what
comes after a target root it has never seen.

The two roots this has to work for differ by more than a hundred characters —
`~/.codex` against a macOS `Library/Application Support` path under a long user
name — so any number chosen at build time is a guess at somebody's home
directory. The provider cannot decide it either: `validate-bundle` runs before
a target is named, and a provider stricter than the compiler refuses bundles the
platform has already blessed.

The consumer is the only place that holds both, and it holds them at plan time.
So the check lives here and runs before `plan-operation`: a bundle that cannot
be written is refused before the provider is asked to plan writing it, rather
than failing partway through `apply` on one operating system out of three.

Not a bundle-format change. `managed_paths` is already in the manifest, so the
longest one is derivable; recording a number beside it would be a second copy of
a fact, and a new manifest field is a seven-provider release for something
arithmetic already answers.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterable
from pathlib import Path

#: Windows resolves a path against a 260-character buffer that includes the
#: terminating NUL, so 259 characters is the longest usable path. Documented on
#: Microsoft's file-path-limits page and enforced by `MoveFileExW` among others.
MAX_PATH_CHARACTERS = 259

#: The opt-out is not something either side may assume. It needs Windows 10
#: 1607 or later **and** either the `LongPathsEnabled` registry value or a
#: per-application manifest, or an explicit `\\?\` prefix on every path — none
#: of which a provider can promise on a machine it did not configure.
_LONG_PATHS_KEY = r"SYSTEM\CurrentControlSet\Control\FileSystem"


def on_windows() -> bool:
    """Whether this is the platform the limit exists on.

    A named predicate rather than `os.name == "nt"` at each site, because the
    obvious way to exercise the other branch is to patch `os.name` — which
    mutates the interpreter's own `os` module for every other test running
    beside it. Patching this instead changes only this decision.
    """
    return os.name == "nt"


def long_paths_enabled() -> bool:
    """Whether this machine has opted out of the 260-character limit.

    Answers `False` everywhere but Windows, and `False` when the value cannot be
    read. A machine that cannot be asked is treated as not opted out: the cost
    of being wrong that way is a refusal, and the cost of the other way is a
    half-applied install.
    """
    # `sys.platform`, not the predicate above: this is the one place the
    # narrowing has to be visible to the type checker, which has no `winreg`
    # off Windows and reports every use of it as an unknown attribute.
    if sys.platform != "win32":
        return False
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _LONG_PATHS_KEY) as key:
            value, _ = winreg.QueryValueEx(key, "LongPathsEnabled")
    except OSError:
        return False
    return bool(value)


def too_long_for_windows(target: Path, relative_paths: Iterable[str]) -> list[str]:
    """Managed paths whose full length this machine cannot write.

    Empty everywhere but an unprepared Windows, which is what makes it safe to
    call unconditionally: on Linux and macOS there is no limit to apply, and
    inventing one would refuse installs that work.

    The comparison is in characters rather than bytes — `MAX_PATH` counts UTF-16
    code units and a length in bytes would over-refuse every non-ASCII name.
    """
    if not on_windows() or long_paths_enabled():
        return []
    root = len(str(target).rstrip("\\/"))
    return sorted(
        path
        for path in relative_paths
        # +1 for the separator the root and the relative path are joined with.
        if root + 1 + len(path) > MAX_PATH_CHARACTERS
    )
