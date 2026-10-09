"""Curated findings keep decisions people made, not resolver output."""

import csv
import io

from ai_stp_contracts.technology import TechnologyEvidence, TechnologyScanFinding
from ai_stp_foundation.ids import new_id
from ai_stp_platform.technology_findings import (
    curate_findings,
    export_findings_csv,
    export_findings_markdown,
    lock_only_transitive,
)


def _evidence(source: str, path: str) -> TechnologyEvidence:
    return TechnologyEvidence(
        source=source,  # type: ignore[arg-type]
        path=path,
        observed_at="2026-01-01T00:00:00.000Z",
    )


def _finding(
    coordinate: str,
    *,
    kind: str = "package",
    context: str | None = "production",
    evidence: list[tuple[str, str]],
    **updates: object,
) -> TechnologyScanFinding:
    return TechnologyScanFinding(
        kind=kind,  # type: ignore[arg-type]
        coordinate=coordinate,
        context=context,  # type: ignore[arg-type]
        state="open",
        evidence=[_evidence(source, path) for source, path in evidence],
        **updates,  # type: ignore[arg-type]
    )


def test_lock_only_transitive_packages_leave_the_review_list() -> None:
    findings = [
        _finding("fastapi", evidence=[("declared", "pyproject.toml"), ("observed", "uv.lock")]),
        _finding("transitive-dep", evidence=[("observed", "uv.lock")]),
        _finding("tool-dep", evidence=[("observed", "tools/uv.lock")]),
        _finding(
            "reviewed-dep",
            evidence=[("observed", "uv.lock")],
            review="confirmed",
        ),
    ]
    result = curate_findings(findings)
    assert [item.coordinate for item in result] == ["fastapi", "reviewed-dep"]
    # The declared row kept its lock evidence — curation drops rows, not facts.
    fastapi = next(item for item in result if item.coordinate == "fastapi")
    assert [entry.path for entry in fastapi.evidence] == ["pyproject.toml", "uv.lock"]


def test_lock_only_transitive_needs_every_trace_to_be_lock_output() -> None:
    declared = {("dep", ".")}
    assert lock_only_transitive(
        "dep", [_evidence("observed", "uv.lock"), _evidence("observed", "poetry.lock")], set()
    )
    assert not lock_only_transitive(
        "dep", [_evidence("observed", "uv.lock"), _evidence("declared", "pyproject.toml")], declared
    )
    # A declaration in another directory does not rescue this directory's row.
    assert lock_only_transitive("dep", [_evidence("observed", "tools/uv.lock")], declared)


def test_declared_but_unrecognized_waits_in_the_unmapped_queue() -> None:
    """A declared package is still not a technology until someone recognizes it."""
    findings = [
        _finding("fastapi", evidence=[("declared", "pyproject.toml")]),
        _finding("acme-internal-stdlib", evidence=[("declared", "pyproject.toml")]),
        _finding(
            "acme-candidate-lib",
            evidence=[("declared", "pyproject.toml")],
            candidate_technology_id=new_id("technology"),
        ),
        _finding(
            "acme-vendored-lib",
            evidence=[("declared", "requirements.txt")],
            review="confirmed",
            technology_id=new_id("technology"),
        ),
    ]
    result = curate_findings(findings)
    assert [item.coordinate for item in result] == [
        "fastapi",
        "acme-candidate-lib",
        "acme-vendored-lib",
    ]


def test_configuration_signature_needs_an_identity() -> None:
    recognized = _finding(
        "conftest.py",
        kind="configuration",
        context="testing",
        evidence=[("configured", "conftest.py")],
    )
    unknown = _finding(
        "inexplicable.rc",
        kind="configuration",
        context="production",
        evidence=[("configured", "inexplicable.rc")],
    )
    result = curate_findings([recognized, unknown])
    assert [item.coordinate for item in result] == ["conftest.py"]
    assert result[0].technology_name == "pytest"


def test_export_findings_csv_is_spreadsheet_safe() -> None:
    rows = [
        _finding(
            "fastapi",
            evidence=[("declared", "pyproject.toml")],
            technology_name="FastAPI",
            version=">=0.100",
            version_kind="declared_range",
        ),
        _finding(
            "=cmd|'/c calc'!A0",
            evidence=[("observed", "uv.lock")],
            review="confirmed",
        ),
    ]
    document = export_findings_csv(rows)
    assert document.startswith("\ufeffkind,coordinate,")
    parsed = list(csv.reader(io.StringIO(document.lstrip("\ufeff"))))
    assert parsed[0] == [
        "kind",
        "coordinate",
        "technology",
        "context",
        "version",
        "version_kind",
        "state",
        "review",
        "evidence",
    ]
    assert parsed[1][:5] == ["package", "fastapi", "FastAPI", "production", ">=0.100"]
    # A formula-looking coordinate is quoted harmless, not executable.
    assert parsed[2][1].startswith("'")
    assert "pyproject.toml" in parsed[1][8]


def test_export_findings_markdown_carries_scan_metadata() -> None:
    document = export_findings_markdown(
        scan_id="scan_01",
        repository="https://github.com/acme/service",
        branch="main",
        commit="deadbeefcafe",
        complete=False,
        detector_version="repository-content-v3",
        mapping_version="v1",
        findings=[
            _finding(
                "fastapi",
                evidence=[("declared", "pyproject.toml")],
                technology_name="FastAPI",
                version=">=0.100",
            ),
            _finding(
                "cell | breaker",
                evidence=[("declared", "requirements.txt")],
            ),
        ],
    )
    assert document.startswith("# Technology scan `scan_01`")
    assert "- Repository: https://github.com/acme/service" in document
    assert "- Complete: no" in document
    assert "| package | fastapi | FastAPI | production | >=0.100 |" in document
    # A pipe inside a coordinate cannot break the table shape.
    assert "cell \\| breaker" in document
