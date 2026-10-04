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
from pathlib import Path


def _abspath(found: str) -> str:
    # `shutil.which` reports a relative spelling when PATH carries a relative
    # entry; callers that spawn with a different `cwd` need it absolute.
    # `absolute`, not `resolve` — the PATH spelling (/usr/bin/python3) must
    # survive, not chase symlinks to /usr/bin/python3.12.
    return str(Path(found).absolute())


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
            return _abspath(found)
    return None


@lru_cache(maxsize=1)
def uv() -> tuple[str, ...] | None:
    """The argv prefix for `uv …` — `(python, -m, uv)` or a `uv` binary.

    `-m uv` needs the interpreter *and* the installed package. A normal
    install has both (the `uv` distribution is a declared dependency); a
    frozen build has neither reachable through `sys.executable`, so it asks
    for a `uv` executable on `PATH` instead. `None` means neither works.
    """
    if not getattr(sys, "frozen", False):
        return (sys.executable, "-m", "uv")
    found = shutil.which("uv")
    return (_abspath(found),) if found is not None else None
