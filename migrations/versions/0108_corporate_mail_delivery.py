"""Corporate invitation mail-delivery ledger (B2B-07 #201)."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0108_corporate_mail_delivery"
down_revision: str | None = "0107_corporate_invitations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "corporate_mail_delivery",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(64),
            sa.ForeignKey("organization.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "invitation_id",
            sa.String(64),
            sa.ForeignKey("corporate_invitation.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("to_email_normalized", sa.String(320), nullable=False),
        sa.Column("display_name", sa.String(80), nullable=False),
        sa.Column("template_key", sa.String(256), nullable=False, server_default=""),
        sa.Column("state", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("provider_message_id", sa.String(256), nullable=True),
        sa.Column("error", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("invitation_id", name="uq_corporate_mail_delivery_invitation"),
        sa.CheckConstraint(
            "state in ('queued', 'sent', 'failed')",
            name="ck_corporate_mail_delivery_state",
        ),
    )
    op.create_index(
        "ix_corporate_mail_delivery_organization_id",
        "corporate_mail_delivery",
        ["organization_id"],
    )
    op.create_index(
        "ix_corporate_mail_delivery_state",
        "corporate_mail_delivery",
        ["state"],
    )


def downgrade() -> None:
    op.drop_index("ix_corporate_mail_delivery_state", table_name="corporate_mail_delivery")
    op.drop_index(
        "ix_corporate_mail_delivery_organization_id",
        table_name="corporate_mail_delivery",
    )
    op.drop_table("corporate_mail_delivery")
