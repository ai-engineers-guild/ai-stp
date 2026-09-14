"""Local cache for explicit cloud project links and sync decisions."""

import sqlite3
from dataclasses import dataclass
from typing import Final

from ai_stp_contracts.context import ProjectLinkResponse, ProjectSyncPlanResponse
from ai_stp_foundation.ids import is_valid_id


def cache_link(connection: sqlite3.Connection, link: ProjectLinkResponse) -> None:
    """Cache the server result; the server remains the authority."""
    if not is_valid_id(link.local_project_id, "project"):
        raise ValueError("local project id is not valid")
    connection.execute(
        """
        INSERT INTO project_link (
            local_project_id, link_id, plan_id, plan_digest, organization_id, remote_project_id,
            provider_project_id,
            state, local_revision, remote_revision, provider_revision, link_revision, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(local_project_id) DO UPDATE SET
            link_id = excluded.link_id,
            plan_id = excluded.plan_id,
            plan_digest = excluded.plan_digest,
            organization_id = excluded.organization_id,
            remote_project_id = excluded.remote_project_id,
            provider_project_id = excluded.provider_project_id,
            state = excluded.state,
            local_revision = excluded.local_revision,
            remote_revision = excluded.remote_revision,
            provider_revision = excluded.provider_revision,
            link_revision = excluded.link_revision,
            updated_at = excluded.updated_at
        """,
        (
            link.local_project_id,
            link.link_id,
            link.plan_id,
            link.plan_digest,
            link.organization_id,
            link.remote_project_id,
            link.provider_project_id,
            link.state,
            link.local_revision,
            link.remote_revision,
            link.provider_revision,
            link.revision,
            link.updated_at,
        ),
    )


def cache_sync_plan(
    connection: sqlite3.Connection,
    *,
    local_project_id: str,
    plan: ProjectSyncPlanResponse,
    idempotency_key: str,
    created_at: str,
) -> None:
    """Persist the last server decision for recovery and inspection."""
    if not is_valid_id(local_project_id, "project"):
        raise ValueError("local project id is not valid")
    connection.execute(
        """
        INSERT INTO project_sync_plan (
            plan_id, local_project_id, link_id, state, action, expected_link_revision,
            local_revision, remote_revision, provider_revision, conflict_code,
            common_ancestor_revision, plan_digest, expires_at, idempotency_key, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(local_project_id, idempotency_key) DO UPDATE SET
            plan_id = excluded.plan_id,
            link_id = excluded.link_id,
            state = excluded.state,
            action = excluded.action,
            expected_link_revision = excluded.expected_link_revision,
            local_revision = excluded.local_revision,
            remote_revision = excluded.remote_revision,
            provider_revision = excluded.provider_revision,
            conflict_code = excluded.conflict_code,
            common_ancestor_revision = excluded.common_ancestor_revision,
            plan_digest = excluded.plan_digest,
            expires_at = excluded.expires_at
        """,
        (
            plan.plan_id,
            local_project_id,
            plan.link_id,
            plan.state,
            plan.action,
            plan.expected_link_revision,
            plan.local_revision,
            plan.remote_revision,
            plan.provider_revision,
            plan.conflict_code,
            plan.common_ancestor_revision,
            plan.plan_digest,
            plan.expires_at,
            idempotency_key,
            created_at,
        ),
    )


#: What a device durably knows about one attempt to apply one plan. `pending`
#: is written before the request leaves, so an interrupted run is visible as an
#: attempt rather than as nothing at all; `unknown` is the honest name for a
#: send whose effect was never confirmed.
APPLY_STATES: Final[frozenset[str]] = frozenset({"pending", "applied", "failed", "unknown"})


@dataclass(frozen=True)
class CachedLink:
    """Which server link a local project is bound to here.

    The local project id alone was the whole key, so nothing recorded which
    remote link or organization the cached rows came from; a valid-looking local
    id could be pointed at another project's plan without anything noticing.
    """

    link_id: str
    organization_id: str
    remote_project_id: str
    state: str
    link_revision: int


