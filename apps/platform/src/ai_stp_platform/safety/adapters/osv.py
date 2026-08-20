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

from ai_stp_platform.safety.adapters._cli import run_cli, which
from ai_stp_platform.safety.normalize import redact_message
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
    if not directory.is_dir():
        return False
    # Layout: {cache}/osv-scanner/{ecosystem}/all.zip  or  {cache}/{ecosystem}/all.zip
    if any(directory.rglob("all.zip")):
        return True
    nested = directory / "osv-scanner"
    return nested.is_dir() and any(nested.rglob("*.zip"))


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
    offline_mode = False
    if cache_dir is not None and cache_dir.is_dir():
        offline_mode = True
        os.environ[_CACHE_ENV] = str(cache_dir.resolve())
        if not offline_db_has_data(cache_dir):
            return CheckOutcome(
                check_id=spec.check_id,
                family=spec.family,
                result="not_run",
                mandatory=spec.mandatory,
                tool_name="osv-scanner",
                detail={
                    "reason": "offline_db_missing",
                    "offline_dir": str(cache_dir),
                    "cache_env_name": _CACHE_ENV,
                },
            )

    # Prefer v2 subcommand shape; fall back to legacy flags.
    argv_candidates = [
        [
            "osv-scanner",
            "scan",
            "source",
            "-r",
            str(tree),
            *(["--offline-vulnerabilities"] if offline_mode else []),
        ],
        [
            "osv-scanner",
            "--recursive",
            *(["--offline", "--offline-vulnerabilities"] if offline_mode else []),
            str(tree),
        ],
    ]
    code, out, err, ms = 127, "", "", 0
    used: list[str] = []
    for argv in argv_candidates:
        used = argv
        code, out, err, ms = run_cli(argv, cwd=tree, timeout=min(spec.timeout_seconds, 30))
        # 127 only if first token missing — should not happen after which().
        if code != 127:
            break

    if code == 127:
        return CheckOutcome(
            check_id=spec.check_id,
            family=spec.family,
            result="not_run",
            mandatory=spec.mandatory,
            tool_name="osv-scanner",
            duration_ms=ms,
            detail={"reason": "tool_missing"},
        )

    combined = f"{out}\n{err}"
    if offline_mode and _looks_like_offline_db_error(combined):
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

    findings: list[Finding] = []
    if code != 0:
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
            "offline": offline_mode,
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
