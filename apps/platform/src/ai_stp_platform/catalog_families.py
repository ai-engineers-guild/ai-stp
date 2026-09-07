"""Setup family persistence and public/owner projections (SPEC-065)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_contracts.families import (
    SetupFamilyCreateRequest,
    SetupFamilyMember,
    SetupFamilyOwner,
    SetupFamilyPatchRequest,
    SetupFamilyPublic,
)
from ai_stp_foundation.ids import new_id
from ai_stp_foundation.refs import SetupRef
from ai_stp_passports.versions import SetupVersionPassport
from ai_stp_platform.catalog_read import PUBLIC_LIFECYCLES
from ai_stp_platform.catalog_targets import alignment_state
from ai_stp_platform.models import (
    AuditEvent,
    CatalogMetadata,
    CatalogSearchProjection,
    SetupFamily,
    SetupFamilyRevision,
)
from ai_stp_platform.models import SetupFamilyMember as FamilyMemberRow


class FamilyError(ValueError):
    """Domain failure for family mutations."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _baseline_payload(family: SetupFamily) -> dict[str, str]:
    return {
        "stable_id": family.baseline_stable_id,
        "version": family.baseline_version,
        "passport_digest": family.baseline_passport_digest,
    }


async def _owned_setup(
    session: AsyncSession, *, owner_id: str, stable_id: str, version: str | None = None
) -> CatalogMetadata | None:
    stmt = select(CatalogMetadata).where(
        CatalogMetadata.object_kind == "setup",
        CatalogMetadata.stable_id == stable_id,
        CatalogMetadata.owner_account_id == owner_id,
        CatalogMetadata.version.is_not(None),
        CatalogMetadata.passport_document.is_not(None),
    )
    if version is not None:
        stmt = stmt.where(CatalogMetadata.version == version)
    rows = list((await session.execute(stmt)).scalars().all())
    if not rows:
        return None
    if version is not None:
        return rows[0]
    return max(rows, key=lambda row: tuple(int(part) for part in str(row.version).split(".")))


