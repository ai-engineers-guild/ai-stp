"""Static migration checks for the platform Alembic tree (SPEC-020)."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text

import ai_stp_platform.content.orm
import ai_stp_platform.models
import ai_stp_platform.organization_models
import ai_stp_platform.queue.models
import ai_stp_platform.seo.orm
from ai_stp_platform.db import Base

pytestmark = pytest.mark.platform


def test_alembic_history_has_single_head() -> None:
    """A branched history is the defect; the head's name is not.

    Pinning the literal head made this fail on every legitimate migration, so
    the fix was always "update the string" — including on the day the history
    actually branches, which is the one case the test exists to catch.
    """
    script = ScriptDirectory.from_config(Config("alembic.ini"))

    heads = script.get_heads()
    assert len(heads) == 1, f"branched migration history: {sorted(heads)}"


def test_sprint1_models_are_registered_on_platform_base() -> None:
    assert ai_stp_platform.models.Account.__tablename__ == "account"
    assert ai_stp_platform.organization_models.Organization.__tablename__ == "organization"
    assert ai_stp_platform.queue.models.Job.__tablename__ == "job"
    assert ai_stp_platform.seo.orm.SeoFactSnapshot.__tablename__ == "seo_fact_snapshot"
    assert ai_stp_platform.content.orm.Article.__tablename__ == "article"
    expected_tables = {
        "account",
        "oauth_identity",
        "device",
        "account_session",
        "catalog_metadata",
        "object_location",
        "audit_event",
        "job",
        "seo_fact_snapshot",
        "seo_revision",
        "seo_active_revision",
        "article",
        "article_revision",
        "article_active",
        "article_repository_state",
        "official_upstream_source",
        "official_upstream_sync",
        "ownership_claim",
        "ownership_revision",
        "organization",
        "organization_membership",
        "project_identity",
        "project_link",
        "project_link_plan",
        "project_unlink_plan",
        "project_sync_plan",
        "organization_resource",
        "project_revision",
        "project_revision_head",
        "project_revision_receipt",
        "project_link_proposal",
    }

    assert expected_tables.issubset(Base.metadata.tables)


def test_audit_migration_defines_append_only_trigger() -> None:
    source = Path("migrations/versions/0002_sprint1_core.py").read_text(encoding="utf-8")
    assert "CREATE TRIGGER audit_event_append_only" in source
    assert "BEFORE UPDATE OR DELETE ON audit_event" in source


def test_project_links_keep_history_and_allow_remote_fan_in() -> None:
    model = Path("apps/platform/src/ai_stp_platform/organization_models.py").read_text(
        encoding="utf-8"
    )
    migration = Path("migrations/versions/0058_b2b00_context_and_project_links.py").read_text(
        encoding="utf-8"
    )

    assert "uq_project_link_local_active" in model
    assert "uq_project_link_remote" not in model
    assert "uq_project_link_remote" not in migration
    assert "project_link_plan" in migration
    assert "project_unlink_plan" in migration


def test_organization_backfill_preserves_account_attribution_and_revision_scope() -> None:
    migration = Path("migrations/versions/0059_project_ledger_and_ownership_scope.py").read_text(
        encoding="utf-8"
    )
    for table in (
        "catalog_metadata",
        "catalog_identity",
        "sync_revision",
        "publication_plan",
        "access_grant",
        "report_case",
        "github_source_binding",
    ):
        assert f'("{table}"' in migration
    assert "attribution_account_id" in migration
    assert "organization_id" in migration
    assert "organization.kind = 'personal'" in migration
    assert "json_array_length(parent_revision_ids) <= 2" in migration


def test_organization_backfill_is_idempotent_and_fails_closed_for_orphans() -> None:
    migration = importlib.import_module(
        "migrations.versions.0059_project_ledger_and_ownership_scope"
    )
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE account (id VARCHAR(64) PRIMARY KEY)"))
        connection.execute(
            text(
                "CREATE TABLE organization (id VARCHAR(64) PRIMARY KEY, "
                "owner_account_id VARCHAR(64), kind VARCHAR(16))"
            )
        )
        connection.execute(
            text("CREATE TABLE legacy_resource (id VARCHAR(64), account_id VARCHAR(64))")
        )
        connection.execute(
            text(
                "CREATE TABLE organization_resource (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "organization_id VARCHAR(64), table_name VARCHAR(128), row_key VARCHAR(512), "
                "attribution_account_id VARCHAR(64), attribution_column VARCHAR(64), "
                "UNIQUE(table_name, row_key))"
            )
        )
        connection.execute(text("INSERT INTO account (id) VALUES ('account_a')"))
        connection.execute(
            text(
                "INSERT INTO organization (id, owner_account_id, kind) "
                "VALUES ('organization_a', 'account_a', 'personal')"
            )
        )
        connection.execute(
            text("INSERT INTO legacy_resource (id, account_id) VALUES ('resource_a', 'account_a')")
        )
        rows = (("legacy_resource", "id", "account_id"),)
        migration._backfill_organization_resources(connection, rows)
        migration._backfill_organization_resources(connection, rows)
        count = connection.execute(text("SELECT COUNT(*) FROM organization_resource")).scalar_one()
        assert count == 1

        connection.execute(text("INSERT INTO account (id) VALUES ('orphan_account')"))
        with pytest.raises(RuntimeError, match="missing or ambiguous"):
            migration._backfill_organization_resources(connection, rows)


def test_official_upstream_sync_does_not_cascade_on_source_delete() -> None:
    text = Path("migrations/versions/0033_official_upstream_components.py").read_text(
        encoding="utf-8"
    )
    sync_create = text.split('"official_upstream_sync"', 1)[1]
    assert "ondelete=" not in sync_create.split("def downgrade", 1)[0]
    column = ai_stp_platform.models.OfficialUpstreamSync.__table__.c.source_id
    assert column.nullable is False
    assert not column.foreign_keys


def test_official_upstream_multi_source_drops_singleton_slot() -> None:
    text = Path("migrations/versions/0035_official_upstream_multi_source.py").read_text(
        encoding="utf-8"
    )
    assert "uq_official_upstream_source_slot" in text
    assert "kind in ('git', 'package')" in text
    table = ai_stp_platform.models.OfficialUpstreamSource.__table__
    constraint_names = {
        str(getattr(item, "name", "") or "")
        for item in ai_stp_platform.models.OfficialUpstreamSource.__table_args__
    }
    assert "uq_official_upstream_source_slot" not in constraint_names
    assert table.c.kind.nullable is False
    assert table.c.repository_url.nullable is True
    assert table.c.ecosystem.nullable is True


def test_object_location_key_is_not_a_unique_owner_of_the_blob() -> None:
    """A unique object_key would refuse a later catalog version of the same bytes."""
    model = Path("apps/platform/src/ai_stp_platform/models.py").read_text(encoding="utf-8")
    assert 'UniqueConstraint("object_key"' not in model
    assert "uq_object_location_metadata_purpose" in model
    drop = Path("migrations/versions/0030_shared_object_location_key.py").read_text(
        encoding="utf-8"
    )
    assert 'op.drop_constraint("uq_object_location_object_key"' in drop
