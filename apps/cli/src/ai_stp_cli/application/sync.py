"""Local reconciliation and replay-safe private registry transport."""

import sqlite3
from collections.abc import Mapping, Sequence
from contextlib import closing
from typing import cast

from ai_stp_cli import config, identity, toolchain
from ai_stp_cli.answer import Answer
from ai_stp_cli.application import cloud_auth
from ai_stp_cli.application.auth import endpoint
from ai_stp_cli.cloud import login as cloud_login
from ai_stp_cli.cloud import session
from ai_stp_cli.cloud import sync as cloud_sync
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import (
    consent,
    lifecycle,
    passports,
    revisions,
    sync_merge,
    sync_state,
    sync_versions,
)
from ai_stp_cli.local.database import configured_path, open_readonly, open_registry
from ai_stp_contracts.http import PAGE_SIZE_DEFAULT, PAGE_SIZE_MAX
from ai_stp_contracts.identity import DetectedHarness, DeviceSummary
from ai_stp_contracts.machine_help import SyncPreview, SyncPullView, SyncPushView
from ai_stp_contracts.sync import (
    ConsentTombstonePayload,
    ConsentUpsertPayload,
    SyncEventReceipt,
    SyncPullQuery,
    SyncPushRequest,
)
from ai_stp_foundation.canonical import JsonValue, canonize
from ai_stp_foundation.harnesses import HARNESS_IDS
from ai_stp_foundation.revisions import revision_id
from ai_stp_passports.envelope import seal_envelope


def _document(stored: revisions.StoredRevision) -> dict[str, JsonValue]:
    document = cast(dict[str, JsonValue], stored.envelope.model_dump(mode="json"))
    document.pop("revision_id", None)
    document.pop("parent_revision_ids", None)
    return document


def _report(connection: sqlite3.Connection, stable_id: str) -> SyncPreview:
    found = revisions.heads(connection, stable_id)
    if not found:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "that identifier has no local revision heads",
            details={"id": stable_id},
        )
    head_ids = sorted(item.revision_id for item in found)
    if len(found) == 1:
        behind = sync_state.unreachable_server_head(connection, stable_id)
        if behind is not None:
            # One local head and a refused push naming a head this device does
            # not hold. There is nothing to merge locally, so the honest answer
            # is the disagreement itself rather than `up_to_date`.
            return SyncPreview(
                stable_id=stable_id,
                state="conflict",
                head_revision_ids=head_ids,
                common_ancestor_revision_id=None,
                candidate_revision_id=None,
                server_head_revision_id=behind,
                affected_fields=[],
            )
        return SyncPreview(
            stable_id=stable_id,
            state="up_to_date",
            head_revision_ids=head_ids,
            common_ancestor_revision_id=found[0].revision_id,
            candidate_revision_id=found[0].revision_id,
            server_head_revision_id=None,
            affected_fields=[],
        )
    if len(found) != 2:
        return SyncPreview(
            stable_id=stable_id,
            state="manual_resolution",
            head_revision_ids=head_ids,
            common_ancestor_revision_id=None,
            candidate_revision_id=None,
            server_head_revision_id=None,
            affected_fields=["/"],
        )

    left, right = found
    if revisions.is_ancestor(connection, left.revision_id, right.revision_id):
        ancestor, descendant = left, right
    elif revisions.is_ancestor(connection, right.revision_id, left.revision_id):
        ancestor, descendant = right, left
    else:
        ancestor = descendant = None
    if ancestor is not None and descendant is not None:
        return SyncPreview(
            stable_id=stable_id,
            state="fast_forward",
            head_revision_ids=head_ids,
            common_ancestor_revision_id=ancestor.revision_id,
            candidate_revision_id=descendant.revision_id,
            server_head_revision_id=None,
            affected_fields=[],
        )

    base = revisions.common_ancestor(connection, left.revision_id, right.revision_id)
    if base is None:
        return SyncPreview(
            stable_id=stable_id,
            state="conflict",
            head_revision_ids=head_ids,
            common_ancestor_revision_id=None,
            candidate_revision_id=None,
            server_head_revision_id=None,
            affected_fields=["/"],
        )
    if left.envelope.kind != "developer":
        return SyncPreview(
            stable_id=stable_id,
            state="manual_resolution",
            head_revision_ids=head_ids,
            common_ancestor_revision_id=base.revision_id,
            candidate_revision_id=None,
            server_head_revision_id=None,
            affected_fields=["/"],
        )

    outcome = sync_merge.merge_documents(_document(base), _document(left), _document(right))
    if outcome.document is None:
        return SyncPreview(
            stable_id=stable_id,
            state="conflict",
            head_revision_ids=head_ids,
            common_ancestor_revision_id=base.revision_id,
            candidate_revision_id=None,
            server_head_revision_id=None,
            affected_fields=[item.path for item in outcome.conflicts],
        )

    candidate = dict(outcome.document)
    candidate["parent_revision_ids"] = cast(list[JsonValue], head_ids)
    sealed = seal_envelope(candidate)
    return SyncPreview(
        stable_id=stable_id,
        state="merge_ready",
        head_revision_ids=head_ids,
        common_ancestor_revision_id=base.revision_id,
        candidate_revision_id=sealed.revision_id,
        server_head_revision_id=None,
        affected_fields=[],
    )


