"""Check, plan, apply, recover and rollback the installed `ai-stp-cli` wheel."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final, Literal, cast

from ai_stp_cli import config
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.runtime import DISTRIBUTION
from ai_stp_cli.self_update import index as index_mod
from ai_stp_cli.self_update import method as method_mod
from ai_stp_cli.self_update import store
from ai_stp_cli.self_update.index import Candidate, ReleaseIndex
from ai_stp_cli.self_update.method import Installation
from ai_stp_contracts.machine_help import (
    CliSelfUpdateCheck,
    CliSelfUpdatePlan,
    CliSelfUpdateResult,
    CliSelfUpdateStatus,
    CliUpdateCheckState,
    CliUpdateJournalState,
)
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_canonical
from ai_stp_foundation.ids import new_id
from ai_stp_foundation.timestamps import format_timestamp

PLAN_DOMAIN: Final[str] = "ai-stp:plan:v1"
NOTICE_WARNING: Final[str] = (
    "a newer {distribution} {version} is available; run: update plan --json"
)


def check(
    parameters: Mapping[str, object],
    *,
    installation: Installation | None = None,
    releases: ReleaseIndex | None = None,
    timeout: float | None = None,
) -> CliSelfUpdateCheck:
    held = installation or method_mod.current_installation()
    channel = _channel(parameters.get("channel"))
    offline = bool(parameters.get("offline"))
    python = (sys.version_info.major, sys.version_info.minor, sys.version_info.micro)
    enabled, configured_channel, _ttl_hours, _notifications = _settings()
    if not parameters.get("channel"):
        channel = configured_channel
    if held.method == "source_managed":
        report = _check_report(
            held,
            channel=channel,
            state="source_managed",
            reason=held.reason,
            cache_age=None,
        )
        _write_cache(report)
        return report
    cached = _read_cache(held, channel)
    if offline:
        if cached is None:
            return _check_report(
                held,
                channel=channel,
                state="unknown",
                reason="no check cache is available offline",
                cache_age=None,
            )
        return cached
    if not enabled:
        return _check_report(
            held,
            channel=channel,
            state="unknown",
            reason="update.enabled is false; pass a command that does not require the index",
            cache_age=_age(cached),
        )
    try:
        client = releases or index_mod.PypiIndex()
        budget = index_mod.CHECK_TIMEOUT if timeout is None else timeout
        deadline = time.monotonic() + budget
        project = client.project(index_mod.PROJECT, timeout=_remaining(deadline))
        simple = client.simple_files(index_mod.PROJECT, timeout=_remaining(deadline))
        _remaining(deadline)
        candidate, state, reason = index_mod.inspect_channel(
            project,
            simple,
            installed=held.version,
            channel=channel,
            python=python,
            requested=_optional_text(parameters.get("version")),
        )
    except CliFailure as failure:
        if failure.code in {
            "AI_STP_DEPENDENCY_UNAVAILABLE",
            "AI_STP_RATE_LIMITED",
            "AI_STP_VALIDATION_ERROR",
        }:
            if cached is not None:
                report = cached.model_copy(update={"state": "stale", "reason": failure.message})
                _write_cache(report, backoff=True)
                return report
            report = _check_report(
                held,
                channel=channel,
                state="unknown",
                reason=failure.message,
                cache_age=None,
            )
            _write_cache(report, backoff=True)
            return report
        raise
    report = _check_report(
        held,
        channel=channel,
        state=cast(CliUpdateCheckState, state),
        reason=reason,
        candidate=candidate,
        cache_age=0,
    )
    _write_cache(report)
    return report


def plan(
    parameters: Mapping[str, object],
    *,
    installation: Installation | None = None,
    releases: ReleaseIndex | None = None,
) -> CliSelfUpdatePlan:
    held = installation or method_mod.current_installation()
    if not held.apply_ready:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            held.reason,
            details={"method": held.method, "executable": method_mod.display_path(held.executable)},
            next_actions=["update check --json"],
        )
    channel = _channel(parameters.get("channel"))
    if not parameters.get("channel"):
        _enabled, channel, _ttl, _notes = _settings()
    client = releases or index_mod.PypiIndex()
    python = (sys.version_info.major, sys.version_info.minor, sys.version_info.micro)
    project = client.project(index_mod.PROJECT, timeout=index_mod.CHECK_TIMEOUT)
    simple = client.simple_files(index_mod.PROJECT, timeout=index_mod.CHECK_TIMEOUT)
    candidate = index_mod.select_candidate(
        project,
        simple,
        installed=held.version,
        channel=channel,
        python=python,
        requested=_optional_text(parameters.get("version")),
    )
    if not candidate.simple_index_ready:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            candidate.reason,
            details={"filename": candidate.wheel.filename},
            next_actions=["update check --json"],
        )
    if candidate.version == held.version or "already installed" in candidate.reason:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "this installation already matches the selected version",
            details={"installed": held.version, "requested": candidate.version},
        )
    installer = _installer_argv(held, stage_wheel(candidate.wheel.filename))
    backup = store.backup_dir() / new_id("operation")
    draft = {
        "source_version": held.version,
        "target_version": candidate.version,
        "python_version": _python_text(),
        "install_method": held.method,
        "executable": str(held.executable),
        "install_root": str(held.prefix),
        "receipt_fingerprint": method_mod.fingerprint(held),
        "distribution": DISTRIBUTION,
        "artifact_filename": candidate.wheel.filename,
        "artifact_url": candidate.wheel.url,
        "artifact_bytes": candidate.wheel.size,
        "artifact_digest": f"sha256:{candidate.wheel.sha256}",
        "index_origin": getattr(client, "origin", index_mod.INDEX_ORIGIN),
        "channel": channel,
        "installer_argv": installer,
        "installer_environment": method_mod.installer_environment(held),
        "restart_effect": "new_process_required",
        "data_backup": str(backup),
        "rollback_available": _rollback_wheel(held.version) is not None,
    }
    plan_id = new_id("plan")
    unsigned = {
        **draft,
        "plan_id": plan_id,
        "apply_ready": True,
        "reason": candidate.reason,
        "plan_digest": "sha256:" + ("0" * 64),
    }
    provisional = CliSelfUpdatePlan.model_validate(unsigned)
    body = provisional.model_dump(mode="json")
    body.pop("plan_digest")
    plan_digest = digest_canonical(PLAN_DOMAIN, cast(JsonValue, body))
    payload = provisional.model_copy(update={"plan_digest": plan_digest})
    store.write_json(store.plans_dir() / f"{plan_digest[7:]}.json", payload.model_dump(mode="json"))
    with store.exclusive_lock():
        journal = store.read_json(store.journal_path()) or {}
        if not journal or journal.get("state") == "planned":
            store.write_json(
                store.journal_path(),
                {
                    "state": "planned",
                    "plan_digest": plan_digest,
                    "plan_id": plan_id,
                    "target_version": payload.target_version,
                    "source_version": payload.source_version,
                    "updated_at": format_timestamp(datetime.now(UTC)),
                    "reason": payload.reason,
                },
            )
    return payload


def apply(
    parameters: Mapping[str, object],
    *,
    installation: Installation | None = None,
    releases: ReleaseIndex | None = None,
    runner: Callable[[Sequence[str]], subprocess.CompletedProcess[str]] | None = None,
) -> CliSelfUpdateResult:
    expected = _required_digest(parameters.get("expected-plan-digest"))
    with store.exclusive_lock():
        planned = _load_plan(expected)
        held = installation or method_mod.current_installation()
        journal = store.read_json(store.journal_path()) or {}
        if journal.get("plan_digest") == expected and held.version == planned.target_version:
            _require_installation_root(held, planned)
            observed = _observe_version(held.executable)
            if observed != planned.target_version:
                _fail_journal(planned, "the replacement cannot be observed")
                raise CliFailure("AI_STP_PARTIAL_OPERATION", "the replacement cannot be observed")
            was_verified = journal.get("state") == "verified"
            return _verified(
                planned, held, observed, outcome="unchanged" if was_verified else "recovered"
            )
        if (
            journal.get("state") in {"applying", "pending", "downloaded", "recovery_required"}
            and journal.get("plan_digest") != expected
        ):
            raise CliFailure(
                "AI_STP_CONFLICT",
                "recover the active CLI update before another apply",
                next_actions=["update recover --json"],
            )
        if method_mod.fingerprint(held) != planned.receipt_fingerprint:
            raise CliFailure(
                "AI_STP_PLAN_STALE",
                "this installation is not the one the plan described",
                details={"plan_digest": planned.plan_digest},
            )
        client = releases or index_mod.PypiIndex()
        project = client.project(index_mod.PROJECT, timeout=index_mod.CHECK_TIMEOUT)
        simple = client.simple_files(index_mod.PROJECT, timeout=index_mod.CHECK_TIMEOUT)
        candidate = index_mod.select_candidate(
            project,
            simple,
            installed=planned.source_version,
            channel=planned.channel,
            python=(sys.version_info.major, sys.version_info.minor, sys.version_info.micro),
            requested=planned.target_version,
        )
        if (
            not candidate.simple_index_ready
            or candidate.wheel.filename != planned.artifact_filename
            or f"sha256:{candidate.wheel.sha256}" != planned.artifact_digest
            or candidate.wheel.size != planned.artifact_bytes
        ):
            raise CliFailure(
                "AI_STP_PLAN_STALE", "the selected index artifact changed after planning"
            )
        staged = stage_wheel(planned.artifact_filename)
        if not staged.is_file():
            client.download(planned.artifact_url, staged, expected_size=planned.artifact_bytes)
        index_mod.verify_wheel(
            staged,
            expected_digest=planned.artifact_digest,
            expected_size=planned.artifact_bytes,
        )
        _preserve_current_wheel(held, client, planned)
        _backup_user_data(Path(planned.data_backup))
        store.write_json(
            store.journal_path(),
            {
                "state": "downloaded",
                "plan_digest": planned.plan_digest,
                "plan_id": planned.plan_id,
                "target_version": planned.target_version,
                "source_version": planned.source_version,
                "staged": str(staged),
                "updated_at": format_timestamp(datetime.now(UTC)),
                "reason": "planned wheel is staged",
            },
        )
        store.write_json(
            store.journal_path(),
            {
                "state": "applying",
                "plan_digest": planned.plan_digest,
                "plan_id": planned.plan_id,
                "target_version": planned.target_version,
                "source_version": planned.source_version,
                "staged": str(staged),
                "updated_at": format_timestamp(datetime.now(UTC)),
                "reason": "installer running",
            },
        )
        if runner is None:
            return _continue_outside_prefix(planned, held, direction="update", wheel=staged)
        try:
            completed = (
                runner(list(planned.installer_argv))
                if runner is not None
                else _run_installer(planned.installer_argv, planned.installer_environment)
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            _fail_journal(planned, f"the installer could not start: {type(error).__name__}")
            raise CliFailure(
                "AI_STP_PARTIAL_OPERATION",
                "the CLI installer could not start; the previous installation should still run",
                details={"exception": type(error).__name__},
                next_actions=["update recover --json", "update status --json"],
            ) from error
        if completed.returncode != 0:
            _fail_journal(planned, "the installer exited non-zero")
            raise CliFailure(
                "AI_STP_PARTIAL_OPERATION",
                "the CLI installer failed; recover or inspect status",
                details={"returncode": str(completed.returncode)},
                next_actions=["update recover --json", "update status --json"],
            )
        observed = _observe_version(held.executable)
        if observed != planned.target_version:
            _fail_journal(planned, f"installed version is {observed}")
            raise CliFailure(
                "AI_STP_PARTIAL_OPERATION",
                "the installer finished but the executable is not the planned version",
                details={"expected": planned.target_version, "observed": observed},
                next_actions=["update recover --json"],
            )
        return _verified(planned, held, observed, outcome="replaced")


def _require_installation_root(held: Installation, planned: CliSelfUpdatePlan) -> None:
    if (
        str(held.prefix) != planned.install_root
        or str(held.executable) != planned.executable
        or held.method != planned.install_method
    ):
        raise CliFailure("AI_STP_PLAN_STALE", "the update belongs to a different installation")


def _verified(
    planned: CliSelfUpdatePlan,
    held: Installation,
    observed: str,
    *,
    outcome: Literal["replaced", "recovered", "unchanged"],
) -> CliSelfUpdateResult:
    rollback_digest = _rollback_digest(planned)
    store.write_json(
        store.journal_path(),
        {
            "state": "verified",
            "plan_digest": planned.plan_digest,
            "plan_id": planned.plan_id,
            "target_version": planned.target_version,
            "source_version": planned.source_version,
            "rollback_digest": rollback_digest,
            "updated_at": format_timestamp(datetime.now(UTC)),
            "reason": "the new process reports the planned version",
        },
    )
    return CliSelfUpdateResult(
        outcome=outcome,
        journal_state="verified",
        installed_version=observed,
        target_version=planned.target_version,
        executable=method_mod.display_path(held.executable),
        plan_digest=planned.plan_digest,
        rollback_digest=rollback_digest,
        reason="the planned replacement is verified in a new process",
    )


def status(*, installation: Installation | None = None) -> CliSelfUpdateStatus:
    held = installation or method_mod.current_installation()
    journal = store.read_json(store.journal_path()) or {}
    state = str(journal.get("state") or "idle")
    if state not in {
        "idle",
        "planned",
        "downloaded",
        "applying",
        "pending",
        "verified",
        "recovery_required",
        "rolled_back",
        "failed",
    }:
        state = "failed"
    reason = str(journal.get("reason") or "no update journal")
    return CliSelfUpdateStatus(
        journal_state=cast(CliUpdateJournalState, state),
        installed_version=held.version,
        target_version=str(journal.get("target_version") or ""),
        previous_version=str(journal.get("source_version") or ""),
        install_method=held.method,
        executable=method_mod.display_path(held.executable),
        plan_digest=str(journal.get("plan_digest") or ""),
        rollback_digest=str(journal.get("rollback_digest") or ""),
        reason=reason,
    )


def recover(
    *,
    installation: Installation | None = None,
    releases: ReleaseIndex | None = None,
    runner: Callable[[Sequence[str]], subprocess.CompletedProcess[str]] | None = None,
) -> CliSelfUpdateResult:
    with store.exclusive_lock():
        journal = store.read_json(store.journal_path()) or {}
        state = str(journal.get("state") or "idle")
        digest = str(journal.get("plan_digest") or "")
        if journal.get("direction") == "rollback":
            return rollback(
                {"expected-plan-digest": journal.get("rollback_digest")},
                installation=installation,
                runner=runner,
            )
        if state not in {
            "verified",
            "applying",
            "pending",
            "downloaded",
            "recovery_required",
            "failed",
        }:
            raise CliFailure(
                "AI_STP_PRECONDITION_FAILED",
                "there is no interrupted CLI update to recover",
                details={"state": state},
                next_actions=["update status --json"],
            )
        if not digest:
            raise CliFailure(
                "AI_STP_PARTIAL_OPERATION",
                "the update journal is missing its plan digest",
                next_actions=["update status --json"],
            )
        result = apply(
            {"expected-plan-digest": digest},
            installation=installation,
            releases=releases,
            runner=runner,
        )
        if result.outcome != "replaced":
            return result
        return result.model_copy(
            update={
                "outcome": "recovered",
                "reason": "the interrupted update finished and the planned version runs",
            }
        )


def rollback(
    parameters: Mapping[str, object],
    *,
    installation: Installation | None = None,
    runner: Callable[[Sequence[str]], subprocess.CompletedProcess[str]] | None = None,
) -> CliSelfUpdateResult:
    expected = _required_digest(parameters.get("expected-plan-digest"))
    with store.exclusive_lock():
        journal = store.read_json(store.journal_path()) or {}
        held_digest = str(journal.get("rollback_digest") or "")
        if held_digest != expected:
            raise CliFailure(
                "AI_STP_PLAN_STALE",
                "rollback requires the digest recorded after the last verified update",
                details={"expected": expected},
                next_actions=["update status --json"],
            )
        previous = str(journal.get("source_version") or "")
        wheel = _rollback_wheel(previous)
        if wheel is None or not previous:
            raise CliFailure(
                "AI_STP_PRECONDITION_FAILED",
                "there are no rollback bytes for the previous CLI version",
                details={"previous": previous},
            )
        held = installation or method_mod.current_installation()
        planned = _load_plan(str(journal.get("plan_digest") or ""))
        _require_installation_root(held, planned)
        if _rollback_digest(planned) != expected:
            raise CliFailure("AI_STP_PLAN_STALE", "rollback artifact identity changed")
        receipt = store.read_json(wheel.with_suffix(".receipt.json"))
        if receipt is None:
            raise CliFailure("AI_STP_PRECONDITION_FAILED", "rollback artifact receipt is absent")
        index_mod.verify_wheel(
            wheel, expected_digest=str(receipt["digest"]), expected_size=int(str(receipt["size"]))
        )
        if held.version == previous and _observe_version(held.executable) == previous:
            return _rolled_back(planned, held, expected, previous)
        store.write_json(
            store.journal_path(),
            {
                **journal,
                "state": "applying",
                "direction": "rollback",
                "updated_at": format_timestamp(datetime.now(UTC)),
            },
        )
        if runner is None:
            return _continue_outside_prefix(planned, held, direction="rollback", wheel=wheel)
        argv = _planned_installer_argv(planned, wheel)
        try:
            completed = (
                runner(argv)
                if runner is not None
                else _run_installer(argv, planned.installer_environment)
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            _fail_journal(planned, "rollback installer did not finish")
            raise CliFailure(
                "AI_STP_PARTIAL_OPERATION", "rollback installer did not finish"
            ) from error
        observed = _observe_version(held.executable)
        if completed.returncode != 0 or observed != previous:
            _fail_journal(planned, "previous CLI version was not restored")
            raise CliFailure(
                "AI_STP_PARTIAL_OPERATION",
                "previous CLI version was not restored",
                next_actions=["update recover --json", "update status --json"],
            )
        return _rolled_back(planned, held, expected, observed)


def _planned_installer_argv(planned: CliSelfUpdatePlan, wheel: Path) -> list[str]:
    original = str(stage_wheel(planned.artifact_filename))
    return [str(wheel) if argument == original else argument for argument in planned.installer_argv]


def _continue_outside_prefix(
    planned: CliSelfUpdatePlan,
    held: Installation,
    *,
    direction: Literal["update", "rollback"],
    wheel: Path,
) -> CliSelfUpdateResult:
    from ai_stp_cli.paths import write_private
    from ai_stp_cli.self_update import helper

    directory = store.root() / "continuations" / new_id("operation")
    copied_helper = directory / "helper.py"
    write_private(copied_helper, Path(helper.__file__).read_text(encoding="utf-8"))
    target = planned.source_version if direction == "rollback" else planned.target_version
    job = {
        "journal": str(store.journal_path()),
        "lock": str(store.lock_path()),
        "argv": _planned_installer_argv(planned, wheel),
        "environment": planned.installer_environment,
        "executable": str(held.executable),
        "wheel": str(wheel),
        "wheel_sha256": index_mod.file_digest(wheel).removeprefix("sha256:"),
        "plan_digest": planned.plan_digest,
        "target_version": target,
        "source_version": held.version,
        "rollback_digest": _rollback_digest(planned),
        "direction": direction,
    }
    job_path = directory / "job.json"
    write_private(job_path, json.dumps(job, sort_keys=True))
    digest = hashlib.sha256(job_path.read_bytes()).hexdigest()
    journal = store.read_json(store.journal_path()) or {}
    store.write_json(store.journal_path(), {**journal, "state": "pending", "direction": direction})
    python = str(getattr(sys, "_base_executable", sys.executable))
    environment = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "PYTHONHOME"}}
    try:
        subprocess.Popen(
            [python, str(copied_helper), str(job_path), digest],
            env=environment,
            cwd=directory,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=os.name != "nt",
            close_fds=True,
            creationflags=(subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
            if os.name == "nt"
            else 0,
        )
    except OSError as error:
        _fail_journal(planned, "the independent update continuation could not start")
        raise CliFailure(
            "AI_STP_PARTIAL_OPERATION", "update continuation could not start"
        ) from error
    return CliSelfUpdateResult(
        outcome="pending",
        journal_state="pending",
        installed_version=held.version,
        target_version=target,
        executable=method_mod.display_path(held.executable),
        plan_digest=planned.plan_digest,
        rollback_digest=_rollback_digest(planned),
        reason="replacement continues outside this process; inspect update status in a new process",
    )


def _rolled_back(
    planned: CliSelfUpdatePlan,
    held: Installation,
    digest: str,
    observed: str,
) -> CliSelfUpdateResult:
    store.write_json(
        store.journal_path(),
        {
            "state": "rolled_back",
            "direction": "rollback",
            "plan_digest": planned.plan_digest,
            "rollback_digest": digest,
            "target_version": planned.source_version,
            "source_version": planned.source_version,
            "updated_at": format_timestamp(datetime.now(UTC)),
            "reason": "previous verified distribution restored",
        },
    )
    return CliSelfUpdateResult(
        outcome="rolled_back",
        journal_state="rolled_back",
        installed_version=observed,
        target_version=planned.source_version,
        executable=method_mod.display_path(held.executable),
        plan_digest=digest,
        reason="the previous verified CLI distribution is installed again",
    )


def maybe_notice(
    command_path: Sequence[str],
    *,
    machine: bool,
    tty: bool,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Warnings and extra next_actions. Never raises; never writes a second envelope."""
    if not command_path or command_path[0] == "update":
        return (), ()
    try:
        _enabled, channel, ttl_hours, notifications = _settings()
        if not notifications:
            return (), ()
        held = method_mod.current_installation()
        if held.method == "source_managed" or not held.apply_ready:
            return (), ()
        cached = _read_cache(held, channel)
        if tty and not machine and _cache_expired(cached, ttl_hours) and _enabled:
            try:
                cached = check({}, installation=held, timeout=index_mod.STARTUP_TIMEOUT)
            except CliFailure:
                cached = _read_cache(held, channel)
        if cached is None or cached.state != "available" or not cached.candidate_version:
            return (), ()
        notice_path = store.root() / "notice.json"
        previous = store.read_json(notice_path) or {}
        if previous.get("candidate_digest") == cached.candidate_digest:
            return (), ()
        warning = NOTICE_WARNING.format(distribution=DISTRIBUTION, version=cached.candidate_version)
        store.write_json(notice_path, {"candidate_digest": cached.candidate_digest})
        return (warning,), ("update plan --json",)
    except Exception:
        return (), ()


