"""Local technology detection and registry mapping services.

The `project detect`/`project technology` command handlers are thin adapters
over these functions, and the `technology` task drain calls them directly —
the task can never disagree with the CLI about what a coordinate or a
snapshot means.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping, Sequence
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
    TaskTechnologyDecision,
    TaskTechnologyOutcome,
)
from ai_stp_contracts.technology import (
    CategoryView,
    CategoryWriteRequest,
    TechnologyCategoryMetadata,
    TechnologyLifecycleRequest,
    TechnologyMappingEntry,
    TechnologyMappingList,
    TechnologyMappingRequest,
    TechnologyMappingView,
    TechnologyMetadata,
    TechnologyUnmappedEntry,
    TechnologyUnmappedReviewRequest,
    TechnologyUnmappedView,
    TechnologyView,
    TechnologyWriteRequest,
    normalize_technology_name,
)
from ai_stp_contracts.technology_seed import SEED_COORDINATES, SEED_PROVENANCE
from ai_stp_foundation.digests import digest_canonical
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


def technology_propose(parameters: Mapping[str, object]) -> Answer[TechnologyUnmappedEntry]:
    """Propose or clear the candidate technology for one queued coordinate."""
    organization = _required(parameters, "organization")
    kind = _coordinate_kind(parameters)
    coordinate = _required(parameters, "coordinate")
    technology_id = _optional(parameters, "technology-id")
    if technology_id is not None and not is_valid_id(technology_id, "technology"):
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the technology option is not a technology identifier",
            details={"option": "--technology-id", "value": technology_id},
        )
    if bool(parameters.get("clear")) == (technology_id is not None):
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "pass exactly one of --technology-id or --clear",
            details={"options": ["--technology-id", "--clear"]},
        )
    request = TechnologyUnmappedReviewRequest(
        authorization_revision=_integer(parameters, "authorization-revision"),
        idempotency_key=_required(parameters, "idempotency-key"),
        kind=kind,
        coordinate=coordinate,
        candidate_technology_id=None if parameters.get("clear") else technology_id,
    )
    held = session_required("technology propose")
    return Answer(
        cloud_technology.review_unmapped(endpoint(), held.access_token, organization, request)
    )


def _coordinate_kind(
    parameters: Mapping[str, object],
) -> Literal["package", "image", "executable", "configuration", "alias"]:
    kind = _required(parameters, "kind")
    if kind not in ("package", "image", "executable", "configuration", "alias"):
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the kind option is not a coordinate kind",
            details={"option": "--kind", "value": kind},
        )
    return kind


def technology_apply(parameters: Mapping[str, object]) -> Answer[TechnologyMappingView]:
    """Extend the organization's current mapping snapshot with reviewed entries.

    The new version overlays `--base-version` (or the cached latest snapshot)
    instead of standing alone, so applying one coordinate never drops the
    mappings the organization already reviewed.
    """
    organization = _required(parameters, "organization")
    given_entries = _optional(parameters, "entries")
    coordinate = _optional(parameters, "coordinate")
    technology_id = _optional(parameters, "technology-id")
    single = coordinate is not None or technology_id is not None or _optional(parameters, "kind")
    if given_entries is not None and single:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "pass either --entries or one --kind/--coordinate/--technology-id triple",
            details={"options": ["--entries", "--kind", "--coordinate", "--technology-id"]},
        )
    if single:
        if coordinate is None or technology_id is None:
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                "a coordinate mapping needs --kind, --coordinate and --technology-id",
                details={"options": ["--kind", "--coordinate", "--technology-id"]},
            )
        if not is_valid_id(technology_id, "technology"):
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                "the technology option is not a technology identifier",
                details={"option": "--technology-id", "value": technology_id},
            )
        entries = [
            TechnologyMappingEntry(
                kind=_coordinate_kind(parameters),
                coordinate=coordinate,
                technology_id=technology_id,
                provenance="cli-review",
            )
        ]
    elif given_entries is not None:
        entries = read_mapping_entries(Path(given_entries).resolve())
    else:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "pass either --entries or one --kind/--coordinate/--technology-id triple",
            details={"options": ["--entries", "--kind", "--coordinate", "--technology-id"]},
        )

    base_version = _optional(parameters, "base-version")
    if base_version is None:
        registry = configured_path()
        if registry.exists():
            with closing(open_registry(registry, create=False)) as connection:
                held_snapshot = tech_findings.cached_mapping(
                    connection, organization_id=organization
                )
            base_version = held_snapshot.version if held_snapshot is not None else None

    request = TechnologyMappingRequest(
        authorization_revision=_integer(parameters, "authorization-revision"),
        expected_revision=0,
        idempotency_key=_required(parameters, "idempotency-key"),
        base_version=base_version,
        entries=entries,
    )
    held = session_required("technology apply")
    host = endpoint()
    version = _optional(parameters, "version")
    if version is None:
        marker = digest_canonical(
            "ai-stp:mapping-apply:v1",
            {
                "organization_id": organization,
                "base_version": base_version,
                "entries": [entry.model_dump(mode="json") for entry in entries],
            },
        )
        version = f"review-{marker.removeprefix('sha256:')[:16]}"
    view = cloud_technology.publish_mapping(host, held.access_token, organization, version, request)

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


def technology_create(parameters: Mapping[str, object]) -> Answer[TechnologyView]:
    """Create a technology record; `--active` publishes it past draft."""
    organization = _required(parameters, "organization")
    name = _required(parameters, "name")
    category_ids = [str(item) for item in cast(list[object], parameters.get("category-id") or [])]
    if not category_ids:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a technology needs at least one --category-id",
            details={"option": "--category-id"},
        )
    description = _optional(parameters, "description") or ""
    request = TechnologyWriteRequest(
        authorization_revision=_integer(parameters, "authorization-revision"),
        expected_revision=0,
        idempotency_key=_required(parameters, "idempotency-key"),
        metadata=TechnologyMetadata(name=name, category_ids=category_ids, description=description),
    )
    held = session_required("technology create")
    host = endpoint()
    view = cloud_technology.write_technology(host, held.access_token, organization, request)
    if parameters.get("active"):
        view = cloud_technology.change_technology_lifecycle(
            host,
            held.access_token,
            organization,
            view.technology_id,
            TechnologyLifecycleRequest(
                lifecycle="active",
                authorization_revision=_integer(parameters, "authorization-revision") + 1,
                expected_revision=view.revision,
                idempotency_key=_required(parameters, "idempotency-key") + "-activate",
            ),
        )
    return Answer(view)


def technology_category_create(parameters: Mapping[str, object]) -> Answer[CategoryView]:
    """Create a technology category — a draft unless `--active` is given."""
    organization = _required(parameters, "organization")
    request = CategoryWriteRequest(
        authorization_revision=_integer(parameters, "authorization-revision"),
        expected_revision=0,
        idempotency_key=_required(parameters, "idempotency-key"),
        metadata=TechnologyCategoryMetadata(
            name=_required(parameters, "name"),
            description=_optional(parameters, "description") or "",
        ),
        state="active" if parameters.get("active") else "draft",
    )
    held = session_required("technology category create")
    return Answer(
        cloud_technology.write_category(endpoint(), held.access_token, organization, request)
    )


def technology_versions(parameters: Mapping[str, object]) -> Answer[TechnologyMappingList]:
    """List every mapping snapshot the organization published."""
    organization = _required(parameters, "organization")
    held = session_required("technology mappings list")
    return Answer(cloud_technology.list_mappings(endpoint(), held.access_token, organization))


def read_decisions(path: Path) -> list[TaskTechnologyDecision]:
    """One `--decisions` document → validated decision rows."""
    if not path.is_file():
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "the decisions file does not exist",
            details={"path": redact_home(path)},
        )
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the decisions file cannot be read",
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
                "the decisions file is not a JSON or YAML document",
                details={"path": redact_home(path)},
            ) from error
    if not isinstance(parsed, list) or not parsed:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the decisions file must hold a nonempty list of review decisions",
            details={"path": redact_home(path)},
        )
    try:
        return [TaskTechnologyDecision.model_validate(item) for item in cast(list[object], parsed)]
    except ValidationError as error:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a review decision does not match the contract",
            details={"path": redact_home(path), "errors": field_issues(error)},
        ) from error


def resolve_decisions(
    *,
    organization: str,
    decisions: Sequence[TaskTechnologyDecision],
    authorization_revision: int,
    idempotency_key: str,
    base_version: str | None = None,
    mapping_version: str | None = None,
) -> TaskTechnologyOutcome:
    """Execute one decision list against the organization's review queue.

    `technology_name` decisions reuse an existing record on an exact
    normalized-name match — a rerun after a partial failure converges instead
    of colliding — and create one otherwise. A category created to hold a
    technology is published immediately: classifications only accept active
    categories. `propose` decisions leave the queue entry open with a
    candidate; `apply` decisions fold into one derived snapshot so a single
    publish resolves the whole batch.
    """
    held = session_required("technology resolve")
    host = endpoint()
    # Every mutation authorizes against the organization's current policy
    # revision; the ones that bump it are counted so the next call stays
    # honest. Review proposals do not bump it.
    revision = authorization_revision

    categories_by_name: dict[str, str] | None = None
    technologies_by_name: dict[str, str] | None = None

    def category_index() -> dict[str, str]:
        nonlocal categories_by_name
        if categories_by_name is None:
            categories_by_name = {
                normalize_technology_name(item.name): item.category_id
                for item in cloud_technology.list_categories(
                    host, held.access_token, organization
                ).items
            }
        return categories_by_name

    def technology_index() -> dict[str, str]:
        nonlocal technologies_by_name
        if technologies_by_name is None:
            technologies_by_name = {}
            for item in cloud_technology.list_technologies(
                host, held.access_token, organization
            ).items:
                technologies_by_name[normalize_technology_name(item.name)] = item.technology_id
                for alias in item.aliases:
                    technologies_by_name.setdefault(
                        normalize_technology_name(alias), item.technology_id
                    )
        return technologies_by_name

    created_technology_ids: list[str] = []
    created_category_ids: list[str] = []
    proposed: list[str] = []
    apply_entries: dict[tuple[str, str], TechnologyMappingEntry] = {}

    for index, decision in enumerate(decisions):
        key = f"{idempotency_key}-d{index}"
        technology_id = decision.technology_id
        if technology_id is None:
            technology_name = cast(str, decision.technology_name)
            technology_id = technology_index().get(normalize_technology_name(technology_name))
        if technology_id is None:
            technology_name = cast(str, decision.technology_name)
            category_ids = list(decision.category_ids)
            if decision.category_name is not None:
                normalized = normalize_technology_name(decision.category_name)
                category_id = category_index().get(normalized)
                if category_id is None:
                    created = cloud_technology.write_category(
                        host,
                        held.access_token,
                        organization,
                        CategoryWriteRequest(
                            authorization_revision=revision,
                            expected_revision=0,
                            idempotency_key=f"{key}-category",
                            metadata=TechnologyCategoryMetadata(
                                name=decision.category_name,
                                description=decision.description,
                            ),
                            state="active",
                        ),
                    )
                    revision += 1
                    category_id = created.category_id
                    category_index()[normalized] = category_id
                    created_category_ids.append(category_id)
                if category_id not in category_ids:
                    category_ids.append(category_id)
            if not category_ids:
                raise CliFailure(
                    "AI_STP_VALIDATION_ERROR",
                    "a new technology needs at least one category",
                    details={"decision": index, "technology": technology_name},
                )
            created_t = cloud_technology.write_technology(
                host,
                held.access_token,
                organization,
                TechnologyWriteRequest(
                    authorization_revision=revision,
                    expected_revision=0,
                    idempotency_key=key,
                    metadata=TechnologyMetadata(
                        name=technology_name,
                        category_ids=category_ids,
                        description=decision.description,
                    ),
                ),
            )
            revision += 1
            technology_id = created_t.technology_id
            technology_index()[normalize_technology_name(created_t.name)] = technology_id
            created_technology_ids.append(technology_id)
            if decision.active and created_t.lifecycle != "active":
                created_t = cloud_technology.change_technology_lifecycle(
                    host,
                    held.access_token,
                    organization,
                    technology_id,
                    TechnologyLifecycleRequest(
                        authorization_revision=revision,
                        expected_revision=created_t.revision,
                        idempotency_key=f"{key}-activate",
                        lifecycle="active",
                    ),
                )
                revision += 1
        if decision.mode == "propose":
            cloud_technology.review_unmapped(
                host,
                held.access_token,
                organization,
                TechnologyUnmappedReviewRequest(
                    authorization_revision=revision,
                    expected_revision=0,
                    idempotency_key=f"{key}-propose",
                    kind=decision.kind,
                    coordinate=decision.coordinate,
                    candidate_technology_id=technology_id,
                ),
            )
            proposed.append(decision.coordinate)
        else:
            apply_entries[(decision.kind, decision.coordinate)] = TechnologyMappingEntry(
                kind=decision.kind,
                coordinate=decision.coordinate,
                technology_id=technology_id,
                provenance="cli-review",
            )

    view: TechnologyMappingView | None = None
    if apply_entries:
        entries = list(apply_entries.values())
        if base_version is None:
            registry = configured_path()
            if registry.exists():
                with closing(open_registry(registry, create=False)) as connection:
                    held_snapshot = tech_findings.cached_mapping(
                        connection, organization_id=organization
                    )
                base_version = held_snapshot.version if held_snapshot is not None else None
        version = mapping_version
        if version is None:
            marker = digest_canonical(
                "ai-stp:mapping-apply:v1",
                {
                    "organization_id": organization,
                    "base_version": base_version,
                    "entries": [entry.model_dump(mode="json") for entry in entries],
                },
            )
            version = f"review-{marker.removeprefix('sha256:')[:16]}"
        view = cloud_technology.publish_mapping(
            host,
            held.access_token,
            organization,
            version,
            TechnologyMappingRequest(
                authorization_revision=revision,
                expected_revision=0,
                idempotency_key=f"{idempotency_key}-publish",
                base_version=base_version,
                entries=entries,
            ),
        )
        with (
            closing(open_registry(configured_path(), create=True)) as connection,
            transaction(connection),
        ):
            tech_findings.cache_mapping(
                connection,
                organization_id=organization,
                version=view.version,
                digest=view.digest,
                entries=[
                    (entry.kind, entry.coordinate, entry.technology_id) for entry in view.entries
                ],
                at=moment(),
            )
    return TaskTechnologyOutcome(
        action="resolve",
        organization_id=organization,
        mapping_version=view.version if view is not None else "",
        mapping_digest=view.digest if view is not None else "",
        proposed=proposed,
        applied=[entry.coordinate for entry in apply_entries.values()],
        created_technology_ids=created_technology_ids,
        created_category_ids=created_category_ids,
    )


def technology_resolve(parameters: Mapping[str, object]) -> Answer[TaskTechnologyOutcome]:
    """Apply one `--decisions` document to the organization's review queue."""
    given = _optional(parameters, "decisions")
    if given is None:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a decisions document is required",
            details={"option": "--decisions"},
        )
    decisions = read_decisions(Path(given).resolve())
    return Answer(
        resolve_decisions(
            organization=_required(parameters, "organization"),
            decisions=decisions,
            authorization_revision=_integer(parameters, "authorization-revision"),
            idempotency_key=_required(parameters, "idempotency-key"),
            base_version=_optional(parameters, "base-version"),
            mapping_version=_optional(parameters, "version"),
        )
    )
