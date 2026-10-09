"""Review identities collect versions without duplicating their evidence."""

from ai_stp_contracts.technology import TechnologyEvidence, TechnologyScanFinding
from ai_stp_platform.technology_interpretation import merge_findings


def test_duplicate_versions_share_one_review_identity() -> None:
    evidence = TechnologyEvidence(
        source="declared",
        path="package.json",
        reference="python",
        observed_at="2026-10-08T00:00:00.000Z",
    )
    first = TechnologyScanFinding(
        kind="alias",
        coordinate="python",
        context="production",
        state="resolved",
        version="3.12",
        evidence=[evidence],
    )
    second = first.model_copy(
        update={
            "version": "3.13",
            "evidence": [evidence, evidence.model_copy(update={"path": "Dockerfile"})],
        }
    )
    result = merge_findings([first, second, first])
    assert len(result) == 1
    assert result[0].version == "3.12, 3.13"
    assert [item.path for item in result[0].evidence] == ["package.json", "Dockerfile"]
    assert first.version == "3.12"