def stage_wheel(filename: str) -> Path:
    from ai_stp_cli.paths import ensure_directory

    path = store.stage_dir() / filename
    ensure_directory(path.parent)
    return path


def _check_report(
    held: Installation,
    *,
    channel: Literal["stable", "prerelease"],
    state: CliUpdateCheckState,
    reason: str,
    candidate: Candidate | None = None,
    cache_age: int | None,
) -> CliSelfUpdateCheck:
    wheel = candidate.wheel if candidate is not None else None
    return CliSelfUpdateCheck(
        state=state,
        installed_version=held.version,
        python_version=_python_text(),
        install_method=held.method,
        executable=method_mod.display_path(held.executable),
        install_root=method_mod.display_path(held.prefix),
        channel=channel,
        candidate_version="" if wheel is None else wheel.version,
        candidate_filename="" if wheel is None else wheel.filename,
        candidate_digest="" if wheel is None else f"sha256:{wheel.sha256}",
        index_origin=index_mod.INDEX_ORIGIN,
        simple_index_ready=bool(candidate and candidate.simple_index_ready),
        cache_age_seconds=cache_age,
        reason=reason,
    )


def _settings() -> tuple[bool, Literal["stable", "prerelease"], int, bool]:
    report = config.effective_config()
    by_path = {item.path: item.value for item in report.values}
    raw = str(by_path["update.channel"])
    channel: Literal["stable", "prerelease"] = "prerelease" if raw == "prerelease" else "stable"
    ttl_raw = by_path["update.check_ttl_hours"]
    ttl_hours = ttl_raw if isinstance(ttl_raw, int) and not isinstance(ttl_raw, bool) else 24
    return (
        bool(by_path["update.enabled"]),
        channel,
        max(ttl_hours, 1),
        bool(by_path["update.notifications"]),
    )


