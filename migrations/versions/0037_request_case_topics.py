"""route service and country requests through report_case

Revision ID: 0037_request_case_topics
Revises: 0036_official_projection
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0037_request_case_topics"
down_revision: str | None = "0036_official_projection"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "report_case",
        sa.Column("topic", sa.String(32), nullable=False, server_default="object_report"),
    )
    op.drop_constraint("ck_report_case_object_kind", "report_case", type_="check")
    for name, type_ in (
        ("object_kind", sa.String(32)),
        ("stable_id", sa.String(64)),
        ("version", sa.String(32)),
        ("content_digest", sa.String(71)),
    ):
        op.alter_column("report_case", name, existing_type=type_, nullable=True)
    op.create_check_constraint(
        "ck_report_case_topic",
        "report_case",
        "topic in ('object_report', 'service_request', 'country_request')",
    )
    op.create_check_constraint(
        "ck_report_case_object_kind",
        "report_case",
        "(topic = 'object_report' and object_kind in ('component', 'setup') "
        "and stable_id is not null and version is not null and content_digest is not null) "
        "or (topic <> 'object_report' and object_kind is null and stable_id is null "
        "and version is null and content_digest is null)",
    )


def downgrade() -> None:
    op.execute("DELETE FROM report_case WHERE topic <> 'object_report'")
    op.drop_constraint("ck_report_case_object_kind", "report_case", type_="check")
    op.drop_constraint("ck_report_case_topic", "report_case", type_="check")
    for name, type_ in (
        ("object_kind", sa.String(32)),
        ("stable_id", sa.String(64)),
        ("version", sa.String(32)),
        ("content_digest", sa.String(71)),
    ):
        op.alter_column("report_case", name, existing_type=type_, nullable=False)
    op.create_check_constraint(
        "ck_report_case_object_kind",
        "report_case",
        "object_kind in ('component', 'setup')",
    )
    op.drop_column("report_case", "topic")
