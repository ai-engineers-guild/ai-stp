"""The interpreter a spawned child can actually run under.

`sys.executable` names the Python interpreter only while the CLI runs under
one. A frozen build — the desktop's bundled sidecar is PyInstaller-built —
makes it name the CLI binary itself, a click application that answers `-c`
and `-m` with "No such option". Every child the CLI spawns that way (sandbox
positive-control probes, provenance verification, scheduled wakeups) then
fails for a reason that names the sandbox rather than the real defect, and
on Linux and macOS that misreads as "isolation unavailable", refusing the
provider path the frozen build exists to serve.

The rule is one sentence: under a frozen build, ask the child's own
environment for an interpreter. The probes already pass a filtered `PATH`
to their subprocesses, so looking one up is not a new trust edge.
"""

from __future__ import annotations

import shutil
import sys
from functools import lru_cache


@lru_cache(maxsize=1)
def python() -> str | None:
    """A Python that answers `-c`/`-m`, or `None` when a frozen build finds none.

    `None` rather than `sys.executable` in the no-interpreter case: the caller
    can then say *why* the child cannot run instead of watching a click
    usage error surface as a sandbox or scheduler failure.
    """
    if not getattr(sys, "frozen", False):
        return sys.executable
    for name in ("python3", "python"):
        found = shutil.which(name)
        if found is not None:
            return found
    return None


@lru_cache(maxsize=1)
def uv() -> list[str] | None:
    """The argv prefix for `uv …` — `[python, -m, uv]` or a `uv` binary.

    `-m uv` needs the interpreter *and* the installed package. A normal
    install has both (the `uv` distribution is a declared dependency); a
    frozen build has neither reachable through `sys.executable`, so it asks
    for a `uv` executable on `PATH` instead. `None` means neither works.
    """
    if not getattr(sys, "frozen", False):
        return [sys.executable, "-m", "uv"]
    found = shutil.which("uv")
    return [found] if found is not None else None
