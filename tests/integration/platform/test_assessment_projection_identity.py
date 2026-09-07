"""Real database evidence must retain all required target contexts and current policy."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_contracts.assurance import (
    TargetAssessmentIdentity,
    TargetAssessmentIngestRequest,
    TargetAssessmentIngestResponse,
)
from ai_stp_contracts.first_party import versions
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_canonical
from ai_stp_foundation.ids import new_id
from ai_stp_foundation.invariants import target_assessment_key_digest
from ai_stp_foundation.timestamps import format_timestamp
from ai_stp_passports import seal_adaptation
from ai_stp_passports.envelope import derive_revision_id
from ai_stp_passports.versions import ComponentVersionPassport
from ai_stp_platform.catalog_assessments import (
    AssessmentError,
    _target_identity,  # pyright: ignore[reportPrivateUsage]
    _upsert_latest,  # pyright: ignore[reportPrivateUsage]
    ingest_assessment,
    load_effective_assessments,
    record_component_scan_assessments,
)
from ai_stp_platform.models import Account, CatalogMetadata, TargetAssessment
from ai_stp_platform.safety.policy import POLICY_VERSION
from ai_stp_platform.safety.types import CheckOutcome, SafetyScanResult

pytestmark = pytest.mark.platform


async def _component(
    session: AsyncSession,
    *,
    harness_versions: tuple[str, ...] = (),
) -> tuple[CatalogMetadata, TargetAssessmentIdentity]:
    source = next(
        item for item in versions() if isinstance(item.passport, ComponentVersionPassport)
    )
    document = source.passport.model_dump(mode="json")
    document["stable_id"] = new_id("component")
    adaptation = document["adaptations"][0]
    scope = adaptation["scope_adaptations"][0]
    scope["supported_os"] = ["linux", "windows"]
    scope["supported_arch"] = ["x86_64"]
    scope["supported_harness_versions"] = list(harness_versions)
    adaptation["scope_adaptations"] = [scope]
    document["adaptations"] = [seal_adaptation(adaptation).model_dump(mode="json")]
    document["revision_id"] = derive_revision_id(document)
    passport = ComponentVersionPassport.model_validate(document)
    digest = digest_canonical("ai-stp:passport:v1", document)
    session.add(Account(id=passport.owner_id))
    await session.flush()
    metadata = CatalogMetadata(
        owner_account_id=passport.owner_id,
        object_kind="component",
        stable_id=passport.stable_id,
        version=passport.version,
        current_revision_id=passport.revision_id,
        visibility="public",
        lifecycle_state="active",
        published_at=datetime.now(UTC),
        passport_document=document,
        passport_digest=digest,
        trust_lane="experimental",
    )
    session.add(metadata)
    await session.flush()
    adaptation = passport.adaptations[0]
    identity = _target_identity(
        passport,
        passport_digest=digest,
        adaptation_id=adaptation.adaptation_id,
        harness_id=adaptation.harness_id,
        scope=adaptation.scope_adaptations[0],
        policy_version=POLICY_VERSION,
        operating_system="linux",
        architecture="x86_64",
    )
    return metadata, identity


async def _append(
    session: AsyncSession,
    identity: TargetAssessmentIdentity,
    state: str,
    *,
    offset: int = 0,
    refs: list[str] | None = None,
    observed_at: datetime | None = None,
) -> None:
    key = target_assessment_key_digest(cast(dict[str, JsonValue], identity.model_dump(mode="json")))
    observed = observed_at or datetime.now(UTC) + timedelta(seconds=offset)
    row = TargetAssessment(
        target_key_digest=key,
        identity=identity.model_dump(mode="json"),
        stored_state=state,
        compatibility_result="passed",
        evidence_refs=refs or [],
        observed_at=observed,
        expires_at=observed + timedelta(days=1),
        idempotency_key="assessment-fixture-" + str(uuid4()),
    )
    session.add(row)
    await session.flush()
    await _upsert_latest(
        session,
        key=key,
        assessment_id=row.id,
        identity=identity,
        stored_state=state,
        expires_at=row.expires_at,
        updated_at=observed,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("reverse", [False, True])
async def test_failed_platform_cannot_be_overwritten_by_another_platform(
    db_session: AsyncSession, reverse: bool
) -> None:
    metadata, identity = await _component(db_session)
    states = [
        (identity, "failed"),
        (identity.model_copy(update={"operating_system": "windows"}), "verified"),
    ]
    for target, state in reversed(states) if reverse else states:
        await _append(db_session, target, state)
    loaded = await load_effective_assessments(
        db_session, component_stable_id=metadata.stable_id, version=str(metadata.version)
    )
    assert len(loaded) == 1
    assert next(iter(loaded.values())).state == "failed"


@pytest.mark.asyncio
async def test_one_platform_cannot_verify_an_unmeasured_advertised_platform(
    db_session: AsyncSession,
) -> None:
    metadata, identity = await _component(db_session)
    await _append(db_session, identity, "verified")
    loaded = await load_effective_assessments(
        db_session, component_stable_id=metadata.stable_id, version=str(metadata.version)
    )
    assert next(iter(loaded.values())).state == "not_verified"


@pytest.mark.asyncio
async def test_replaced_policy_is_stale_until_each_required_context_is_refreshed(
    db_session: AsyncSession,
) -> None:
    metadata, identity = await _component(db_session)
    for operating_system in ["linux", "windows"]:
        await _append(
            db_session,
            identity.model_copy(
                update={"operating_system": operating_system, "policy_version": "safety-previous"}
            ),
            "verified",
        )
    loaded = await load_effective_assessments(
        db_session, component_stable_id=metadata.stable_id, version=str(metadata.version)
    )
    assert next(iter(loaded.values())).state == "stale"
    for operating_system in ["linux", "windows"]:
        await _append(
            db_session,
            identity.model_copy(update={"operating_system": operating_system}),
            "verified",
        )
    refreshed = await load_effective_assessments(
        db_session, component_stable_id=metadata.stable_id, version=str(metadata.version)
    )
    assert next(iter(refreshed.values())).state == "verified"


@pytest.mark.asyncio
async def test_public_evidence_never_serializes_a_writers_arbitrary_reference(
    db_session: AsyncSession,
) -> None:
    metadata, identity = await _component(db_session)
    unsafe_reference = "https://writer.example/private?access_token=synthetic-canary"
    for operating_system in ["linux", "windows"]:
        await _append(
            db_session,
            identity.model_copy(update={"operating_system": operating_system}),
            "verified",
            refs=[unsafe_reference, identity.projection_artifact_digest],
        )
    loaded = await load_effective_assessments(
        db_session, component_stable_id=metadata.stable_id, version=str(metadata.version)
    )
    refs = next(iter(loaded.values())).evidence_refs
    assert all(item.value != unsafe_reference for item in refs)
    assert any(item.value == identity.projection_artifact_digest for item in refs)


@pytest.mark.asyncio
async def test_concurrent_identical_ingestion_is_one_result(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with db_sessionmaker() as session:
        _metadata, identity = await _component(session)
        await session.commit()
    gate_key = uuid4().int % (2**63 - 1)
    app_name = "assessment-race-" + uuid4().hex
    observed_at = datetime.now(UTC)
    body = TargetAssessmentIngestRequest(
        identity=identity,
        stored_state="verified",
        compatibility_result="passed",
        observed_at=format_timestamp(observed_at),
        expires_at=format_timestamp(observed_at + timedelta(days=1)),
        idempotency_key="concurrent-assessment-" + uuid4().hex,
    )
    async with db_sessionmaker() as setup:
        await setup.execute(
            text(f"""
            CREATE FUNCTION assessment_insert_gate() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                PERFORM pg_advisory_xact_lock({gate_key});
                RETURN NEW;
            END $$
        """)
        )
        await setup.execute(
            text("""
            CREATE TRIGGER assessment_insert_gate BEFORE INSERT ON target_assessment
            FOR EACH ROW EXECUTE FUNCTION assessment_insert_gate()
        """)
        )
        await setup.commit()

    async def write() -> TargetAssessmentIngestResponse:
        async with db_sessionmaker() as session, session.begin():
            await session.execute(
                text("SELECT set_config('application_name', :name, true)"), {"name": app_name}
            )
            return await ingest_assessment(session, body)

    tasks: list[asyncio.Task[TargetAssessmentIngestResponse]] = []
    try:
        async with db_sessionmaker() as gate:
            await gate.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": gate_key})
            tasks = [asyncio.create_task(write()), asyncio.create_task(write())]
            async with asyncio.timeout(30), db_sessionmaker() as observer:
                while True:
                    blocked = await observer.scalar(
                        text("""
                        SELECT count(*) FROM pg_stat_activity
                        WHERE application_name = :name AND wait_event_type = 'Lock'
                    """),
                        {"name": app_name},
                    )
                    if blocked == 2:
                        break
                    await observer.commit()
            await gate.commit()
        results = await asyncio.gather(*tasks)
        assert sorted(result.created for result in results) == [False, True]
        assert len({result.target_key_digest for result in results}) == 1
    finally:
        await asyncio.gather(*tasks, return_exceptions=True)
        async with db_sessionmaker() as cleanup:
            await cleanup.execute(text("DROP TRIGGER assessment_insert_gate ON target_assessment"))
            await cleanup.execute(text("DROP FUNCTION assessment_insert_gate()"))
            await cleanup.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("reverse", [False, True])
async def test_equal_observation_times_preserve_the_restrictive_result(
    db_session: AsyncSession, reverse: bool
) -> None:
    metadata, identity = await _component(db_session)
    observed = datetime.now(UTC)
    for state in ["verified", "failed"] if reverse else ["failed", "verified"]:
        await _append(db_session, identity, state, observed_at=observed)
    await _append(
        db_session, identity.model_copy(update={"operating_system": "windows"}), "verified"
    )
    loaded = await load_effective_assessments(
        db_session, component_stable_id=metadata.stable_id, version=str(metadata.version)
    )
    assert next(iter(loaded.values())).state == "failed"


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", ["future", "expiry", "foreign_artifact", "failed_observation"])
async def test_ingest_rejects_unbound_or_impossible_evidence_before_writing(
    db_session: AsyncSession, invalid: str
) -> None:
    _metadata, identity = await _component(db_session)
    moment = datetime.now(UTC) - timedelta(seconds=1)
    observed = moment + timedelta(days=1) if invalid == "future" else moment
    expiry = moment - timedelta(seconds=1) if invalid == "expiry" else moment + timedelta(days=1)
    observation = {
        "identity": {
            "artifact_digest": "sha256:" + "f" * 64
            if invalid == "foreign_artifact"
            else identity.projection_artifact_digest,
            "check_id": "path_denylist",
            "scanner_id": "ai-stp-safety",
            "scanner_version": POLICY_VERSION,
            "policy_version": POLICY_VERSION,
            "operating_system": "linux",
            "architecture": "x86_64",
        },
        "result": "failed" if invalid == "failed_observation" else "passed",
        "observed_at": format_timestamp(moment),
        "expires_at": format_timestamp(moment + timedelta(days=1)),
    }
    body = TargetAssessmentIngestRequest.model_validate(
        {
            "identity": identity.model_dump(mode="json"),
            "stored_state": "verified",
            "compatibility_result": "passed",
            "observations": [observation],
            "observed_at": format_timestamp(observed),
            "expires_at": format_timestamp(expiry),
            "idempotency_key": "invalid-assessment-" + uuid4().hex,
        }
    )
    with pytest.raises(AssessmentError):
        await ingest_assessment(db_session, body)
    assert await db_session.scalar(select(func.count()).select_from(TargetAssessment)) == 0


@pytest.mark.asyncio
async def test_byte_scan_cannot_invent_an_observed_harness_version(
    db_session: AsyncSession,
) -> None:
    metadata, _identity = await _component(db_session, harness_versions=("1.2.3", "1.2.4"))
    passport = ComponentVersionPassport.model_validate(metadata.passport_document)
    digest = passport.adaptations[0].scope_adaptations[0].projection_artifact.digest
    await record_component_scan_assessments(
        db_session,
        plan_id="scan-fixture-" + uuid4().hex,
        passport=passport,
        passport_digest=str(metadata.passport_digest),
        policy_version=POLICY_VERSION,
        payloads_by_digest={
            digest: next(
                item.artifact for item in versions() if item.passport.artifact.digest == digest
            )
        },
        scans_by_digest={
            digest: SafetyScanResult(
                content_digest=digest,
                policy_version=POLICY_VERSION,
                profile="standard",
                outcomes=[
                    CheckOutcome(
                        check_id="artifact_unpack", family="unpack", result="passed", mandatory=True
                    )
                ],
            )
        },
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    rows = (await db_session.scalars(select(TargetAssessment))).all()
    assert len(rows) == 1
    assert rows[0].identity["harness_version"] == "unspecified"
    assert rows[0].stored_state == "not_verified"
    assert rows[0].reason_code == "harness_execution_not_observed"


@pytest.mark.asyncio
@pytest.mark.parametrize("second_state", ["verified", "failed", "not_verified"])
async def test_native_closure_is_checked_per_adaptation_without_poisoning_shared_scans(
    db_session: AsyncSession, second_state: str
) -> None:
    sources = [
        next(
            item
            for item in versions()
            if isinstance(item.passport, ComponentVersionPassport)
            and item.passport.component_type == "instruction"
            and item.passport.adaptations[0].harness_id == harness
        )
        for harness in ["claude-code", "pi"]
    ]
    document = sources[0].passport.model_dump(mode="json")
    document["stable_id"] = new_id("component")
    adaptations: list[dict[str, JsonValue]] = []
    payloads: dict[str, bytes] = {}
    scans: dict[str, SafetyScanResult] = {}
    for index, source in enumerate(sources):
        adaptation = source.passport.model_dump(mode="json")["adaptations"][0]
        scope = adaptation["scope_adaptations"][0]
        adaptation["scope_adaptations"] = [scope]
        scope["supported_harness_versions"] = []
        if index == 1 and second_state == "failed":
            next(member for member in scope["members"] if member["object_type"] == "file")[
                "content_artifact"
            ]["digest"] = sources[0].passport.artifact.digest
        adaptations.append(seal_adaptation(adaptation).model_dump(mode="json"))
        digest = scope["projection_artifact"]["digest"]
        if index == 0 or second_state != "not_verified":
            payloads[digest] = source.artifact
        scans[digest] = SafetyScanResult(
            content_digest=digest,
            policy_version=POLICY_VERSION,
            profile="standard",
            outcomes=[
                CheckOutcome(
                    check_id="artifact_unpack", family="unpack", result="passed", mandatory=True
                )
            ],
        )
    document["adaptations"] = adaptations
    document["revision_id"] = derive_revision_id(document)
    passport = ComponentVersionPassport.model_validate(document)
    await record_component_scan_assessments(
        db_session,
        plan_id="scan-" + uuid4().hex,
        passport=passport,
        passport_digest=digest_canonical("ai-stp:passport:v1", document),
        policy_version=POLICY_VERSION,
        scans_by_digest=scans,
        payloads_by_digest=payloads,
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    rows = (await db_session.scalars(select(TargetAssessment))).all()
    states = {row.identity["harness_id"]: row.stored_state for row in rows}
    assert states == {"claude-code": "verified", "pi": second_state}
    if second_state == "failed":
        failed = next(row for row in rows if row.stored_state == "failed")
        assert failed.reason_code == "projection_integrity_mismatch"
        assert failed.checks_summary is not None
        assert (
            cast(list[dict[str, object]], failed.checks_summary["checks"])[0]["result"] == "failed"
        )
    assert all(scan.outcomes[0].result == "passed" for scan in scans.values())


@pytest.mark.asyncio
@pytest.mark.parametrize("expired_kind", ["target", "common"])
async def test_expired_evidence_removes_badge_from_reads_and_sql_without_refresh(
    db_session: AsyncSession, expired_kind: str
) -> None:
    from ai_stp_platform.catalog_read import current_author_verification, public_version_row
    from ai_stp_platform.catalog_search import search_catalog, upsert_catalog_search_projection
    from ai_stp_platform.models import (
        AccountAuthorVerification,
        CatalogSearchProjection,
        EvidenceBinding,
        PublicationPlan,
        ValidationSnapshot,
    )
    from ai_stp_platform.safety.percent import build_checks_summary

    metadata, identity = await _component(db_session)
    now = datetime.now(UTC)
    for operating_system in ["linux", "windows"]:
        await _append(
            db_session,
            identity.model_copy(update={"operating_system": operating_system}),
            "verified",
        )
    passport = ComponentVersionPassport.model_validate(metadata.passport_document)
    check = {
        "check_id": "artifact_unpack",
        "result": "passed",
        "mandatory": True,
        "source": "platform",
    }
    metadata.checks_summary = build_checks_summary([check])
    metadata.author_verified = True
    db_session.add(AccountAuthorVerification(account_id=metadata.owner_account_id, verified=True))
    plan = PublicationPlan(
        id=new_id("plan"),
        actor_account_id=metadata.owner_account_id,
        device_id=new_id("device"),
        object_kind="component",
        stable_id=metadata.stable_id,
        version=passport.version,
        content_digest=passport.artifact.digest,
        passport=metadata.passport_document,
        policy_version=POLICY_VERSION,
        plan_hash="plan_" + uuid4().hex,
        state="published",
        expires_at=now + timedelta(days=1),
        idempotency_key=uuid4().hex,
    )
    db_session.add(plan)
    await db_session.flush()
    snapshot = ValidationSnapshot(
        id=new_id("snapshot"),
        plan_id=plan.id,
        content_digest=plan.content_digest,
        policy_version=POLICY_VERSION,
        state="passed",
        component_verified=True,
    )
    db_session.add(snapshot)
    await db_session.flush()
    binding = EvidenceBinding(snapshot_id=snapshot.id, **check, expires_at=now + timedelta(hours=1))
    db_session.add(binding)
    await db_session.flush()
    await upsert_catalog_search_projection(
        db_session, object_kind="component", stable_id=metadata.stable_id
    )
    projection = (await db_session.scalars(select(CatalogSearchProjection))).one()
    assert projection.component_verified is True
    assert metadata.component_verified is True
    row = (await current_author_verification(db_session, [public_version_row(metadata)]))[0]
    assert row.component_verified is True

    # Advance beyond the effective proof's expiry by moving the persisted timestamps,
    # without invoking the refresher that previously hid the stale-read defect.
    expired = now - timedelta(seconds=1)
    if expired_kind == "common":
        binding.expires_at = expired
    else:
        histories = (await db_session.scalars(select(TargetAssessment))).all()
        histories[0].expires_at = expired
    projection.component_verified_expires_at = expired
    await db_session.flush()
    assert metadata.component_verified is True
    row = (await current_author_verification(db_session, [public_version_row(metadata)]))[0]
    assert row.component_verified is False
    hits = await search_catalog(
        db_session,
        object_kind="component",
        q=None,
        tags=[],
        harness_id=None,
        component_type=None,
        harness_ids=[],
        component_types=[],
        authors=[],
        verified_only=True,
        sort="updated",
        sort_direction="desc",
        support_tier=None,
        support_state=None,
        service_domain=None,
        country_code=None,
        service_domains=[],
        country_codes=[],
        include_experimental=True,
        include_deprecated=False,
        page_size=20,
        page_number=1,
        after=None,
        query_expression=None,
        updated_from=None,
        updated_to=None,
    )
    assert hits.total_items == 0
    assert hits.rows == []
    await upsert_catalog_search_projection(
        db_session, object_kind="component", stable_id=metadata.stable_id
    )
    assert metadata.component_verified is False
    refreshed = (await db_session.scalars(select(CatalogSearchProjection))).one()
    assert refreshed.component_verified is False
