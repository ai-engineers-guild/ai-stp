"""safety scan runs, findings, and catalog checks summary

Revision ID: 0020_safety_scan
Revises: 0019_component_presentation
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_safety_scan"
down_revision: str | None = "0019_component_presentation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "safety_scan_run",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("content_digest", sa.String(length=71), nullable=False),
        sa.Column("policy_version", sa.String(length=32), nullable=False),
        sa.Column("profile", sa.String(length=32), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("cache_hit", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("wall_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("engine_status", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "state in ('running', 'complete', 'failed')",
            name="ck_safety_scan_run_state",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "content_digest",
            "policy_version",
            name="uq_safety_scan_run_digest_policy",
        ),
    )
    op.create_index("ix_safety_scan_run_digest", "safety_scan_run", ["content_digest"])

    op.create_table(
        "safety_finding",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scan_run_id", sa.String(length=64), nullable=False),
        sa.Column("check_id", sa.String(length=64), nullable=False),
        sa.Column("family", sa.String(length=64), nullable=False),
        sa.Column("rule_id", sa.String(length=128), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("path", sa.String(length=512), nullable=True),
        sa.Column("message", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("tool_name", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("fingerprint", sa.String(length=32), nullable=False, server_default=""),
        sa.ForeignKeyConstraint(["scan_run_id"], ["safety_scan_run.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_safety_finding_scan_run_id", "safety_finding", ["scan_run_id"])

    op.add_column(
        "evidence_binding",
        sa.Column("family", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "evidence_binding",
        sa.Column("tool_name", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "evidence_binding",
        sa.Column("tool_version", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "evidence_binding",
        sa.Column("duration_ms", sa.Integer(), nullable=True),
    )
    op.add_column(
        "evidence_binding",
        sa.Column("severity_max", sa.String(length=16), nullable=True),
    )

    op.add_column(
        "catalog_metadata",
        sa.Column("checks_summary", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("catalog_metadata", "checks_summary")
    op.drop_column("evidence_binding", "severity_max")
    op.drop_column("evidence_binding", "duration_ms")
    op.drop_column("evidence_binding", "tool_version")
    op.drop_column("evidence_binding", "tool_name")
    op.drop_column("evidence_binding", "family")
    op.drop_index("ix_safety_finding_scan_run_id", table_name="safety_finding")
    op.drop_table("safety_finding")
    op.drop_index("ix_safety_scan_run_digest", table_name="safety_scan_run")
    op.drop_table("safety_scan_run")
