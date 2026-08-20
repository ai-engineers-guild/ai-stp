"""The inventory of published versions the public projection cannot read."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_platform.catalog_reconcile import reconcile_catalog_integrity
from ai_stp_platform.catalog_seed import seed_corpus
from ai_stp_platform.models import Account, CatalogMetadata

pytestmark = pytest.mark.platform


def _seed_component() -> tuple[dict[str, object], str]:
    kind, passport, _published, digest = next(c for c in seed_corpus() if c[0] == "component")
    assert kind == "component"
    return dict(passport), digest


def _owner_of(passport: dict[str, object]) -> str:
    return str(passport.get("owner_id") or "account_x")


def _row(*, passport: dict[str, object], digest: str, version: str = "1.0") -> CatalogMetadata:
    return CatalogMetadata(
        owner_account_id=_owner_of(passport),
        object_kind="component",
        stable_id=str(passport.get("stable_id") or "component_x"),
        version=str(passport.get("version") or version),
        current_revision_id=str(passport.get("revision_id") or "revision_" + "0" * 64),
        visibility="public",
        lifecycle_state="active",
        published_at=datetime(2026, 8, 5, tzinfo=UTC),
        trust_lane="experimental",
        author_verified=False,
        component_verified=False,
        passport_digest=digest,
        passport_document=passport,
    )


@pytest.mark.asyncio
async def test_a_healthy_catalog_reports_no_unreadable_versions(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    passport, digest = _seed_component()
    async with db_sessionmaker() as session:
        session.add(Account(id=_owner_of(passport)))
        await session.flush()
        session.add(_row(passport=passport, digest=digest))
        await session.commit()

        report = await reconcile_catalog_integrity(session)

    assert report.checked >= 1
    assert report.healthy
    assert report.unreadable == []


@pytest.mark.asyncio
async def test_a_poisoned_version_is_named_with_its_identity_and_reason(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """The count alone cannot drive a recovery — an immutable X.Y needs naming.

    The same version cannot be republished under its own number, so whoever
    plans the repair has to know exactly which objects and versions are
    affected before deciding anything.
    """
    passport, _digest = _seed_component()
    async with db_sessionmaker() as session:
        session.add(Account(id=_owner_of(passport)))
        await session.flush()
        session.add(_row(passport=passport, digest="sha256:" + "1" * 64))
        await session.commit()

        report = await reconcile_catalog_integrity(session)

    assert not report.healthy
    assert len(report.unreadable) == 1
    found = report.unreadable[0]
    assert found.object_kind == "component"
    assert found.stable_id == str(passport["stable_id"])
    assert found.version == str(passport["version"])
    assert "digest" in found.reason


@pytest.mark.asyncio
async def test_the_sweep_uses_the_same_rules_as_the_read_path(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """A row refused for a reason other than its digest is caught too.

    The inventory calls the projection's own verification rather than a second
    implementation, so it cannot drift from the behaviour it describes. Editing
    the stored passport breaks its revision seal, and the seal is checked before
    visibility — so this also pins the order: content tampering is caught as
    tampering, not as a policy violation further down.
    """
    passport, _digest = _seed_component()
    private = dict(passport) | {"visibility": "private"}
    async with db_sessionmaker() as session:
        session.add(Account(id=_owner_of(private)))
        await session.flush()
        session.add(_row(passport=private, digest="sha256:" + ("0" * 64)))
        await session.commit()

        report = await reconcile_catalog_integrity(session)

    assert not report.healthy
    reasons = [item.reason for item in report.unreadable]
    assert reasons == ["passport revision seal mismatch"], reasons
