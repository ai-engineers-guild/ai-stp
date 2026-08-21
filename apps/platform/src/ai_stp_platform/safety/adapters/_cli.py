"""Shared CLI runner helpers for optional external tools."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Final

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
    timeout = effective_timeout(timeout)
    from ai_stp_platform.safety.sandbox import (
        force_sandbox_mode,
        is_bwrap_failure,
        plan_cli_argv,
    )
    from ai_stp_platform.safety.workdir import env_no_network

    env = env_no_network()
    plan = plan_cli_argv(argv, cwd=cwd)
    code, out, err, ms = _run(plan.argv, cwd=cwd, timeout=timeout, env=env, started=started)

    # Live fallback: probe may pass in some environments while real launch fails.
    if plan.mode == "bwrap" and is_bwrap_failure(err, argv0=plan.argv[0] if plan.argv else None):
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
    try:
        from ai_stp_platform.safety.metrics import record_cli_result

        record_cli_result(code=code, duration_ms=duration_ms, sandbox_mode=sandbox_mode)
    except Exception:
        pass
