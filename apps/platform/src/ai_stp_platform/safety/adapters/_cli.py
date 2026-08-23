"""Shared CLI runner helpers for optional external tools."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import time
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Final

_LOG: Final[logging.Logger] = logging.getLogger(__name__)

# External CLIs can hang or pull network on some hosts. Default is owned
# in-proc engines only; worker image sets AI_STP_SAFETY_EXTERNAL_CLI=1.
_EXTERNAL_FLAG = "AI_STP_SAFETY_EXTERNAL_CLI"


def external_cli_enabled() -> bool:
    return os.environ.get(_EXTERNAL_FLAG, "").strip().lower() in {"1", "true", "yes", "on"}


def which(name: str) -> str | None:
    if not external_cli_enabled():
        return None
    return shutil.which(name)


#: Ceiling on one tool's run, whatever the caller asks for. It is a backstop
#: against a bad argument, not a second policy: `safety.policy` decides how long
#: each check may take, and `tests` refuses a declared value above this.
#:
#: It used to be 25s, silently, while three checks declared 30s and 60s. Nothing
#: reported the difference, so raising `skill_static_gate` to 60s changed
#: nothing at all and the scanner kept being killed at 25 — which is what
#: refused most of a corpus as dangerous content. Well under the suite's own
#: eight-minute budget in `safety.orchestrator`.
MAX_TIMEOUT_SECONDS: Final[float] = 120.0
_SCAN_DEADLINE: ContextVar[float | None] = ContextVar("safety_scan_deadline", default=None)


@contextmanager
def scan_deadline(deadline: float):
    """Limit every nested CLI invocation to the suite's remaining wall time."""
    token = _SCAN_DEADLINE.set(deadline)
    try:
        yield
    finally:
        _SCAN_DEADLINE.reset(token)


def remaining_timeout(requested: float) -> float:
    """Return the smaller of a check timeout and the active suite deadline."""
    remaining = _SCAN_DEADLINE.get()
    if remaining is not None:
        requested = min(float(requested), max(0.0, remaining - time.perf_counter()))
    return effective_timeout(requested)


def deadline_expired() -> bool:
    deadline = _SCAN_DEADLINE.get()
    return deadline is not None and time.perf_counter() >= deadline


def classify_cli_exit(code: int, stdout: str, stderr: str) -> tuple[str, dict[str, object]]:
    """Classify a CLI result without turning tool failures into a clean pass.

    The scanners used here reserve exit 1 for findings. Other non-zero exits
    are execution/configuration failures unless the adapter has a narrower
    documented contract of its own.
    """
    if code == 127:
        return "not_run", {"reason": "tool_missing"}
    if code == 124:
        return "degraded", {"reason": "timeout", "timed_out": ["scanner"]}
    if code == 0:
        return "passed", {}
    if code == 1 and (stdout or stderr):
        return "finding", {}
    return "degraded", {
        "reason": "tool_error",
        "exit_code": code,
        "stderr": stderr[:200],
    }


def effective_timeout(timeout: float) -> float:
    """The limit a tool will actually be given.

    Exported so an adapter can report what it waited for rather than what it
    asked for. A check that says "did not finish within 60s" after being killed
    at 25 is a report that sends somebody looking in the wrong place.
    """
    return min(float(timeout), MAX_TIMEOUT_SECONDS)


