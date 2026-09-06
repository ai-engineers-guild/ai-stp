"""Additive catalog tables for target assessments and setup families.

Revision ID: 0049_catalog_projections_assurance_families
Revises: 0048_catalog_obt_support_and_provenance
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0049_catalog_projections_assurance_families"
down_revision: str | None = "0048_catalog_obt_support_and_provenance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "catalog_search_projection",
        sa.Column(
            "claimed_harness_ids",
            postgresql.ARRAY(sa.String(32)),
            server_default="{}",
            nullable=False,
        ),
    )
    op.add_column(
        "catalog_search_projection",
        sa.Column("family_id", sa.String(64), nullable=True),
    )
    op.add_column(
        "catalog_search_projection",
        sa.Column("family_member_count", sa.Integer(), nullable=True),
    )
    op.add_column(
        "catalog_search_projection",
        sa.Column("family_alignment", sa.String(32), nullable=True),
    )
    op.add_column(
        "catalog_search_projection",
        sa.Column("verified_targets", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "catalog_search_projection",
        sa.Column("assessed_targets", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_index(
        "ix_catalog_search_projection_claimed_harnesses",
        "catalog_search_projection",
        ["claimed_harness_ids"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_catalog_search_projection_family_id",
        "catalog_search_projection",
        ["family_id"],
    )

    op.create_table(
        "artifact_observation",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("identity_digest", sa.String(71), nullable=False),
        sa.Column("artifact_digest", sa.String(71), nullable=False),
        sa.Column("check_id", sa.String(64), nullable=False),
        sa.Column("scanner_id", sa.String(64), nullable=False),
        sa.Column("scanner_version", sa.String(64), nullable=False),
        sa.Column("policy_version", sa.String(64), nullable=False),
        sa.Column("operating_system", sa.String(32), nullable=True),
        sa.Column("architecture", sa.String(32), nullable=True),
        sa.Column("result", sa.String(16), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("identity_digest", name="uq_artifact_observation_identity"),
    )
    op.create_index(
        "ix_artifact_observation_artifact_digest",
        "artifact_observation",
        ["artifact_digest"],
    )

    op.create_table(
        "target_assessment",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("target_key_digest", sa.String(71), nullable=False),
        sa.Column("identity", sa.JSON(), nullable=False),
        sa.Column("stored_state", sa.String(32), nullable=False),
        sa.Column("compatibility_result", sa.String(16), nullable=False, server_default="not_run"),
        sa.Column("reason_code", sa.String(64), nullable=True),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_target_assessment_idempotency"),
        sa.CheckConstraint(
            "stored_state in ('not_verified', 'verified', 'failed')",
            name="ck_target_assessment_stored_state",
        ),
    )
    op.create_index(
        "ix_target_assessment_target_key",
        "target_assessment",
        ["target_key_digest", "observed_at"],
    )

    op.create_table(
        "target_assessment_latest",
        sa.Column("target_key_digest", sa.String(71), primary_key=True),
        sa.Column(
            "assessment_id",
            sa.Integer(),
            sa.ForeignKey("target_assessment.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("component_stable_id", sa.String(64), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("adaptation_id", sa.String(76), nullable=False),
        sa.Column("harness_id", sa.String(32), nullable=False),
        sa.Column("scope", sa.String(32), nullable=False),
        sa.Column("stored_state", sa.String(32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("target_key_digest", name="uq_target_assessment_latest_key"),
    )
    op.create_index(
        "ix_target_assessment_latest_component",
        "target_assessment_latest",
        ["component_stable_id"],
    )
    op.create_index(
        "ix_target_assessment_latest_harness",
        "target_assessment_latest",
        ["harness_id"],
    )

    op.create_table(
        "setup_family",
        sa.Column("family_id", sa.String(64), primary_key=True),
        sa.Column(
            "owner_account_id",
            sa.String(64),
            sa.ForeignKey("account.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("baseline_stable_id", sa.String(64), nullable=False),
        sa.Column("baseline_version", sa.String(32), nullable=False),
        sa.Column("baseline_passport_digest", sa.String(71), nullable=False),
        sa.Column("created_from", sa.String(32), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("create_idempotency_key", sa.String(128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("create_idempotency_key", name="uq_setup_family_create_idempotency"),
        sa.CheckConstraint("revision >= 1", name="ck_setup_family_revision"),
        sa.CheckConstraint(
            "created_from in ('recast', 'owner', 'staff_migration', 'migration')",
            name="ck_setup_family_created_from",
        ),
    )
    op.create_index("ix_setup_family_owner", "setup_family", ["owner_account_id"])

    op.create_table(
        "setup_family_member",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "family_id",
            sa.String(64),
            sa.ForeignKey("setup_family.family_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stable_id", sa.String(64), nullable=False),
        sa.Column("harness_id", sa.String(32), nullable=False),
        sa.UniqueConstraint("family_id", "stable_id", name="uq_setup_family_member_setup"),
        sa.UniqueConstraint("family_id", "harness_id", name="uq_setup_family_member_harness"),
        sa.UniqueConstraint("stable_id", name="uq_setup_family_member_one_family"),
    )
    op.create_index("ix_setup_family_member_family", "setup_family_member", ["family_id"])

    op.create_table(
        "setup_family_revision",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "family_id",
            sa.String(64),
            sa.ForeignKey("setup_family.family_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("actor_account_id", sa.String(64), nullable=False),
        sa.Column("reason", sa.String(200), nullable=False),
        sa.Column("previous_baseline", sa.JSON(), nullable=True),
        sa.Column("new_baseline", sa.JSON(), nullable=False),
        sa.Column("added_members", sa.JSON(), nullable=False),
        sa.Column("removed_members", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_setup_family_revision_idempotency"),
    )
    op.create_index(
        "ix_setup_family_revision_family",
        "setup_family_revision",
        ["family_id", "revision"],
    )


def downgrade() -> None:
    op.drop_index("ix_setup_family_revision_family", table_name="setup_family_revision")
    op.drop_table("setup_family_revision")
    op.drop_index("ix_setup_family_member_family", table_name="setup_family_member")
    op.drop_table("setup_family_member")
    op.drop_index("ix_setup_family_owner", table_name="setup_family")
    op.drop_table("setup_family")
    op.drop_index("ix_target_assessment_latest_harness", table_name="target_assessment_latest")
    op.drop_index("ix_target_assessment_latest_component", table_name="target_assessment_latest")
    op.drop_table("target_assessment_latest")
    op.drop_index("ix_target_assessment_target_key", table_name="target_assessment")
    op.drop_table("target_assessment")
    op.drop_index("ix_artifact_observation_artifact_digest", table_name="artifact_observation")
    op.drop_table("artifact_observation")
    op.drop_index("ix_catalog_search_projection_family_id", table_name="catalog_search_projection")
    op.drop_index(
        "ix_catalog_search_projection_claimed_harnesses",
        table_name="catalog_search_projection",
    )
    op.drop_column("catalog_search_projection", "assessed_targets")
    op.drop_column("catalog_search_projection", "verified_targets")
    op.drop_column("catalog_search_projection", "family_alignment")
    op.drop_column("catalog_search_projection", "family_member_count")
    op.drop_column("catalog_search_projection", "family_id")
    op.drop_column("catalog_search_projection", "claimed_harness_ids")
