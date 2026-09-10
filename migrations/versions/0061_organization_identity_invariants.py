"""Enforce immutable product organization identity and personal ownership."""

from collections.abc import Sequence

from alembic import op

revision: str = "0061_organization_identity_invariants"
down_revision: str | None = "0060_sync_plan_identity_revisions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        """
        CREATE OR REPLACE FUNCTION ai_stp_reject_organization_identity_change()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.kind IS DISTINCT FROM OLD.kind THEN
                RAISE EXCEPTION 'organization kind is immutable';
            END IF;
            IF OLD.kind = 'personal'
               AND NEW.owner_account_id IS DISTINCT FROM OLD.owner_account_id THEN
                RAISE EXCEPTION 'personal organization owner is immutable';
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER organization_identity_immutable
        BEFORE UPDATE OF kind, owner_account_id ON organization
        FOR EACH ROW EXECUTE FUNCTION ai_stp_reject_organization_identity_change();
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION ai_stp_validate_personal_membership()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE organization_kind text; owner_id varchar(64);
        BEGIN
            SELECT kind, owner_account_id INTO organization_kind, owner_id
            FROM organization WHERE id = NEW.organization_id;
            IF organization_kind = 'personal'
               AND (NEW.account_id IS DISTINCT FROM owner_id
                    OR NEW.role <> 'owner' OR NEW.state <> 'active') THEN
                RAISE EXCEPTION 'personal organization has exactly one active owner';
            END IF;
            IF organization_kind = 'personal'
               AND EXISTS (
                   SELECT 1 FROM organization_membership
                   WHERE organization_id = NEW.organization_id
                     AND id <> COALESCE(NEW.id, -1)
               ) THEN
                RAISE EXCEPTION 'personal organization cannot contain another member';
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER personal_membership_invariant
        BEFORE INSERT OR UPDATE ON organization_membership
        FOR EACH ROW EXECUTE FUNCTION ai_stp_validate_personal_membership();
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION ai_stp_reject_personal_membership_delete()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM organization
                WHERE id = OLD.organization_id AND kind = 'personal'
            ) THEN
                RAISE EXCEPTION 'personal organization owner membership is required';
            END IF;
            RETURN OLD;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER personal_membership_required
        BEFORE DELETE ON organization_membership
        FOR EACH ROW EXECUTE FUNCTION ai_stp_reject_personal_membership_delete();
        """
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("DROP TRIGGER personal_membership_required ON organization_membership")
    op.execute("DROP FUNCTION ai_stp_reject_personal_membership_delete()")
    op.execute("DROP TRIGGER personal_membership_invariant ON organization_membership")
    op.execute("DROP FUNCTION ai_stp_validate_personal_membership()")
    op.execute("DROP TRIGGER organization_identity_immutable ON organization")
    op.execute("DROP FUNCTION ai_stp_reject_organization_identity_change()")
