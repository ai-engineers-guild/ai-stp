"""Retain project lifecycle and enforce its compatible legacy state projection."""

from collections.abc import Sequence

from alembic import op

revision: str = "0068_retained_project_lifecycle"
down_revision: str | None = "0067_technology_relations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE corporate_project ADD COLUMN lifecycle VARCHAR(16)")
    op.execute(
        "ALTER TABLE corporate_project ADD COLUMN restore_lifecycle VARCHAR(16) "
        "NOT NULL DEFAULT 'active'"
    )
    op.execute("""
        UPDATE corporate_project p SET
            lifecycle = CASE WHEN i.state = 'deleted' THEN 'deleted' ELSE p.state END,
            state = CASE WHEN i.state = 'deleted' THEN 'archived' ELSE p.state END
        FROM project_identity i
        WHERE i.organization_id = p.organization_id AND i.id = p.id
          AND i.namespace = 'remote'
    """)
    op.execute("ALTER TABLE corporate_project ALTER COLUMN lifecycle SET NOT NULL")
    op.execute("""
        ALTER TABLE corporate_project
        ADD CONSTRAINT ck_corporate_project_lifecycle
            CHECK (lifecycle IN ('active','deprecated','archived','deleted')),
        ADD CONSTRAINT ck_corporate_project_restore
            CHECK (restore_lifecycle IN ('active','deprecated')),
        ADD CONSTRAINT ck_corporate_project_projection
            CHECK (state = CASE WHEN lifecycle = 'active' THEN 'active' ELSE 'archived' END)
    """)
    op.execute("""
        CREATE FUNCTION corporate_project_lifecycle_projection() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                NEW.lifecycle := COALESCE(NEW.lifecycle, NEW.state);
            ELSIF NEW.lifecycle IS NOT DISTINCT FROM OLD.lifecycle
                AND NEW.state IS DISTINCT FROM OLD.state THEN
                IF OLD.lifecycle = 'deleted' THEN
                    RAISE EXCEPTION 'deleted project requires explicit lifecycle restoration';
                END IF;
                NEW.lifecycle := NEW.state;
            END IF;
            IF TG_OP = 'UPDATE' AND NEW.lifecycle IS DISTINCT FROM OLD.lifecycle
                AND OLD.lifecycle IN ('active','deprecated') THEN
                NEW.restore_lifecycle := OLD.lifecycle;
            END IF;
            NEW.state := CASE WHEN NEW.lifecycle = 'active' THEN 'active' ELSE 'archived' END;
            RETURN NEW;
        END $$
    """)
    op.execute("""
        CREATE TRIGGER corporate_project_lifecycle_projection
        BEFORE INSERT OR UPDATE ON corporate_project
        FOR EACH ROW EXECUTE FUNCTION corporate_project_lifecycle_projection()
    """)


def downgrade() -> None:
    """Remove the additive lifecycle projection for an explicit schema downgrade."""
    op.execute("DROP TRIGGER IF EXISTS corporate_project_lifecycle_projection ON corporate_project")
    op.execute("DROP FUNCTION IF EXISTS corporate_project_lifecycle_projection()")
    op.drop_constraint("ck_corporate_project_projection", "corporate_project", type_="check")
    op.drop_constraint("ck_corporate_project_restore", "corporate_project", type_="check")
    op.drop_constraint("ck_corporate_project_lifecycle", "corporate_project", type_="check")
    op.drop_column("corporate_project", "restore_lifecycle")
    op.drop_column("corporate_project", "lifecycle")
