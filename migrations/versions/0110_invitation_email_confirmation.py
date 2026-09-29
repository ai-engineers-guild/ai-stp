"""Invitation email-confirmation claimant binding (B2B-07 #201).

When the accepting account's verified emails do not include the invited
address, the invitation stops being a dead end: the claimant is bound to the
invitation and a confirmation token is mailed to the invited address. Clicking
it proves inbox ownership and activates the membership for the claimant.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0110_invitation_email_confirmation"
down_revision: str | Sequence[str] | None = (
    "0108_corporate_mail_delivery",
    "0109_schema_model_parity",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("corporate_invitation", "state", type_=sa.String(32))
    op.drop_constraint("ck_corporate_invitation_state", "corporate_invitation", type_="check")
    op.create_check_constraint(
        "ck_corporate_invitation_state",
        "corporate_invitation",
        "state in ('pending', 'email_confirm_pending', 'accepted', 'expired', 'revoked')",
    )
    op.add_column(
        "corporate_invitation",
        sa.Column(
            "claimant_account_id",
            sa.String(64),
            sa.ForeignKey("account.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "corporate_invitation",
        sa.Column("confirmation_token_hash", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("corporate_invitation", "confirmation_token_hash")
    op.drop_column("corporate_invitation", "claimant_account_id")
    op.drop_constraint("ck_corporate_invitation_state", "corporate_invitation", type_="check")
    op.create_check_constraint(
        "ck_corporate_invitation_state",
        "corporate_invitation",
        "state in ('pending', 'accepted', 'expired', 'revoked')",
    )
    op.alter_column("corporate_invitation", "state", type_=sa.String(16))
