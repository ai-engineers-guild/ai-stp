"""Static migration checks for the platform Alembic tree (SPEC-020)."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

import ai_stp_platform.content.orm
import ai_stp_platform.models
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
    }

    assert expected_tables.issubset(Base.metadata.tables)


def test_audit_migration_defines_append_only_trigger() -> None:
    source = Path("migrations/versions/0002_sprint1_core.py").read_text(encoding="utf-8")
    assert "CREATE TRIGGER audit_event_append_only" in source
    assert "BEFORE UPDATE OR DELETE ON audit_event" in source


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
