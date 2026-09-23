"""The local store for technology scans and their review state (issue #222).

A *scan* is immutable: it records what one detector pass saw, under which
detector and mapping versions, and whether the index underneath was complete.
A *finding* is the standing record review decisions attach to — identity is
`(kind, coordinate, context)`, never the version, so `package:django` at
`>=5` and later at `5.2.1` is the same finding with a new claim.

Two rules keep the store honest across rescans:

- **Review survives evidence.** A merge updates claims, evidence and
  freshness, but never `review`, `reviewed_at` or the override fields. A
  rejected coordinate detected again stays rejected; confirming does not have
  to be re-done because a dependency moved.
- **Absence requires a complete scan.** A finding missing from a *complete*
  scan of the same scope goes `absent`; missing from a partial scan it only
  goes `stale` — the walk stopped early, so "not seen" and "not there" are
  different facts and only the first is true.
"""

import json
import re
import sqlite3
from dataclasses import dataclass
from typing import Final, Literal, cast

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import tech_detect
from ai_stp_contracts.technology import (
    TechnologyEvidence,
    TechnologyObservation,
    TechnologyScanHandoff,
    TechnologyUsageFact,
)
from ai_stp_foundation.ids import is_valid_id, new_id

FINDING_KINDS: Final[frozenset[str]] = frozenset(
    {"package", "image", "executable", "configuration", "alias"}
)
REVIEW_STATES: Final[frozenset[str]] = frozenset(
    {"proposed", "confirmed", "rejected", "overridden", "retired"}
)

#: Which reviews travel in a handoff. `rejected` says the finding is not a
#: usage; `retired` says it no longer is — excluding both is the statement,
#: because a complete scan marks their server-side facts absent.
PUBLISHABLE_REVIEWS: Final[frozenset[str]] = frozenset({"proposed", "confirmed", "overridden"})


ReviewState = Literal["proposed", "confirmed", "rejected", "overridden", "retired"]
FreshnessState = Literal["current", "absent", "stale", "unknown"]

#: The wire pattern `TechnologyScanHandoff.scope` carries. A scope that
#: cannot travel is refused at store time, not at publication time.
SCOPE_PATTERN: Final = re.compile(r"^[A-Za-z0-9._/-]+$")


@dataclass(frozen=True)
class Claim:
    """One version claim inside a finding, with the evidence that made it."""

    version: str | None
    version_kind: tech_detect.VersionKind
    evidence: tuple[tech_detect.Trace, ...]


@dataclass(frozen=True)
class Finding:
    """The standing record for one (kind, coordinate, context)."""

    project_id: str
    scope: str
    kind: tech_detect.DetectionKind
    coordinate: str
    context: tech_detect.UsageContext
    claims: tuple[Claim, ...]
    technology_id: str | None
    review: ReviewState
    freshness: FreshnessState
    override_technology_id: str | None
    override_version: str | None
    first_seen_scan: str
    last_seen_scan: str
    source_revision: str | None
    reviewed_at: str | None
    updated_at: str

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.coordinate}:{self.context}"

    @property
    def version(self) -> str | None:
        claim = self.headline
        return claim.version if claim else None

    @property
    def version_kind(self) -> tech_detect.VersionKind:
        claim = self.headline
        return claim.version_kind if claim else "unknown"

    @property
    def headline(self) -> Claim | None:
        """The strongest claim: observed beats declared beats unknown."""
        if not self.claims:
            return None
        order = {"observed_version": 0, "declared_range": 1, "unknown": 2}
        return sorted(
            self.claims, key=lambda item: (order.get(item.version_kind, 3), item.version or "")
        )[0]

    @property
    def evidence(self) -> tuple[tech_detect.Trace, ...]:
        seen: list[tech_detect.Trace] = []
        for claim in self.claims:
            for trace in claim.evidence:
                if trace not in seen:
                    seen.append(trace)
        return tuple(seen)

    @property
    def effective_technology_id(self) -> str | None:
        return self.override_technology_id if self.review == "overridden" else self.technology_id


@dataclass(frozen=True)
class ScanRecord:
    scan_id: str
    project_id: str
    scope: str
    complete: bool
    stopped_by: str | None
    detector_version: str
    mapping_version: str
    source_revision: str | None
    created_at: str