def _channel(value: object) -> Literal["stable", "prerelease"]:
    text = _optional_text(value)
    if text is None:
        return "stable"
    if text not in {"stable", "prerelease"}:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "channel must be stable or prerelease",
            details={"channel": text},
        )
    return text if text == "prerelease" else "stable"


def _optional_text(value: object) -> str | None:
    if value is None or value == "" or value is False:
        return None
    if not isinstance(value, str):
        return None
    return value


def _required_digest(value: object) -> str:
    text = _optional_text(value)
    if text is None:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "expected-plan-digest is required",
            details={"parameter": "expected-plan-digest"},
        )
    from ai_stp_foundation.digests import is_digest

    if not is_digest(text):
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "expected-plan-digest is not a digest",
            details={"parameter": "expected-plan-digest"},
        )
    return text


def _python_text() -> str:
    return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"


def _remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise CliFailure("AI_STP_DEPENDENCY_UNAVAILABLE", "the package index check timed out")
    return remaining


def _write_cache(report: CliSelfUpdateCheck, *, backoff: bool = False) -> None:
    payload = report.model_dump(mode="json")
    payload["cached_at"] = format_timestamp(datetime.now(UTC))
    if backoff:
        payload["backoff_until"] = format_timestamp(datetime.now(UTC) + timedelta(minutes=15))
    store.write_json(store.cache_path(), payload)


