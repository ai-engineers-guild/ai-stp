"""Bind grant mutations to exact requests and current state."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0124_grant_operation_receipts"
down_revision: str = "0114_corporate_role_flat"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "access_grant", sa.Column("revision", sa.Integer(), server_default="1", nullable=False)
    )
    op.create_check_constraint("ck_access_grant_revision", "access_grant", "revision >= 1")
    # Migration precedes API replacement. An old writer must not bypass the
    # new precondition/receipt service during that overlap or a source rollback.
    op.execute("""
        CREATE FUNCTION enforce_access_grant_revision() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.revision::bigint <> OLD.revision::bigint +
                (CASE WHEN NEW.state IS DISTINCT FROM OLD.state THEN 1 ELSE 0 END)
            THEN
                RAISE EXCEPTION 'grant state change requires its next revision'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER access_grant_revision_guard
        BEFORE UPDATE OF state, revision ON access_grant
        FOR EACH ROW EXECUTE FUNCTION enforce_access_grant_revision()
    """)
    op.create_table(
        "grant_operation_receipt",
        sa.Column(
            "actor_account_id",
            sa.String(64),
            sa.ForeignKey("account.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("idempotency_key", sa.String(128), primary_key=True),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column(
            "grant_id",
            sa.String(64),
            sa.ForeignKey("access_grant.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("action in ('direct', 'revoke')", name="ck_grant_operation_action"),
    )
    op.create_index("ix_grant_operation_receipt_grant_id", "grant_operation_receipt", ["grant_id"])


def downgrade() -> None:
    populated = op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM access_grant) "
            "OR EXISTS (SELECT 1 FROM grant_operation_receipt)"
        )
    )
    if populated:
        raise RuntimeError(
            "Grant replay protection has retained data; preserve revisions and receipts."
        )
    op.execute("DROP TRIGGER access_grant_revision_guard ON access_grant")
    op.execute("DROP FUNCTION enforce_access_grant_revision()")
    op.drop_index("ix_grant_operation_receipt_grant_id", table_name="grant_operation_receipt")
    op.drop_table("grant_operation_receipt")
    op.drop_constraint("ck_access_grant_revision", "access_grant", type_="check")
    op.drop_column("access_grant", "revision")