def preview(parameters: Mapping[str, object]) -> Answer[SyncPreview]:
    """Preview local reconciliation without moving heads or contacting cloud."""
    stable_id = parameters.get("id")
    if stable_id is None:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a stable identifier is required",
            next_actions=["passport developer show --json"],
        )
    registry = configured_path()
    if not registry.exists():
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "the local registry does not exist yet",
            next_actions=["passport developer init --json"],
        )
    with closing(open_readonly(registry)) as connection:
        return Answer(_report(connection, str(stable_id)))


def merge(parameters: Mapping[str, object]) -> Answer[SyncPreview]:
    """Commit one mechanically clean developer-passport merge after confirmation."""
    _confirmed(parameters, "merge")
    stable_id = str(parameters.get("id") or "")
    if not stable_id:
        raise CliFailure("AI_STP_VALIDATION_ERROR", "--id is required")
    held_identity, _warning = identity.current()
    if held_identity is None or held_identity.state != "active":
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "an active local device identity is required to record a merge",
            next_actions=["device init --json"],
        )
    with closing(open_registry(configured_path())) as connection:
        commit_merge(connection, stable_id=stable_id, device_id=held_identity.device_id)
        return Answer(_report(connection, stable_id))


def commit_merge(
    connection: sqlite3.Connection, *, stable_id: str, device_id: str
) -> revisions.StoredRevision:
    """Commit a deterministic merge candidate without hiding field conflicts."""
    found = revisions.heads(connection, stable_id)
    if len(found) != 2:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED", "sync merge requires exactly two local heads"
        )
    left, right = found
    base = revisions.common_ancestor(connection, left.revision_id, right.revision_id)
    if base is None or left.envelope.kind != "developer":
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "only connected developer-passport heads can be merged mechanically",
        )
    outcome = sync_merge.merge_documents(_document(base), _document(left), _document(right))
    if outcome.document is None:
        raise CliFailure(
            "AI_STP_CONFLICT",
            "the two heads change the same fields and need an explicit passport edit",
            details={"fields": ",".join(item.path for item in outcome.conflicts)},
        )
    candidate = dict(outcome.document)
    candidate["parent_revision_ids"] = cast(
        list[JsonValue], sorted([left.revision_id, right.revision_id])
    )
    return revisions.commit(
        connection,
        candidate,
        device_id=device_id,
        operation_id="sync-merge",
    )


def _enabled() -> None:
    _catalog, enabled = config.catalog_and_sync_enabled()
    if not enabled:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "cloud synchronisation is disabled in local configuration",
            next_actions=["config set --set sync.enabled=true --json"],
        )


def _confirmed(parameters: Mapping[str, object], action: str) -> None:
    if parameters.get("confirm") is not True:
        raise CliFailure(
            "AI_STP_USER_DECISION_REQUIRED",
            "this action requires explicit confirmation",
            details={"action": f"sync {action}"},
            next_actions=[f"sync {action} --confirm --json"],
        )


