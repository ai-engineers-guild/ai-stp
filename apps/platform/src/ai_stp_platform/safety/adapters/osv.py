"""OSV-Scanner SCA adapter with offline DB via local cache directory.

Offline data is read from ``OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY`` (osv-scanner
upstream contract). We set that env to ``AI_STP_OSV_OFFLINE_DIR`` (or the
worker default) so the compose volume is the real DB location — the offline
dir is never a scan target path.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from ai_stp_platform.safety.adapters._cli import classify_cli_exit, run_cli, which
from ai_stp_platform.safety.normalize import redact_message
from ai_stp_platform.safety.osv_health import offline_db_packs, osv_db_status
from ai_stp_platform.safety.policy import CheckSpec
from ai_stp_platform.safety.types import ArtifactManifest, CheckOutcome, Finding

_DEFAULT_OFFLINE = Path("/var/lib/ai_stp/osv")
_CACHE_ENV = "OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY"
_OFFLINE_DIR_ENV = "AI_STP_OSV_OFFLINE_DIR"


def resolve_offline_cache_dir() -> Path | None:
    """Return configured offline cache root (may be empty of data)."""
    raw = os.environ.get(_OFFLINE_DIR_ENV, "").strip()
    if raw:
        return Path(raw)
    if _DEFAULT_OFFLINE.is_dir():
        return _DEFAULT_OFFLINE
    return None


def offline_db_has_data(directory: Path) -> bool:
    """True when ecosystem zip packs exist under the cache root."""
    return bool(offline_db_packs(directory))


def run(tree: Path, manifest: ArtifactManifest, spec: CheckSpec) -> CheckOutcome:
    if "manifests" not in manifest.flags:
        return CheckOutcome(
            check_id=spec.check_id,
            family=spec.family,
            result="not_applicable",
            mandatory=spec.mandatory,
            tool_name="osv-scanner",
        )

    if which("osv-scanner") is None:
        return CheckOutcome(
            check_id=spec.check_id,
            family=spec.family,
            result="not_run",
            mandatory=spec.mandatory,
            tool_name="osv-scanner",
            detail={"reason": "tool_missing"},
        )

    cache_dir = resolve_offline_cache_dir()
    status = osv_db_status()
    if cache_dir is None or not status["fresh"]:
        reason = (
            "offline_db_stale"
            if status["reason"] == "stale"
            else "offline_db_unavailable"
            if status["present"]
            else "offline_db_missing"
        )
        return CheckOutcome(
            check_id=spec.check_id,
            family=spec.family,
            result="not_run",
            mandatory=spec.mandatory,
            tool_name="osv-scanner",
            detail={
                "reason": reason,
                "database_status": status["reason"],
                "offline_dir": str(cache_dir) if cache_dir else None,
                "cache_env_name": _CACHE_ENV,
            },
        )

    os.environ[_CACHE_ENV] = str(cache_dir.resolve())
    used = [
        "osv-scanner",
        "scan",
        "source",
        "--offline",
        "--no-resolve",
        "-r",
        str(tree),
    ]
    code, out, err, ms = run_cli(used, cwd=tree, timeout=spec.timeout_seconds)

    combined = f"{out}\n{err}"
    if code not in {0, 1} and _looks_like_offline_db_error(err):
        return CheckOutcome(
            check_id=spec.check_id,
            family=spec.family,
            result="not_run",
            mandatory=spec.mandatory,
            tool_name="osv-scanner",
            duration_ms=ms,
            detail={
                "reason": "offline_db_unavailable",
                "offline_dir": str(cache_dir) if cache_dir else None,
                "stderr": redact_message(combined[:200]),
            },
        )

    state, detail = classify_cli_exit(code, out, err)
    if code == 127 and not err.startswith("missing:"):
        # OSV also uses 127 for extraction/database failures after it starts.
        state = "degraded"
        detail = {"reason": "tool_error", "exit_code": code, "stderr": redact_message(err[:200])}
    if state == "degraded":
        return CheckOutcome(
            check_id=spec.check_id,
            family=spec.family,
            result=state,
            mandatory=spec.mandatory,
            tool_name="osv-scanner",
            duration_ms=ms,
            detail={**detail, "argv0": " ".join(used[:4])},
        )
    findings: list[Finding] = []
    if state == "finding":
        findings.append(
            Finding(
                check_id=spec.check_id,
                family=spec.family,
                rule_id="osv",
                severity="medium",
                title="OSV-Scanner reported vulnerabilities",
                message=redact_message(combined[:300]),
                tool_name="osv-scanner",
            )
        )
    return CheckOutcome(
        check_id=spec.check_id,
        family=spec.family,
        result="warning" if findings else "passed",
        mandatory=spec.mandatory,
        tool_name="osv-scanner",
        duration_ms=ms,
        findings=findings,
        detail={
            "offline": True,
            "database_age_hours": status["age_hours"],
            "offline_dir": str(cache_dir) if cache_dir else None,
            "cache_env_name": _CACHE_ENV,
            "cache_env_value": os.environ.get(_CACHE_ENV),
            "argv0": " ".join(used[:4]),
        },
    )


def _looks_like_offline_db_error(text: str) -> bool:
    low = text.lower()
    patterns = (
        r"local database",
        r"offline database",
        r"no.*database",
        r"database.*not found",
        r"failed to load.*db",
        r"missing.*zip",
        r"osv-scanner.*not found",
    )
    return any(re.search(p, low) for p in patterns)
