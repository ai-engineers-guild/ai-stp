from dataclasses import replace
from datetime import UTC, datetime

import pytest

from ai_stp_platform.catalog_read import PublicVersionRow, with_current_author_verification
from ai_stp_platform.models import CatalogMetadata


def test_current_author_verification_overrides_publication_snapshot() -> None:
    metadata = CatalogMetadata(owner_account_id="account_current")
    row = PublicVersionRow(
        metadata=metadata,
        passport={},
        passport_digest="sha256:" + "0" * 64,
        published_at=datetime(2026, 1, 1, tzinfo=UTC),
        trust_lane="experimental",
        author_verified=False,
        component_verified=False,
        lifecycle="active",
        stable_id="component_test",
        version="1.0",
        object_kind="component",
    )

    verified = with_current_author_verification([row], {metadata.owner_account_id: True})

    assert verified == [replace(row, author_verified=True)]


@pytest.mark.asyncio
async def test_author_verification_does_not_overturn_a_safety_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A blocked version keeps its failed safety verdict: author verification
    must not re-mark it component_verified or promote its trust lane."""
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker

    import ai_stp_platform.catalog_search as catalog_search
    from ai_stp_platform import catalog_transfer
    from ai_stp_platform.models import (
        Account,
        AccountAuthorVerification,
        AuditEvent,
    )
    from ai_stp_platform.organization_models import Organization, OrganizationMembership

    engine = create_engine("sqlite://")
    from sqlalchemy import Table

    for cls in (
        Account,
        Organization,
        OrganizationMembership,
        CatalogMetadata,
        AccountAuthorVerification,
        AuditEvent,
    ):
        table = cls.__table__
        assert isinstance(table, Table)
        table.create(engine)
    sync = sessionmaker(bind=engine)()

    class Facade:
        def get_bind(self) -> object:
            return sync.get_bind()

        def add(self, row: object) -> None:
            sync.add(row)

        async def get(self, entity: type[object], ident: object) -> object:
            return sync.get(entity, ident)

        async def scalars(self, statement: object, parameters: object = None) -> object:
            return sync.scalars(statement, parameters)  # type: ignore[arg-type]

        async def flush(self) -> None:
            sync.flush()

    async def noop(*_a: object, **_k: object) -> None:
        return None

    monkeypatch.setattr(catalog_search, "upsert_catalog_search_projection", noop, raising=True)
    try:
        sync.add(Account(id="account_subject"))
        sync.add(Account(id="account_operator"))
        blocked = CatalogMetadata(
            owner_account_id="account_subject",
            object_kind="component",
            stable_id="component_blocked",
            current_revision_id="r" * 73,
            lifecycle_state="blocked",
            trust_lane="experimental",
            author_verified=False,
            component_verified=False,
        )
        sync.add(blocked)
        sync.flush()

        await catalog_transfer.apply_author_verification(
            Facade(),  # type: ignore[arg-type]
            subject_account_id="account_subject",
            verified=True,
            reason="docs verified",
            operator_account_id="account_operator",
        )

        assert blocked.author_verified is True
        # The safety verdict stands: the component axis and lane do not move.
        assert blocked.component_verified is False
        assert blocked.trust_lane == "experimental"

        row = sync.get(AccountAuthorVerification, "account_subject")
        assert row is not None and row.verified is True
        actions = sync.scalars(select(AuditEvent.action)).all()
        assert "staff.author_verified_issued" in actions
    finally:
        sync.close()
        engine.dispose()