def push(parameters: Mapping[str, object]) -> Answer[SyncPushView]:
    """Push one exact local head, replaying its durable event after uncertainty."""
    _enabled()
    _confirmed(parameters, "push")
    stable_id = str(parameters.get("id") or "")
    if not stable_id:
        raise CliFailure("AI_STP_VALIDATION_ERROR", "--id is required")
    held = cloud_auth.required("sync push")
    with closing(open_registry(configured_path())) as connection:
        stored = revisions.head(connection, stable_id)
        if stored is not None and stored.envelope.kind == "device":
            # REQ-911: the full device passport never leaves the device — what
            # pushes is its permitted summary, as the contract's own entity.
            return _push_device_summary(connection, held, stored)
        if stored is None and stable_id.startswith(("consent_", "request_")):
            # A consent entity, addressed by its wire id or its local record id.
            return _push_consent(connection, held, stable_id)
        if stored is None:
            raise CliFailure("AI_STP_NOT_FOUND", "that identifier has no local revision head")
        ordered: list[revisions.StoredRevision] = []
        visited: set[str] = set()

        def visit(item: revisions.StoredRevision) -> None:
            if item.revision_id in visited:
                return
            for parent_id in item.parents:
                parent = revisions.get(connection, parent_id)
                if parent is None:
                    raise CliFailure(
                        "AI_STP_VALIDATION_ERROR",
                        "the local revision graph has a missing parent",
                    )
                visit(parent)
            visited.add(item.revision_id)
            ordered.append(item)

        visit(stored)
        processed = 0
        pending: sync_state.Pending | None = None
        receipt: SyncEventReceipt | None = None
        final_event_id = ""
        final_remote_revision_id = ""
        for candidate in ordered:
            is_head = candidate.revision_id == stored.revision_id
            payload = sync_state.payload_for(connection, candidate, include_versions=is_head)
            while True:
                mapping = sync_state.mapping_for_local(
                    connection,
                    account_id=held.account_id,
                    local_revision_id=candidate.revision_id,
                    payload=payload if is_head else None,
                )
                if mapping is not None and mapping.state == "accepted":
                    processed += 1
                    final_event_id = mapping.event_id
                    final_remote_revision_id = mapping.remote_revision_id
                    receipt = SyncEventReceipt(
                        event_id=mapping.event_id,
                        state="accepted",
                        revision_id=mapping.remote_revision_id,
                        server_head_revision_id=mapping.remote_revision_id,
                        cursor=None,
                        conflict=None,
                        conflicting_entity_id=None,
                        error_code=None,
                    )
                    break
                pending = sync_state.prepare(
                    connection,
                    account_id=held.account_id,
                    device_id=held.device_id,
                    stored=candidate,
                    payload=payload,
                )
                receipt = _deliver(connection, held, pending)
                final_event_id = pending.request.event_id
                final_remote_revision_id = pending.request.revision_id
                processed += 1
                if receipt.state != "accepted" or canonize(
                    cast(JsonValue, pending.request.payload)
                ) == canonize(cast(JsonValue, payload)):
                    break
                # An older uncertain request completed. Only now may the new
                # version closure create its own event and idempotency key.
            if receipt.state != "accepted" and (is_head or receipt.state == "rejected"):
                # A 'conflict' or 'superseded' ancestor is already in the
                # server ledger — the merge built on it can still ship, and
                # the server re-checks the head transition when it does. Only
                # 'rejected' (the revision never landed) or a refused head
                # itself stops the walk.
                break
        if (
            lifecycle.entombed(connection, stable_id) is not None
            and receipt is not None
            and receipt.state == "accepted"
        ):
            pending = sync_state.prepare_tombstone(
                connection,
                account_id=held.account_id,
                device_id=held.device_id,
                stable_id=stable_id,
            )
            receipt = _deliver(connection, held, pending)
            final_event_id = pending.request.event_id
            final_remote_revision_id = pending.request.revision_id
            processed += 1
        assert receipt is not None and final_event_id and final_remote_revision_id
    return Answer(
        SyncPushView(
            stable_id=stable_id,
            processed_events=processed,
            local_revision_id=stored.revision_id,
            event_id=final_event_id,
            remote_revision_id=final_remote_revision_id,
            state=receipt.state,
            server_head_revision_id=receipt.server_head_revision_id,
            conflict_fields=[] if receipt.conflict is None else receipt.conflict.affected_fields,
            conflicting_entity_id=receipt.conflicting_entity_id,
        )
    )


