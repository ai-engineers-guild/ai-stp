"""Tenant registry and single canonical relationships (SPEC-080/081).

Evidence is attached data. It is never another project-technology edge.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from ai_stp_platform.db import Base


class _TenantRow:
    organization_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("organization.id", ondelete="RESTRICT"),
        primary_key=True,
        sort_order=-10,
    )


class TechnologyCategory(_TenantRow, Base):
    __tablename__ = "technology_category"
    __table_args__ = (
        UniqueConstraint("organization_id", "normalized_name", name="uq_technology_category_name"),
        CheckConstraint("revision >= 1", name="ck_technology_category_revision"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(
        String(2000), nullable=False, default="", server_default=""
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    provenance: Mapped[str] = mapped_column(String(256), nullable=False)


class Technology(_TenantRow, Base):
    __tablename__ = "technology"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "redirect_id"],
            ["technology.organization_id", "technology.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "lifecycle IN ('draft','active','deprecated','archived')",
            name="ck_technology_lifecycle",
        ),
        CheckConstraint(
            "restore_lifecycle IN ('draft','active','deprecated')", name="ck_technology_restore"
        ),
        CheckConstraint("redirect_id IS NULL OR redirect_id <> id", name="ck_technology_redirect"),
        CheckConstraint("revision >= 1", name="ck_technology_revision"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(
        String(4000), nullable=False, default="", server_default=""
    )
    icon_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    official_urls: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]"
    )
    lifecycle: Mapped[str] = mapped_column(
        String(16), nullable=False, default="draft", server_default="draft"
    )
    restore_lifecycle: Mapped[str] = mapped_column(
        String(16), nullable=False, default="draft", server_default="draft"
    )
    redirect_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provenance: Mapped[str] = mapped_column(String(256), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TechnologyAlias(_TenantRow, Base):
    """One collision-checked lookup namespace for canonical names and aliases."""

    __tablename__ = "technology_alias"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "technology_id"],
            ["technology.organization_id", "technology.id"],
            ondelete="RESTRICT",
        ),
    )
    normalized_name: Mapped[str] = mapped_column(String(200), primary_key=True)
    technology_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    canonical: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )


class TechnologyClassification(_TenantRow, Base):
    __tablename__ = "technology_classification"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "technology_id"],
            ["technology.organization_id", "technology.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "category_id"],
            ["technology_category.organization_id", "technology_category.id"],
            ondelete="RESTRICT",
        ),
    )
    technology_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    category_id: Mapped[str] = mapped_column(String(64), primary_key=True)


class OrganizationTechnologyDecision(_TenantRow, Base):
    """Adoption and designated lead, separate from canonical technology metadata."""

    __tablename__ = "organization_technology_decision"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "technology_id"],
            ["technology.organization_id", "technology.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "lead_account_id"],
            ["organization_membership.organization_id", "organization_membership.account_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "adoption IN ('none','assess','trial','adopt','hold')", name="ck_technology_adoption"
        ),
        CheckConstraint("revision >= 1", name="ck_technology_decision_revision"),
    )
    technology_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    lead_account_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approved: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    adoption: Mapped[str] = mapped_column(
        String(16), nullable=False, default="none", server_default="none"
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")


class ProjectTechnologyRelation(_TenantRow, Base):
    __tablename__ = "project_technology_relation"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "project_id", "technology_id", name="uq_project_technology_pair"
        ),
        ForeignKeyConstraint(
            ["organization_id", "project_id", "project_namespace"],
            [
                "project_identity.organization_id",
                "project_identity.id",
                "project_identity.namespace",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint("project_namespace = 'remote'", name="ck_project_technology_namespace"),
        ForeignKeyConstraint(
            ["organization_id", "technology_id"],
            ["technology.organization_id", "technology.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("state IN ('current','retired')", name="ck_project_technology_state"),
        CheckConstraint("revision >= 1", name="ck_project_technology_revision"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    project_namespace: Mapped[str] = mapped_column(
        String(16), nullable=False, default="remote", server_default="remote"
    )
    technology_id: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="current", server_default="current"
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")


class TechnologyUsageFact(_TenantRow, Base):
    __tablename__ = "technology_usage_fact"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "relation_id"],
            ["project_technology_relation.organization_id", "project_technology_relation.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "context IN ('production','development','testing','browser_support')",
            name="ck_usage_context",
        ),
        CheckConstraint(
            "review IN ('proposed','confirmed','rejected','overridden','retired')",
            name="ck_usage_review",
        ),
        CheckConstraint(
            "freshness IN ('current','stale','absent','unknown')", name="ck_usage_freshness"
        ),
        CheckConstraint(
            "version_kind IN ('unknown','declared_range','observed_version')",
            name="ck_usage_version_kind",
        ),
        CheckConstraint(
            "(version_kind = 'unknown') = (version IS NULL)", name="ck_usage_version_value"
        ),
    )
    relation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    context: Mapped[str] = mapped_column(String(32), primary_key=True)
    review: Mapped[str] = mapped_column(String(16), nullable=False)
    version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    version_kind: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unknown", server_default="unknown"
    )
    freshness: Mapped[str] = mapped_column(
        String(16), nullable=False, default="unknown", server_default="unknown"
    )
    evidence: Mapped[list[dict[str, object]]] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]"
    )


class ProjectTeamRelation(_TenantRow, Base):
    __tablename__ = "project_team_relation"
    __table_args__ = (
        UniqueConstraint("organization_id", "project_id", "team_id", name="uq_project_team_pair"),
        ForeignKeyConstraint(
            ["organization_id", "project_id"],
            ["corporate_project.organization_id", "corporate_project.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "team_id"],
            ["corporate_team.organization_id", "corporate_team.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "role IN ('owner','responsible','contributor')", name="ck_project_team_role"
        ),
        CheckConstraint("state IN ('current','retired')", name="ck_project_team_state"),
        CheckConstraint("revision >= 1", name="ck_project_team_revision"),
        Index(
            "uq_project_owner",
            "organization_id",
            "project_id",
            unique=True,
            postgresql_where=text("state = 'current' AND role = 'owner'"),
            sqlite_where=text("state = 'current' AND role = 'owner'"),
        ),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    team_id: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="current", server_default="current"
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")


class TechnologyTeamResponsibility(_TenantRow, Base):
    __tablename__ = "technology_team_responsibility"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "technology_id", "team_id", name="uq_technology_team_pair"
        ),
        ForeignKeyConstraint(
            ["organization_id", "technology_id"],
            ["technology.organization_id", "technology.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "team_id"],
            ["corporate_team.organization_id", "corporate_team.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("state IN ('current','retired')", name="ck_technology_team_state"),
        CheckConstraint("revision >= 1", name="ck_technology_team_revision"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    technology_id: Mapped[str] = mapped_column(String(64), nullable=False)
    team_id: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="current", server_default="current"
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")


class TechnologyScan(_TenantRow, Base):
    """Immutable complete/partial observation batch; never the owner review state."""

    __tablename__ = "technology_scan"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    project_namespace: Mapped[str] = mapped_column(
        String(16), nullable=False, default="remote", server_default="remote"
    )
    fingerprint: Mapped[str] = mapped_column(String(71), nullable=False)
    handoff: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "project_id", "project_namespace"],
            [
                "project_identity.organization_id",
                "project_identity.id",
                "project_identity.namespace",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint("project_namespace = 'remote'", name="ck_technology_scan_namespace"),
    )


class TechnologyCoordinateMapping(_TenantRow, Base):
    __tablename__ = "technology_coordinate_mapping"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "technology_id"],
            ["technology.organization_id", "technology.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "kind IN ('package','image','executable','configuration','alias')",
            name="ck_mapping_kind",
        ),
    )
    version: Mapped[str] = mapped_column(String(128), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), primary_key=True)
    coordinate: Mapped[str] = mapped_column(String(512), primary_key=True)
    technology_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    provenance: Mapped[str] = mapped_column(String(256), nullable=False)


class TechnologyReference(_TenantRow, Base):
    """Explicit catalog subject/applicability reference, excluded from usage totals."""

    __tablename__ = "technology_reference"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "technology_id"],
            ["technology.organization_id", "technology.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "object_kind IN ('component','setup')", name="ck_technology_reference_object"
        ),
        CheckConstraint(
            "meaning IN ('subject','applicability')", name="ck_technology_reference_meaning"
        ),
    )
    object_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    technology_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    meaning: Mapped[str] = mapped_column(String(16), primary_key=True)
    object_kind: Mapped[str] = mapped_column(String(16), nullable=False)


class TechnologyLandscapePolicy(_TenantRow, Base):
    __tablename__ = "technology_landscape_policy"
    __table_args__ = (
        CheckConstraint("inactivity_months BETWEEN 1 AND 120", name="ck_landscape_inactivity"),
        CheckConstraint("revision >= 1", name="ck_landscape_policy_revision"),
    )
    inactivity_months: Mapped[int] = mapped_column(
        Integer, nullable=False, default=9, server_default="9"
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
