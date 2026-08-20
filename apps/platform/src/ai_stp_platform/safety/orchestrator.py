"""Staged safety orchestrator with budgets and optional artifact injection."""

from __future__ import annotations

import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

from ai_stp_foundation.digests import digest_bytes
from ai_stp_platform.safety.adapters import get_adapter
from ai_stp_platform.safety.detect import detect_manifest
from ai_stp_platform.safety.normalize import apply_findings_to_outcome
from ai_stp_platform.safety.planner import plan_checks
from ai_stp_platform.safety.policy import POLICY_VERSION, SafetyProfile
from ai_stp_platform.safety.types import CheckOutcome, SafetyScanResult
from ai_stp_platform.safety.workdir import (
    WorkdirError,
    isolated_workdir,
    materialize_artifact,
)
from ai_stp_platform.storage.object_store import ARTIFACT_DIGEST_DOMAIN, ImmutableObjectStore

# Global wall-clock hard cap for the full suite (ms).
HARD_CAP_MS = 8 * 60 * 1000
SOFT_CAP_MS = 5 * 60 * 1000
MAX_PARALLEL_HINT = 2  # serial stages; parallel reserved for future


class ArtifactSource(Protocol):
    async def fetch_bytes(self, content_digest: str, size_bytes: int | None) -> bytes | None: ...


class StoreArtifactSource:
    """Fetch from ImmutableObjectStore by content-addressed key."""

    def __init__(self, store: ImmutableObjectStore, *, key_for_digest: str | None = None) -> None:
        self._store = store
        self._key = key_for_digest

    async def fetch_bytes(self, content_digest: str, size_bytes: int | None) -> bytes | None:
        if self._key is not None and size_bytes is not None:
            return await self._store.read_verified(
                object_key=self._key,
                expected_digest=content_digest,
                expected_size=size_bytes,
            )
        try:
            return await self._store.read_by_digest(
                content_digest,
                expected_size=size_bytes,
            )
        except Exception as exc:
            raise WorkdirError(f"object fetch failed: {exc}") from exc


class BytesArtifactSource:
    """Test/injected artifact bytes."""

    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    async def fetch_bytes(self, content_digest: str, size_bytes: int | None) -> bytes | None:
        del size_bytes
        actual = digest_bytes(ARTIFACT_DIGEST_DOMAIN, self._payload)
        if actual != content_digest:
            # Allow tests to pass mismatched passport digests only when empty
            # digest sentinel; otherwise re-hash requirement fails the suite.
            raise WorkdirError(
                f"injected artifact digest mismatch: expected {content_digest}, got {actual}"
            )
        return self._payload


# In-process cache for complete results (idempotent same process / tests).
_RESULT_CACHE: dict[tuple[str, str], SafetyScanResult] = {}


def clear_safety_cache() -> None:
    _RESULT_CACHE.clear()


def _finish(result: SafetyScanResult) -> SafetyScanResult:
    """Record metrics and return the suite result."""
    try:
        from ai_stp_platform.safety.metrics import record_scan

        record_scan(
            profile=result.profile,
            wall_ms=result.wall_ms,
            cache_hit=result.cache_hit,
            outcomes=result.outcomes,
        )
    except Exception:
        pass
    return result


