"""`ai-stp project` — finding projects without scanning anything (issue #154)."""

import sqlite3
from collections.abc import Mapping
from contextlib import closing
from pathlib import Path
from typing import cast

from ai_stp_cli import identity
from ai_stp_cli.answer import Answer
from ai_stp_cli.cloud import context as cloud_context
from ai_stp_cli.commands import cloud_auth
from ai_stp_cli.commands.auth import endpoint
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import (
    harnesses,
    importing,
    project_index,
    project_links,
    project_passport,
    projects,
    symbols,
)
from ai_stp_cli.local.database import configured_path, open_registry, transaction
from ai_stp_cli.local.passports import moment, owner
from ai_stp_cli.paths import redact_home
from ai_stp_contracts.context import (
    ProjectLinkPlanRequest,
    ProjectLinkPlanResponse,
    ProjectLinkRequest,
    ProjectLinkResponse,
    ProjectSyncApplyRequest,
    ProjectSyncPlanRequest,
    ProjectSyncPlanResponse,
    ProjectUnlinkPlanRequest,
    ProjectUnlinkPlanResponse,
    ProjectUnlinkRequest,
)
from ai_stp_contracts.machine_help import (
    DiscoveryDiagnostic,
    ExcludedPath,
    ImportedFile,
    ImportedSetup,
    ImportInspection,
    IndexedFile,
    LanguageOutline,
    PassportView,
    ProjectCandidate,
    ProjectCandidates,
    ProjectIndex,
    ProjectSymbols,
    SetupImportComponent,
    SetupImportPlan,
)
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.harnesses import HARNESS_IDS
from ai_stp_foundation.ids import is_valid_id


def link(parameters: Mapping[str, object]) -> Answer[ProjectLinkResponse]:
    """Confirm one exact server-authored link plan and cache the response."""
    _confirmed(parameters, "link create")
    request = ProjectLinkRequest(
        plan_id=_required(parameters, "plan-id"),
        plan_digest=_required(parameters, "plan-digest"),
        authorization_revision=_required(parameters, "authorization-revision"),
        idempotency_key=_required(parameters, "idempotency-key"),
    )
    held = cloud_auth.required("project link")
    response = cloud_context.link(
        endpoint(), held.access_token, _required(parameters, "organization-id"), request
    )
    with closing(open_registry(configured_path())) as connection, transaction(connection):
        project_links.cache_link(connection, response)
    return Answer(response)


def link_plan(parameters: Mapping[str, object]) -> Answer[ProjectLinkPlanResponse]:
    """Create one no-side-effect server-authored link plan."""
    local_project_id = _required(parameters, "local-project-id")
    if not is_valid_id(local_project_id, "project"):
        raise CliFailure("AI_STP_VALIDATION_ERROR", "--local-project-id must be a project id")
    request = ProjectLinkPlanRequest(
        local_project_id=local_project_id,
        remote_project_id=_required(parameters, "remote-project-id"),
        provider_project_id=_optional(parameters, "provider-project-id"),
        local_revision=_required(parameters, "local-revision"),
        remote_revision=_required(parameters, "remote-revision"),
        provider_revision=_optional(parameters, "provider-revision"),
        authorization_revision=_required(parameters, "authorization-revision"),
        idempotency_key=_required(parameters, "idempotency-key"),
    )
    held = cloud_auth.required("project link plan")
    return Answer(
        cloud_context.link_plan(
            endpoint(), held.access_token, _required(parameters, "organization-id"), request
        )
    )


def link_plan_show(parameters: Mapping[str, object]) -> Answer[ProjectLinkPlanResponse]:
    """Read one authoritative link plan."""
    held = cloud_auth.required("project link plan show")
    return Answer(
        cloud_context.link_plan_show(
            endpoint(),
            held.access_token,
            _required(parameters, "organization-id"),
            _required(parameters, "plan-id"),
        )
    )


def link_show(parameters: Mapping[str, object]) -> Answer[ProjectLinkResponse]:
    """Read one authoritative link; the local cache is never used for this view."""
    held = cloud_auth.required("project link show")
    return Answer(
        cloud_context.show(
            endpoint(),
            held.access_token,
            _required(parameters, "organization-id"),
            _required(parameters, "link-id"),
        )
    )