def cached_link(connection: sqlite3.Connection, *, local_project_id: str) -> CachedLink | None:
    """The link this device recorded for one local project."""
    row = connection.execute(
        "SELECT link_id, organization_id, remote_project_id, state, link_revision "
        "FROM project_link WHERE local_project_id = ?",
        (local_project_id,),
    ).fetchone()
    if row is None:
        return None
    return CachedLink(
        link_id=str(row[0]),
        organization_id=str(row[1]),
        remote_project_id=str(row[2]),
        state=str(row[3]),
        link_revision=int(row[4]),
    )


@dataclass(frozen=True)
class CachedSyncPlan:
    """One cached server decision and this device's apply attempt on it."""

    plan_id: str
    link_id: str
    plan_digest: str
    state: str
    action: str
    apply_idempotency_key: str | None
    apply_state: str | None
    receipt: ProjectSyncPlanResponse | None


def cached_sync_plan(
    connection: sqlite3.Connection, *, local_project_id: str, plan_id: str
) -> CachedSyncPlan | None:
    """The plan this device recorded, with whatever is known about applying it."""
    row = connection.execute(
        "SELECT plan_digest, state, action, apply_idempotency_key, apply_state, "
        "apply_receipt_json, link_id FROM project_sync_plan "
        "WHERE plan_id = ? AND local_project_id = ?",
        (plan_id, local_project_id),
    ).fetchone()
    if row is None:
        return None
    receipt = None if row[5] is None else ProjectSyncPlanResponse.model_validate_json(str(row[5]))
    return CachedSyncPlan(
        plan_id=plan_id,
        link_id=str(row[6]),
        plan_digest=str(row[0]),
        state=str(row[1]),
        action=str(row[2]),
        apply_idempotency_key=None if row[3] is None else str(row[3]),
        apply_state=None if row[4] is None else str(row[4]),
        receipt=receipt,
    )


def begin_sync_apply(
    connection: sqlite3.Connection,
    *,
    local_project_id: str,
    plan_id: str,
    idempotency_key: str,
) -> None:
    """Retain the exact key this device is about to send.

    Before the request, not after: a key generated again on the next run is a
    second operation, and the server would apply it as one. This row is what
    makes a retry the *same* operation.
    """
    changed = connection.execute(
        "UPDATE project_sync_plan SET apply_idempotency_key = ?, apply_state = 'pending' "
        "WHERE plan_id = ? AND local_project_id = ?",
        (idempotency_key, plan_id, local_project_id),
    ).rowcount
    if changed != 1:
        raise ValueError("no cached sync plan to apply")


def mark_sync_apply(
    connection: sqlite3.Connection, *, local_project_id: str, plan_id: str, state: str
) -> None:
    """Record how an attempt ended when no receipt arrived."""
    if state not in APPLY_STATES:
        raise ValueError("unknown sync apply state")
    connection.execute(
        "UPDATE project_sync_plan SET apply_state = ? WHERE plan_id = ? AND local_project_id = ?",
        (state, plan_id, local_project_id),
    )


def record_sync_apply(
    connection: sqlite3.Connection,
    *,
    local_project_id: str,
    plan: ProjectSyncPlanResponse,
    idempotency_key: str,
) -> None:
    """Persist the server's receipt for an applied plan.

    One short write, holding no network call open: the receipt is knowledge the
    device already paid for, and anything that happens afterwards must not be
    able to take it back.
    """
    changed = connection.execute(
        "UPDATE project_sync_plan SET state = ?, apply_idempotency_key = ?, "
        "apply_state = 'applied', apply_receipt_json = ? "
        "WHERE plan_id = ? AND local_project_id = ?",
        (
            plan.state,
            idempotency_key,
            plan.model_dump_json(),
            plan.plan_id,
            local_project_id,
        ),
    ).rowcount
    if changed != 1:
        raise ValueError("no cached sync plan to receipt")
