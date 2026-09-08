"""Store exact owner visibility decisions independently of publication versions."""

import sqlalchemy as sa
from alembic import op

revision: str = "0056_distribution_visibility_plans"
down_revision: str = "0055_component_media_digest_compat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "visibility_plan",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "actor_account_id",
            sa.String(64),
            sa.ForeignKey("account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("document", sa.JSON(), nullable=False),
        sa.UniqueConstraint(
            "actor_account_id", "idempotency_key", name="uq_visibility_plan_actor_key"
        ),
        sa.CheckConstraint(
            "state in ('planned', 'applied', 'expired', 'refused')", name="ck_visibility_plan_state"
        ),
    )
    op.create_index("ix_visibility_plan_actor_account_id", "visibility_plan", ["actor_account_id"])


def downgrade() -> None:
    op.drop_index("ix_visibility_plan_actor_account_id", table_name="visibility_plan")
    op.drop_table("visibility_plan")
