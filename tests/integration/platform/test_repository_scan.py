"""The shared repository-scan pipeline every provider adapter feeds.

These tests drive ``scan_linked_repository`` with a deterministic adapter
against a migrated database, so every invariant — identity/link/project
availability, observed-head pinning, mapping snapshot, evidence policy,
concurrency rechecks, idempotent replay, provenance, unmapped queue — is
covered once instead of once per provider.
"""

from __future__ import annotations

import io
import tarfile
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.session import AuthContext
from ai_stp_api.slices.corporate.service import bootstrap, create_project
from ai_stp_api.slices.technology.service import change_lifecycle, import_seed
from ai_stp_contracts.corporate import CorporateBootstrapRequest, CorporateProjectCreateRequest
from ai_stp_contracts.technology import TechnologyLifecycleRequest, TechnologySeedRequest
from ai_stp_contracts.technology_seed import SEED_COORDINATES_VERSION, SEED_TECHNOLOGIES
from ai_stp_foundation.ids import new_id
from ai_stp_platform.gitlab_sources import request_digest
from ai_stp_platform.models import Account, Device
from ai_stp_platform.organization_models import (
    CorporateProject,
    Organization,
    ProjectIdentity,
    ProjectLink,
)
from ai_stp_platform.queue.engine import TenantJobInvalid, enqueue, validate_tenant_job
from ai_stp_platform.queue.models import Job
from ai_stp_platform.queue.states import JobType, PermanentJobFailure
from ai_stp_platform.repository_scan import RepositorySnapshot, scan_linked_repository
from ai_stp_platform.technology_models import (
    ProjectTechnologyRelation,
    TechnologyScan,
    TechnologyUnmappedCoordinate,
)

_HEAD = "a" * 40
_OTHER_HEAD = "b" * 40