def _claims_document(detections: list[tech_detect.Detection]) -> str:
    return json.dumps(
        [
            {
                "version": detection.version,
                "version_kind": detection.version_kind,
                "evidence": [
                    {
                        "source": trace.source,
                        "path": trace.path,
                        "reference": trace.reference,
                        "confidence": trace.confidence,
                    }
                    for trace in detection.traces
                ],
            }
            for detection in detections
        ]
    )


def _row_table(value: object) -> dict[str, object]:
    return cast(dict[str, object], value) if isinstance(value, dict) else {}


def _row_seq(value: object) -> list[object]:
    return cast(list[object], value) if isinstance(value, list) else []


def _row_text(value: object) -> str | None:
    return str(value) if value is not None else None


def _row_number(value: object) -> float:
    return float(value) if isinstance(value, (int, float)) else 0.0


def _parse_trace(item: object) -> tech_detect.Trace:
    body = _row_table(item)
    return tech_detect.Trace(
        source=cast(Literal["declared", "configured", "observed"], body.get("source")),
        path=str(body.get("path") or ""),
        reference=_row_text(body.get("reference")),
        confidence=_row_number(body.get("confidence")),
    )


def _parse_claims(document: str) -> tuple[Claim, ...]:
    raw: object = json.loads(document)
    claims: list[Claim] = []
    for entry in _row_seq(raw):
        row = _row_table(entry)
        claims.append(
            Claim(
                version=_row_text(row.get("version")),
                version_kind=cast(
                    tech_detect.VersionKind, str(row.get("version_kind") or "unknown")
                ),
                evidence=tuple(_parse_trace(item) for item in _row_seq(row.get("evidence"))),
            )
        )
    return tuple(claims)


def _finding(row: sqlite3.Row) -> Finding:
    return Finding(
        project_id=str(row["project_id"]),
        scope=str(row["scope"]),
        kind=cast(tech_detect.DetectionKind, str(row["kind"])),
        coordinate=str(row["coordinate"]),
        context=cast(tech_detect.UsageContext, str(row["context"])),
        claims=_parse_claims(str(row["claims"])),
        technology_id=row["technology_id"],
        review=cast(ReviewState, str(row["review"])),
        freshness=cast(FreshnessState, str(row["freshness"])),
        override_technology_id=row["override_technology_id"],
        override_version=row["override_version"],
        first_seen_scan=str(row["first_seen_scan"]),
        last_seen_scan=str(row["last_seen_scan"]),
        source_revision=str(row["source_revision"] or "") or None,
        reviewed_at=row["reviewed_at"],
        updated_at=str(row["updated_at"]),
    )