def unlink(parameters: Mapping[str, object]) -> Answer[ProjectLinkResponse]:
    """Confirm one exact unlink plan without deleting either endpoint."""
    _confirmed(parameters, "unlink")
    link_id = _required(parameters, "link-id")
    request = ProjectUnlinkRequest(
        plan_id=_required(parameters, "plan-id"),
        plan_digest=_required(parameters, "plan-digest"),
        authorization_revision=_required(parameters, "authorization-revision"),
        idempotency_key=_required(parameters, "idempotency-key"),
    )
    held = cloud_auth.required("project unlink")
    response = cloud_context.unlink(
        endpoint(),
        held.access_token,
        _required(parameters, "organization-id"),
        link_id,
        request,
    )
    with closing(open_registry(configured_path())) as connection, transaction(connection):
        project_links.cache_link(connection, response)
    return Answer(response)


def unlink_plan(parameters: Mapping[str, object]) -> Answer[ProjectUnlinkPlanResponse]:
    """Create one no-side-effect server-authored unlink plan."""
    request = ProjectUnlinkPlanRequest(
        link_id=_required(parameters, "link-id"),
        expected_link_revision=_integer(parameters, "expected-link-revision"),
        authorization_revision=_required(parameters, "authorization-revision"),
        idempotency_key=_required(parameters, "idempotency-key"),
    )
    held = cloud_auth.required("project unlink plan")
    return Answer(
        cloud_context.unlink_plan(
            endpoint(), held.access_token, _required(parameters, "organization-id"), request
        )
    )


def unlink_plan_show(parameters: Mapping[str, object]) -> Answer[ProjectUnlinkPlanResponse]:
    """Read one authoritative unlink plan."""
    held = cloud_auth.required("project unlink plan show")
    return Answer(
        cloud_context.unlink_plan_show(
            endpoint(),
            held.access_token,
            _required(parameters, "organization-id"),
            _required(parameters, "plan-id"),
        )
    )


def sync_plan(parameters: Mapping[str, object]) -> Answer[ProjectSyncPlanResponse]:
    """Ask the server for a deterministic, no-side-effect sync decision."""
    link_id = _required(parameters, "link-id")
    request = ProjectSyncPlanRequest(
        link_id=link_id,
        expected_link_revision=_integer(parameters, "expected-link-revision"),
        local_revision=_required(parameters, "local-revision"),
        remote_revision=_required(parameters, "remote-revision"),
        provider_revision=_optional(parameters, "provider-revision"),
        authorization_revision=_required(parameters, "authorization-revision"),
        idempotency_key=_required(parameters, "idempotency-key"),
    )
    held = cloud_auth.required("project sync plan")
    response = cloud_context.sync_plan(
        endpoint(),
        held.access_token,
        _required(parameters, "organization-id"),
        link_id,
        request,
    )
    with closing(open_registry(configured_path())) as connection, transaction(connection):
        project_links.cache_sync_plan(
            connection,
            local_project_id=_required(parameters, "local-project-id"),
            plan=response,
            idempotency_key=request.idempotency_key,
            created_at=moment(),
        )
    return Answer(response)


def sync_apply(parameters: Mapping[str, object]) -> Answer[ProjectSyncPlanResponse]:
    """Apply one exact ready sync plan and cache its idempotent receipt."""
    _confirmed(parameters, "sync apply")
    link_id = _required(parameters, "link-id")
    request = ProjectSyncApplyRequest(
        plan_digest=_required(parameters, "plan-digest"),
        expected_link_revision=_integer(parameters, "expected-link-revision"),
        authorization_revision=_required(parameters, "authorization-revision"),
        idempotency_key=_required(parameters, "idempotency-key"),
    )
    held = cloud_auth.required("project sync apply")
    response = cloud_context.sync_apply(
        endpoint(),
        held.access_token,
        _required(parameters, "organization-id"),
        link_id,
        _required(parameters, "plan-id"),
        request,
    )
    with closing(open_registry(configured_path())) as connection, transaction(connection):
        project_links.cache_sync_plan(
            connection,
            local_project_id=_required(parameters, "local-project-id"),
            plan=response,
            idempotency_key=request.idempotency_key,
            created_at=moment(),
        )
        project_links.cache_link(
            connection,
            cloud_context.show(
                endpoint(),
                held.access_token,
                _required(parameters, "organization-id"),
                link_id,
            ),
        )
    return Answer(response)


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


def _confirmed(parameters: Mapping[str, object], action: str) -> None:
    if parameters.get("confirm") is not True:
        raise CliFailure(
            "AI_STP_USER_DECISION_REQUIRED",
            "this action requires explicit confirmation",
            next_actions=[f"project {action} --confirm --json"],
        )


