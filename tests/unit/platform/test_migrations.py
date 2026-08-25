"""Static migration checks for the platform Alembic tree (SPEC-020)."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

import ai_stp_platform.models
import ai_stp_platform.queue.models
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
    expected_tables = {
        "account",
        "oauth_identity",
        "device",
        "account_session",
        "catalog_metadata",
        "object_location",
        "audit_event",
        "job",
    }

    assert expected_tables.issubset(Base.metadata.tables)


def test_audit_migration_defines_append_only_trigger() -> None:
    source = Path("migrations/versions/0002_sprint1_core.py").read_text(encoding="utf-8")
    assert "CREATE TRIGGER audit_event_append_only" in source
    assert "BEFORE UPDATE OR DELETE ON audit_event" in source


def test_object_location_key_is_not_a_unique_owner_of_the_blob() -> None:
    """A unique object_key would refuse a later catalog version of the same bytes."""
    model = Path("apps/platform/src/ai_stp_platform/models.py").read_text(encoding="utf-8")
    assert 'UniqueConstraint("object_key"' not in model
    assert "uq_object_location_metadata_purpose" in model
    drop = Path("migrations/versions/0030_shared_object_location_key.py").read_text(
        encoding="utf-8"
    )
    assert 'op.drop_constraint("uq_object_location_object_key"' in drop