def _read_cache(held: Installation, channel: str) -> CliSelfUpdateCheck | None:
    payload = store.read_json(store.cache_path())
    if payload is None:
        return None
    expected = {
        "installed_version": held.version,
        "channel": channel,
        "install_root": method_mod.display_path(held.prefix),
        "executable": method_mod.display_path(held.executable),
        "install_method": held.method,
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        return None
    try:
        report = CliSelfUpdateCheck.model_validate(payload)
    except Exception:
        return None
    age = _age(report)
    if age is None:
        return report
    return report.model_copy(update={"cache_age_seconds": age})


def _age(report: CliSelfUpdateCheck | None) -> int | None:
    if report is None:
        return None
    payload = store.read_json(store.cache_path())
    if payload is None:
        return report.cache_age_seconds
    cached_at = payload.get("cached_at")
    if not isinstance(cached_at, str):
        return report.cache_age_seconds
    try:
        stamp = datetime.fromisoformat(cached_at.replace("Z", "+00:00"))
    except ValueError:
        return report.cache_age_seconds
    return max(0, int((datetime.now(UTC) - stamp).total_seconds()))


def _cache_expired(report: CliSelfUpdateCheck | None, ttl_hours: int) -> bool:
    payload = store.read_json(store.cache_path())
    if payload is None or report is None:
        return True
    backoff = payload.get("backoff_until")
    if isinstance(backoff, str):
        try:
            if datetime.fromisoformat(backoff.replace("Z", "+00:00")) > datetime.now(UTC):
                return False
        except (TypeError, ValueError):
            pass
    cached_at = payload.get("cached_at")
    if not isinstance(cached_at, str):
        return True
    try:
        stamp = datetime.fromisoformat(cached_at.replace("Z", "+00:00"))
    except ValueError:
        return True
    return datetime.now(UTC) - stamp >= timedelta(hours=max(ttl_hours, 1))


def _load_plan(digest: str) -> CliSelfUpdatePlan:
    path = store.plans_dir() / f"{digest[7:]}.json"
    payload = store.read_json(path)
    if payload is None:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "that update plan is not stored on this device",
            details={"plan_digest": digest},
            next_actions=["update plan --json"],
        )
    planned = CliSelfUpdatePlan.model_validate(payload)
    body = planned.model_dump(mode="json")
    body.pop("plan_digest")
    recomputed = digest_canonical(PLAN_DOMAIN, cast(JsonValue, body))
    if recomputed != digest or planned.plan_digest != digest:
        raise CliFailure(
            "AI_STP_PLAN_STALE",
            "the stored update plan no longer matches its digest",
            details={"plan_digest": digest},
        )
    return planned


