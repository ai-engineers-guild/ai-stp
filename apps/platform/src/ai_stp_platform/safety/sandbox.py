"""Linux Bubblewrap wrapper for external safety CLI processes.

When ``bwrap`` is available *and* can create a user/network namespace, scanner
argv is re-wrapped with ``--unshare-net``. On non-Linux hosts, missing bwrap,
or kernels that deny unprivileged user namespaces (common on Docker Desktop
defaults), mode falls back to ``env_only`` (proxy cleared + network hint).

This is best-effort host isolation complementary to the worker container
network policy; it is not a full multi-tenant security boundary.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

SandboxMode = Literal["bwrap", "env_only", "disabled"]

_BWRAP_BASE: tuple[str, ...] = (
    "--unshare-net",
    "--die-with-parent",
    "--new-session",
    "--ro-bind",
    "/",
    "/",
    "--dev",
    "/dev",
    "--proc",
    "/proc",
    "--tmpfs",
    "/tmp",
)

_lock = threading.Lock()
_cached_mode: SandboxMode | None = None
_cached_bwrap: str | None = None
_probe_detail: str = ""


@dataclass(frozen=True, slots=True)
class SandboxPlan:
    """Resolved launch plan for one CLI invocation."""

    mode: SandboxMode
    argv: list[str]
    bwrap_path: str | None = None


def reset_sandbox_cache() -> None:
    """Clear mode detection cache (tests)."""
    global _cached_mode, _cached_bwrap, _probe_detail
    with _lock:
        _cached_mode = None
        _cached_bwrap = None
        _probe_detail = ""


def force_sandbox_mode(mode: SandboxMode, *, bwrap_path: str | None = None) -> None:
    """Override cached mode (runtime fallback after a live bwrap failure)."""
    global _cached_mode, _cached_bwrap, _probe_detail
    with _lock:
        _cached_mode = mode
        _cached_bwrap = bwrap_path
        _probe_detail = f"forced:{mode}"


def sandbox_enabled() -> bool:
    """Return whether sandbox wrapping is allowed by env."""
    raw = os.environ.get("AI_STP_SAFETY_SANDBOX", "auto").strip().lower()
    return raw not in {"0", "false", "off", "disabled", "no"}


def _probe_bwrap(executable: str) -> tuple[bool, str]:
    """Return (ok, detail). Requires unprivileged user namespaces."""
    true_bin = shutil.which("true") or "/bin/true"
    if not Path(true_bin).exists() and not shutil.which("true"):
        return False, "true_binary_missing"
    argv = [
        executable,
        "--unshare-net",
        "--die-with-parent",
        "--ro-bind",
        "/",
        "/",
        "--dev",
        "/dev",
        "--",
        true_bin if Path(true_bin).exists() else "true",
    ]
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=3.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"probe_error:{exc}"
    if proc.returncode == 0:
        return True, "ok"
    err = (proc.stderr or proc.stdout or "").strip().replace("\n", " ")[:200]
    return False, err or f"exit:{proc.returncode}"


def detect_sandbox_mode() -> SandboxMode:
    """Detect once: bwrap | env_only | disabled."""
    global _cached_mode, _cached_bwrap, _probe_detail
    with _lock:
        if _cached_mode is not None:
            return _cached_mode
        if not sandbox_enabled():
            _cached_mode = "disabled"
            _cached_bwrap = None
            _probe_detail = "env_disabled"
            return _cached_mode
        if platform.system().lower() != "linux":
            _cached_mode = "env_only"
            _cached_bwrap = None
            _probe_detail = "non_linux"
            return _cached_mode
        path = shutil.which("bwrap")
        if path is None:
            _cached_mode = "env_only"
            _cached_bwrap = None
            _probe_detail = "bwrap_missing"
            return _cached_mode
        ok, detail = _probe_bwrap(path)
        _probe_detail = detail
        if ok:
            _cached_mode = "bwrap"
            _cached_bwrap = path
        else:
            _cached_mode = "env_only"
            _cached_bwrap = path  # present but unusable
        return _cached_mode


def plan_cli_argv(argv: list[str], *, cwd: Path) -> SandboxPlan:
    """Return argv possibly wrapped in bwrap with network namespace isolation.

    The workdir is bind-mounted RW so scanners can write temp/report files
    under the tree when needed; the rest of the filesystem is read-only.
    """
    mode = detect_sandbox_mode()
    if mode != "bwrap" or not argv:
        return SandboxPlan(mode=mode if mode != "disabled" else "disabled", argv=list(argv))

    bwrap = _cached_bwrap or shutil.which("bwrap")
    if not bwrap:
        return SandboxPlan(mode="env_only", argv=list(argv))

    resolved_cwd = cwd.resolve()
    # Prefer absolute tool path so ro-bind root still finds the binary.
    tool = argv[0]
    tool_path = shutil.which(tool) if not Path(tool).is_absolute() else tool
    launch = list(argv)
    if tool_path:
        launch[0] = tool_path

    wrapped: list[str] = [
        bwrap,
        *_BWRAP_BASE,
        "--bind",
        str(resolved_cwd),
        str(resolved_cwd),
        "--chdir",
        str(resolved_cwd),
        "--",
        *launch,
    ]
    return SandboxPlan(mode="bwrap", argv=wrapped, bwrap_path=bwrap)


def is_bwrap_failure(stderr: str, *, argv0: str | None = None) -> bool:
    """Detect bwrap launch failures that must not be treated as tool findings."""
    text = (stderr or "").lower()
    if "no permissions to create new namespace" in text:
        return True
    if "bwrap:" in text and ("namespace" in text or "permission" in text):
        return True
    return bool(argv0 and "bwrap" in Path(argv0).name.lower() and "permission" in text)


def sandbox_status() -> dict[str, str]:
    """Compact status for doctor/metrics."""
    mode = detect_sandbox_mode()
    return {
        "mode": mode,
        "bwrap": _cached_bwrap or "",
        "env_flag": os.environ.get("AI_STP_SAFETY_SANDBOX", "auto"),
        "platform": platform.system().lower(),
        "probe": _probe_detail,
    }
