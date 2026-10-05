"""Executable PostgreSQL migration checks for SPEC-020."""

from __future__ import annotations

import asyncio

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine
from ulid import ULID

pytestmark = pytest.mark.platform


async def _scalar(database_url: str, statement: str) -> object:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            return await connection.scalar(text(statement))
    finally:
        await engine.dispose()


def _version(database_url: str) -> object:
    return asyncio.run(_scalar(database_url, "SELECT version_num FROM alembic_version"))


def test_migrations_upgrade_repeat_downgrade_and_upgrade_again(
    isolated_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A broken migration chain fails upgrade idempotency or downgrade compatibility."""
    from alembic.script import ScriptDirectory

    monkeypatch.setenv("AI_STP_DB_URL", isolated_database_url)
    config = Config("alembic.ini")
    heads = ScriptDirectory.from_config(config).get_heads()
    assert len(heads) == 1, f"branched migration history: {sorted(heads)}"
    head = heads[0]

    command.upgrade(config, "head")
    command.upgrade(config, "head")
    assert _version(isolated_database_url) == head

    command.downgrade(config, "0001_create_job")
    assert _version(isolated_database_url) == "0001_create_job"
    assert asyncio.run(_scalar(isolated_database_url, "SELECT to_regclass('public.job')")) == "job"
    assert (
        asyncio.run(_scalar(isolated_database_url, "SELECT to_regclass('public.catalog_metadata')"))
        is None
    )

    command.upgrade(config, "head")
    assert _version(isolated_database_url) == head


#: The module set migrations/env.py registers on Base.metadata.
_MODEL_MODULES = (
    "ai_stp_platform.catalog_ownership_models",
    "ai_stp_platform.dashboard_models",
    "ai_stp_platform.github_models",
    "ai_stp_platform.gitlab_models",
    "ai_stp_platform.grant_identity_models",
    "ai_stp_platform.heartbeat_models",
    "ai_stp_platform.installation_inventory_models",
    "ai_stp_platform.installation_usage_models",
    "ai_stp_platform.models",
    "ai_stp_platform.organization_models",
    "ai_stp_platform.queue.models",
    "ai_stp_platform.runtime_usage_models",
    "ai_stp_platform.technology_models",
    "ai_stp_platform.telemetry_policy_models",
    "ai_stp_platform.content.orm",
    "ai_stp_platform.seo.orm",
)


def _model_drift(database_url: str) -> list[object]:
    """Autogenerate's view of what the models want that the database lacks."""
    import importlib

    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from ai_stp_platform.db import Base

    for module in _MODEL_MODULES:
        importlib.import_module(module)

    async def diff() -> list[object]:
        engine = create_async_engine(database_url)
        try:
            async with engine.connect() as connection:
                return await connection.run_sync(
                    lambda sync_connection: compare_metadata(
                        MigrationContext.configure(sync_connection), Base.metadata
                    )
                )
        finally:
            await engine.dispose()

    return asyncio.run(diff())


def test_models_match_migrated_ddl(
    isolated_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Model metadata must equal the migrated DDL; drift is a missing migration."""
    monkeypatch.setenv("AI_STP_DB_URL", isolated_database_url)
    config = Config("alembic.ini")
    command.upgrade(config, "head")

    assert _model_drift(isolated_database_url) == []


#: `0096_heartbeat_reports` … `0106_technology_review_queue`, the chain the
#: reordered history let applied databases skip (see `0112`).
_SKIPPED_CHAIN = (
    "0096_heartbeat_reports",
    "0097_installation_operation_facts",
    "0098_inventory_scan_policy",
    "0099_installation_inventory",
    "0100_usage_evidence_source",
    "0101_direct_component_usage",
    "0102_usage_collection_policy",
    "0103_report_timezone",
    "0104_project_link_permissions",
    "0105_technology_unmapped_coordinates",
    "0106_technology_review_queue",
)

_CHAIN_TABLES = (
    "installation_heartbeat_event",
    "installation_heartbeat_policy_event",
    "installation_operation_fact",
    "installation_inventory_snapshot",
    "technology_unmapped_coordinate",
)


def _skip_chain_like_production(database_url: str, config: Config) -> None:
    """Leave a database at `0111` without the chain, as production stood.

    The chain's own downgrades remove its objects while `alembic_version`
    stays where it is. `device.display_name` comes back: production carries it
    from `0096_device_session_semantics`, which `0096_heartbeat_reports`'s
    downgrade also drops.
    """
    import sqlalchemy as sa
    from alembic import op
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from alembic.script import ScriptDirectory

    scripts = ScriptDirectory.from_config(config)

    def remove(sync_connection: sa.Connection) -> None:
        with Operations.context(MigrationContext.configure(sync_connection)):
            for skipped in reversed(_SKIPPED_CHAIN):
                script = scripts.get_revision(skipped)
                assert script is not None
                script.module.downgrade()
            op.add_column("device", sa.Column("display_name", sa.String(160), nullable=True))

    async def run() -> None:
        engine = create_async_engine(database_url)
        try:
            async with engine.begin() as connection:
                await connection.run_sync(remove)
        finally:
            await engine.dispose()

    asyncio.run(run())


def _catalog(database_url: str) -> tuple[object, ...]:
    """Columns, constraints, indexes, policies and triggers of the public schema."""

    async def read() -> tuple[object, ...]:
        engine = create_async_engine(database_url)
        try:
            async with engine.connect() as connection:
                parts: list[object] = []
                for statement in (
                    "SELECT table_name, column_name, is_nullable, data_type "
                    "FROM information_schema.columns WHERE table_schema = 'public' "
                    "ORDER BY 1, 2",
                    "SELECT conrelid::regclass::text, conname, pg_get_constraintdef(oid) "
                    "FROM pg_constraint WHERE connamespace = 'public'::regnamespace "
                    "ORDER BY 1, 2",
                    "SELECT tablename, indexname FROM pg_indexes "
                    "WHERE schemaname = 'public' ORDER BY 1, 2",
                    "SELECT tablename, policyname FROM pg_policies "
                    "WHERE schemaname = 'public' ORDER BY 1, 2",
                    "SELECT tgrelid::regclass::text, tgname FROM pg_trigger "
                    "WHERE NOT tgisinternal ORDER BY 1, 2",
                ):
                    rows = await connection.execute(text(statement))
                    parts.append(tuple(tuple(row) for row in rows))
                return tuple(parts)
        finally:
            await engine.dispose()

    return asyncio.run(read())


def test_replay_restores_the_chain_a_reordered_history_skipped(
    isolated_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production stood at `0111` without eleven revisions; `0112` brings them back."""
    monkeypatch.setenv("AI_STP_DB_URL", isolated_database_url)
    config = Config("alembic.ini")
    command.upgrade(config, "0111_corporate_access_provenance")
    complete = _catalog(isolated_database_url)

    _skip_chain_like_production(isolated_database_url, config)
    assert _version(isolated_database_url) == "0111_corporate_access_provenance"
    assert _model_drift(isolated_database_url) != []

    command.upgrade(config, "head")
    assert _model_drift(isolated_database_url) == []
    # Autogenerate does not compare policies, triggers or check constraints;
    # the catalog of a database that ran the chain in order does.
    assert _catalog(isolated_database_url) == complete
    for table in _CHAIN_TABLES:
        assert (
            asyncio.run(
                _scalar(
                    isolated_database_url,
                    "SELECT relrowsecurity AND relforcerowsecurity "
                    f"FROM pg_class WHERE relname = '{table}'",
                )
            )
            is True
        ), table


def test_replay_changes_nothing_on_a_database_that_ran_the_chain(
    isolated_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AI_STP_DB_URL", isolated_database_url)
    config = Config("alembic.ini")
    command.upgrade(config, "0111_corporate_access_provenance")
    before = _catalog(isolated_database_url)
    command.upgrade(config, "head")
    assert _version(isolated_database_url) == "0112_replay_skipped_feature_chain"
    assert _catalog(isolated_database_url) == before


def test_dashboard_migration_has_tenant_policies_and_downgrades(
    isolated_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AI_STP_DB_URL", isolated_database_url)
    config = Config("alembic.ini")
    command.upgrade(config, "0092_corporate_dashboard")
    for table in ("corporate_ci_check", "corporate_dashboard_view"):
        assert (
            asyncio.run(_scalar(isolated_database_url, f"SELECT to_regclass('public.{table}')"))
            == table
        )
        assert (
            asyncio.run(
                _scalar(
                    isolated_database_url,
                    "SELECT relrowsecurity AND relforcerowsecurity "
                    f"FROM pg_class WHERE relname = '{table}'",
                )
            )
            is True
        )
    command.downgrade(config, "0091_gitlab_project_observations")
    for table in ("corporate_ci_check", "corporate_dashboard_view"):
        assert (
            asyncio.run(_scalar(isolated_database_url, f"SELECT to_regclass('public.{table}')"))
            is None
        )


def test_job_title_migrations_upgrade_and_downgrade_cleanly(
    isolated_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AI_STP_DB_URL", isolated_database_url)
    config = Config("alembic.ini")
    command.upgrade(config, "0078_corporate_catalog_permissions")
    organization_id = f"organization_{ULID()}"

    async def seed_superadmin_role() -> None:
        engine = create_async_engine(isolated_database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO organization (id, kind, display_name) "
                        "VALUES (:id, 'corporate', 'Migration test')"
                    ),
                    {"id": organization_id},
                )
                await connection.execute(
                    text(
                        "INSERT INTO corporate_role (organization_id, name) "
                        "VALUES (:id, 'superadmin')"
                    ),
                    {"id": organization_id},
                )
        finally:
            await engine.dispose()

    asyncio.run(seed_superadmin_role())
    command.upgrade(config, "0079_corporate_job_title_permissions")
    assert (
        asyncio.run(
            _scalar(isolated_database_url, "SELECT to_regclass('public.corporate_job_title')")
        )
        == "corporate_job_title"
    )
    assert (
        asyncio.run(
            _scalar(
                isolated_database_url,
                "SELECT COUNT(*) FROM information_schema.columns "
                "WHERE table_name = 'organization_membership' AND column_name = 'job_title_id'",
            )
        )
        == 1
    )
    assert (
        asyncio.run(
            _scalar(
                isolated_database_url,
                "SELECT COUNT(*) FROM corporate_role_permission "
                "WHERE permission LIKE 'job_title.%'",
            )
        )
        == 4
    )

    command.downgrade(config, "0078_corporate_catalog_permissions")
    assert (
        asyncio.run(
            _scalar(
                isolated_database_url,
                "SELECT COUNT(*) FROM corporate_role_permission "
                "WHERE permission LIKE 'job_title.%'",
            )
        )
        == 0
    )
    command.downgrade(config, "0076_milestone5_corporate_governance")
    assert (
        asyncio.run(
            _scalar(isolated_database_url, "SELECT to_regclass('public.corporate_job_title')")
        )
        is None
    )
    assert (
        asyncio.run(
            _scalar(
                isolated_database_url,
                "SELECT COUNT(*) FROM information_schema.columns "
                "WHERE table_name = 'organization_membership' AND column_name = 'job_title_id'",
            )
        )
        == 0
    )

    command.upgrade(config, "head")


def test_identity_migration_preserves_distinct_account_suffixes(
    isolated_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Truncating ULIDs makes a populated deployment fail while an empty DB passes."""
    from alembic.script import ScriptDirectory

    from ai_stp_foundation.identity import HANDLE_MAX_LENGTH, normalize_handle

    monkeypatch.setenv("AI_STP_DB_URL", isolated_database_url)
    config = Config("alembic.ini")
    scripts = ScriptDirectory.from_config(config)
    identity = scripts.get_revision("0040_public_identities_official_sync")
    assert identity is not None
    assert isinstance(identity.down_revision, str)
    command.upgrade(config, identity.down_revision)
    account_ids = tuple(f"account_{ULID.from_int(value)}" for value in (1, 2))

    async def seed() -> None:
        engine = create_async_engine(isolated_database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text("INSERT INTO account (id) VALUES (:id)"),
                    [{"id": account_id} for account_id in account_ids],
                )
        finally:
            await engine.dispose()

    async def names() -> list[tuple[str, str, str]]:
        engine = create_async_engine(isolated_database_url)
        try:
            async with engine.connect() as connection:
                rows = await connection.execute(
                    text("SELECT id, handle, display_name FROM account ORDER BY id")
                )
                return [(row[0], row[1], row[2]) for row in rows]
        finally:
            await engine.dispose()

    asyncio.run(seed())
    command.upgrade(config, "head")
    assigned = asyncio.run(names())
    assert {row[0] for row in assigned} == set(account_ids)
    assert len({row[1] for row in assigned}) == len(account_ids)
    assert len({row[2] for row in assigned}) == len(account_ids)
    assert all(normalize_handle(row[1]) == row[1] for row in assigned)
    assert all(len(row[1]) <= HANDLE_MAX_LENGTH for row in assigned)

    command.upgrade(config, "head")
    assert asyncio.run(names()) == assigned


def test_organization_identity_and_ownership_invariants(
    migrated_database_url: str,
) -> None:
    account_id = f"account_{ULID()}"
    other_account_id = f"account_{ULID()}"
    personal_id = f"organization_{ULID()}"

    async def exercise() -> None:
        engine = create_async_engine(migrated_database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text("INSERT INTO account (id) VALUES (:id), (:other_id)"),
                    {"id": account_id, "other_id": other_account_id},
                )

            with pytest.raises(DBAPIError):
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            "INSERT INTO organization "
                            "(id, kind, owner_account_id, display_name) "
                            "VALUES (:id, 'personal', NULL, 'Invalid')"
                        ),
                        {"id": f"organization_{ULID()}"},
                    )

            with pytest.raises(DBAPIError):
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            "INSERT INTO organization "
                            "(id, kind, owner_account_id, display_name) "
                            "VALUES (:id, 'corporate', :owner, 'Invalid')"
                        ),
                        {"id": f"organization_{ULID()}", "owner": account_id},
                    )

            with pytest.raises(DBAPIError):
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            "INSERT INTO organization "
                            "(id, kind, owner_account_id, display_name) "
                            "VALUES ('not_an_organization', 'personal', :owner, 'Invalid')"
                        ),
                        {"owner": account_id},
                    )

            with pytest.raises(DBAPIError):
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            "INSERT INTO organization "
                            "(id, kind, owner_account_id, display_name) "
                            "VALUES (:id, 'personal', :owner, 'Missing membership')"
                        ),
                        {"id": f"organization_{ULID()}", "owner": account_id},
                    )

            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO organization "
                        "(id, kind, owner_account_id, display_name) "
                        "VALUES (:id, 'personal', :owner, 'Personal')"
                    ),
                    {"id": personal_id, "owner": account_id},
                )
                await connection.execute(
                    text(
                        "INSERT INTO organization_membership "
                        "(organization_id, account_id, role, state) "
                        "VALUES (:organization, :account, 'owner', 'active')"
                    ),
                    {"organization": personal_id, "account": account_id},
                )

            with pytest.raises(DBAPIError):
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            "INSERT INTO organization_membership "
                            "(organization_id, account_id, role, state) "
                            "VALUES (:organization, :account, 'member', 'active')"
                        ),
                        {"organization": personal_id, "account": other_account_id},
                    )

            with pytest.raises(DBAPIError):
                async with engine.begin() as connection:
                    await connection.execute(
                        text("UPDATE organization SET kind = 'corporate' WHERE id = :id"),
                        {"id": personal_id},
                    )
        finally:
            await engine.dispose()

    asyncio.run(exercise())
