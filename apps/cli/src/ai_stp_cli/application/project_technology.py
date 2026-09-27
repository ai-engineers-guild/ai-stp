"""Local technology detection and registry mapping services.

The `project detect`/`project technology` command handlers are thin adapters
over these functions, and the `technology` task drain calls them directly —
the task can never disagree with the CLI about what a coordinate or a
snapshot means.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from contextlib import closing
from pathlib import Path
from typing import Literal, cast

import yaml
from pydantic import ValidationError

from ai_stp_cli.answer import Answer
from ai_stp_cli.application.auth import endpoint
from ai_stp_cli.application.cloud_auth import required as session_required
from ai_stp_cli.cloud import technology as cloud_technology
from ai_stp_cli.errors import CliFailure, field_issues, leaf_help_continuation
from ai_stp_cli.local import project_links, project_passport, tech_detect, tech_findings
from ai_stp_cli.local.database import configured_path, open_registry, transaction
from ai_stp_cli.local.passports import moment
from ai_stp_cli.paths import redact_home
from ai_stp_cli.yaml_documents import DuplicateKeyError, UniqueSafeLoader
from ai_stp_contracts.machine_help import (
    CliTechnologyClaim,
    CliTechnologyEvidence,
    CliTechnologyFinding,
    CliTechnologyScan,
    CliTechnologyUnmapped,
    CliTechnologyUnmappedItem,
)
from ai_stp_contracts.technology import (
    TechnologyMappingEntry,
    TechnologyMappingRequest,
    TechnologyMappingView,
    TechnologyUnmappedView,
)
from ai_stp_contracts.technology_seed import SEED_COORDINATES, SEED_PROVENANCE
from ai_stp_foundation.ids import is_valid_id


def _required(parameters: Mapping[str, object], name: str) -> str:
    value = str(parameters.get(name) or "")
    if not value:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a required option was not supplied",
            details={"option": f"--{name}"},
        )
    return value


def _optional(parameters: Mapping[str, object], name: str) -> str | None:
    value = parameters.get(name)
    return None if value is None or str(value) == "" else str(value)


def _integer(parameters: Mapping[str, object], name: str) -> int:
    try:
        return int(_required(parameters, name))
    except ValueError as error:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a required option must be an integer",
            details={"option": f"--{name}"},
        ) from error


def scan_scope(parameters: Mapping[str, object]) -> str:
    scope = _optional(parameters, "scope") or "repository"
    if len(scope) > 128 or tech_findings.SCOPE_PATTERN.match(scope) is None:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a scan scope is required and must be at most 128 characters of "
            "letters, digits, dot, underscore, dash or slash",
            details={"option": "--scope"},
        )
    return scope


def project_id_for(
    connection: sqlite3.Connection, parameters: Mapping[str, object], *, path: tuple[str, ...]
) -> str:
    """The local project identity: explicit `--project`, or resolved from `--root`."""
    project_id = _optional(parameters, "project")
    if project_id is not None:
        if _optional(parameters, "root") is not None:
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                "pass either --project or --root, not both",
                details={"options": ["--project", "--root"]},
                continuations=[leaf_help_continuation(path)],
            )
        if not is_valid_id(project_id, "project"):
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                "a project identity is written as project_<ulid>",
                details={"option": "--project"},
            )
        return project_id
    root = _optional(parameters, "root")
    if root is None:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a local project is required",
            details={"options": ["--project", "--root"]},
            continuations=[leaf_help_continuation(path)],
            next_actions=["project detect --root <path> --json"],
        )
    resolved = Path(root).resolve()
    known = project_passport.stable_id_for(connection, resolved)
    if known is None:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "that root has no local project identity yet",
            details={"root": redact_home(resolved)},
            next_actions=[f"project detect --root {resolved} --json"],
        )
    return known


def finding_view(held: tech_findings.Finding) -> CliTechnologyFinding:
    return CliTechnologyFinding(
        key=held.key,
        kind=held.kind,
        coordinate=held.coordinate,
        context=held.context,
        technology_id=held.technology_id,
        effective_technology_id=held.effective_technology_id,
        version=held.version,
        version_kind=held.version_kind,
        review=held.review,
        freshness=held.freshness,
        claims=[
            CliTechnologyClaim(
                version=claim.version,
                version_kind=claim.version_kind,
                evidence=[
                    CliTechnologyEvidence(
                        source=trace.source,
                        path=trace.path,
                        reference=trace.reference,
                        confidence=trace.confidence,
                    )
                    for trace in claim.evidence
                ],
            )
            for claim in held.claims
        ],
        override_technology_id=held.override_technology_id,
        override_version=held.override_version,
        first_seen_scan=held.first_seen_scan,
        last_seen_scan=held.last_seen_scan,
        source_revision=held.source_revision,
        reviewed_at=held.reviewed_at,
    )


def detect(parameters: Mapping[str, object]) -> Answer[CliTechnologyScan]:
    """Detect the technology coordinates one project root uses (issue #222).

    Reads the same bounded index the passport builds — one walk, one truth —
    over files the index already hashed. Nothing executes, nothing installs,
    nothing is sent anywhere: the scan and its findings are stored locally,
    and publication is a separate explicit act.
    """
    given = parameters.get("root")
    if given is None:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a project root is required",
            next_actions=["project discover --root <path> --json"],
        )
    scope = scan_scope(parameters)
    at = moment()

    def work(connection: sqlite3.Connection) -> CliTechnologyScan:
        found = project_passport.scan(connection, Path(str(given)))
        detected = tech_detect.detect(found.index)
        link = project_links.cached_link(connection, local_project_id=found.stable_id)
        mapping = tech_findings.effective_mapping(
            connection,
            organization_id=link.organization_id if link is not None else None,
        )
        record = tech_findings.record_scan(
            connection,
            project_id=found.stable_id,
            scope=scope,
            detected=detected,
            mapping=mapping,
            at=at,
            source_revision=found.index_digest.removeprefix("sha256:"),
        )
        stored = tech_findings.findings(connection, project_id=found.stable_id, scope=scope)
        # The wire preview resolves the way publication does: the platform
        # rejects observations outside the named organization snapshot, so
        # bundled-only coordinates travel only when no snapshot exists yet.
        held_snapshot = (
            tech_findings.cached_mapping(connection, organization_id=link.organization_id)
            if link is not None
            else None
        )
        wire_mapping = held_snapshot if held_snapshot is not None else tech_detect.bundled_mapping()
        handoff = tech_findings.build_handoff(
            project_findings=stored,
            scan_id=record.scan_id,
            scope=scope,
            complete=record.complete,
            mapping=wire_mapping,
            local_project_id=found.stable_id,
            organization_id=link.organization_id if link is not None else None,
            remote_project_id=link.remote_project_id if link is not None else None,
            at=at,
            source_revision=record.source_revision,
            detector_version=record.detector_version,
        )
        return CliTechnologyScan(
            scan_id=record.scan_id,
            project_id=found.stable_id,
            root=redact_home(found.root),
            scope=scope,
            state="complete" if record.complete else "partial",
            stopped_by=record.stopped_by,
            detector_version=record.detector_version,
            mapping_version=mapping.version,
            source_revision=record.source_revision,
            findings=[finding_view(item) for item in stored],
            unmapped=list(handoff.unmapped),
            observations=len(handoff.handoff.observations),
            handoff=handoff.handoff,
        )

    with (
        closing(open_registry(configured_path(), create=True)) as connection,
        transaction(connection),
    ):
        return Answer(work(connection))


def unmapped(parameters: Mapping[str, object]) -> Answer[CliTechnologyUnmapped]:
    """List the stored coordinates the effective mapping cannot resolve.

    This is the project's registry review queue: every finding that is still
    a raw coordinate. What an operator resolves here — through an override or
    a wider organization mapping — turns into canonical observations at the
    next publish.
    """
    scope = scan_scope(parameters) if _optional(parameters, "scope") is not None else None

    def work(connection: sqlite3.Connection) -> CliTechnologyUnmapped:
        project_id = project_id_for(
            connection, parameters, path=("project", "technology", "unmapped")
        )
        stored = tech_findings.findings(connection, project_id=project_id, scope=scope)
        mapping = tech_findings.effective_mapping(
            connection, organization_id=_optional(parameters, "organization")
        )
        grouped: dict[tuple[str, str], set[tech_detect.UsageContext]] = {}
        for held in stored:
            if held.freshness != "current" or held.review not in tech_findings.PUBLISHABLE_REVIEWS:
                continue
            identity = (
                held.override_technology_id
                if held.review == "overridden"
                else mapping.resolve(held.kind, held.coordinate)
            )
            if identity is None:
                grouped.setdefault((held.kind, held.coordinate), set()).add(held.context)
        return CliTechnologyUnmapped(
            project_id=project_id,
            coordinates=[
                CliTechnologyUnmappedItem(
                    kind=cast(
                        Literal["package", "image", "executable", "configuration", "alias"],
                        kind,
                    ),
                    coordinate=coordinate,
                    contexts=sorted(contexts),
                )
                for (kind, coordinate), contexts in sorted(grouped.items())
            ],
        )

    with closing(open_registry(configured_path(), create=False)) as connection:
        return Answer(work(connection))


def unmapped_remote(
    parameters: Mapping[str, object],
) -> Answer[TechnologyUnmappedView]:
    """Read the organization's queue of coordinates no mapping snapshot resolved."""
    organization = _required(parameters, "organization")
    held = session_required("technology unmapped coordinates")
    return Answer(cloud_technology.read_unmapped(endpoint(), held.access_token, organization))


def mapping_publish(
    parameters: Mapping[str, object],
) -> Answer[TechnologyMappingView]:
    """Publish one immutable organization mapping snapshot.

    `--entries <file>` takes a JSON/YAML document of `{kind, coordinate,
    technology_id, provenance}` rows; `--seed` publishes the bundled seed
    table as-is. Either way the platform stores the exact version once —
    replaying the same body is a no-op, changing it is a conflict.
    """
    organization = _required(parameters, "organization")
    version = _required(parameters, "version")
    given_entries = _optional(parameters, "entries")
    seed = bool(parameters.get("seed"))
    if seed == (given_entries is not None):
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "pass exactly one of --entries or --seed",
            details={"options": ["--entries", "--seed"]},
        )
    if seed:
        entries = [
            TechnologyMappingEntry(
                kind=cast(
                    Literal["package", "image", "executable", "configuration", "alias"], kind
                ),
                coordinate=coordinate,
                technology_id=technology_id,
                provenance=SEED_PROVENANCE,
            )
            for technology_id, kind, coordinate in SEED_COORDINATES
        ]
    else:
        entries = read_mapping_entries(Path(str(given_entries)).resolve())
    request = TechnologyMappingRequest(
        authorization_revision=_integer(parameters, "authorization-revision"),
        expected_revision=0,
        idempotency_key=_required(parameters, "idempotency-key"),
        entries=entries,
    )
    held = session_required("technology mapping publish")
    view = cloud_technology.publish_mapping(
        endpoint(), held.access_token, organization, version, request
    )

    def work(connection: sqlite3.Connection) -> None:
        tech_findings.cache_mapping(
            connection,
            organization_id=organization,
            version=view.version,
            digest=view.digest,
            entries=[(entry.kind, entry.coordinate, entry.technology_id) for entry in view.entries],
            at=moment(),
        )

    with (
        closing(open_registry(configured_path(), create=True)) as connection,
        transaction(connection),
    ):
        work(connection)
    return Answer(view)


def read_mapping_entries(path: Path) -> list[TechnologyMappingEntry]:
    """One `--entries` document → validated rows. Bad input is a usage error."""
    if not path.is_file():
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "the mapping entries file does not exist",
            details={"path": redact_home(path)},
        )
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the mapping entries file cannot be read",
            details={"path": redact_home(path), "error": str(error)},
        ) from error
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        try:
            parsed = yaml.load(text, Loader=UniqueSafeLoader)
        except (yaml.YAMLError, DuplicateKeyError, RecursionError) as error:
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                "the entries file is not a JSON or YAML document",
                details={"path": redact_home(path)},
            ) from error
    if not isinstance(parsed, list):
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the entries file must hold a list of mapping entries",
            details={"path": redact_home(path)},
        )
    try:
        return [TechnologyMappingEntry.model_validate(item) for item in cast(list[object], parsed)]
    except ValidationError as error:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a mapping entry does not match the contract",
            details={"path": redact_home(path), "errors": field_issues(error)},
        ) from error
