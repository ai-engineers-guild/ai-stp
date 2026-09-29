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
from ai_stp_platform.queue.models import Job
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
async def test_terminal_settlement_scrubs_sensitive_payload_keys(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """Credentials in the payload must not sit in retained terminal rows."""
    now = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)
    async with db_sessionmaker() as session, session.begin():
        await enqueue(
            session,
            job_type=JobType.UPLOAD,
            payload={"path": "ok", "accept_token": "secret-a", "note": "kept"},
            idempotency_key="queue-scrub-success",
            max_attempts=1,
            run_after=now,
        )
        await enqueue(
            session,
            job_type=JobType.UPLOAD,
            payload={"path": "ko", "invitation_token": "secret-b", "note": "kept"},
            idempotency_key="queue-scrub-dead",
            max_attempts=1,
            run_after=now,
        )
        await enqueue(
            session,
            job_type=JobType.UPLOAD,
            payload={"path": "retry", "accept_token": "secret-c"},
            idempotency_key="queue-scrub-retry",
            max_attempts=2,
            run_after=now,
        )

    async with db_sessionmaker() as session, session.begin():
        claimed = await claim(session, worker_id="worker-scrub", batch=3, now=now)
        by_key = {job.idempotency_key: job for job in claimed}
        await mark_succeeded(session, by_key["queue-scrub-success"])
        await fail(session, by_key["queue-scrub-dead"], error="done", now=now)
        assert by_key["queue-scrub-dead"].state is JobState.DEAD_LETTER
        await fail(session, by_key["queue-scrub-retry"], error="again", now=now)
        assert by_key["queue-scrub-retry"].state is JobState.RETRY_SCHEDULED

    async with db_sessionmaker() as session, session.begin():
        rows = (
            await session.execute(
                select(Job).where(
                    Job.idempotency_key.in_(
                        [
                            "queue-scrub-success",
                            "queue-scrub-dead",
                            "queue-scrub-retry",
                        ]
                    )
                )
            )
        ).scalars()
        by_key = {row.idempotency_key: row for row in rows}
        for key in ("queue-scrub-success", "queue-scrub-dead"):
            payload = by_key[key].payload
            assert payload["note"] == "kept"
            assert "secret" not in str(payload.values())
        assert by_key["queue-scrub-success"].payload["accept_token"] == "[delivered]"
        assert by_key["queue-scrub-dead"].payload["invitation_token"] == "[delivered]"
        # A job that will run again keeps its payload — the retry still needs it.
        assert by_key["queue-scrub-retry"].payload["accept_token"] == "secret-c"


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
async def test_stale_worker_cannot_settle_over_a_reclaimed_job(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """An expired lease loses the verdict: settle returns False and writes nothing."""
    now = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)
    async with db_sessionmaker() as session, session.begin():
        await enqueue(
            session,
            job_type=JobType.UPLOAD,
            payload={"path": "superseded"},
            idempotency_key="queue-superseded-settle",
            max_attempts=5,
            run_after=now,
        )

    async with db_sessionmaker() as session, session.begin():
        claimed = await claim(session, worker_id="worker-stale", batch=1, now=now)
        stale_job = claimed[0]
        stale_job_id = stale_job.id

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
        reclaimed = await claim(session, worker_id="worker-live", batch=1, now=expired)
        assert len(reclaimed) == 1
        live_job = reclaimed[0]

    async with db_sessionmaker() as session, session.begin():
        # The stale worker still holds its detached Job object; every settle
        # path must refuse to stamp it over the live row.
        assert await mark_succeeded(session, stale_job) is False
        assert await fail(session, stale_job, error="late failure", now=expired) is False
        row = await session.get(Job, stale_job_id)
        assert row is not None
        assert row.state == JobState.RUNNING
        assert row.locked_by == "worker-live"
        # `requeue_stale` itself records the lease expiry; the stale worker's
        # late failure must not overwrite it.
        assert row.last_error == "stale worker lease expired"
        # Positive control: the owning worker settles the same row normally
        # (`row` shares this session's identity map, so it reflects the write).
        assert await mark_succeeded(session, live_job) is True
        assert row.state == JobState.SUCCEEDED


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


@pytest.mark.asyncio
async def test_stale_requeue_to_dead_letter_scrubs_the_payload(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """The lease-expiry dead-letter path applies the same scrub `fail` does.

    A credential-bearing payload in a terminal row would otherwise rest for
    the 30-day GC window; a bulk UPDATE could not rewrite it per row, which
    is why the reclaim is a bounded per-row pass.
    """
    now = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)
    async with db_sessionmaker() as session, session.begin():
        await enqueue(
            session,
            job_type=JobType.UPLOAD,
            payload={"path": "kept", "access_token": "dead-secret"},
            idempotency_key="queue-dead-letter-scrub",
            max_attempts=1,
            run_after=now,
        )

    async with db_sessionmaker() as session, session.begin():
        claimed = await claim(session, worker_id="worker-doomed", batch=1, now=now)
        assert len(claimed) == 1
        job_id = claimed[0].id

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
        row = await session.get(Job, job_id)
        assert row is not None
        assert row.state == JobState.DEAD_LETTER
        assert row.payload == {"path": "kept", "access_token": "[delivered]"}
        assert row.last_error == "stale worker lease expired"