def run_cli(
    argv: list[str],
    *,
    cwd: Path,
    timeout: float,
) -> tuple[int, str, str, int]:
    """Return (code, stdout, stderr, duration_ms). Missing binary → code 127.

    On Linux with a working ``bwrap``, the argv is re-wrapped with
    ``--unshare-net`` (see ``safety.sandbox``). If bwrap cannot create a
    namespace, the runner falls back to an unwrapped env-only launch.
    A caller's timeout is bounded by ``MAX_TIMEOUT_SECONDS``.
    """
    if not argv or which(argv[0]) is None:
        try:
            from ai_stp_platform.safety.metrics import record_cli_result

            record_cli_result(code=127, duration_ms=0, sandbox_mode="n/a")
        except Exception:
            pass
        return 127, "", f"missing:{argv[0] if argv else 'tool'}", 0
    started = time.perf_counter()
    timeout = remaining_timeout(timeout)
    if timeout <= 0:
        _record(124, 0, "deadline")
        return 124, "", "timeout", 0
    from ai_stp_platform.safety.sandbox import (
        force_sandbox_mode,
        is_bwrap_failure,
        plan_cli_argv,
    )
    from ai_stp_platform.safety.workdir import env_no_network

    env = env_no_network()
    plan = plan_cli_argv(argv, cwd=cwd)
    # Never expose the worker user's home to an untrusted scanner. Bubblewrap
    # gives each launch a fresh writable /tmp; native hosts use their temp dir.
    scanner_home = "/tmp" if plan.mode == "bwrap" else tempfile.gettempdir()
    env.update(
        {
            "HOME": scanner_home,
            "USERPROFILE": scanner_home,
            "TMPDIR": scanner_home,
            "XDG_CACHE_HOME": f"{scanner_home}/.cache",
        }
    )
    require_bwrap = os.environ.get("AI_STP_SAFETY_REQUIRE_BWRAP", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if require_bwrap and plan.mode != "bwrap":
        _record(126, 0, plan.mode)
        return 126, "", "required bwrap sandbox unavailable", 0
    code, out, err, ms = _run(plan.argv, cwd=cwd, timeout=timeout, env=env, started=started)

    # Live fallback: probe may pass in some environments while real launch fails.
    if (
        not require_bwrap
        and plan.mode == "bwrap"
        and is_bwrap_failure(err, argv0=plan.argv[0] if plan.argv else None)
    ):
        force_sandbox_mode("env_only", bwrap_path=plan.bwrap_path)
        plain = list(argv)
        tool_path = shutil.which(plain[0]) if plain and not Path(plain[0]).is_absolute() else None
        if tool_path:
            plain[0] = tool_path
        code, out, err, ms = _run(plain, cwd=cwd, timeout=timeout, env=env, started=started)
        _record(code, ms, "env_only")
        return code, out, err, ms

    _record(code, ms, plan.mode)
    return code, out, err, ms


def _run(
    argv: list[str],
    *,
    cwd: Path,
    timeout: float,
    env: dict[str, str],
    started: float,
) -> tuple[int, str, str, int]:
    try:
        proc = subprocess.run(
            argv,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=env,
        )
        ms = int((time.perf_counter() - started) * 1000)
        return proc.returncode, proc.stdout or "", proc.stderr or "", ms
    except subprocess.TimeoutExpired:
        ms = int((time.perf_counter() - started) * 1000)
        # subprocess.run already terminated the child on timeout; no process handle.
        return 124, "", "timeout", ms
    except OSError as exc:
        ms = int((time.perf_counter() - started) * 1000)
        return 126, "", str(exc), ms


def _record(code: int, duration_ms: int, sandbox_mode: str) -> None:
    """Record one adapter run, and never let recording change the outcome.

    A scan's verdict is a property of the artefact, not of whether a metric
    reached a collector — so this swallows everything, deliberately. What it
    did not do was say so: an empty `except Exception: pass` is
    indistinguishable from one somebody forgot to finish, and CodeQL reports
    it for exactly that reason.

    Logged at debug rather than dropped: a metrics backend that is failing
    every call is worth being able to find, and this is the only place that
    knows it happened.
    """
    try:
        from ai_stp_platform.safety.metrics import record_cli_result

        record_cli_result(code=code, duration_ms=duration_ms, sandbox_mode=sandbox_mode)
    except Exception:
        _LOG.debug("safety adapter metrics were not recorded", exc_info=True)


def manifest_roots(tree: Path, *names: str) -> tuple[Path, ...]:
    """Every directory in this artefact holding one of `names`, sorted.

    Adapters used to test `tree / "package.json"` and friends, which assumes the
    artefact is a flat checkout. It is not: an `ai-stp-component-tree/1` unpacks
    to `component.json` and a `files/` directory, so every dependency manifest
    sits one level down and the root test found nothing.

    That did not read as a bug, because the check answered `not_applicable` —
    the same word it uses for an artefact that genuinely has no manifest. The
    planner meanwhile schedules these checks off `ArtifactManifest.languages`,
    which `detect.py` builds with `rglob`, so the language was detected from the
    very file the adapter then failed to find. The result was a dependency scan
    that was planned, reported and never run, for every component tree.

    Sorted so two runs over the same bytes visit the same directories in the
    same order, which is what lets identical bytes reach an identical verdict.
    """
    found: set[Path] = set()
    for name in names:
        if (tree / name).is_file():
            found.add(tree)
        for path in tree.rglob(name):
            if path.is_file():
                found.add(path.parent)
    return tuple(sorted(found))
