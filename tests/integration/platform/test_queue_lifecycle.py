"""PostgreSQL claim/fail/cancel/requeue paths for the custom job queue."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import AuditEvent
from ai_stp_platform.organization_models import (
    CorporateRole,
    CorporateRoleBinding,
    CorporateRolePermission,
    CorporateServicePrincipal,
    Organization,
)
from ai_stp_platform.queue.engine import (
    DEFAULT_LEASE_TIMEOUT_SECONDS,
    TenantJobInvalid,
    cancel,
    claim,
    enqueue,
    fail,
    heartbeat,
    mark_succeeded,
    requeue_locked,
    requeue_stale,
    validate_tenant_job,
)
from ai_stp_platform.queue.states import JobState, JobType
from ai_stp_worker.runner import audit_tenant_job_outcome

pytestmark = pytest.mark.platform


@pytest.mark.asyncio
async def test_tenant_jobs_are_partitioned_and_revalidate_delayed_authorization(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    first_id = new_id("organization")
    second_id = new_id("organization")
    async with db_sessionmaker() as session, session.begin():
        session.add_all(
            [
                Organization(id=first_id, kind="corporate", display_name="First"),
                Organization(id=second_id, kind="corporate", display_name="Second"),
            ]
        )
        await session.flush()
        principals: list[CorporateServicePrincipal] = []
        for organization_id in (first_id, second_id):
            principal = CorporateServicePrincipal(
                id=new_id("service_principal"),
                organization_id=organization_id,
                name="queue-worker",
            )
            principals.append(principal)
            session.add_all(
                [
                    principal,
                    CorporateRole(
                        organization_id=organization_id,
                        name="staff",
                        parent_role=None,
                    ),
                    CorporateRolePermission(
                        organization_id=organization_id,
                        role="staff",
                        permission="project.read",
                    ),
                ]
            )
            await session.flush()
            session.add(
                CorporateRoleBinding(
                    id=new_id("operation"),
                    organization_id=organization_id,
                    principal_type="service_principal",
                    service_principal_id=principal.id,
                    role="staff",
                    scope_kind="organization",
                    scope_id=organization_id,
                )
            )
        await session.flush()
        first = await enqueue(
            session,
            job_type=JobType.UPLOAD,
            payload={"path": "first"},
            idempotency_key="same-logical-work",
            organization_id=first_id,
            authorization_revision=1,
            principal_type="service_principal",
            principal_id=principals[0].id,
            required_permission="project.read",
        )
        second = await enqueue(
            session,
            job_type=JobType.UPLOAD,
            payload={"path": "second"},
            idempotency_key="same-logical-work",
            organization_id=second_id,
            authorization_revision=1,
            principal_type="service_principal",
            principal_id=principals[1].id,
            required_permission="project.read",
        )
        assert first.id != second.id
        assert (
            await cancel(session, idempotency_key="same-logical-work", organization_id=first_id)
            is True
        )
        assert (
            await cancel(session, idempotency_key="same-logical-work", organization_id=first_id)
            is False
        )
        assert (
            await cancel(session, idempotency_key="same-logical-work", organization_id=second_id)
            is True
        )
        assert (await validate_tenant_job(session, first))["path"] == "first"
        first_organization = await session.get(Organization, first_id)
        assert first_organization is not None
        first_organization.policy_revision += 1
        await session.flush()
        with pytest.raises(TenantJobInvalid, match="revision is stale"):
            await validate_tenant_job(session, first)
        await audit_tenant_job_outcome(session, first, "failed", "TenantJobInvalid: stale")
        audit = await session.scalar(
            select(AuditEvent).where(
                AuditEvent.organization_id == first_id,
                AuditEvent.target_id == str(first.id),
                AuditEvent.action == "job.execute",
            )
        )
        assert audit is not None
        assert audit.actor_type == "service_principal"
        assert audit.actor_id == principals[0].id
        assert audit.outcome == "failed"
        assert audit.reason == "TenantJobInvalid"
        assert (await validate_tenant_job(session, second))["path"] == "second"

        with pytest.raises(TenantJobInvalid, match="does not match"):
            await enqueue(
                session,
                job_type=JobType.UPLOAD,
                payload={
                    "_tenant": {
                        "organization_id": second_id,
                        "authorization_revision": 1,
                    }
                },
                idempotency_key="forged-tenant",
                organization_id=first_id,
                authorization_revision=1,
                principal_type="service_principal",
                principal_id=principals[0].id,
                required_permission="project.read",
            )


@pytest.mark.asyncio
async def test_claim_succeed_and_retry_dead_letter(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """Claim moves work to running; failures retry then dead-letter at max_attempts."""
    now = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)
    async with db_sessionmaker() as session, session.begin():
        await enqueue(
            session,
            job_type=JobType.UPLOAD,
            payload={"path": "a"},
            idempotency_key="queue-lifecycle-success",
            max_attempts=2,
            run_after=now,
        )
        await enqueue(
            session,
            job_type=JobType.UPLOAD,
            payload={"path": "b"},
            idempotency_key="queue-lifecycle-fail",
            max_attempts=2,
            run_after=now,
        )

    async with db_sessionmaker() as session, session.begin():
        claimed = await claim(session, worker_id="worker-a", batch=2, now=now)
        assert {job.idempotency_key for job in claimed} == {
            "queue-lifecycle-success",
            "queue-lifecycle-fail",
        }
        assert all(job.state is JobState.RUNNING for job in claimed)
        by_key = {job.idempotency_key: job for job in claimed}
        await mark_succeeded(session, by_key["queue-lifecycle-success"])
        await fail(session, by_key["queue-lifecycle-fail"], error="first", now=now)
        assert by_key["queue-lifecycle-fail"].state is JobState.RETRY_SCHEDULED

    async with db_sessionmaker() as session, session.begin():
        # Retry after backoff window.
        later = now + timedelta(seconds=10)
        retried = await claim(session, worker_id="worker-b", batch=2, now=later)
        assert len(retried) == 1
        assert retried[0].idempotency_key == "queue-lifecycle-fail"
        await fail(session, retried[0], error="second", now=later)
        assert retried[0].state is JobState.DEAD_LETTER


@pytest.mark.asyncio
async def test_cancel_and_requeue_locked(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """Cancel only claimable jobs; drain requeues work still held by a worker."""
    now = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)
    async with db_sessionmaker() as session, session.begin():
        await enqueue(
            session,
            job_type=JobType.UPLOAD,
            payload={"path": "c"},
            idempotency_key="queue-cancel-me",
            run_after=now,
        )
        await enqueue(
            session,
            job_type=JobType.UPLOAD,
            payload={"path": "d"},
            idempotency_key="queue-requeue-me",
            run_after=now,
        )

    async with db_sessionmaker() as session, session.begin():
        assert await cancel(session, idempotency_key="queue-cancel-me") is True
        assert await cancel(session, idempotency_key="missing") is False
        claimed = await claim(session, worker_id="worker-drain", batch=5, now=now)
        assert len(claimed) == 1
        assert claimed[0].idempotency_key == "queue-requeue-me"
        # Cancel is cooperative: running work is not cancelled.
        assert await cancel(session, idempotency_key="queue-requeue-me") is False

    async with db_sessionmaker() as session, session.begin():
        count = await requeue_locked(session, worker_id="worker-drain")
        assert count == 1
        reclaimed = await claim(session, worker_id="worker-new", batch=5, now=now)
        assert len(reclaimed) == 1
        assert reclaimed[0].idempotency_key == "queue-requeue-me"
        assert reclaimed[0].locked_by == "worker-new"


@pytest.mark.asyncio
async def test_stale_lease_is_reclaimed_and_counts_as_a_delivery(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """A crashed worker cannot leave a running job permanently invisible."""
    now = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)
    async with db_sessionmaker() as session, session.begin():
        await enqueue(
            session,
            job_type=JobType.UPLOAD,
            payload={"path": "stale"},
            idempotency_key="queue-stale-lease",
            max_attempts=2,
            run_after=now,
        )

    async with db_sessionmaker() as session, session.begin():
        claimed = await claim(session, worker_id="worker-crashed", batch=1, now=now)
        assert len(claimed) == 1

    expired = now + timedelta(seconds=DEFAULT_LEASE_TIMEOUT_SECONDS + 1)
    async with db_sessionmaker() as session, session.begin():
        assert (
            await requeue_stale(
                session,
                lease_timeout_seconds=DEFAULT_LEASE_TIMEOUT_SECONDS,
                now=expired,
            )
            == 1
        )

    async with db_sessionmaker() as session, session.begin():
        reclaimed = await claim(session, worker_id="worker-recovered", batch=1, now=expired)
        assert len(reclaimed) == 1
        assert reclaimed[0].attempts == 1
        assert reclaimed[0].locked_by == "worker-recovered"


@pytest.mark.asyncio
async def test_heartbeat_keeps_a_live_lease_claimed(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """A live worker heartbeat prevents another worker from reclaiming work."""
    now = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)
    async with db_sessionmaker() as session, session.begin():
        await enqueue(
            session,
            job_type=JobType.UPLOAD,
            payload={"path": "live"},
            idempotency_key="queue-live-lease",
            run_after=now,
        )
        claimed = await claim(session, worker_id="worker-live", batch=1, now=now)
        assert len(claimed) == 1

    extended = now + timedelta(seconds=DEFAULT_LEASE_TIMEOUT_SECONDS - 1)
    async with db_sessionmaker() as session, session.begin():
        assert (
            await heartbeat(
                session,
                worker_id="worker-live",
                job_id=claimed[0].id,
                now=extended,
            )
            is True
        )
        assert (
            await requeue_stale(
                session,
                lease_timeout_seconds=DEFAULT_LEASE_TIMEOUT_SECONDS,
                now=extended,
            )
            == 0
        )
