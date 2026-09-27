"""Organization invitation links and the email-domain allowlist (B2B-07 #201)."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0107_corporate_invitations"
down_revision: str | None = "0097_profile_publish_idempotency"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organization",
        sa.Column(
            "allowed_email_domains",
            sa.JSON(),
            nullable=False,
            server_default="[]",
        ),
    )
    op.create_table(
        "corporate_invitation",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(64),
            sa.ForeignKey("organization.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "issuer_account_id",
            sa.String(64),
            sa.ForeignKey("account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("recipient_email_normalized", sa.String(320), nullable=False),
        sa.Column("display_name", sa.String(80), nullable=False),
        sa.Column("role", sa.String(64), nullable=False),
        sa.Column("team_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("project_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("job_title_id", sa.String(64), nullable=True),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "accepted_account_id",
            sa.String(64),
            sa.ForeignKey("account.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "organization_id", "idempotency_key", name="uq_corporate_invitation_key"
        ),
        sa.CheckConstraint(
            "state in ('pending', 'accepted', 'expired', 'revoked')",
            name="ck_corporate_invitation_state",
        ),
    )
    op.create_index(
        "ix_corporate_invitation_organization_id",
        "corporate_invitation",
        ["organization_id"],
    )
    op.create_index(
        "ix_corporate_invitation_issuer_account_id",
        "corporate_invitation",
        ["issuer_account_id"],
    )
    op.create_index(
        "ix_corporate_invitation_recipient_email_normalized",
        "corporate_invitation",
        ["recipient_email_normalized"],
    )
    # Built-in roles gained `member.invite`; seed it into every existing tenant.
    op.execute(
        "INSERT INTO corporate_role_permission (organization_id, role, permission) "
        "SELECT organization_id, name, 'member.invite' FROM corporate_role "
        "WHERE name IN ('superadmin', 'lead')"
    )


def downgrade() -> None:
    op.execute("DELETE FROM corporate_role_permission WHERE permission = 'member.invite'")
    op.drop_index(
        "ix_corporate_invitation_recipient_email_normalized",
        table_name="corporate_invitation",
    )
    op.drop_index("ix_corporate_invitation_issuer_account_id", table_name="corporate_invitation")
    op.drop_index("ix_corporate_invitation_organization_id", table_name="corporate_invitation")
    op.drop_table("corporate_invitation")
    op.drop_column("organization", "allowed_email_domains")
