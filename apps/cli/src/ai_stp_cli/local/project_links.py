"""Local cache for explicit cloud project links and sync decisions."""

import sqlite3

from ai_stp_contracts.context import ProjectLinkResponse, ProjectSyncPlanResponse
from ai_stp_foundation.ids import is_valid_id


def cache_link(connection: sqlite3.Connection, link: ProjectLinkResponse) -> None:
    """Cache the server result; the server remains the authority."""
    if not is_valid_id(link.local_project_id, "project"):
        raise ValueError("local project id is not valid")
    connection.execute(
        """
        INSERT INTO project_link (
            local_project_id, plan_id, plan_digest, organization_id, remote_project_id,
            provider_project_id,
            state, local_revision, remote_revision, provider_revision, link_revision, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(local_project_id) DO UPDATE SET
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
            plan_id, local_project_id, state, action, expected_link_revision,
            local_revision, remote_revision, provider_revision, conflict_code,
            common_ancestor_revision, plan_digest, expires_at, idempotency_key, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(local_project_id, idempotency_key) DO UPDATE SET
            plan_id = excluded.plan_id,
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