async def run_safety_suite(
    *,
    passport: Mapping[str, object],
    content_digest: str,
    policy_version: str = POLICY_VERSION,
    object_kind: str = "component",
    profile: SafetyProfile | str = SafetyProfile.STANDARD,
    artifact_source: ArtifactSource | None = None,
    artifact_bytes: bytes | None = None,
    use_cache: bool = True,
) -> SafetyScanResult:
    """Run planned safety checks; return outcomes with source platform_safety_scan."""
    # SafetyProfile is a StrEnum (also a str); always normalize via the enum.
    prof = profile if isinstance(profile, SafetyProfile) else SafetyProfile(str(profile))
    cache_key = (content_digest, policy_version)
    if use_cache and cache_key in _RESULT_CACHE:
        cached = _RESULT_CACHE[cache_key]
        return _finish(
            SafetyScanResult(
                content_digest=cached.content_digest,
                policy_version=cached.policy_version,
                profile=cached.profile,
                outcomes=list(cached.outcomes),
                cache_hit=True,
                wall_ms=0,
                workdir=None,
            )
        )

    started = time.perf_counter()
    passport_dict = dict(passport)

    if object_kind == "setup":
        # pin_context may be set by execute_validate before calling the suite
        outcomes = _run_setup_only(prof)
        result = SafetyScanResult(
            content_digest=content_digest,
            policy_version=policy_version,
            profile=prof.value,
            outcomes=outcomes,
            wall_ms=int((time.perf_counter() - started) * 1000),
        )
        if use_cache:
            _RESULT_CACHE[cache_key] = result
        return _finish(result)

    source = artifact_source
    if artifact_bytes is not None:
        source = BytesArtifactSource(artifact_bytes)

    size = _artifact_size(passport_dict)
    if source is None:
        # No artifact available: mandatory safety tree checks become not_run
        # (never auto-passed).
        outcomes = _not_run_all_component(prof, reason="artifact_unavailable")
        result = SafetyScanResult(
            content_digest=content_digest,
            policy_version=policy_version,
            profile=prof.value,
            outcomes=outcomes,
            wall_ms=int((time.perf_counter() - started) * 1000),
        )
        if use_cache:
            _RESULT_CACHE[cache_key] = result
        return _finish(result)

    try:
        payload = await source.fetch_bytes(content_digest, size)
    except WorkdirError as exc:
        outcomes = [
            CheckOutcome(
                check_id="artifact_unpack",
                family="unpack",
                result="failed",
                mandatory=True,
                tool_name="artifact_source",
                detail={"error": str(exc)},
            )
        ]
        result = SafetyScanResult(
            content_digest=content_digest,
            policy_version=policy_version,
            profile=prof.value,
            outcomes=outcomes,
            wall_ms=int((time.perf_counter() - started) * 1000),
        )
        if use_cache:
            _RESULT_CACHE[cache_key] = result
        return _finish(result)

    if payload is None:
        outcomes = _not_run_all_component(prof, reason="artifact_not_found")
        result = SafetyScanResult(
            content_digest=content_digest,
            policy_version=policy_version,
            profile=prof.value,
            outcomes=outcomes,
            wall_ms=int((time.perf_counter() - started) * 1000),
        )
        if use_cache:
            _RESULT_CACHE[cache_key] = result
        return _finish(result)

    # Re-hash gate
    actual = digest_bytes(ARTIFACT_DIGEST_DOMAIN, payload)
    if actual != content_digest:
        outcomes = [
            CheckOutcome(
                check_id="artifact_unpack",
                family="unpack",
                result="failed",
                mandatory=True,
                tool_name="digest_reverify",
                detail={"expected": content_digest, "actual": actual},
            )
        ]
        result = SafetyScanResult(
            content_digest=content_digest,
            policy_version=policy_version,
            profile=prof.value,
            outcomes=outcomes,
            wall_ms=int((time.perf_counter() - started) * 1000),
        )
        if use_cache:
            _RESULT_CACHE[cache_key] = result
        return _finish(result)

    with isolated_workdir() as workdir:
        try:
            tree = materialize_artifact(workdir, payload)
        except WorkdirError as exc:
            outcomes = [
                CheckOutcome(
                    check_id="artifact_unpack",
                    family="unpack",
                    result="failed",
                    mandatory=True,
                    tool_name="workdir",
                    detail={"error": str(exc)},
                )
            ]
            result = SafetyScanResult(
                content_digest=content_digest,
                policy_version=policy_version,
                profile=prof.value,
                outcomes=outcomes,
                wall_ms=int((time.perf_counter() - started) * 1000),
                workdir=str(workdir),
            )
            if use_cache:
                _RESULT_CACHE[cache_key] = result
            return _finish(result)

        manifest = detect_manifest(tree, passport=passport_dict)
        planned = plan_checks(object_kind=object_kind, manifest=manifest, profile=prof)
        outcomes = _execute_plan(tree, manifest, planned, started)

    result = SafetyScanResult(
        content_digest=content_digest,
        policy_version=policy_version,
        profile=prof.value,
        outcomes=outcomes,
        wall_ms=int((time.perf_counter() - started) * 1000),
    )
    if use_cache:
        _RESULT_CACHE[cache_key] = result
    return _finish(result)


def _execute_plan(
    tree: Path,
    manifest: Any,
    planned: list[Any],
    started: float,
) -> list[CheckOutcome]:
    outcomes: list[CheckOutcome] = []
    for spec in planned:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        if elapsed_ms > HARD_CAP_MS:
            outcomes.append(
                CheckOutcome(
                    check_id=spec.check_id,
                    family=spec.family,
                    result="degraded",
                    mandatory=spec.mandatory,
                    tool_name="orchestrator",
                    detail={"reason": "hard_cap"},
                )
            )
            continue
        if elapsed_ms > SOFT_CAP_MS and not spec.mandatory:
            outcomes.append(
                CheckOutcome(
                    check_id=spec.check_id,
                    family=spec.family,
                    result="skipped",
                    mandatory=spec.mandatory,
                    tool_name="orchestrator",
                    detail={"reason": "soft_cap"},
                )
            )
            continue
        adapter = get_adapter(spec.check_id)
        if adapter is None:
            outcomes.append(
                CheckOutcome(
                    check_id=spec.check_id,
                    family=spec.family,
                    result="not_run",
                    mandatory=spec.mandatory,
                    tool_name="missing_adapter",
                )
            )
            continue
        try:
            outcome = adapter(tree, manifest, spec)
        except Exception as exc:
            outcome = CheckOutcome(
                check_id=spec.check_id,
                family=spec.family,
                result="degraded",
                mandatory=spec.mandatory,
                tool_name=spec.check_id,
                detail={"error": str(exc)[:200]},
            )
        outcome = apply_findings_to_outcome(outcome)
        # Failed findings in high-risk families always block publish, even when
        # the engine itself is optional when missing (e.g. gitleaks not installed).
        if outcome.result == "failed" and outcome.family in _BLOCKING_ON_FAIL:
            outcome.mandatory = True
        outcomes.append(outcome)
    return outcomes