async def _public_setups(
    session: AsyncSession, stable_ids: Sequence[str]
) -> tuple[dict[str, CatalogMetadata], dict[tuple[str, str], CatalogMetadata]]:
    """Load latest and exact public members in one bounded family read."""
    if not stable_ids:
        return {}, {}
    rows = list(
        (
            await session.execute(
                select(CatalogMetadata).where(
                    CatalogMetadata.object_kind == "setup",
                    CatalogMetadata.stable_id.in_(list(stable_ids)),
                    CatalogMetadata.visibility == "public",
                    CatalogMetadata.lifecycle_state.in_(tuple(PUBLIC_LIFECYCLES)),
                    CatalogMetadata.published_at.is_not(None),
                    CatalogMetadata.passport_document.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )
    latest: dict[str, CatalogMetadata] = {}
    exact: dict[tuple[str, str], CatalogMetadata] = {}
    for row in rows:
        if not row.version:
            continue
        exact[(row.stable_id, str(row.version))] = row
        current = latest.get(row.stable_id)
        if current is None or _version_parts(str(row.version)) > _version_parts(
            str(current.version or "0.0")
        ):
            latest[row.stable_id] = row
    return latest, exact


def _harness_of(row: CatalogMetadata) -> str:
    passport = SetupVersionPassport.model_validate(row.passport_document)
    return passport.harness_id


def _invariant_of(row: CatalogMetadata) -> str | None:
    passport = SetupVersionPassport.model_validate(row.passport_document)
    return passport.harness_invariant_digest


async def _member_rows(session: AsyncSession, family_id: str) -> list[FamilyMemberRow]:
    result = await session.execute(
        select(FamilyMemberRow)
        .where(FamilyMemberRow.family_id == family_id)
        .order_by(FamilyMemberRow.harness_id, FamilyMemberRow.stable_id)
    )
    return list(result.scalars().all())


async def project_family(
    session: AsyncSession,
    family: SetupFamily,
    *,
    current_stable_id: str | None,
    exact_version: str | None,
    authorized_owner_id: str | None,
) -> SetupFamilyPublic | SetupFamilyOwner:
    """Public members only; owner diagnostics never name foreign identities."""
    authorized = authorized_owner_id is not None and authorized_owner_id == family.owner_account_id
    member_rows = await _member_rows(session, family.family_id)
    latest_by_id, exact_by_id = await _public_setups(
        session,
        [family.baseline_stable_id, *(row.stable_id for row in member_rows)],
    )
    baseline_row = exact_by_id.get((family.baseline_stable_id, family.baseline_version))
    baseline_digest = _invariant_of(baseline_row) if baseline_row is not None else None
    members: list[SetupFamilyMember] = []
    diagnostics: list[str] = []
    for row in member_rows:
        latest = latest_by_id.get(row.stable_id)
        if latest is None:
            if authorized:
                diagnostics.append("inaccessible_member")
            continue
        version_row = latest
        if exact_version is not None and row.stable_id == current_stable_id:
            pinned = exact_by_id.get((row.stable_id, exact_version))
            if pinned is not None:
                version_row = pinned
        alignment = alignment_state(
            member_digest=_invariant_of(version_row),
            baseline_digest=baseline_digest,
            member_accessible=True,
            authorized=authorized,
        )
        passport = SetupVersionPassport.model_validate(version_row.passport_document)
        members.append(
            SetupFamilyMember(
                name=str(version_row.name or passport.name),
                stable_id=row.stable_id,  # type: ignore[arg-type]
                harness_id=row.harness_id,  # type: ignore[arg-type]
                latest_version=str(latest.version) if latest.version else None,  # type: ignore[arg-type]
                exact_version=str(version_row.version) if version_row.version else None,  # type: ignore[arg-type]
                passport_digest=version_row.passport_digest,  # type: ignore[arg-type]
                alignment=alignment,  # type: ignore[arg-type]
                ported_from=passport.ported_from,
            )
        )
    current = next((item for item in members if item.stable_id == current_stable_id), None)
    public = SetupFamilyPublic(
        family_id=family.family_id,  # type: ignore[arg-type]
        name=family.name,
        baseline=SetupRef(
            stable_id=family.baseline_stable_id,  # type: ignore[arg-type]
            version=family.baseline_version,  # type: ignore[arg-type]
            passport_digest=family.baseline_passport_digest,  # type: ignore[arg-type]
        ),
        current_member=current,
        members=members,
        created_from=family.created_from,  # type: ignore[arg-type]
    )
    if not authorized:
        return public
    actions = ["update_name", "change_baseline", "add_member", "remove_member"]
    return SetupFamilyOwner(
        **public.model_dump(),
        revision=family.revision,
        diagnostics=diagnostics,
        allowed_actions=actions,
    )


async def family_for_setup(session: AsyncSession, stable_id: str) -> SetupFamily | None:
    member = (
        await session.execute(select(FamilyMemberRow).where(FamilyMemberRow.stable_id == stable_id))
    ).scalar_one_or_none()
    if member is None:
        return None
    return await session.get(SetupFamily, member.family_id)


async def create_family(
    session: AsyncSession,
    *,
    owner_id: str,
    body: SetupFamilyCreateRequest,
    created_from: Literal["recast", "owner", "staff_migration", "migration"] = "owner",
) -> SetupFamily:
    existing = (
        await session.execute(
            select(SetupFamily).where(SetupFamily.create_idempotency_key == body.idempotency_key)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    if len(body.members) < 2:
        raise FamilyError("AI_STP_VALIDATION_ERROR", "a family must have at least two members")
    harnesses: dict[str, str] = {}
    for stable_id in body.members:
        row = await _owned_setup(session, owner_id=owner_id, stable_id=stable_id)
        if row is None:
            raise FamilyError("AI_STP_NOT_FOUND", "family member is not an owned setup")
        already = (
            await session.execute(
                select(FamilyMemberRow).where(FamilyMemberRow.stable_id == stable_id)
            )
        ).scalar_one_or_none()
        if already is not None:
            raise FamilyError("AI_STP_CONFLICT", "a setup belongs to at most one active family")
        harness = _harness_of(row)
        if harness in harnesses:
            raise FamilyError("AI_STP_CONFLICT", "a family has at most one member per harness")
        harnesses[harness] = stable_id
    baseline_row = await _owned_setup(
        session,
        owner_id=owner_id,
        stable_id=body.baseline.stable_id,
        version=body.baseline.version,
    )
    if baseline_row is None:
        raise FamilyError("AI_STP_NOT_FOUND", "family baseline is not an accessible owned setup")
    if baseline_row.passport_digest != body.baseline.passport_digest:
        raise FamilyError("AI_STP_CATALOG_INTEGRITY", "family baseline digest does not match")
    family = SetupFamily(
        family_id=new_id("family"),
        owner_account_id=owner_id,
        name=body.name,
        baseline_stable_id=body.baseline.stable_id,
        baseline_version=body.baseline.version,
        baseline_passport_digest=body.baseline.passport_digest,
        created_from=created_from,
        revision=1,
        create_idempotency_key=body.idempotency_key,
    )
    session.add(family)
    for harness_id, stable_id in harnesses.items():
        session.add(
            FamilyMemberRow(family_id=family.family_id, stable_id=stable_id, harness_id=harness_id)
        )
    session.add(
        SetupFamilyRevision(
            family_id=family.family_id,
            revision=1,
            actor_account_id=owner_id,
            reason=body.reason,
            previous_baseline=None,
            new_baseline=_baseline_payload(family),
            added_members=list(body.members),
            removed_members=[],
            idempotency_key=body.idempotency_key,
        )
    )
    await session.flush()
    return family


async def patch_family(
    session: AsyncSession,
    *,
    owner_id: str,
    family_id: str,
    body: SetupFamilyPatchRequest,
) -> SetupFamily:
    replay = (
        await session.execute(
            select(SetupFamilyRevision).where(
                SetupFamilyRevision.idempotency_key == body.idempotency_key
            )
        )
    ).scalar_one_or_none()
    family = await session.get(SetupFamily, family_id)
    if replay is not None:
        if family is None or replay.family_id != family_id:
            raise FamilyError("AI_STP_CONFLICT", "idempotency key is bound to another family")
        return family
    if family is None or family.owner_account_id != owner_id:
        raise FamilyError("AI_STP_NOT_FOUND", "family not found")
    if family.revision != body.expected_revision:
        raise FamilyError("AI_STP_CONFLICT", "family revision does not match")
    previous = _baseline_payload(family)
    members = await _member_rows(session, family.family_id)
    by_id = {item.stable_id: item for item in members}
    for stable_id in body.remove_members:
        row = by_id.get(stable_id)
        if row is None:
            raise FamilyError("AI_STP_VALIDATION_ERROR", "removed member is not in the family")
        await session.delete(row)
        del by_id[stable_id]
    for stable_id in body.add_members:
        if stable_id in by_id:
            raise FamilyError("AI_STP_CONFLICT", "member is already in the family")
        owned = await _owned_setup(session, owner_id=owner_id, stable_id=stable_id)
        if owned is None:
            raise FamilyError("AI_STP_NOT_FOUND", "added member is not an owned setup")
        already = (
            await session.execute(
                select(FamilyMemberRow).where(FamilyMemberRow.stable_id == stable_id)
            )
        ).scalar_one_or_none()
        if already is not None:
            raise FamilyError("AI_STP_CONFLICT", "a setup belongs to at most one active family")
        harness = _harness_of(owned)
        if any(item.harness_id == harness for item in by_id.values()):
            raise FamilyError("AI_STP_CONFLICT", "a family has at most one member per harness")
        added = FamilyMemberRow(family_id=family.family_id, stable_id=stable_id, harness_id=harness)
        session.add(added)
        by_id[stable_id] = added
    if len(by_id) < 2:
        raise FamilyError("AI_STP_VALIDATION_ERROR", "a family must have at least two members")
    if body.name is not None:
        family.name = body.name
    if body.baseline is not None:
        if body.baseline.stable_id not in by_id:
            raise FamilyError("AI_STP_VALIDATION_ERROR", "family baseline must be a member")
        baseline = await _owned_setup(
            session,
            owner_id=owner_id,
            stable_id=body.baseline.stable_id,
            version=body.baseline.version,
        )
        if baseline is None or baseline.passport_digest != body.baseline.passport_digest:
            raise FamilyError("AI_STP_CATALOG_INTEGRITY", "family baseline digest does not match")
        family.baseline_stable_id = body.baseline.stable_id
        family.baseline_version = body.baseline.version
        family.baseline_passport_digest = body.baseline.passport_digest
    elif family.baseline_stable_id not in by_id:
        raise FamilyError("AI_STP_VALIDATION_ERROR", "family baseline must remain a member")
    family.revision += 1
    family.updated_at = datetime.now(UTC)
    session.add(
        SetupFamilyRevision(
            family_id=family.family_id,
            revision=family.revision,
            actor_account_id=owner_id,
            reason=body.reason,
            previous_baseline=previous,
            new_baseline=_baseline_payload(family),
            added_members=list(body.add_members),
            removed_members=list(body.remove_members),
            idempotency_key=body.idempotency_key,
        )
    )
    await session.flush()
    return family


def _version_parts(version: str) -> tuple[int, int]:
    major, minor = version.split(".", 1)
    return int(major), int(minor)


def _invariant_of_meta(meta: CatalogMetadata | None) -> str | None:
    if meta is None:
        return None
    return _invariant_of(meta)


async def fill_search_projection_family_fields(
    session: AsyncSession, rows: Sequence[CatalogSearchProjection]
) -> None:
    """Attach family search columns in a bounded number of queries."""
    setup_rows = [row for row in rows if row.object_kind == "setup"]
    if not setup_rows:
        return
    ids = [row.stable_id for row in setup_rows]
    members = list(
        (await session.execute(select(FamilyMemberRow).where(FamilyMemberRow.stable_id.in_(ids))))
        .scalars()
        .all()
    )
    by_setup = {item.stable_id: item for item in members}
    if not by_setup:
        return
    family_ids = {item.family_id for item in members}
    families = {
        item.family_id: item
        for item in (
            await session.execute(select(SetupFamily).where(SetupFamily.family_id.in_(family_ids)))
        )
        .scalars()
        .all()
    }
    all_members = list(
        (
            await session.execute(
                select(FamilyMemberRow).where(FamilyMemberRow.family_id.in_(family_ids))
            )
        )
        .scalars()
        .all()
    )
    members_by_family: dict[str, list[FamilyMemberRow]] = {}
    for item in all_members:
        members_by_family.setdefault(item.family_id, []).append(item)
    needed_ids = {item.stable_id for item in all_members}
    needed_ids.update(family.baseline_stable_id for family in families.values())
    public_rows = list(
        (
            await session.execute(
                select(CatalogMetadata).where(
                    CatalogMetadata.object_kind == "setup",
                    CatalogMetadata.stable_id.in_(list(needed_ids)),
                    CatalogMetadata.visibility == "public",
                    CatalogMetadata.lifecycle_state.in_(tuple(PUBLIC_LIFECYCLES)),
                    CatalogMetadata.published_at.is_not(None),
                    CatalogMetadata.passport_document.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )
    public_latest: dict[str, CatalogMetadata] = {}
    public_exact: dict[tuple[str, str], CatalogMetadata] = {}
    for meta in public_rows:
        public_exact[(meta.stable_id, str(meta.version))] = meta
        current = public_latest.get(meta.stable_id)
        if current is None or _version_parts(str(meta.version)) > _version_parts(
            str(current.version or "0.0")
        ):
            public_latest[meta.stable_id] = meta
    for row in setup_rows:
        member = by_setup.get(row.stable_id)
        if member is None:
            continue
        family = families.get(member.family_id)
        if family is None:
            continue
        family_members = members_by_family.get(family.family_id, [])
        accessible = sum(1 for item in family_members if item.stable_id in public_latest)
        current = public_latest.get(row.stable_id)
        baseline = public_exact.get((family.baseline_stable_id, family.baseline_version))
        row.family_id = family.family_id
        row.family_member_count = accessible
        row.family_alignment = alignment_state(
            member_digest=_invariant_of_meta(current),
            baseline_digest=_invariant_of_meta(baseline),
            member_accessible=current is not None,
            authorized=False,
        )


def _recast_idempotency_key(source_stable_id: str, target_stable_id: str) -> str:
    return f"recast.{source_stable_id}.{target_stable_id}"


def _record_family_audit(
    session: AsyncSession,
    *,
    owner_id: str,
    family_id: str,
    action: str,
    reason: str,
    payload: dict[str, object],
) -> None:
    session.add(
        AuditEvent(
            actor_account_id=owner_id,
            action=action,
            target_table="setup_family",
            target_id=family_id,
            reason=reason,
            payload=payload,
        )
    )


async def apply_recast_family_effect(
    session: AsyncSession, published: CatalogMetadata
) -> SetupFamily | None:
    """Join or create a family after authorized recast publication (REQ-6510/6511).

    Provenance stays on the passport regardless of the outcome. Policy refusals
    (cross-owner, missing source, duplicate harness, existing other family) skip
    the mutable family write and do not fail publication.
    """
    if published.object_kind != "setup" or published.passport_document is None:
        return None
    passport = SetupVersionPassport.model_validate(published.passport_document)
    source_ref = passport.ported_from
    if source_ref is None:
        return None
    owner_id = published.owner_account_id
    source = await _owned_setup(
        session,
        owner_id=owner_id,
        stable_id=source_ref.stable_id,
        version=source_ref.version,
    )
    if source is None or source.passport_digest != source_ref.passport_digest:
        return None
    key = _recast_idempotency_key(source_ref.stable_id, published.stable_id)
    replay = (
        await session.execute(
            select(SetupFamilyRevision).where(SetupFamilyRevision.idempotency_key == key)
        )
    ).scalar_one_or_none()
    if replay is not None:
        return await session.get(SetupFamily, replay.family_id)
    source_family = await family_for_setup(session, source_ref.stable_id)
    target_family = await family_for_setup(session, published.stable_id)
    if source_family is not None and target_family is not None:
        if source_family.family_id == target_family.family_id:
            return source_family
        return None
    if target_family is not None:
        return None
    if source_family is not None:
        if source_family.owner_account_id != owner_id:
            return None
        try:
            family = await patch_family(
                session,
                owner_id=owner_id,
                family_id=source_family.family_id,
                body=SetupFamilyPatchRequest.model_validate(
                    {
                        "schema_version": 1,
                        "expected_revision": source_family.revision,
                        "idempotency_key": key,
                        "add_members": [published.stable_id],
                        "reason": "recast_join",
                    }
                ),
            )
        except FamilyError:
            return None
        _record_family_audit(
            session,
            owner_id=owner_id,
            family_id=family.family_id,
            action="family.recast_join",
            reason="recast_join",
            payload={
                "source_stable_id": source_ref.stable_id,
                "target_stable_id": published.stable_id,
            },
        )
        return family
    name = (source.name or source.stable_id).strip() or source.stable_id
    try:
        family = await create_family(
            session,
            owner_id=owner_id,
            body=SetupFamilyCreateRequest.model_validate(
                {
                    "schema_version": 1,
                    "name": name[:200],
                    "baseline": {
                        "stable_id": source_ref.stable_id,
                        "version": source_ref.version,
                        "passport_digest": source_ref.passport_digest,
                    },
                    "members": [source_ref.stable_id, published.stable_id],
                    "expected_revision": 0,
                    "idempotency_key": key,
                    "reason": "recast_create",
                }
            ),
            created_from="recast",
        )
    except FamilyError:
        return None
    _record_family_audit(
        session,
        owner_id=owner_id,
        family_id=family.family_id,
        action="family.recast_create",
        reason="recast_create",
        payload={
            "source_stable_id": source_ref.stable_id,
            "target_stable_id": published.stable_id,
        },
    )
    return family