def discover(parameters: Mapping[str, object]) -> Answer[ProjectCandidates]:
    """List the projects inside a directory the user named. Creates nothing.

    The root is named rather than searched for. `SPEC-004` REQ-401 is explicit
    that the home directory is not scanned, and REQ-1416 says the same about a
    disk — so there is no mode where this command goes looking on its own.
    """
    given = parameters.get("root")
    if given is None:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a directory to look inside is required",
            next_actions=["project discover --root <path> --json"],
        )
    top = Path(str(given))
    found = projects.discover(top)
    return Answer(
        ProjectCandidates(
            discovery_root=redact_home(projects.resolved(top)),
            complete=found.complete,
            candidates=[_view(candidate) for candidate in found.candidates],
            diagnostics=[
                DiscoveryDiagnostic(
                    path=redact_home(item.path),
                    code=item.code,
                    reason=item.reason,
                )
                for item in found.diagnostics
            ],
        )
    )


def _view(candidate: projects.Candidate) -> ProjectCandidate:
    return ProjectCandidate(
        root=redact_home(candidate.root),
        kind=candidate.kind,  # pyright: ignore[reportArgumentType]
        state=candidate.state,  # pyright: ignore[reportArgumentType]
        markers=list(candidate.markers),
        reason=candidate.reason,
    )


def index(parameters: Mapping[str, object]) -> Answer[ProjectIndex]:
    """Index one project root, bounded, without reading anything unsafe.

    Reads and reports; writes nothing. The passport that records an index is a
    separate act, so looking at a project cannot change it.
    """
    given = parameters.get("root")
    if given is None:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a project root is required",
            next_actions=["project discover --root <path> --json"],
        )
    built = project_index.build(Path(str(given)))
    return Answer(
        ProjectIndex(
            root=redact_home(built.root),
            state=built.state,  # pyright: ignore[reportArgumentType]
            stopped_by=built.stopped_by,
            files=[
                IndexedFile(
                    path=item.path,
                    kind=item.kind,  # pyright: ignore[reportArgumentType]
                    language=item.language,
                    size_bytes=item.size_bytes,
                    digest=item.digest,
                    lines=item.lines,
                )
                for item in built.entries
            ],
            excluded=[ExcludedPath(path=item.path, reason=item.reason) for item in built.excluded],
        )
    )


def symbol_index(parameters: Mapping[str, object]) -> Answer[ProjectSymbols]:
    """Read a project's table of contents (`SPEC-004` REQ-404, REQ-411).

    The index decides what exists and what language it is; this reads only what
    the index hands over. Walking the tree a second time would be a second
    chance to disagree with the first, and the disagreement would reach a
    passport as a contradiction rather than as an error.
    """
    given = parameters.get("root")
    if given is None:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a project root is required",
            next_actions=["project discover --root <path> --json"],
        )
    root = Path(str(given))
    built = project_index.build(root)
    found = symbols.survey(
        built.root, [(item.path, item.language) for item in built.entries if item.language]
    )
    return Answer(
        ProjectSymbols(
            root=redact_home(built.root),
            state=found.state,  # pyright: ignore[reportArgumentType]
            stopped_by=found.stopped_by,
            languages=[
                LanguageOutline(
                    language=item.language,
                    state=item.state,  # pyright: ignore[reportArgumentType]
                    method=item.method,  # pyright: ignore[reportArgumentType]
                    reason=item.reason,
                    files=item.files,
                    symbols=item.symbols,
                    tests=item.tests,
                    entry_points=list(item.entry_points),
                )
                for item in found.languages
            ],
        )
    )


def passport(parameters: Mapping[str, object]) -> Answer[PassportView]:
    """Record a project passport revision for one root (`SPEC-004`, `P3-07`).

    Scanning twice keeps the project's identity and, if nothing changed, adds no
    revision: the content is identical, the revision id is that content's
    digest, and the store returns what is already there. Idempotency is the
    store's property here rather than a comparison made in this function, which
    is why there is no comparison in this function.
    """
    given = parameters.get("root")
    if given is None:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a project root is required",
            next_actions=["project discover --root <path> --json"],
        )
    current, _warning = identity.load_or_create()

    def work(connection: sqlite3.Connection) -> PassportView:
        found = project_passport.scan(connection, Path(str(given)))
        stored = project_passport.record(connection, found, device_id=current.device_id)
        document = cast(dict[str, JsonValue], stored.envelope.model_dump(mode="json"))
        return PassportView(
            kind=stored.envelope.kind,  # pyright: ignore[reportArgumentType]
            stable_id=stored.stable_id,
            revision_id=stored.revision_id,
            parent_revision_ids=list(stored.parents),
            created_at=stored.envelope.created_at,
            owner_id=stored.envelope.owner_id,
            facts=cast(dict[str, JsonValue], document["facts"]),
        )

    with closing(open_registry(configured_path(), create=True)) as connection:
        return Answer(work(connection))


