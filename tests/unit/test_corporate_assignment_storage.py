"""Verify assignment storage has tenant and selector integrity boundaries."""

# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportAttributeAccessIssue=false

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint

from ai_stp_platform.organization_models import (
    CorporateAssignmentDistribution,
    CorporateCatalogAssignment,
)


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
    checks = {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert {
        "ck_corporate_assignment_subject",
        "ck_corporate_assignment_selector",
        "ck_corporate_assignment_selector_version",
    } <= checks
    unique = {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert {
        "uq_corporate_assignment_account",
        "uq_corporate_assignment_team",
        "uq_corporate_assignment_project",
        "uq_corporate_assignment_technology",
    } <= unique


def test_assignment_storage_supports_latest_and_organization_scope() -> None:
    table = CorporateCatalogAssignment.__table__
    assert table.c.version.nullable
    assert not table.c.selector.nullable
    assert table.c.harness.nullable
    assert table.c.passport_digest.nullable
    organization_scope = {index.name for index in table.indexes if index.unique}
    assert "uq_corporate_assignment_organization" in organization_scope


def test_distribution_storage_is_derived_and_never_copies_policy() -> None:
    table = CorporateAssignmentDistribution.__table__
    assert {column.name for column in table.primary_key.columns} == {
        "organization_id",
        "source_assignment_id",
        "target_kind",
        "target_id",
        "operation_revision",
    }
    # Derived rows must not duplicate the source assignment's policy fields:
    # the source row stays the single owner of selector, coordinate, and
    # condition (ADR-0195).
    for copied in ("selector", "version", "passport_digest", "harness", "object_kind"):
        assert copied not in table.c
    checks = {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert {
        "ck_distribution_target_kind",
        "ck_distribution_action",
        "ck_distribution_result",
        "ck_distribution_state",
        "ck_distribution_operation_revision",
    } <= checks
    keys = {
        tuple(element.target_fullname for element in constraint.elements)
        for constraint in table.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    }
    assert ("corporate_catalog_assignment.id",) in keys
    assert ("organization.id",) in keys
