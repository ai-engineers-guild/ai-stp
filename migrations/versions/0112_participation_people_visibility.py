"""Project participation roles and organization people visibility (ADR-0230).

`corporate_project_member.role` records the member's participation role on a
project (`owner | lead | contributor | staff`), distinct from the organization
role and from the access binding it materializes to. Existing rows keep
`staff`, preserving their current effective access.

`organization.people_visibility` chooses how members see each other:
`teammates` (default) scopes visibility to shared teams and projects,
`members` opens the roster, `admins` restricts it to scoped `member.list`
holders.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0112_participation_people_visibility"
down_revision: str | Sequence[str] | None = "0111_corporate_access_provenance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_SCOPE_KINDS = (
    "'system', 'organization', 'team', 'project', 'technology', "
    "'category', 'catalog_object', 'telemetry'"
)
_SCOPE_KINDS_BEFORE = (
    "'system', 'organization', 'team', 'project', 'technology', 'catalog_object', 'telemetry'"
)


def upgrade() -> None:
    op.add_column(
        "corporate_project_member",
        sa.Column("role", sa.String(16), nullable=False, server_default="staff"),
    )
    op.create_check_constraint(
        "ck_corporate_project_member_role",
        "corporate_project_member",
        "role in ('owner', 'lead', 'contributor', 'staff')",
    )
    op.add_column(
        "organization",
        sa.Column("people_visibility", sa.String(16), nullable=False, server_default="teammates"),
    )
    op.create_check_constraint(
        "ck_organization_people_visibility",
        "organization",
        "people_visibility in ('members', 'teammates', 'admins')",
    )
    # `category` becomes a first-class binding/grant scope (ADR-0230).
    for table, constraint in (
        ("corporate_role_binding", "ck_role_binding_scope_kind"),
        ("corporate_permission_grant", "ck_permission_grant_scope_kind"),
    ):
        op.drop_constraint(constraint, table, type_="check")
        op.create_check_constraint(constraint, table, f"scope_kind in ({_SCOPE_KINDS})")
    # Built-in `lead` roles gain `member.manage` so team/project leads can run
    # membership assignments; built-in role matrices are immutable, so the
    # backfill cannot collide with a custom permission set.
    op.execute(
        "INSERT INTO corporate_role_permission (organization_id, role, permission) "
        "SELECT organization_id, name, 'member.manage' FROM corporate_role "
        "WHERE name = 'lead' "
        "ON CONFLICT (organization_id, role, permission) DO NOTHING"
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM corporate_role_permission WHERE role = 'lead' AND permission = 'member.manage'"
    )
    for table, constraint in (
        ("corporate_role_binding", "ck_role_binding_scope_kind"),
        ("corporate_permission_grant", "ck_permission_grant_scope_kind"),
    ):
        op.drop_constraint(constraint, table, type_="check")
        op.create_check_constraint(constraint, table, f"scope_kind in ({_SCOPE_KINDS_BEFORE})")
    op.drop_constraint("ck_organization_people_visibility", "organization", type_="check")
    op.drop_column("organization", "people_visibility")
    op.drop_constraint(
        "ck_corporate_project_member_role", "corporate_project_member", type_="check"
    )
    op.drop_column("corporate_project_member", "role")
