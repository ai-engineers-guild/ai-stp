"""Populated-data boundaries for the Official locale repair (SPEC-059)."""

from __future__ import annotations

import asyncio

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Table, insert, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from ulid import ULID

from ai_stp_contracts.official_manifest import load_official_manifest
from ai_stp_foundation.identity import normalize_display_key
from ai_stp_platform.models import (
    Account,
    CatalogIdentity,
    CatalogIdentityLocale,
    OfficialUpstreamSource,
)

pytestmark = pytest.mark.platform


@pytest.mark.parametrize("conflicting_locale", ["en", "ru"])
def test_locale_repair_preserves_nonconflicting_names(
    isolated_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
    conflicting_locale: str,
) -> None:
    """One source must not rename every other owner's localized catalog names."""
    monkeypatch.setenv("AI_STP_DB_URL", isolated_database_url)
    config = Config("alembic.ini")
    revision = ScriptDirectory.from_config(config).get_revision(
        "0047_repair_official_locale_collisions"
    )
    assert revision is not None
    assert isinstance(revision.down_revision, str)
    command.upgrade(config, revision.down_revision)
    manifest = load_official_manifest()
    entry = next(item for item in manifest.entries if item.canonical_name == "ai-repo-safety")
    owner_id = f"account_{ULID.from_int(1)}"
    legacy_id = f"component_{ULID.from_int(1)}"
    unrelated_id = f"component_{ULID.from_int(2)}"
    names = {"en": entry.display_name_en, "ru": entry.display_name_ru}
    canonical = entry.canonical_name + "-legacy"
    original: dict[tuple[str, str], str] = {}

    async def seed() -> None:
        engine = create_async_engine(isolated_database_url)
        try:
            async with async_sessionmaker(engine)() as session, session.begin():
                session.add_all([Account(id=owner_id), Account(id=manifest.official_account_id)])
                await session.flush()
                columns = set(OfficialUpstreamSource.__table__.columns.keys())
                source = {key: value for key, value in entry.model_dump().items() if key in columns}
                source.update(
                    id=entry.source_id,
                    owner_account_id=manifest.official_account_id,
                    actor_device_id=f"device_{ULID.from_int(1)}",
                    name=entry.display_name_en,
                )
                source.pop("organization_id", None)
                source_table = OfficialUpstreamSource.__table__
                assert isinstance(source_table, Table)
                await session.execute(insert(source_table).values(source))
                for stable_id, slug in ((legacy_id, canonical), (unrelated_id, "review-tool")):
                    identity_table = CatalogIdentity.__table__
                    assert isinstance(identity_table, Table)
                    await session.execute(
                        insert(identity_table).values(
                            stable_id=stable_id,
                            owner_account_id=owner_id,
                            canonical_name=slug,
                            canonical_name_normalized=slug,
                        )
                    )
                    for locale in names:
                        display = (
                            names[locale]
                            if stable_id == legacy_id and locale == conflicting_locale
                            else f"Independent {slug} {locale}"
                        )
                        original[(stable_id, locale)] = display
                        session.add(
                            CatalogIdentityLocale(
                                stable_id=stable_id,
                                locale=locale,
                                display_name=display,
                                display_name_normalized=normalize_display_key(display),
                            )
                        )
        finally:
            await engine.dispose()

    async def read() -> dict[tuple[str, str], str]:
        engine = create_async_engine(isolated_database_url)
        try:
            async with async_sessionmaker(engine)() as session:
                rows = await session.scalars(select(CatalogIdentityLocale))
                return {(row.stable_id, row.locale): row.display_name for row in rows}
        finally:
            await engine.dispose()

    asyncio.run(seed())
    command.upgrade(config, "head")
    expected = original | {(legacy_id, conflicting_locale): canonical}
    assert asyncio.run(read()) == expected
    command.upgrade(config, "head")
    assert asyncio.run(read()) == expected
