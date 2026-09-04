"""Local reconciliation and replay-safe private registry transport."""

import sqlite3
from collections.abc import Mapping, Sequence
from contextlib import closing
from typing import cast

from ai_stp_cli import config, identity
from ai_stp_cli.answer import Answer
from ai_stp_cli.cloud import sync as cloud_sync
from ai_stp_cli.commands import cloud_auth
from ai_stp_cli.commands.auth import endpoint
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import lifecycle, passports, revisions, sync_merge, sync_state
from ai_stp_cli.local.database import configured_path, open_readonly, open_registry
from ai_stp_contracts.http import PAGE_SIZE_DEFAULT, PAGE_SIZE_MAX
from ai_stp_contracts.machine_help import SyncPreview, SyncPullView, SyncPushView
from ai_stp_contracts.sync import SyncEventReceipt, SyncPullQuery, SyncPushRequest
from ai_stp_foundation.canonical import JsonValue
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
            mapping = sync_state.mapping_for_local(
                connection,
                account_id=held.account_id,
                local_revision_id=candidate.revision_id,
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
                continue
            pending = sync_state.prepare(
                connection,
                account_id=held.account_id,
                device_id=held.device_id,
                stored=candidate,
            )
            receipt = sync_state.saved_receipt(
                connection, account_id=held.account_id, event_id=pending.request.event_id
            )
            if receipt is None:
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
            final_event_id = pending.request.event_id
            final_remote_revision_id = pending.request.revision_id
            processed += 1
            if receipt.state in {"rejected", "superseded"}:
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
            receipt = sync_state.saved_receipt(
                connection, account_id=held.account_id, event_id=pending.request.event_id
            )
            if receipt is None:
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
    return Answer(
        SyncPullView(
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
