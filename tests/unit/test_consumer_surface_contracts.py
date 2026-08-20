"""Server consumer-surface contracts stay separate from local v1 reports."""

import pytest
from pydantic import ValidationError

from ai_stp_contracts.catalog import GitHubMetadata
from ai_stp_contracts.impact import (
    AccountBlastRadiusQuery,
    AccountSelectionImpactQuery,
    AccountSelectionImpactReport,
    BlastRadiusReport,
    SelectionImpactReport,
)
from ai_stp_contracts.openapi import OPERATIONS


def test_local_impact_report_keeps_local_authority() -> None:
    assert SelectionImpactReport.model_fields["schema_version"].default == 1
    assert SelectionImpactReport.model_fields["freshness"].default == "local_snapshot"
    assert BlastRadiusReport.model_fields["authority_boundary"].default == "local_registry"
    assert AccountSelectionImpactReport.model_fields["schema_version"].default == 1
    assert AccountSelectionImpactReport.model_fields["authority_boundary"].default == "account"


def test_account_impact_query_requires_a_complete_baseline_pair() -> None:
    with pytest.raises(ValidationError):
        AccountSelectionImpactQuery(
            candidate_id="setup_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
            candidate_version="1.0",
            baseline_id="setup_01JQZK7B8N4M6P2R9T5V0X3Y7A",
        )


def test_generated_http_inventory_has_no_account_blast_radius() -> None:
    assert not any(operation.path.endswith("/blast-radius") for operation in OPERATIONS)


def test_account_blast_radius_query_rejects_an_unknown_scenario() -> None:
    with pytest.raises(ValidationError):
        AccountBlastRadiusQuery(
            component_id="component_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
            component_version="1.0",
            scenario="delete",  # type: ignore[arg-type]
        )


def test_github_metadata_keeps_stars_and_archived_nullable() -> None:
    empty = GitHubMetadata()
    assert empty.stars is None
    assert empty.archived is None
    archived = GitHubMetadata(stars=4, archived=True)
    assert archived.stars == 4
    assert archived.archived is True
    with pytest.raises(ValidationError):
        GitHubMetadata(stars=-1)