def _installer_argv(held: Installation, wheel: Path) -> list[str]:
    if held.method == "uv_tool":
        uv = shutil.which("uv")
        if uv is None:
            raise CliFailure(
                "AI_STP_PRECONDITION_FAILED",
                "uv is not on PATH; it owns this installation",
                next_actions=["update check --json"],
            )
        return [uv, "tool", "install", "--force", str(wheel), "--python", str(held.python)]
    if held.method == "pipx":
        pipx = shutil.which("pipx")
        if pipx is None:
            raise CliFailure(
                "AI_STP_PRECONDITION_FAILED",
                "pipx is not on PATH; it owns this installation",
                next_actions=["update check --json"],
            )
        return [pipx, "install", "--force", str(wheel)]
    if held.method == "pip_venv":
        scripts = "Scripts" if os.name == "nt" else "bin"
        python = held.prefix / scripts / ("python.exe" if os.name == "nt" else "python")
        if not python.is_file():
            python = held.python
        return [str(python), "-m", "pip", "install", "--force-reinstall", str(wheel)]
    raise CliFailure(
        "AI_STP_PRECONDITION_FAILED",
        held.reason,
        details={"method": held.method},
    )


def _run_installer(
    argv: Sequence[str],
    overrides: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = {
        key: value for key, value in os.environ.items() if key not in {"PYTHONPATH", "PYTHONHOME"}
    }
    for key, value in (overrides or {}).items():
        if key not in {"UV_TOOL_DIR", "UV_TOOL_BIN_DIR", "PIPX_HOME", "PIPX_BIN_DIR"}:
            raise CliFailure("AI_STP_VALIDATION_ERROR", "unknown installer environment binding")
        environment[key] = value
    return subprocess.run(
        list(argv),
        capture_output=True,
        text=True,
        env=environment,
        check=False,
        timeout=300,
    )


def _observe_version(executable: Path) -> str:
    environment = {
        key: value for key, value in os.environ.items() if key not in {"PYTHONPATH", "PYTHONHOME"}
    }
    try:
        completed = subprocess.run(
            [str(executable), "version", "--json"],
            capture_output=True,
            text=True,
            env=environment,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    if completed.returncode != 0:
        return "unknown"
    try:
        parsed: object = json.loads(completed.stdout)
    except ValueError:
        return "unknown"
    if not isinstance(parsed, dict):
        return "unknown"
    envelope = cast(dict[str, object], parsed)
    data = envelope.get("data")
    if not isinstance(data, dict):
        return "unknown"
    version = cast(dict[str, object], data).get("cli_version")
    return version if isinstance(version, str) and version else "unknown"


def _backup_user_data(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    by_path = {item.path: item.value for item in config.effective_config().values}
    registry_path = Path(str(by_path["registry.path"]))
    if registry_path.is_file() and not registry_path.is_symlink():
        from contextlib import closing

        with (
            closing(sqlite3.connect(registry_path)) as source,
            closing(sqlite3.connect(destination / registry_path.name)) as backup,
        ):
            source.backup(backup)
    config_file = config.config_path()
    if config_file.is_file() and not config_file.is_symlink():
        shutil.copy2(config_file, destination / "config.yaml")


def _preserve_current_wheel(
    held: Installation, client: ReleaseIndex, planned: CliSelfUpdatePlan
) -> None:
    previous = (
        store.stage_dir() / f"{DISTRIBUTION.replace('-', '_')}-{held.version}-py3-none-any.whl"
    )
    receipt = store.read_json(previous.with_suffix(".receipt.json"))
    if previous.is_file() and receipt is not None:
        index_mod.verify_wheel(
            previous,
            expected_digest=str(receipt["digest"]),
            expected_size=int(str(receipt["size"])),
        )
        return
    try:
        project = client.project(index_mod.PROJECT, timeout=index_mod.CHECK_TIMEOUT)
        simple = client.simple_files(index_mod.PROJECT, timeout=index_mod.CHECK_TIMEOUT)
        candidate = index_mod.select_candidate(
            project,
            simple,
            installed="0.0.0",
            channel="prerelease",
            python=(sys.version_info.major, sys.version_info.minor, sys.version_info.micro),
            requested=held.version,
        )
        client.download(candidate.wheel.url, previous, expected_size=candidate.wheel.size)
        index_mod.verify_wheel(
            previous,
            expected_digest=f"sha256:{candidate.wheel.sha256}",
            expected_size=candidate.wheel.size,
        )
        store.write_json(
            previous.with_suffix(".receipt.json"),
            {
                "digest": f"sha256:{candidate.wheel.sha256}",
                "size": candidate.wheel.size,
                "version": held.version,
            },
        )
    except CliFailure:
        return


def _rollback_wheel(version: str) -> Path | None:
    if not version:
        return None
    path = store.stage_dir() / f"{DISTRIBUTION.replace('-', '_')}-{version}-py3-none-any.whl"
    return path if path.is_file() and not path.is_symlink() else None


def _rollback_digest(planned: CliSelfUpdatePlan) -> str:
    body: dict[str, JsonValue] = {
        "operation": "rollback",
        "from": planned.target_version,
        "to": planned.source_version,
        "plan_digest": planned.plan_digest,
        "artifact": store.read_json(
            (
                store.stage_dir()
                / f"{DISTRIBUTION.replace('-', '_')}-{planned.source_version}-py3-none-any.whl"
            ).with_suffix(".receipt.json")
        ),
    }
    return digest_canonical(PLAN_DOMAIN, body)


def _fail_journal(planned: CliSelfUpdatePlan, reason: str) -> None:
    previous = store.read_json(store.journal_path()) or {}
    store.write_json(
        store.journal_path(),
        {
            **previous,
            "state": "recovery_required",
            "plan_digest": planned.plan_digest,
            "plan_id": planned.plan_id,
            "target_version": planned.target_version,
            "source_version": planned.source_version,
            "updated_at": format_timestamp(datetime.now(UTC)),
            "reason": reason,
        },
    )