def _archive(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for name, payload in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(payload)
            tar.addfile(member, io.BytesIO(payload))
    return buffer.getvalue()


_REPO_TARBALL = _archive({"service/requirements.txt": b"django==5.0\nunmapped-widget==1.0\n"})


def _snapshot(**overrides: object) -> RepositorySnapshot:
    values: dict[str, object] = {
        "repository": "group/service",
        "branch": "main",
        "head": _HEAD,
        "archive": _REPO_TARBALL,
        "observed_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    values.update(overrides)
    return RepositorySnapshot(**values)  # type: ignore[arg-type]


class _Adapter:
    """Deterministic adapter: the pipeline is under test, not the provider."""

    def __init__(
        self,
        snapshot: RepositorySnapshot | None = None,
        *,
        provider: str = "gitlab",
        validate_error: PermanentJobFailure | None = None,
        fetch_error: Exception | None = None,
        bound: bool = True,
    ) -> None:
        self.provider = provider
        self._snapshot = snapshot or _snapshot()
        self._validate_error = validate_error
        self._fetch_error = fetch_error
        self._bound = bound
        self.fetch_calls = 0

    def validate_identity(self, identity: ProjectIdentity) -> None:
        if self._validate_error is not None:
            raise self._validate_error

    async def fetch_snapshot(
        self, db: AsyncSession, identity: ProjectIdentity
    ) -> RepositorySnapshot:
        self.fetch_calls += 1
        if self._fetch_error is not None:
            raise self._fetch_error
        return self._snapshot

    def still_bound(self, identity: ProjectIdentity, snapshot: RepositorySnapshot) -> bool:
        return self._bound

    def request_digest(self, value: object) -> str:
        return request_digest(value)


async def _bootstrap_org(db_session: AsyncSession) -> tuple[AuthContext, str, str]:
    account_id = new_id("account")
    db_session.add(Account(id=account_id, status="active"))
    await db_session.flush()
    ctx = AuthContext(account_id, "scan-test", None, "active", False, False)
    organization_id = (
        await bootstrap(
            db_session,
            payload=CorporateBootstrapRequest(
                organization_name="Repository scan acceptance",
                superadmin_account_id=account_id,
                idempotency_key=f"scan-bootstrap-{uuid.uuid4().hex[:16]}",
            ),
            request_id="scan-test",
        )
    ).organization_id
    return ctx, organization_id, account_id


async def _seed_and_activate(
    db_session: AsyncSession, ctx: AuthContext, organization_id: str
) -> str:
    await import_seed(
        db_session,
        ctx=ctx,
        organization_id=organization_id,
        payload=TechnologySeedRequest(
            authorization_revision=1, idempotency_key=f"scan-seed-{uuid.uuid4().hex[:16]}"
        ),
        request_id="scan-test",
    )
    django_id = next(
        technology_id for technology_id, metadata in SEED_TECHNOLOGIES if metadata.name == "Django"
    )
    await change_lifecycle(
        db_session,
        ctx=ctx,
        organization_id=organization_id,
        technology_id=django_id,
        payload=TechnologyLifecycleRequest(
            lifecycle="active",
            expected_revision=1,
            authorization_revision=2,
            idempotency_key=f"scan-approve-{uuid.uuid4().hex[:16]}",
        ),
        request_id="scan-test",
    )
    return django_id


async def _linked_scan_setup(
    db_session: AsyncSession,
    *,
    provider_kind: str = "gitlab",
    identity_overrides: dict[str, object] | None = None,
) -> tuple[AuthContext, str, str, str, str]:
    """Bootstrap org + seed + linked project; return ids for the scan call."""
    ctx, organization_id, account_id = await _bootstrap_org(db_session)
    django_id = await _seed_and_activate(db_session, ctx, organization_id)
    fields: dict[str, object] = {
        "provider_installation_id": "https://gitlab.example",
        "immutable_repository_id": "42",
        "provider_default_branch": "main",
        "provider_observed_revision": _HEAD,
        "observed_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    fields.update(identity_overrides or {})
    project_id, provider_id = await _add_linked_project(
        db_session,
        organization_id=organization_id,
        account_id=account_id,
        ctx=ctx,
        provider_kind=provider_kind,
        identity_overrides=fields,
        authorization_revision=3,
        project_name="Scanned service",
    )
    return ctx, organization_id, project_id, provider_id, django_id


async def _add_linked_project(
    db_session: AsyncSession,
    *,
    organization_id: str,
    account_id: str,
    ctx: AuthContext,
    provider_kind: str,
    identity_overrides: dict[str, object],
    authorization_revision: int,
    project_name: str = "Second scanned service",
) -> tuple[str, str]:
    """One more linked project inside an already bootstrapped organization."""
    project = await create_project(
        db_session,
        ctx=ctx,
        organization_id=organization_id,
        payload=CorporateProjectCreateRequest(
            name=project_name,
            authorization_revision=authorization_revision,
            idempotency_key=f"scan-project-{uuid.uuid4().hex[:16]}",
        ),
        request_id="scan-test",
    )
    device_id = new_id("device")
    db_session.add(
        Device(id=device_id, account_id=account_id, public_key=f"scan-device-{device_id}")
    )
    provider_id = new_id("provider_project")
    identity_fields: dict[str, object] = {
        "id": provider_id,
        "organization_id": organization_id,
        "namespace": "provider",
        "external_key": f"{provider_kind}:{provider_id}",
        "display_name": "group/second",
        "provider_kind": provider_kind,
        "state": "active",
    }
    identity_fields.update(identity_overrides)
    db_session.add(ProjectIdentity(**identity_fields))  # type: ignore[arg-type]
    await db_session.flush()
    db_session.add(
        ProjectLink(
            id=new_id("project_link"),
            plan_id=new_id("link_plan"),
            plan_digest="sha256:" + "b" * 64,
            organization_id=organization_id,
            actor_account_id=account_id,
            device_id=device_id,
            local_project_id=new_id("project"),
            remote_project_id=project.project_id,
            provider_project_id=provider_id,
            state="linked",
            local_revision="local1",
            remote_revision="remote1",
            provider_revision="provider1",
            create_idempotency_key=f"scan-link-{uuid.uuid4().hex[:16]}",
        )
    )
    await db_session.flush()
    return project.project_id, provider_id


async def _scan(
    db_session: AsyncSession,
    organization_id: str,
    project_id: str,
    provider_id: str,
    *,
    scan_id: str | None = None,
    mapping_version: str = SEED_COORDINATES_VERSION,
    adapter: _Adapter | None = None,
) -> str:
    return await scan_linked_repository(
        db_session,
        organization_id=organization_id,
        provider_project_id=provider_id,
        project_id=project_id,
        scan_id=scan_id or new_id("scan"),
        mapping_version=mapping_version,
        adapter=adapter or _Adapter(),
    )


async def test_scan_applies_findings_and_records_provenance(
    db_session: AsyncSession,
) -> None:
    _, organization_id, project_id, provider_id, django_id = await _linked_scan_setup(db_session)
    scan_id = new_id("scan")

    assert (
        await _scan(db_session, organization_id, project_id, provider_id, scan_id=scan_id)
        == "applied"
    )

    scan = await db_session.get(TechnologyScan, (organization_id, scan_id))
    assert scan is not None
    assert scan.project_id == project_id
    assert scan.source == "gitlab"
    assert scan.repository == "group/service"
    assert scan.branch == "main"
    assert scan.commit == _HEAD

    relation = await db_session.scalar(
        select(ProjectTechnologyRelation).where(
            ProjectTechnologyRelation.organization_id == organization_id,
            ProjectTechnologyRelation.project_id == project_id,
            ProjectTechnologyRelation.technology_id == django_id,
        )
    )
    assert relation is not None and relation.state == "current"

    unmapped = (
        await db_session.scalars(
            select(TechnologyUnmappedCoordinate).where(
                TechnologyUnmappedCoordinate.organization_id == organization_id,
                TechnologyUnmappedCoordinate.project_id == project_id,
            )
        )
    ).all()
    assert [(row.kind, row.coordinate, row.scan_id) for row in unmapped] == [
        ("package", "unmapped-widget", scan_id)
    ]


async def test_scan_replay_is_skipped_and_reuse_rejected(db_session: AsyncSession) -> None:
    _, organization_id, project_id, provider_id, _ = await _linked_scan_setup(db_session)
    scan_id = new_id("scan")
    assert (
        await _scan(db_session, organization_id, project_id, provider_id, scan_id=scan_id)
        == "applied"
    )

    # Identical replay short-circuits before touching storage again.
    adapter = _Adapter()
    assert (
        await _scan(
            db_session,
            organization_id,
            project_id,
            provider_id,
            scan_id=scan_id,
            adapter=adapter,
        )
        == "skipped"
    )
    assert adapter.fetch_calls == 1

    # A different snapshot under the same scan id is a reuse violation.
    with pytest.raises(PermanentJobFailure, match="scan ID was reused"):
        await _scan(
            db_session,
            organization_id,
            project_id,
            provider_id,
            scan_id=scan_id,
            mapping_version="other-version",
        )


async def test_scan_requires_linked_identity_project_and_remote(
    db_session: AsyncSession,
) -> None:
    _, organization_id, project_id, provider_id, _ = await _linked_scan_setup(db_session)

    # An adapter of the other provider sees no identity row.
    with pytest.raises(PermanentJobFailure, match="unavailable"):
        await _scan(
            db_session,
            organization_id,
            project_id,
            provider_id,
            adapter=_Adapter(provider="github"),
        )

    # An unlinked pair is rejected before any fetch happens.
    link = await db_session.scalar(
        select(ProjectLink).where(ProjectLink.provider_project_id == provider_id)
    )
    assert link is not None
    link.state = "conflict"
    adapter = _Adapter()
    with pytest.raises(PermanentJobFailure, match="unavailable"):
        await _scan(db_session, organization_id, project_id, provider_id, adapter=adapter)
    assert adapter.fetch_calls == 0
    link.state = "linked"

    # A retired project is unavailable too.
    project_identity = await db_session.get(ProjectIdentity, project_id)
    assert project_identity is not None
    project_identity.state = "deleted"
    with pytest.raises(PermanentJobFailure, match="unavailable"):
        await _scan(db_session, organization_id, project_id, provider_id)
    project_identity.state = "active"

    # An archived project row rejects the scan.
    project = await db_session.get(CorporateProject, project_id)
    assert project is not None
    project.lifecycle = "archived"
    with pytest.raises(PermanentJobFailure, match="unavailable"):
        await _scan(db_session, organization_id, project_id, provider_id)
    project.lifecycle = "active"


async def test_observed_head_pins_the_scan(db_session: AsyncSession) -> None:
    ctx, organization_id, project_id, provider_id, _ = await _linked_scan_setup(
        db_session, identity_overrides={"provider_observed_revision": _OTHER_HEAD}
    )
    adapter = _Adapter()
    with pytest.raises(PermanentJobFailure, match="requires refresh"):
        await _scan(db_session, organization_id, project_id, provider_id, adapter=adapter)
    assert adapter.fetch_calls == 1  # fetch happened; the pin rejected the result

    # An identity without a recorded observation scans whatever head arrived.
    project_id2, provider_id2 = await _add_linked_project(
        db_session,
        organization_id=organization_id,
        account_id=ctx.account_id,
        ctx=ctx,
        provider_kind="github",
        identity_overrides={
            "provider_observed_revision": None,
            "provider_default_branch": None,
            "observed_at": None,
        },
        authorization_revision=4,
    )
    assert (
        await _scan(
            db_session,
            organization_id,
            project_id2,
            provider_id2,
            adapter=_Adapter(provider="github"),
        )
        == "applied"
    )


async def test_transient_fetch_errors_propagate_unwrapped(db_session: AsyncSession) -> None:
    _, organization_id, project_id, provider_id, _ = await _linked_scan_setup(db_session)
    transient = RuntimeError("upstream timeout")
    with pytest.raises(RuntimeError, match="upstream timeout"):
        await _scan(
            db_session,
            organization_id,
            project_id,
            provider_id,
            adapter=_Adapter(fetch_error=transient),
        )


async def test_validate_failure_and_unusable_archive_dead_letter(
    db_session: AsyncSession,
) -> None:
    _, organization_id, project_id, provider_id, _ = await _linked_scan_setup(db_session)
    with pytest.raises(PermanentJobFailure, match="identity failed"):
        await _scan(
            db_session,
            organization_id,
            project_id,
            provider_id,
            adapter=_Adapter(validate_error=PermanentJobFailure("identity failed")),
        )
    with pytest.raises(PermanentJobFailure, match="archive is unusable"):
        await _scan(
            db_session,
            organization_id,
            project_id,
            provider_id,
            adapter=_Adapter(snapshot=_snapshot(archive=b"not a tar")),
        )


async def test_mapping_snapshot_must_exist(db_session: AsyncSession) -> None:
    _, organization_id, project_id, provider_id, _ = await _linked_scan_setup(db_session)
    with pytest.raises(PermanentJobFailure, match="mapping snapshot is unavailable"):
        await _scan(
            db_session,
            organization_id,
            project_id,
            provider_id,
            mapping_version="missing-version",
        )


async def test_lock_recheck_catches_binding_and_state_drift(
    db_session: AsyncSession,
) -> None:
    _, organization_id, project_id, provider_id, _ = await _linked_scan_setup(db_session)

    # The adapter re-proved nothing under lock → the merge never runs.
    with pytest.raises(PermanentJobFailure, match="link changed"):
        await _scan(
            db_session,
            organization_id,
            project_id,
            provider_id,
            adapter=_Adapter(bound=False),
        )
    assert (
        await db_session.scalar(
            select(TechnologyScan.id).where(TechnologyScan.organization_id == organization_id)
        )
        is None
    )

    # An observed revision rebound between fetch and lock also aborts.
    identity = await db_session.get(ProjectIdentity, provider_id)
    assert identity is not None
    original = identity.provider_observed_revision

    class _DriftingAdapter(_Adapter):
        def request_digest(self, value: object) -> str:
            # Rebind the recorded observation after the pin check but before
            # the locked recheck — the second guard must catch it.
            identity.provider_observed_revision = _OTHER_HEAD
            return super().request_digest(value)

    with pytest.raises(PermanentJobFailure, match="link changed"):
        await _scan(
            db_session,
            organization_id,
            project_id,
            provider_id,
            adapter=_DriftingAdapter(),
        )
    identity.provider_observed_revision = original
    await db_session.flush()


async def test_rescan_replaces_unmapped_queue_but_keeps_candidates(
    db_session: AsyncSession,
) -> None:
    _, organization_id, project_id, provider_id, django_id = await _linked_scan_setup(db_session)
    scan_id = new_id("scan")
    await _scan(db_session, organization_id, project_id, provider_id, scan_id=scan_id)

    row = await db_session.scalar(
        select(TechnologyUnmappedCoordinate).where(
            TechnologyUnmappedCoordinate.organization_id == organization_id,
            TechnologyUnmappedCoordinate.coordinate == "unmapped-widget",
        )
    )
    assert row is not None
    row.candidate_technology_id = django_id
    await db_session.flush()

    second_id = new_id("scan")
    await _scan(db_session, organization_id, project_id, provider_id, scan_id=second_id)
    refreshed = await db_session.scalar(
        select(TechnologyUnmappedCoordinate).where(
            TechnologyUnmappedCoordinate.organization_id == organization_id,
            TechnologyUnmappedCoordinate.coordinate == "unmapped-widget",
        )
    )
    assert refreshed is not None
    assert refreshed.scan_id == second_id
    assert refreshed.candidate_technology_id == django_id

    # An organization in a terminal state fails the lock recheck.
    organization = await db_session.get(Organization, organization_id)
    assert organization is not None
    organization.state = "suspended"
    with pytest.raises(PermanentJobFailure, match="link changed"):
        await _scan(db_session, organization_id, project_id, provider_id, adapter=_Adapter())


async def test_scan_batch_reauthorizes_siblings_but_keeps_unrelated_stale_jobs_rejected(
    db_session: AsyncSession,
) -> None:
    ctx, org, project, provider, _ = await _linked_scan_setup(db_session)
    second, second_provider = await _add_linked_project(
        db_session,
        organization_id=org,
        account_id=ctx.account_id,
        ctx=ctx,
        provider_kind="gitlab",
        identity_overrides={},
        authorization_revision=4,
    )
    organization = await db_session.get(Organization, org)
    assert organization is not None
    revision = organization.policy_revision
    scan_ids = [new_id("scan") for _ in range(3)]
    jobs: list[Job] = []
    for index, scan_id in enumerate(scan_ids):
        target = project if index == 0 else second
        jobs.append(
            await enqueue(
                db_session,
                job_type=JobType.GITLAB_TECHNOLOGY_SCAN,
                payload={
                    "scan_id": scan_id,
                    "project_id": target,
                    "batch_id": "acceptance-batch" if index < 2 else "unrelated-batch",
                },
                idempotency_key=f"batch-job-{scan_id}",
                organization_id=org,
                authorization_revision=revision,
                principal_type="user",
                principal_id=ctx.account_id,
                required_permission="technology.scan.publish",
                scope_kind="project",
                scope_id=target,
            )
        )
    await validate_tenant_job(db_session, jobs[0])
    await _scan(db_session, org, project, provider, scan_id=scan_ids[0])
    await validate_tenant_job(db_session, jobs[1])
    with pytest.raises(TenantJobInvalid, match="revision is stale"):
        await validate_tenant_job(db_session, jobs[2])
    await _scan(db_session, org, second, second_provider, scan_id=scan_ids[1])
    # A policy mutation independent of the batch must still reject old authority.
    organization.policy_revision += 1
    await db_session.flush()
    with pytest.raises(TenantJobInvalid, match="revision is stale"):
        await validate_tenant_job(db_session, jobs[0])