def pull(parameters: Mapping[str, object]) -> Answer[SyncPullView]:
    """Pull and atomically apply one bounded ordered server page."""
    _enabled()
    _confirmed(parameters, "pull")
    try:
        page_size = int(str(parameters.get("page-size") or PAGE_SIZE_DEFAULT))
    except (TypeError, ValueError) as error:
        raise CliFailure("AI_STP_VALIDATION_ERROR", "--page-size must be an integer") from error
    if not 1 <= page_size <= PAGE_SIZE_MAX:
        raise CliFailure("AI_STP_VALIDATION_ERROR", "--page-size is outside the contract limit")
    held = cloud_auth.required("sync pull")
    with closing(open_registry(configured_path())) as connection:
        current = sync_state.cursor(connection, held.account_id)
        response = cloud_sync.pull(
            endpoint(),
            held.access_token,
            SyncPullQuery(cursor=current, page_size=page_size),
        )
        applied, replayed, skipped = sync_state.apply_page(
            connection,
            account_id=held.account_id,
            response=response,
            at=passports.moment(),
            skip_event_ids=_skipped_event_ids(parameters),
        )
        pending_count, pending_versions = sync_versions.pending(connection, account=held.account_id)
    return Answer(
        SyncPullView(
            state="partial"
            if pending_count
            else (
                "up_to_date"
                if not response.items or response.page.next_cursor is None
                else "pulling"
            ),
            pending_version_count=pending_count,
            pending_versions=pending_versions,
            received=len(response.items),
            applied=applied,
            replayed=replayed,
            skipped=skipped,
            next_cursor=response.page.next_cursor,
        )
    )


def _skipped_event_ids(parameters: Mapping[str, object]) -> frozenset[str]:
    """Exact event ids the caller is abandoning, and nothing looser.

    A refused event stops this account's pulls on every device, and no page
    size gets past it. Recovering means walking past one — which is abandoning
    a revision, so the caller names it. The refusal answers the id; this takes
    that id back and nothing else.
    """
    given = parameters.get("skip-event")
    # A repeatable option arrives from the parser as a tuple, empty when it was
    # not given at all — `None` is only what a caller passing this in code
    # leaves out. Reading an empty tuple as one value produced the id `"()"`.
    if isinstance(given, list | tuple):
        values: tuple[object, ...] = tuple(cast(Sequence[object], given))
    elif given is None:
        values = ()
    else:
        values = (given,)
    if not values:
        return frozenset()
    ids = frozenset(str(item) for item in values)
    if len(ids) > 64:
        raise CliFailure("AI_STP_VALIDATION_ERROR", "--skip-event is bounded at 64 ids")
    for value in sorted(ids):
        if not value.startswith("event_"):
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                "--skip-event takes the exact event id a refused pull named",
                details={"given": value},
            )
    return ids


def _deliver(
    connection: sqlite3.Connection, held: session.Session, pending: sync_state.Pending
) -> SyncEventReceipt:
    """Send one prepared event when no durable receipt already exists.

    The receipt is read from the outbox first — a retry after a lost response
    replays the stored answer instead of sending the same event twice.
    """
    receipt = sync_state.saved_receipt(
        connection, account_id=held.account_id, event_id=pending.request.event_id
    )
    if receipt is not None:
        return receipt
    response = cloud_sync.push(
        endpoint(), held.access_token, SyncPushRequest(events=[pending.request])
    )
    receipt = response.receipts[0]
    if receipt.event_id != pending.request.event_id:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the sync receipt does not match the sent event",
        )
    sync_state.record_receipt(connection, account_id=held.account_id, receipt=receipt)
    return receipt


def _push_view(
    stable_id: str,
    local_revision_id: str,
    pending: sync_state.Pending,
    receipt: SyncEventReceipt,
    processed: int = 1,
) -> Answer[SyncPushView]:
    return Answer(
        SyncPushView(
            stable_id=stable_id,
            processed_events=processed,
            local_revision_id=local_revision_id,
            event_id=pending.request.event_id,
            remote_revision_id=pending.request.revision_id,
            state=receipt.state,
            server_head_revision_id=receipt.server_head_revision_id,
            conflict_fields=[] if receipt.conflict is None else receipt.conflict.affected_fields,
            conflicting_entity_id=receipt.conflicting_entity_id,
        )
    )