def record_scan(
    connection: sqlite3.Connection,
    *,
    project_id: str,
    scope: str,
    detected: tech_detect.DetectedScan,
    mapping: tech_detect.MappingSnapshot,
    at: str,
    source_revision: str | None = None,
) -> ScanRecord:
    """Store one scan and merge its detections into findings.

    The scan row is new every time — two identical scans are two readings —
    while findings merge by identity, which is where review survives: an
    UPDATE that never touches `review` cannot undo a decision.
    """
    if not scope or len(scope) > 128 or SCOPE_PATTERN.match(scope) is None:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a scan scope is required and must be at most 128 characters of "
            "letters, digits, dot, underscore, dash or slash",
            details={"option": "--scope"},
        )
    if source_revision is not None and re.fullmatch(r"[0-9a-f]{64}", source_revision) is None:
        raise ValueError("source revision must be an index digest")
    scan_id = new_id("scan")
    connection.execute(
        """
        INSERT INTO tech_scan (
            scan_id, project_id, scope, complete, stopped_by,
            detector_version, mapping_version, source_revision, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            scan_id,
            project_id,
            scope,
            1 if detected.complete else 0,
            detected.stopped_by or "",
            tech_detect.DETECTOR_VERSION,
            mapping.version,
            source_revision or "",
            at,
        ),
    )

    grouped: dict[tuple[str, str, str], list[tech_detect.Detection]] = {}
    for detection in detected.detections:
        grouped.setdefault((detection.kind, detection.coordinate, detection.context), []).append(
            detection
        )

    seen: set[tuple[str, str, str]] = set()
    for (kind, coordinate, context), detections in grouped.items():
        seen.add((kind, coordinate, context))
        technology_id = mapping.resolve(kind, coordinate)
        claims = _claims_document(detections)
        existing = connection.execute(
            """
            SELECT freshness FROM tech_finding
            WHERE project_id = ? AND scope = ? AND kind = ? AND coordinate = ? AND context = ?
            """,
            (project_id, scope, kind, coordinate, context),
        ).fetchone()
        if existing is None:
            connection.execute(
                """
                INSERT INTO tech_finding (
                    project_id, scope, kind, coordinate, context,
                    claims, technology_id, review, freshness,
                    first_seen_scan, last_seen_scan, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'proposed', 'current', ?, ?, ?)
                """,
                (
                    project_id,
                    scope,
                    kind,
                    coordinate,
                    context,
                    claims,
                    technology_id,
                    scan_id,
                    scan_id,
                    at,
                ),
            )
        else:
            connection.execute(
                """
                UPDATE tech_finding
                SET claims = ?, technology_id = ?, freshness = 'current',
                    last_seen_scan = ?, updated_at = ?
                WHERE project_id = ? AND scope = ? AND kind = ? AND coordinate = ? AND context = ?
                """,
                (
                    claims,
                    technology_id,
                    scan_id,
                    at,
                    project_id,
                    scope,
                    kind,
                    coordinate,
                    context,
                ),
            )

    # What the scan did not see: absent only when the walk was complete.
    missing = connection.execute(
        """
        SELECT kind, coordinate, context, freshness FROM tech_finding
        WHERE project_id = ? AND scope = ?
        """,
        (project_id, scope),
    ).fetchall()
    for row in missing:
        key = (str(row["kind"]), str(row["coordinate"]), str(row["context"]))
        if key in seen:
            continue
        if detected.complete:
            freshness = "absent"
        else:
            freshness = "stale" if row["freshness"] == "current" else str(row["freshness"])
        connection.execute(
            """
            UPDATE tech_finding SET freshness = ?, updated_at = ?
            WHERE project_id = ? AND scope = ? AND kind = ? AND coordinate = ? AND context = ?
            """,
            (freshness, at, project_id, scope, *key),
        )

    return ScanRecord(
        scan_id=scan_id,
        project_id=project_id,
        scope=scope,
        complete=detected.complete,
        stopped_by=detected.stopped_by,
        detector_version=tech_detect.DETECTOR_VERSION,
        mapping_version=mapping.version,
        source_revision=source_revision,
        created_at=at,
    )


def findings(
    connection: sqlite3.Connection,
    *,
    project_id: str,
    scope: str | None = None,
) -> list[Finding]:
    if scope is None:
        rows = connection.execute(
            """SELECT f.*, s.source_revision FROM tech_finding AS f
            JOIN tech_scan AS s ON s.scan_id = f.last_seen_scan
            WHERE f.project_id = ? ORDER BY f.kind, f.coordinate, f.context""",
            (project_id,),
        ).fetchall()
    else:
        rows = connection.execute(
            """
            SELECT f.*, s.source_revision FROM tech_finding AS f
            JOIN tech_scan AS s ON s.scan_id = f.last_seen_scan
            WHERE f.project_id = ? AND f.scope = ?
            ORDER BY f.kind, f.coordinate, f.context
            """,
            (project_id, scope),
        ).fetchall()
    return [_finding(row) for row in rows]


def scans(connection: sqlite3.Connection, *, project_id: str) -> list[ScanRecord]:
    rows = connection.execute(
        "SELECT * FROM tech_scan WHERE project_id = ? ORDER BY rowid",
        (project_id,),
    ).fetchall()
    return [
        ScanRecord(
            scan_id=str(row["scan_id"]),
            project_id=str(row["project_id"]),
            scope=str(row["scope"]),
            complete=bool(row["complete"]),
            stopped_by=row["stopped_by"] or None,
            detector_version=str(row["detector_version"]),
            mapping_version=str(row["mapping_version"]),
            source_revision=str(row["source_revision"]) or None,
            created_at=str(row["created_at"]),
        )
        for row in rows
    ]


def find(
    connection: sqlite3.Connection,
    *,
    project_id: str,
    scope: str,
    kind: str,
    coordinate: str,
    context: str,
) -> Finding | None:
    row = connection.execute(
        """
        SELECT f.*, s.source_revision FROM tech_finding AS f
        JOIN tech_scan AS s ON s.scan_id = f.last_seen_scan
        WHERE f.project_id = ? AND f.scope = ? AND f.kind = ?
          AND f.coordinate = ? AND f.context = ?
        """,
        (project_id, scope, kind, coordinate, context),
    ).fetchone()
    return _finding(row) if row is not None else None


def review(
    connection: sqlite3.Connection,
    *,
    project_id: str,
    scope: str,
    kind: str,
    coordinate: str,
    context: str,
    decision: str,
    override_technology_id: str | None = None,
    override_version: str | None = None,
    at: str,
) -> Finding:
    """Record one review decision. The finding must already exist.

    Review is attached to the standing record, not to a scan: the decision
    outlives whatever evidence produced it, and the next merge is forbidden
    from touching these columns.
    """
    if decision not in REVIEW_STATES:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a review decision is confirm, reject, override or retire",
            details={"decision": decision},
        )
    held = find(
        connection,
        project_id=project_id,
        scope=scope,
        kind=kind,
        coordinate=coordinate,
        context=context,
    )
    if held is None:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "no technology finding exists for that coordinate",
            details={"finding": f"{kind}:{coordinate}:{context}", "scope": scope},
        )
    if decision == "overridden":
        if not override_technology_id or not is_valid_id(override_technology_id, "technology"):
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                "an override names the canonical technology it resolves to",
                details={"option": "--technology"},
            )
    else:
        override_technology_id = None
        override_version = None
    connection.execute(
        """
        UPDATE tech_finding
        SET review = ?, override_technology_id = ?, override_version = ?,
            reviewed_at = ?, updated_at = ?
        WHERE project_id = ? AND scope = ? AND kind = ? AND coordinate = ? AND context = ?
        """,
        (
            decision,
            override_technology_id,
            override_version,
            at,
            at,
            project_id,
            scope,
            kind,
            coordinate,
            context,
        ),
    )
    updated = find(
        connection,
        project_id=project_id,
        scope=scope,
        kind=kind,
        coordinate=coordinate,
        context=context,
    )
    assert updated is not None  # the row the guard above proved
    return updated


def cache_mapping(
    connection: sqlite3.Connection,
    *,
    organization_id: str,
    version: str,
    digest: str,
    entries: list[tuple[str, str, str]],
    at: str,
) -> None:
    """Store one fetched organization mapping snapshot verbatim."""
    connection.execute(
        """
        INSERT INTO tech_mapping_cache (
            organization_id, version, digest, entries, fetched_at
        ) VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (organization_id, version) DO UPDATE SET
            digest = excluded.digest,
            entries = excluded.entries,
            fetched_at = excluded.fetched_at
        """,
        (
            organization_id,
            version,
            digest,
            json.dumps([list(entry) for entry in entries]),
            at,
        ),
    )


def cached_mapping(
    connection: sqlite3.Connection,
    *,
    organization_id: str,
    version: str | None = None,
) -> tech_detect.MappingSnapshot | None:
    """One cached snapshot: exact version, or the most recently fetched."""
    if version is not None:
        row = connection.execute(
            """
            SELECT version, entries FROM tech_mapping_cache
            WHERE organization_id = ? AND version = ?
            """,
            (organization_id, version),
        ).fetchone()
    else:
        row = connection.execute(
            """
            SELECT version, entries FROM tech_mapping_cache
            WHERE organization_id = ?
            ORDER BY fetched_at DESC, version DESC LIMIT 1
            """,
            (organization_id,),
        ).fetchone()
    if row is None:
        return None
    entries = [
        (str(item[0]), str(item[1]), str(item[2])) for item in json.loads(str(row["entries"]))
    ]
    return tech_detect.MappingSnapshot(version=str(row["version"]), entries=tuple(entries))


def cached_mappings(
    connection: sqlite3.Connection, *, organization_id: str
) -> list[tuple[str, str, int]]:
    """(version, digest, entry count) for every snapshot cached for one org."""
    rows = connection.execute(
        """
        SELECT version, digest, entries FROM tech_mapping_cache
        WHERE organization_id = ? ORDER BY fetched_at DESC, version DESC
        """,
        (organization_id,),
    ).fetchall()
    return [
        (str(row["version"]), str(row["digest"]), len(json.loads(str(row["entries"]))))
        for row in rows
    ]


def effective_mapping(
    connection: sqlite3.Connection, *, organization_id: str | None = None
) -> tech_detect.MappingSnapshot:
    """Bundled table overlaid by the linked organization's snapshot.

    The bundled table resolves only canonical seed identities; an organization
    snapshot adds its own registry's identities and wins on the same
    coordinate, because for that project the organization is the authority.
    """
    base = tech_detect.bundled_mapping()
    if organization_id is None:
        return base
    held = cached_mapping(connection, organization_id=organization_id)
    if held is None:
        return base
    # The organization is the authority for its registry: on a shared
    # coordinate its entry replaces the bundled one, not joins it.
    overridden = {(kind, coordinate): tid for kind, coordinate, tid in held.entries}
    bundled_coordinates = {(kind, coordinate) for kind, coordinate, _ in base.entries}
    merged = [
        (kind, coordinate, overridden.get((kind, coordinate), tid))
        for kind, coordinate, tid in base.entries
    ]
    merged.extend(
        entry for entry in held.entries if (entry[0], entry[1]) not in bundled_coordinates
    )
    return tech_detect.MappingSnapshot(version=held.version, entries=tuple(merged))


@dataclass(frozen=True)
class HandoffResult:
    """The wire handoff plus the findings that could not travel in it."""

    handoff: TechnologyScanHandoff
    unmapped: tuple[str, ...]
    excluded: tuple[str, ...]


def build_handoff(
    *,
    project_findings: list[Finding],
    scan_id: str,
    scope: str,
    complete: bool,
    mapping: tech_detect.MappingSnapshot,
    local_project_id: str,
    organization_id: str | None = None,
    remote_project_id: str | None = None,
    at: str,
    source_revision: str | None = None,
) -> HandoffResult:
    """Project stored findings into one `TechnologyScanHandoff`.

    Only `current`, publishable findings travel — `absent` and `stale` say
    nothing about presence, and `rejected`/`retired` say the finding is not a
    usage. Two coordinates resolving to the same technology in one context
    merge into one observation, because the wire requires that key to be
    unique. An override swaps the coordinate's resolution for the identity
    the reviewer named; it does not fabricate evidence.
    """
    unmapped: list[str] = []
    excluded: list[str] = []
    observations: dict[tuple[str, str], list[TechnologyEvidence]] = {}
    # (rank, version text, claim version, claim kind) — rank first so the
    # strongest claim wins the comparison deterministically.
    versions: dict[tuple[str, str], tuple[int, str, str | None, str]] = {}
    order = {"observed_version": 0, "declared_range": 1, "unknown": 2}

    for finding in sorted(project_findings, key=lambda item: item.key):
        if finding.freshness != "current" or finding.review not in PUBLISHABLE_REVIEWS:
            excluded.append(finding.key)
            continue
        technology_id = finding.effective_technology_id
        if technology_id is None:
            technology_id = mapping.resolve(finding.kind, finding.coordinate)
        if technology_id is None:
            unmapped.append(finding.key)
            continue
        key = (technology_id, finding.context)
        bucket = observations.setdefault(key, [])
        for claim in finding.claims:
            for trace in claim.evidence:
                candidate = TechnologyEvidence(
                    source=trace.source,
                    path=trace.path,
                    reference=trace.reference,
                    observed_at=at,
                    source_revision=source_revision,
                    confidence=trace.confidence,
                    detector_version=tech_detect.DETECTOR_VERSION,
                    mapping_version=mapping.version,
                )
                if candidate not in bucket:
                    bucket.append(candidate)
        headline = finding.headline
        if headline is not None:
            rank = order.get(headline.version_kind, 3)
            candidate_rank = (rank, headline.version or "")
            current = versions.get(key)
            if current is None or candidate_rank < (current[0], current[1]):
                versions[key] = (
                    rank,
                    headline.version or "",
                    headline.version,
                    headline.version_kind,
                )

    items = [
        TechnologyObservation(
            technology_id=technology_id,
            fact=TechnologyUsageFact(
                context=cast(
                    Literal["production", "development", "testing", "browser_support"], context
                ),
                version=versions.get(key, (0, "", None, "unknown"))[2],
                version_kind=cast(
                    Literal["unknown", "declared_range", "observed_version"],
                    versions.get(key, (0, "", None, "unknown"))[3],
                ),
                evidence=evidence[:64],
            ),
        )
        for key, evidence in sorted(observations.items())
        for technology_id, context in [key]
    ]
    if len(items) > 4096:
        raise CliFailure(
            "AI_STP_CONFLICT",
            "the scan produced more observations than the handoff can carry",
            details={"observations": str(len(items)), "limit": "4096"},
        )
    return HandoffResult(
        handoff=TechnologyScanHandoff(
            local_project_id=local_project_id,
            organization_id=organization_id,
            project_id=remote_project_id,
            scan_id=scan_id,
            scope=scope,
            complete=complete,
            detector_version=tech_detect.DETECTOR_VERSION,
            mapping_version=mapping.version,
            observations=items,
        ),
        unmapped=tuple(unmapped),
        excluded=tuple(excluded),
    )
