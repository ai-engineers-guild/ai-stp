"""Enforce organization identity and ownership shape.

Revision ID: 0062_organization_shape_invariants
Revises: 0061_organization_identity_invariants
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0062_organization_shape_invariants"
down_revision: str | None = "0061_organization_identity_invariants"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_organization_id",
        "organization",
        "substr(id, 1, 13) = 'organization_' AND length(id) = 39",
    )
    op.create_check_constraint(
        "ck_organization_owner_shape",
        "organization",
        "(kind = 'personal' AND owner_account_id IS NOT NULL) OR "
        "(kind = 'corporate' AND owner_account_id IS NULL)",
    )
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        """
        CREATE OR REPLACE FUNCTION ai_stp_require_personal_owner_membership()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.kind = 'personal' AND (
                SELECT COUNT(*) FROM organization_membership
                WHERE organization_id = NEW.id
                  AND account_id = NEW.owner_account_id
                  AND role = 'owner'
                  AND state = 'active'
            ) <> 1 THEN
                RAISE EXCEPTION 'personal organization owner membership is required';
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER personal_organization_owner_membership
        AFTER INSERT ON organization
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION ai_stp_require_personal_owner_membership();
        """
    )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER personal_organization_owner_membership ON organization")
        op.execute("DROP FUNCTION ai_stp_require_personal_owner_membership()")
    op.drop_constraint("ck_organization_owner_shape", "organization", type_="check")
    op.drop_constraint("ck_organization_id", "organization", type_="check")