def _push_device_summary(
    connection: sqlite3.Connection, held: session.Session, stored: revisions.StoredRevision
) -> Answer[SyncPushView]:
    """Push the device passport's permitted summary, never the passport itself.

    REQ-911 and `device-passport.md` close the summary to five facts plus the
    refresh time, and the server binds the entity to the session device. An
    environment this build cannot summarise (`unknown` os or architecture) is
    a refusal, not a guessed value — the same rule the passport applies.
    """
    facts = cast(
        dict[str, JsonValue],
        cast(dict[str, JsonValue], stored.envelope.model_dump(mode="json")).get("facts", {}),
    )

    def fact(name: str) -> JsonValue:
        entry = facts.get(name)
        return entry.get("value") if isinstance(entry, dict) else None

    detected: list[DetectedHarness] = []
    installations = fact("harness_installations")
    if isinstance(installations, list):
        for raw in installations:
            if not isinstance(raw, dict):
                continue
            harness_id = raw.get("harness_id")
            versions = raw.get("installations")
            version = None
            if isinstance(versions, list) and versions:
                first = versions[0]
                if isinstance(first, dict) and isinstance(first.get("version"), str):
                    version = first["version"]
            if isinstance(harness_id, str) and harness_id in HARNESS_IDS and version is not None:
                detected.append(DetectedHarness(harness_id=harness_id, version=version))  # pyright: ignore[reportArgumentType]
    os_name, arch = fact("operating_system"), fact("architecture")
    if os_name not in ("linux", "macos", "windows") or arch not in ("x86_64", "arm64"):
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the device environment cannot be summarised for sync",
            details={"reason": "an observed value falls outside the closed summary set"},
        )
    try:
        summary = DeviceSummary(
            display_name=cloud_login.device_display_name(),
            operating_system=os_name,
            architecture=arch,
            detected_harnesses=detected[:16],
            toolchain_profile_version=(
                f"{toolchain.load().profile}/{toolchain.MANIFEST_SCHEMA_VERSION}"
            ),
            summary_updated_at=stored.created_at,
        )
    except ValueError as error:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the device environment cannot be summarised for sync",
            details={"reason": "an observed value falls outside the closed summary set"},
        ) from error
    payload = cast(dict[str, object], summary.model_dump(mode="json"))
    pending = sync_state.prepare_event(
        connection,
        account_id=held.account_id,
        device_id=held.device_id,
        entity_id=held.device_id,
        entity_kind="device_summary",
        operation="upsert",
        payload=payload,
        created_at=stored.created_at,
        local_revision_id=stored.revision_id,
    )
    receipt = _deliver(connection, held, pending)
    return _push_view(stored.stable_id, stored.revision_id, pending, receipt)


def _push_consent(
    connection: sqlite3.Connection, held: session.Session, entity_id: str
) -> Answer[SyncPushView]:
    """Push one consent record's current state, or its tombstone once revoked.

    The wire entity is `consent_<digest(scope, target)>` — the same identifier
    on every device, because the consent is a property of the account and its
    target, not of the installation that recorded it first.
    """
    record = None
    for item in consent.all_records(connection):
        if item.consent_id == entity_id or consent.entity_id(item.scope, item.target) == entity_id:
            record = item
            break
    if record is None:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "no consent record is known by that identifier",
            next_actions=["consent list --json"],
        )
    entity = consent.entity_id(record.scope, record.target)
    if record.active:
        document = ConsentUpsertPayload(
            scope=record.scope,  # pyright: ignore[reportArgumentType]
            target=record.target,
            fingerprint=record.fingerprint,
            observed=list(record.observed),
            decided_by=record.decided_by,
            origin=record.origin,
            created_at=record.created_at,
        )
        operation = "upsert"
        at = record.created_at
    else:
        document = ConsentTombstonePayload(
            scope=record.scope,  # pyright: ignore[reportArgumentType]
            target=record.target,
            revoked_at=record.revoked_at,
        )
        operation = "tombstone"
        at = str(record.revoked_at)
    payload = cast(dict[str, object], document.model_dump(mode="json"))
    pending = sync_state.prepare_event(
        connection,
        account_id=held.account_id,
        device_id=held.device_id,
        entity_id=entity,
        entity_kind="unverified_consent",
        operation=operation,
        payload=payload,
        created_at=at,
    )
    receipt = _deliver(connection, held, pending)
    # The record is not a registry revision, but its exact pushed state still
    # has a content address, and that is what the view reports.
    local_id = revision_id(cast(JsonValue, payload))
    return _push_view(entity, local_id, pending, receipt)
