"""Verify assignment storage has tenant and exact-version integrity boundaries."""

# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportAttributeAccessIssue=false

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint

from ai_stp_platform.organization_models import CorporateCatalogAssignment


def test_assignment_storage_restricts_subjects_to_the_same_tenant() -> None:
    table = CorporateCatalogAssignment.__table__
    keys = {
        tuple(element.target_fullname for element in constraint.elements)
        for constraint in table.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    }
    assert ("corporate_team.organization_id", "corporate_team.id") in keys
    assert ("corporate_project.organization_id", "corporate_project.id") in keys
    assert ("organization_membership.organization_id", "organization_membership.account_id") in keys
    assert (
        "catalog_metadata.object_kind",
        "catalog_metadata.stable_id",
        "catalog_metadata.version",
    ) in keys
    assert not table.c.version.nullable
    checks = {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert "ck_corporate_assignment_subject" in checks
    unique = {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert {
        "uq_corporate_assignment_account",
        "uq_corporate_assignment_team",
        "uq_corporate_assignment_project",
    } <= unique