_BLOCKING_ON_FAIL = frozenset(
    {
        "secrets",
        "path",
        "unpack",
        "malware",
        "mcp_config",
        "hook_command",
        "hook_schema",
        "skill_static",
    }
)


def _run_setup_only(profile: SafetyProfile) -> list[CheckOutcome]:
    planned = plan_checks(object_kind="setup", manifest=None, profile=profile)
    outcomes: list[CheckOutcome] = []
    for spec in planned:
        adapter = get_adapter(spec.check_id)
        if adapter is None:
            outcomes.append(
                CheckOutcome(
                    check_id=spec.check_id,
                    family=spec.family,
                    result="not_run",
                    mandatory=spec.mandatory,
                )
            )
            continue
        # setup adapters ignore tree
        outcomes.append(adapter(Path(), None, spec))  # type: ignore[arg-type]
    return outcomes


def _not_run_all_component(profile: SafetyProfile, *, reason: str) -> list[CheckOutcome]:
    from ai_stp_platform.safety.types import ArtifactManifest

    empty = ArtifactManifest(component_type="unknown")
    planned = plan_checks(object_kind="component", manifest=empty, profile=profile)
    # Always-run checks only (empty flags) — still mark not_run rather than pass
    return [
        CheckOutcome(
            check_id=spec.check_id,
            family=spec.family,
            result="not_run",
            mandatory=spec.mandatory,
            tool_name="orchestrator",
            detail={"reason": reason},
        )
        for spec in planned
        if not spec.requires_any_flag
    ]


def _artifact_size(passport: dict[str, object] | Mapping[str, object]) -> int | None:
    from typing import cast

    art = passport.get("artifact")
    if isinstance(art, dict):
        size = cast(dict[str, object], art).get("size_bytes")
        if isinstance(size, int):
            return size
    return None


def doctor_tools() -> dict[str, str]:
    """Return tool name -> version, missing, or disabled (external CLI off)."""
    import shutil

    from ai_stp_platform.safety.adapters._cli import external_cli_enabled, run_cli
    from ai_stp_platform.safety.metrics import snapshot as metrics_snapshot
    from ai_stp_platform.safety.osv_health import osv_db_status
    from ai_stp_platform.safety.sandbox import sandbox_status

    tools = [
        "gitleaks",
        "opengrep",
        "shellcheck",
        "bandit",
        "pip-audit",
        "gosec",
        "govulncheck",
        "cargo",
        "eslint",
        "npm",
        "osv-scanner",
        "clamscan",
        "yara",
        "skillspector",
        "skill-scanner",
        "bwrap",
    ]
    out: dict[str, str] = {
        "external_cli": "enabled" if external_cli_enabled() else "disabled",
    }
    for name in tools:
        path = shutil.which(name)
        if path is None:
            out[name] = "missing"
            continue
        if name == "bwrap":
            out[name] = f"present:{path}"
            continue
        if not external_cli_enabled():
            out[name] = f"present:{path} (disabled until AI_STP_SAFETY_EXTERNAL_CLI=1)"
            continue
        code, stdout, stderr, _ = run_cli([name, "--version"], cwd=Path(), timeout=5)
        line = (stdout or stderr or "").strip().splitlines()
        out[name] = line[0][:120] if line else ("ok" if code in (0, 1) else f"exit:{code}")

    sb = sandbox_status()
    out["sandbox_mode"] = sb["mode"]
    out["sandbox_env"] = sb["env_flag"]

    osv = osv_db_status()
    out["osv_offline_present"] = "yes" if osv.get("present") else "no"
    out["osv_offline_fresh"] = "yes" if osv.get("fresh") else "no"
    out["osv_offline_reason"] = str(osv.get("reason") or "")
    if osv.get("age_hours") is not None:
        out["osv_offline_age_hours"] = str(osv["age_hours"])
    if osv.get("path"):
        out["osv_offline_path"] = str(osv["path"])

    snap = metrics_snapshot()
    out["metrics_scan_total"] = str(snap.get("safety_scan_total", 0))
    out["metrics_cli_timeout_total"] = str(snap.get("safety_cli_timeout_total", 0))
    return out


def safety_diagnostics() -> dict[str, object]:
    """Structured diagnostics for ops (doctor + metrics + OSV + sandbox)."""
    from ai_stp_platform.safety.metrics import snapshot as metrics_snapshot
    from ai_stp_platform.safety.osv_health import osv_db_ready, osv_db_status
    from ai_stp_platform.safety.sandbox import sandbox_status

    return {
        "tools": doctor_tools(),
        "osv": osv_db_status(),
        "osv_ready": osv_db_ready(),
        "sandbox": sandbox_status(),
        "metrics": metrics_snapshot(),
    }
