#!/usr/bin/env python3
"""Publish the first-party launch corpus through the ordinary authenticated pipeline.

Review stores the exact corpus digest, object coordinates, plan IDs/hashes and
blockers. Apply binds exact bytes and confirms each saved plan. The tool never
writes the catalog and never changes validation policy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Final, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ai_stp_cli.cloud import catalog, login, publication
from ai_stp_cli.cloud.client import Endpoint
from ai_stp_cli.cloud.session import Session
from ai_stp_cli.commands import auth, cloud_auth
from ai_stp_cli.errors import CliFailure
from ai_stp_contracts.first_party import OWNER_ID, FirstPartyVersion
from ai_stp_contracts.first_party import versions as first_party_versions
from ai_stp_contracts.publication import (
    PublicationConfirmRequest,
    PublicationPlanCreateRequest,
    PublicationPlanResponse,
)
from ai_stp_foundation.canonical import JsonValue, canonize
from ai_stp_passports.versions import SetupVersionPassport

IN_PROGRESS_STATES = frozenset({"draft", "ready", "validating", "publish_planned"})
PUBLISHED = "published"
BLOCKED = "blocked"
PENDING = "pending"
TERMINAL_FAILURES = frozenset({"failed", "cancelled", "stale"})
DEFAULT_POLLS = 180


@dataclass(frozen=True)
class Pin:
    stable_id: str
    version: str
    passport_digest: str


@dataclass(frozen=True)
class LaunchObject:
    kind: Literal["component", "setup"]
    stable_id: str
    version: str
    content_digest: str
    passport_digest: str
    passport: dict[str, object]
    artifact: bytes
    component_pins: tuple[Pin, ...]


class PinRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    stable_id: str
    version: str
    passport_digest: str


class ObjectRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["component", "setup"]
    stable_id: str
    version: str
    content_digest: str
    passport_digest: str
    component_pins: list[PinRecord]
    create_idempotency_key: str
    confirm_idempotency_key: str
    plan_id: str | None = None
    plan_hash: str | None = None
    state: str = PENDING
    blocker: str | None = None
    #: Which mandatory checks the platform did not pass, and what it said about
    #: each. `blocker` names the plan's state; this names the cause, and the two
    #: are not the same sentence. Without it a refusal reads "the platform
    #: reported a failure" and the next step is guesswork against a worker log.
    refused_by: list[str] = Field(default_factory=list)


class BatchState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    corpus_digest: str
    account_id: str
    device_id: str
    objects: list[ObjectRecord]


def launch_objects(versions: Sequence[FirstPartyVersion] | None = None) -> tuple[LaunchObject, ...]:
    """Project the immutable first-party snapshot into publication coordinates."""
    corpus = first_party_versions() if versions is None else versions
    objects: list[LaunchObject] = []
    for item in corpus:
        pins: tuple[Pin, ...] = ()
        if item.kind == "setup":
            if not isinstance(item.passport, SetupVersionPassport):
                raise CliFailure(
                    "AI_STP_VALIDATION_ERROR",
                    "a first-party setup is missing exact component pins",
                )
            pins = tuple(
                Pin(
                    stable_id=ref.stable_id,
                    version=ref.version,
                    passport_digest=ref.passport_digest,
                )
                for ref in item.passport.components
            )
        objects.append(
            LaunchObject(
                kind=item.kind,
                stable_id=item.passport.stable_id,
                version=item.passport.version,
                content_digest=item.passport.artifact.digest,
                passport_digest=item.passport_digest,
                passport=cast(dict[str, object], item.passport.model_dump(mode="json")),
                artifact=item.artifact,
                component_pins=pins,
            )
        )
    return tuple(objects)


def publication_order(objects: Sequence[LaunchObject]) -> tuple[LaunchObject, ...]:
    """Components first, then setups, preserving relative corpus order."""
    components = tuple(item for item in objects if item.kind == "component")
    setups = tuple(item for item in objects if item.kind == "setup")
    return components + setups


def corpus_digest(objects: Sequence[LaunchObject]) -> str:
    payload = canonize(
        cast(
            JsonValue,
            {
                "schema_version": 1,
                "kind": "first_party_launch_corpus",
                "objects": [
                    {
                        "kind": item.kind,
                        "stable_id": item.stable_id,
                        "version": item.version,
                        "passport_digest": item.passport_digest,
                        "content_digest": item.content_digest,
                    }
                    for item in objects
                ],
            },
        )
    )
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def snapshot(objects: Sequence[LaunchObject] | None = None) -> tuple[str, tuple[LaunchObject, ...]]:
    ordered = publication_order(launch_objects() if objects is None else objects)
    _require_closed_pins(ordered)
    return corpus_digest(ordered), ordered


def _require_closed_pins(objects: Sequence[LaunchObject]) -> None:
    known = {
        (item.stable_id, item.version, item.passport_digest)
        for item in objects
        if item.kind == "component"
    }
    for item in objects:
        for pin in item.component_pins:
            if (pin.stable_id, pin.version, pin.passport_digest) not in known:
                raise CliFailure(
                    "AI_STP_PRECONDITION_FAILED",
                    "a setup pins a component that is not in the launch corpus",
                    details={"stable_id": item.stable_id},
                )


def _require_owner(held: Session) -> None:
    if held.account_id != OWNER_ID:
        raise CliFailure(
            "AI_STP_PERMISSION_DENIED",
            "first-party launch publication requires the platform owner account",
        )


def _load_state(path: Path) -> BatchState | None:
    if not path.is_file():
        return None
    try:
        return BatchState.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as error:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the launch publication state file is not a valid batch snapshot",
            details={"exception": type(error).__name__},
        ) from error


def _save_state(path: Path, state: BatchState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (state.model_dump_json(indent=2) + "\n").encode("utf-8")
    scratch = path.with_name(path.name + ".tmp")
    scratch.write_bytes(payload)
    scratch.replace(path)


def _index_objects(objects: Sequence[LaunchObject]) -> dict[tuple[str, str, str], LaunchObject]:
    return {(item.stable_id, item.version, item.content_digest): item for item in objects}


def _pins_published(state: BatchState, pins: Sequence[PinRecord]) -> bool:
    published = {
        (item.stable_id, item.version, item.passport_digest)
        for item in state.objects
        if item.state == PUBLISHED
    }
    return all((pin.stable_id, pin.version, pin.passport_digest) in published for pin in pins)


def _published_passport_digest(
    endpoint: Endpoint, kind: str, stable_id: str, version: str
) -> str | None:
    """Return the live catalog digest for this X.Y, or None if it is unpublished."""
    try:
        view = catalog.version(
            endpoint, cast(Literal["component", "setup"], kind), stable_id, version
        )
    except CliFailure as error:
        if error.code == "AI_STP_NOT_FOUND":
            return None
        raise
    return view.passport_digest


def _record_for(state: BatchState, item: LaunchObject) -> ObjectRecord:
    for record in state.objects:
        if (
            record.stable_id == item.stable_id
            and record.version == item.version
            and record.content_digest == item.content_digest
        ):
            return record
    raise CliFailure(
        "AI_STP_PRECONDITION_FAILED",
        "the batch snapshot is missing a reviewed corpus object",
        details={"stable_id": item.stable_id},
    )


#: Results that did not stand in the way. The field is called `refused_by`, so
#: it holds what refused. `passed` never does; neither does `warning`, which is
#: a finding the policy accepted, nor `not_applicable` and `skipped`, which say
#: the check had nothing to look at. What is left — `failed`, `degraded`,
#: `not_run`, `running`, `expired` — is every way a mandatory check blocks a
#: publication, including the three that mean it never reached a verdict.
_UNREMARKABLE: Final[frozenset[str]] = frozenset({"passed", "warning", "not_applicable", "skipped"})


def _refusals(plan: PublicationPlanResponse) -> list[str]:
    """Name the mandatory checks that stood in the way, with their reasons.

    The platform already explains itself: every binding carries `result` and,
    since `0026_evidence_reason`, a short `reason` that names rules rather than
    quoting what was scanned. Reading `state` alone throws that away, which is
    how a corpus refusal spent a week looking like a mystery — the answer was on
    the wire the whole time and nothing wrote it down.

    Only the bindings that did not pass are kept: a list of thirteen "passed" is
    noise in a state file somebody opens because something went wrong.
    """
    refused: list[str] = []
    for binding in plan.evidence:
        if binding.result in _UNREMARKABLE:
            continue
        reason = getattr(binding, "reason", None)
        refused.append(f"{binding.check_id}: {binding.result}" + (f" — {reason}" if reason else ""))
    return refused


def _apply_plan(record: ObjectRecord, plan: PublicationPlanResponse) -> None:
    record.plan_id = plan.plan_id
    record.plan_hash = plan.plan_hash
    record.state = plan.state
    record.refused_by = _refusals(plan)
    if plan.state == PUBLISHED:
        record.blocker = None


def _plan_create(
    endpoint: Endpoint,
    held: Session,
    item: LaunchObject,
    record: ObjectRecord,
) -> None:
    request = PublicationPlanCreateRequest(
        object_kind=item.kind,
        stable_id=item.stable_id,
        version=item.version,
        content_digest=item.content_digest,
        passport=item.passport,
        attestations=[],
        idempotency_key=record.create_idempotency_key,
        device_id=held.device_id,
    )
    plan = publication.create(endpoint, held.access_token, request)
    _apply_plan(record, plan)


def _replan_terminal(state: BatchState) -> list[str]:
    """Give every terminally failed record a fresh attempt, and say which.

    A plan is created under `create_idempotency_key`, so re-planning a record
    returns the **same** plan the server already has — including a failed one.
    That is the key working correctly: it binds one attempt. It also means a
    plan that failed for a reason outside the object cannot be retried at all,
    and the reason this exists is exactly such a case. A deploy rolled the
    service under a running publication and four plans were lost in flight;
    the objects were fine and unpublishable.

    So the recovery is a new attempt, not a retry: a fresh key, no plan, back to
    pending. It is an explicit flag rather than automatic because
    `TERMINAL_FAILURES` also covers plans that failed on their merits, and
    re-planning those blindly would turn a refusal into a loop. The operator
    says which situation this is; the tool does not guess.
    """
    reset: list[str] = []
    for record in state.objects:
        if record.state not in TERMINAL_FAILURES:
            continue
        record.create_idempotency_key = login.new_idempotency_key()
        record.confirm_idempotency_key = login.new_idempotency_key()
        record.plan_id = None
        record.plan_hash = None
        record.state = PENDING
        record.blocker = None
        record.refused_by = []
        reset.append(f"{record.kind} {record.stable_id} {record.version}")
    return reset


def review(
    *,
    state_path: Path,
    endpoint: Endpoint,
    held: Session,
    objects: Sequence[LaunchObject] | None = None,
    pause: Callable[[float], None] = time.sleep,
    replan_failed: bool = False,
) -> BatchState:
    """Create exact plans for the ordered corpus and persist resume coordinates."""
    _require_owner(held)
    digest, ordered = snapshot(objects)
    existing = _load_state(state_path)
    if existing is not None:
        if existing.corpus_digest != digest:
            raise CliFailure(
                "AI_STP_CONFLICT",
                "the stored batch snapshot belongs to another corpus digest",
                details={"expected": existing.corpus_digest},
            )
        if existing.account_id != held.account_id or existing.device_id != held.device_id:
            raise CliFailure(
                "AI_STP_PRECONDITION_FAILED",
                "the stored batch snapshot belongs to another owner or device",
            )
        state = existing
    else:
        state = BatchState(
            corpus_digest=digest,
            account_id=held.account_id,
            device_id=held.device_id,
            objects=[
                ObjectRecord(
                    kind=item.kind,
                    stable_id=item.stable_id,
                    version=item.version,
                    content_digest=item.content_digest,
                    passport_digest=item.passport_digest,
                    component_pins=[
                        PinRecord(
                            stable_id=pin.stable_id,
                            version=pin.version,
                            passport_digest=pin.passport_digest,
                        )
                        for pin in item.component_pins
                    ],
                    create_idempotency_key=login.new_idempotency_key(),
                    confirm_idempotency_key=login.new_idempotency_key(),
                )
                for item in ordered
            ],
        )
    if replan_failed:
        _replan_terminal(state)
        _save_state(state_path, state)
    by_object = _index_objects(ordered)
    for record in state.objects:
        item = by_object[(record.stable_id, record.version, record.content_digest)]
        if record.plan_id is not None and record.blocker is None:
            continue
        try:
            _retrying(partial(_plan_create, endpoint, held, item, record), pause=pause)
            record.blocker = None
        except CliFailure as error:
            record.blocker = error.message
            if record.state not in TERMINAL_FAILURES and record.state != PUBLISHED:
                record.state = BLOCKED
        _save_state(state_path, state)
    return state


RETRY_PAUSES: Final[tuple[float, ...]] = (2.0, 5.0, 15.0, 30.0, 60.0)


def _retrying[T](work: Callable[[], T], *, pause: Callable[[float], None]) -> T:
    """Run `work`, waiting out a rejection that says it is worth retrying.

    Every `CliFailure` used to become a blocker, and a blocker is a terminal
    verdict a human reads as "this object cannot be published". A rate-limit
    rejection is not that: `AI_STP_RATE_LIMITED` carries `retryable: true`, and
    the honest response to it is to wait rather than to record a defeat.

    This bit on 2026-08-29 when the reseed ran against the dual-window limiter
    that shipped the same day. Publishing forty objects, each with a plan, a
    bind, a confirm and a poll loop, exhausts a hundred-request window quickly;
    fourteen went out and five were recorded `blocked` with "request rate limit
    exceeded". Nothing was wrong with those five, and nothing about them would
    have been different a minute later.

    Waits are bounded and escalating rather than unlimited: the caller's own
    failure is still reached when the rejection is not transient, so a genuinely
    unavailable platform fails as before instead of spinning.
    """
    last: CliFailure | None = None
    for wait in (*RETRY_PAUSES, None):
        try:
            return work()
        except CliFailure as error:
            if not error.retryable or wait is None:
                raise
            last = error
            pause(wait)
    assert last is not None
    raise last


def _wait_terminal(
    endpoint: Endpoint,
    held: Session,
    record: ObjectRecord,
    *,
    pause: Callable[[float], None],
    max_polls: int,
) -> PublicationPlanResponse:
    if record.plan_id is None:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "a reviewed object has no publication plan to poll",
            details={"stable_id": record.stable_id},
        )
    plan: PublicationPlanResponse | None = None
    for _ in range(max(1, max_polls)):
        plan = _retrying(
            partial(publication.status, endpoint, held.access_token, record.plan_id),
            pause=pause,
        )
        _apply_plan(record, plan)
        if plan.state == PUBLISHED or plan.state in TERMINAL_FAILURES:
            return plan
        if plan.state not in IN_PROGRESS_STATES:
            record.blocker = f"publication plan entered unexpected state {plan.state}"
            record.state = BLOCKED
            return plan
        pause(1.0)
    record.blocker = "publication did not reach a terminal state"
    record.state = BLOCKED
    assert plan is not None
    return plan


def apply(
    *,
    state_path: Path,
    endpoint: Endpoint,
    held: Session,
    corpus_digest_value: str,
    confirm: bool,
    objects: Sequence[LaunchObject] | None = None,
    pause: Callable[[float], None] = time.sleep,
    max_polls: int = DEFAULT_POLLS,
    published_digest: Callable[[str, str, str], str | None] | None = None,
) -> BatchState:
    """Bind exact bytes and confirm each reviewed plan, components before setups."""
    if not confirm:
        raise CliFailure(
            "AI_STP_USER_DECISION_REQUIRED",
            "apply requires explicit confirmation of the exact reviewed corpus digest",
            details={"corpus_digest": corpus_digest_value},
            next_actions=[
                "first_party_launch_publication.py apply "
                f"--state {state_path} --corpus-digest {corpus_digest_value} --confirm"
            ],
        )
    _require_owner(held)
    digest, ordered = snapshot(objects)
    if digest != corpus_digest_value:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the confirmed corpus digest does not match the current first-party snapshot",
            details={"expected": digest},
        )
    state = _load_state(state_path)
    if state is None:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "apply requires a reviewed batch snapshot",
            next_actions=[f"first_party_launch_publication.py review --state {state_path}"],
        )
    if state.corpus_digest != corpus_digest_value:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "apply requires the exact reviewed corpus digest",
            details={"expected": state.corpus_digest},
        )
    if state.account_id != held.account_id or state.device_id != held.device_id:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the stored batch snapshot belongs to another owner or device",
        )

    def lookup(kind: str, stable_id: str, version: str) -> str | None:
        if published_digest is not None:
            return published_digest(kind, stable_id, version)
        return _published_passport_digest(endpoint, kind, stable_id, version)

    for item in ordered:
        record = _record_for(state, item)
        if record.state == PUBLISHED:
            continue
        try:
            live_digest = _retrying(
                partial(lookup, item.kind, item.stable_id, item.version), pause=pause
            )
        except CliFailure as error:
            record.blocker = error.message
            if record.state not in TERMINAL_FAILURES:
                record.state = BLOCKED
            _save_state(state_path, state)
            continue
        if live_digest is not None:
            if live_digest == item.passport_digest:
                record.state = PUBLISHED
                record.blocker = None
            else:
                record.blocker = "version already published with different digest"
                record.state = BLOCKED
            _save_state(state_path, state)
            continue
        if record.kind == "setup" and not _pins_published(state, record.component_pins):
            record.blocker = "exact component pins are not published"
            record.state = BLOCKED
            _save_state(state_path, state)
            continue
        try:
            if record.plan_id is None:
                _retrying(partial(_plan_create, endpoint, held, item, record), pause=pause)
            current = _retrying(
                partial(publication.status, endpoint, held.access_token, cast(str, record.plan_id)),
                pause=pause,
            )
            _apply_plan(record, current)
            if current.state == PUBLISHED:
                record.blocker = None
                _save_state(state_path, state)
                continue
            if current.state in TERMINAL_FAILURES:
                record.blocker = f"publication plan is {current.state}"
                _save_state(state_path, state)
                continue
            if current.state in {"ready", "draft"}:
                _retrying(
                    partial(
                        publication.bind,
                        endpoint,
                        held.access_token,
                        current.plan_id,
                        item.artifact,
                        pause=pause,
                    ),
                    pause=pause,
                )
                if record.plan_hash is None:
                    raise CliFailure(
                        "AI_STP_PRECONDITION_FAILED",
                        "a reviewed plan is missing its exact hash",
                        details={"stable_id": record.stable_id},
                    )
                confirmed = _retrying(
                    partial(
                        publication.confirm,
                        endpoint,
                        held.access_token,
                        current.plan_id,
                        PublicationConfirmRequest(
                            plan_hash=record.plan_hash,
                            confirmed=True,
                            idempotency_key=record.confirm_idempotency_key,
                        ),
                    ),
                    pause=pause,
                )
                _apply_plan(record, confirmed)
            finished = _wait_terminal(endpoint, held, record, pause=pause, max_polls=max_polls)
            if finished.state != PUBLISHED:
                record.blocker = record.blocker or f"publication plan is {finished.state}"
                if finished.state in TERMINAL_FAILURES:
                    record.state = finished.state
        except CliFailure as error:
            record.blocker = error.message
            if record.state not in TERMINAL_FAILURES and record.state != PUBLISHED:
                record.state = BLOCKED
        _save_state(state_path, state)
    return state


def refresh_status(
    *,
    state_path: Path,
    endpoint: Endpoint,
    held: Session,
) -> BatchState:
    _require_owner(held)
    state = _load_state(state_path)
    if state is None:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "status requires a reviewed batch snapshot",
        )
    if state.account_id != held.account_id or state.device_id != held.device_id:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the stored batch snapshot belongs to another owner or device",
        )
    for record in state.objects:
        if record.plan_id is None:
            continue
        plan = publication.status(endpoint, held.access_token, record.plan_id)
        _apply_plan(record, plan)
    _save_state(state_path, state)
    return state


def report(state: BatchState) -> dict[str, object]:
    published = sum(1 for item in state.objects if item.state == PUBLISHED)
    blocked = [item for item in state.objects if item.blocker]
    return {
        "corpus_digest": state.corpus_digest,
        "object_count": len(state.objects),
        "component_count": sum(1 for item in state.objects if item.kind == "component"),
        "setup_count": sum(1 for item in state.objects if item.kind == "setup"),
        "published": published,
        "blocked": len(blocked),
        "blockers": [
            {
                "kind": item.kind,
                "stable_id": item.stable_id,
                "version": item.version,
                "state": item.state,
                "blocker": item.blocker,
                # What the platform said, beside what the tool concluded. A
                # report that names only the latter sends the reader to a
                # worker log for something already on the wire.
                "refused_by": item.refused_by,
            }
            for item in blocked
        ],
        "objects": [
            {
                "kind": item.kind,
                "stable_id": item.stable_id,
                "version": item.version,
                "content_digest": item.content_digest,
                "plan_id": item.plan_id,
                "plan_hash": item.plan_hash,
                "state": item.state,
                "blocker": item.blocker,
            }
            for item in state.objects
        ],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    review_cmd = sub.add_parser("review")
    review_cmd.add_argument("--state", required=True, type=Path)
    review_cmd.add_argument(
        "--replan-failed",
        action="store_true",
        help=(
            "give every terminally failed record a fresh idempotency key and plan. "
            "For a plan lost to something outside the object — a service restart "
            "under a running publication — not for one the platform refused."
        ),
    )
    apply_cmd = sub.add_parser("apply")
    apply_cmd.add_argument("--state", required=True, type=Path)
    apply_cmd.add_argument("--corpus-digest", required=True)
    apply_cmd.add_argument("--confirm", action="store_true")
    apply_cmd.add_argument("--max-polls", type=int, default=DEFAULT_POLLS)
    status_cmd = sub.add_parser("status")
    status_cmd.add_argument("--state", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        held = cloud_auth.required("first-party launch publication")
        endpoint = auth.endpoint()
        if args.command == "review":
            state = review(
                state_path=args.state,
                endpoint=endpoint,
                held=held,
                replan_failed=bool(args.replan_failed),
            )
        elif args.command == "apply":
            state = apply(
                state_path=args.state,
                endpoint=endpoint,
                held=held,
                corpus_digest_value=args.corpus_digest,
                confirm=bool(args.confirm),
                max_polls=max(1, int(args.max_polls)),
            )
        else:
            state = refresh_status(state_path=args.state, endpoint=endpoint, held=held)
    except CliFailure as error:
        print(f"first_party_launch_publication.py: ERROR: {error.code}: {error}", file=sys.stderr)
        return error.exit_code
    print(json.dumps(report(state), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