def import_inspect(parameters: Mapping[str, object]) -> Answer[ImportInspection]:
    """Read one native configuration and report what it holds (`REQ-813`).

    Reads and nothing else. Nothing is written to the configuration, to the
    registry or anywhere else, which is what makes this safe to run against a
    working machine before deciding anything.
    """
    found = importing.inspect(_root(parameters), harness_id=_harness(parameters))
    return Answer(
        ImportInspection(
            root=redact_home(Path(found.root)),
            harness_id=found.harness_id,  # pyright: ignore[reportArgumentType]
            detection_rule=found.detection_rule,
            files=[
                ImportedFile(
                    path=item.path,
                    byte_length=item.byte_length,
                    digest=item.digest,
                    redacted_keys=list(item.redacted_keys),
                    unreadable=item.unreadable,
                    oversized=item.oversized,
                )
                for item in found.findings
            ],
            redacted_keys=list(found.redacted_keys),
            unreadable=list(found.unreadable),
            oversized=list(found.oversized),
        )
    )


def import_plan(parameters: Mapping[str, object]) -> Answer[SetupImportPlan]:
    """Plan exact setup/component registration without changing local state."""
    proposed = importing.plan(importing.inspect(_root(parameters), harness_id=_harness(parameters)))
    return Answer(
        SetupImportPlan(
            root=redact_home(Path(proposed.root)),
            harness_id=proposed.harness_id,  # pyright: ignore[reportArgumentType]
            inspection_digest=proposed.inspection_digest,
            plan_digest=proposed.plan_digest,
            components=[
                SetupImportComponent(
                    candidate_id=item.candidate_id,
                    component_type=item.component_type,  # pyright: ignore[reportArgumentType]
                    native_role=item.native_role,
                    paths=list(item.paths),
                    file_set_digest=item.file_set_digest,
                    byte_length=item.byte_length,
                )
                for item in proposed.components
            ],
            excluded=list(proposed.excluded),
            blocked_by=list(proposed.blocked_by),
            effects=list(proposed.effects),
        )
    )


def import_register(parameters: Mapping[str, object]) -> Answer[ImportedSetup]:
    """Register an inspected configuration as the user's own setup.

    The provider's backup reference is required and is not produced here: the
    provider owns the backup, and taking a reference to something nobody made
    would record a recovery path that does not exist.

    No secret value reaches the registry. Only the *names* of the keys whose
    values were removed travel, which is the whole of what `REQ-815` allows.
    """
    provider_ref = str(parameters.get("backup-ref") or "")
    plan_digest = str(parameters.get("plan-digest") or "")
    if not plan_digest:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the exact import plan digest is required",
            next_actions=["setup import register ... --plan-digest <digest> --json"],
        )
    harness = _harness(parameters)
    root = _root(parameters)

    def work(connection: sqlite3.Connection) -> ImportedSetup:
        at = moment()
        found = importing.inspect(root, harness_id=harness)
        # Pin what the capture was captured against. One detection, best
        # answer wins: the normalized token when the harness spoke, the raw
        # line when it spoke unparseably, and honestly empty when this machine
        # holds no answering installation — an imported tree from elsewhere is
        # exactly that case.
        detector = next((item for item in harnesses.DETECTORS if item.harness_id == harness), None)
        harness_version = ""
        if detector is not None:
            detected = harnesses.detect(detector)
            if detected.installations:
                first = detected.installations[0]
                if first.version != "unknown":
                    harness_version = first.normalized_version or first.version
        current, _warning = identity.load_or_create()
        imported = importing.register_graph(
            connection,
            found,
            expected_plan_digest=plan_digest,
            target_id=str(parameters.get("target") or root.name),
            provider_ref=provider_ref,
            partial=bool(parameters.get("partial", False)),
            harness_version=harness_version,
            owner_id=owner().account_id,
            device_id=current.device_id,
            at=at,
        )
        return ImportedSetup(
            stable_id=imported.stable_id,
            revision_id=imported.revision_id,
            backup_id=imported.backup_id,
            redacted_keys=list(found.redacted_keys),
            plan_digest=imported.plan_digest,
            component_ids=list(imported.component_ids),
        )

    with closing(open_registry(configured_path(), create=True)) as connection:
        return Answer(work(connection))


def _harness(parameters: Mapping[str, object]) -> str:
    harness = str(parameters.get("harness") or "")
    if harness not in HARNESS_IDS:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a supported harness identifier is required",
            details={"supported": ", ".join(sorted(HARNESS_IDS))},
            next_actions=["toolchain harnesses --json"],
        )
    return harness


def _root(parameters: Mapping[str, object]) -> Path:
    given = parameters.get("root")
    if given is None:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the configuration directory to read is required",
            next_actions=["toolchain harnesses --json"],
        )
    return Path(str(given)).expanduser()
