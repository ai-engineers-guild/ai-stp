"""Technology review projection; dependency inventories remain immutable evidence."""

import re
from collections.abc import Iterable
from pathlib import PurePosixPath
from typing import Protocol

from ai_stp_contracts.technology import TechnologyScanFinding
from ai_stp_contracts.technology_seed import SEED_TECHNOLOGIES
from ai_stp_sources.tech_detect import bundled_mapping

_NAMES = {key: metadata.name for key, metadata in SEED_TECHNOLOGIES}
_MAPPING = bundled_mapping()
_LOCKS = frozenset(
    {
        "uv.lock",
        "poetry.lock",
        "Cargo.lock",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "pubspec.lock",
        "go.sum",
        "bun.lock",
        "bun.lockb",
    }
)


class _TraceLike(Protocol):
    @property
    def source(self) -> str: ...
    @property
    def path(self) -> str | None: ...


def declared_package_dirs(
    items: Iterable[tuple[str, str, Iterable[_TraceLike]]],
) -> set[tuple[str, str]]:
    """(coordinate, manifest directory) pairs that a declaration named."""
    direct: set[tuple[str, str]] = set()
    for kind, coordinate, traces in items:
        if kind != "package":
            continue
        for trace in traces:
            if trace.source == "declared" and trace.path:
                direct.add((coordinate.casefold(), str(PurePosixPath(trace.path).parent)))
    return direct


def lock_only_transitive(
    coordinate: str,
    traces: Iterable[_TraceLike],
    declared: set[tuple[str, str]],
) -> bool:
    """A package every trace of which is a lock row with no same-directory
    declaration is resolution output, not a project decision."""
    rows = list(traces)
    return bool(rows) and all(
        trace.path
        and PurePosixPath(trace.path).name in _LOCKS
        and (coordinate.casefold(), str(PurePosixPath(trace.path).parent)) not in declared
        for trace in rows
    )


def technology_identity(kind: str, coordinate: str) -> tuple[str, str] | None:
    """Recognize a technology family without inventing a tenant registry record."""
    key = _MAPPING.resolve(kind, coordinate)
    if key is None and kind == "image":
        key = _MAPPING.resolve("alias", coordinate.rsplit("/", 1)[-1])
    return (key, _NAMES[key]) if key in _NAMES else None


def curate_findings(findings: list[TechnologyScanFinding]) -> list[TechnologyScanFinding]:
    """Keep technologies and declared dependencies; drop resolver output.

    A finding is a `technology` when something names it — a seed identity,
    a mapped or candidate technology, or an owner's decision. A declared
    package or image nobody recognizes is a `dependency`: visible and
    reviewable, but not counted as a technology. Lock-only resolver output
    and unrecognized signatures stay raw evidence in `coordinates`.
    """
    direct = declared_package_dirs((item.kind, item.coordinate, item.evidence) for item in findings)
    result: list[TechnologyScanFinding] = []
    for item in findings:
        identity = technology_identity(item.kind, item.coordinate)
        owned = item.candidate_technology_id or item.review in {"confirmed", "rejected"}
        recognized = identity is not None or item.technology_id is not None
        if not owned:
            if item.kind == "package" and lock_only_transitive(
                item.coordinate, item.evidence, direct
            ):
                continue
            if not recognized and item.kind not in {"package", "image"}:
                continue
        result.append(
            item.model_copy(
                update={
                    "tier": "technology"
                    if recognized or item.candidate_technology_id
                    else "dependency",
                    "technology_key": identity[0] if identity else None,
                    "technology_name": identity[1] if identity else item.coordinate,
                }
            )
        )
    return result


def display_identity(item: TechnologyScanFinding) -> str | tuple[str, str]:
    return (
        item.technology_id
        or item.candidate_technology_id
        or item.technology_key
        or (item.kind, item.coordinate)
    )


# ---------------------------------------------------------------------------
# Findings export — the same curated rows, as files people can keep.
# ---------------------------------------------------------------------------

_EXPORT_COLUMNS = (
    "kind",
    "tier",
    "coordinate",
    "technology",
    "context",
    "version",
    "version_kind",
    "state",
    "review",
    "evidence",
)


def _export_technology(item: TechnologyScanFinding) -> str:
    return item.technology_name or item.technology_id or item.candidate_technology_id or ""


def _export_evidence(item: TechnologyScanFinding) -> str:
    return "; ".join(
        entry.path or entry.reference or ""
        for entry in item.evidence
        if entry.path or entry.reference
    )


def _csv_cell(value: str) -> str:
    # A leading spreadsheet formula marker is defused the way Excel does it.
    if re.match(r"\s*[=+@-]", value):
        value = f"'{value}"
    if any(char in value for char in '",\r\n'):
        value = f'"{value.replace(chr(34), chr(34) * 2)}"'
    return value


def export_findings_csv(findings: Iterable[TechnologyScanFinding]) -> str:
    """The curated finding rows as one CSV document (UTF-8, BOM-prefixed)."""
    rows = [",".join(_EXPORT_COLUMNS)]
    for item in findings:
        rows.append(
            ",".join(
                _csv_cell(value)
                for value in (
                    item.kind,
                    item.tier,
                    item.coordinate,
                    _export_technology(item),
                    item.context or "",
                    item.version or "",
                    item.version_kind,
                    item.state,
                    item.review,
                    _export_evidence(item),
                )
            )
        )
    return "\ufeff" + "\r\n".join(rows) + "\r\n"


def _md_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def export_findings_markdown(
    *,
    scan_id: str,
    repository: str | None,
    branch: str | None,
    commit: str | None,
    complete: bool,
    detector_version: str | None,
    mapping_version: str | None,
    findings: Iterable[TechnologyScanFinding],
) -> str:
    """The curated finding rows as a human-readable Markdown document."""
    lines = [
        f"# Technology scan `{scan_id}`",
        "",
        f"- Repository: {repository or '—'}",
        f"- Branch: {branch or '—'}",
        f"- Commit: {commit or '—'}",
        f"- Complete: {'yes' if complete else 'no'}",
        f"- Detector: {detector_version or '—'}",
        f"- Mapping: {mapping_version or '—'}",
        "",
        "| Kind | Tier | Coordinate | Technology | Context | Version "
        "| Version kind | State | Review | Evidence |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in findings:
        cells = (
            item.kind,
            item.tier,
            item.coordinate,
            _export_technology(item),
            item.context or "",
            item.version or "",
            item.version_kind,
            item.state,
            item.review,
            _export_evidence(item),
        )
        lines.append("| " + " | ".join(_md_cell(cell) for cell in cells) + " |")
    return "\n".join(lines) + "\n"
