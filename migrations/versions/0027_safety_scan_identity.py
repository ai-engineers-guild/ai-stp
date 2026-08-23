"""bind safety scan identity to profile and object kind

Revision ID: 0027_safety_identity
Revises: 0026_evidence_reason
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027_safety_identity"
down_revision: str | None = "0026_evidence_reason"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "safety_scan_run",
        sa.Column(
            "object_kind",
            sa.String(length=32),
            nullable=False,
            server_default="component",
        ),
    )
    op.drop_constraint(
        "uq_safety_scan_run_digest_policy",
        "safety_scan_run",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_safety_scan_run_identity",
        "safety_scan_run",
        ["content_digest", "policy_version", "profile", "object_kind"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_safety_scan_run_identity",
        "safety_scan_run",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_safety_scan_run_digest_policy",
        "safety_scan_run",
        ["content_digest", "policy_version"],
    )
    op.drop_column("safety_scan_run", "object_kind")
