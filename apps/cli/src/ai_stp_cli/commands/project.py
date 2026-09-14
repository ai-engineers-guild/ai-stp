"""`ai-stp project` — finding projects without scanning anything (issue #154)."""

import sqlite3
from collections.abc import Mapping
from contextlib import closing
from pathlib import Path
from typing import cast

from pydantic import ValidationError

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
    project_ledger,
    project_links,
    project_passport,
    projects,
    revisions,
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
    ProjectRevisionPullResponse,
    ProjectRevisionPushRequest,
    ProjectRevisionPushResponse,
    ProjectRevisionView,
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
from ai_stp_foundation.errors import ERROR_CODES
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
    local_project_id = _required(parameters, "local-project-id")
    if not is_valid_id(local_project_id, "project"):
        raise CliFailure("AI_STP_VALIDATION_ERROR", "--local-project-id must be a project id")
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
    with closing(open_registry(configured_path())) as connection:
        _rebind_empty_link(
            connection,
            parameters=parameters,
            access_token=held.access_token,
            local_project_id=local_project_id,
        )
        response = cloud_context.sync_plan(
            endpoint(),
            held.access_token,
            _required(parameters, "organization-id"),
            link_id,
            request,
        )
        with transaction(connection):
            project_links.cache_sync_plan(
                connection,
                local_project_id=local_project_id,
                plan=response,
                idempotency_key=request.idempotency_key,
                created_at=moment(),
            )
    return Answer(response)


def sync_apply(parameters: Mapping[str, object]) -> Answer[ProjectSyncPlanResponse]:
    """Apply one exact ready sync plan and keep its receipt whatever follows.

    The order here is the whole point. A remote effect that succeeded is not
    allowed to disappear because something after it failed, and no network call
    runs inside a write transaction: `BEGIN IMMEDIATE` holds the local write
    lock, so a request made under it blocks every other local writer for as long
    as the network takes and then rolls back the receipt if it fails.

    Three outcomes are different things and are reported as different things:
    the effect happened and this device knows it, the effect happened and the
    local view of the link is stale, and the effect is unknown. The last one
    keeps the exact idempotency key, because the way out of an unknown effect is
    to ask again as the *same* operation rather than to start a second one.
    """
    _confirmed(parameters, "sync apply")
    link_id = _required(parameters, "link-id")
    organization_id = _required(parameters, "organization-id")
    local_project_id = _required(parameters, "local-project-id")
    plan_id = _required(parameters, "plan-id")
    request = ProjectSyncApplyRequest(
        plan_digest=_required(parameters, "plan-digest"),
        expected_link_revision=_integer(parameters, "expected-link-revision"),
        authorization_revision=_required(parameters, "authorization-revision"),
        idempotency_key=_required(parameters, "idempotency-key"),
    )
    held = cloud_auth.required("project sync apply")
    warnings: list[str] = []
    with closing(open_registry(configured_path())) as connection:
        _rebind_empty_link(
            connection,
            parameters=parameters,
            access_token=held.access_token,
            local_project_id=local_project_id,
        )
        cached = _checked_locally(
            project_links.cached_sync_plan(
                connection, local_project_id=local_project_id, plan_id=plan_id
            ),
            held_link=project_links.cached_link(connection, local_project_id=local_project_id),
            parameters=parameters,
            plan_id=plan_id,
            request=request,
        )
        if cached.receipt is not None and cached.apply_idempotency_key == request.idempotency_key:
            # The effect already happened and this device recorded it. Sending
            # the same key again would be answered from the server's receipt;
            # reading the local one costs nothing and cannot fail.
            response = cached.receipt
        else:
            with transaction(connection):
                project_links.begin_sync_apply(
                    connection,
                    local_project_id=local_project_id,
                    plan_id=plan_id,
                    idempotency_key=request.idempotency_key,
                )
            try:
                response = cloud_context.sync_apply(
                    endpoint(), held.access_token, organization_id, link_id, plan_id, request
                )
            except CliFailure as failure:
                unknown = _effect_unknown(failure)
                with transaction(connection):
                    project_links.mark_sync_apply(
                        connection,
                        local_project_id=local_project_id,
                        plan_id=plan_id,
                        state="unknown" if unknown else "failed",
                    )
                raise _with_effect(failure, parameters, unknown=unknown) from failure
            with transaction(connection):
                project_links.record_sync_apply(
                    connection,
                    local_project_id=local_project_id,
                    plan=response,
                    idempotency_key=request.idempotency_key,
                )
        try:
            refreshed = cloud_context.show(endpoint(), held.access_token, organization_id, link_id)
        except CliFailure:
            # Enrichment, not the effect. The link is the server's to report and
            # this device can ask again; the receipt above stays either way.
            warnings.append(
                "the sync was applied; refreshing the cached link failed, "
                "so the local link view is stale until `project link show` succeeds"
            )
        else:
            with transaction(connection):
                project_links.cache_link(connection, refreshed)
    return Answer(response, tuple(warnings))


def revision_push(parameters: Mapping[str, object]) -> Answer[ProjectRevisionPushResponse]:
    """Publish the local passport projection into the organization ledger.

    Sync planning refuses a revision the organization has not seen. This is the
    transport that puts one there: allowlisted passport facts, content-addressed
    with the same domain the API recomputes, and a durable attempt so a lost
    answer is retried as the same operation.
    """
    _confirmed(parameters, "revision push")
    organization_id = _required(parameters, "organization-id")
    link_id = _required(parameters, "link-id")
    local_project_id = _required(parameters, "local-project-id")
    if not is_valid_id(local_project_id, "project"):
        raise CliFailure("AI_STP_VALIDATION_ERROR", "--local-project-id must be a project id")
    held = cloud_auth.required("project revision push")
    warnings: list[str] = []
    with closing(open_registry(configured_path())) as connection:
        cached = project_ledger.cached_push(
            connection,
            local_project_id=local_project_id,
            idempotency_key=_required(parameters, "idempotency-key"),
        )
        replayed = False
        if cached is not None and (
            cached.link_id != link_id
            or cached.organization_id != organization_id
            or _key_conflicts(cached.request, parameters)
        ):
            raise CliFailure(
                "AI_STP_CONFLICT",
                "that idempotency key already belongs to another revision push",
                details={"idempotency_key": cached.idempotency_key},
                next_actions=[_link_show(parameters), _revision_help()],
            )
        if cached is not None and cached.receipt is not None:
            response = cached.receipt
            replayed = True
        else:
            if cached is not None:
                request = cached.request
            else:
                binding = _rebind_empty_link(
                    connection,
                    parameters=parameters,
                    access_token=held.access_token,
                    local_project_id=local_project_id,
                )
                request = _push_request(connection, parameters=parameters, binding=binding)
            with transaction(connection):
                project_ledger.begin_push(
                    connection,
                    local_project_id=local_project_id,
                    link_id=link_id,
                    organization_id=organization_id,
                    request=request,
                )
            try:
                response = cloud_context.revision_push(
                    endpoint(), held.access_token, organization_id, link_id, request
                )
            except CliFailure as failure:
                unknown = _effect_unknown(failure)
                with transaction(connection):
                    project_ledger.mark_push(
                        connection,
                        local_project_id=local_project_id,
                        idempotency_key=request.idempotency_key,
                        state="unknown" if unknown else "failed",
                    )
                raise _with_push_effect(failure, parameters, request, unknown=unknown) from failure
            with transaction(connection):
                project_ledger.record_push(
                    connection,
                    local_project_id=local_project_id,
                    idempotency_key=request.idempotency_key,
                    receipt=response,
                )
                if response.receipt.revision_id is not None:
                    project_ledger.cache_revision(
                        connection,
                        local_project_id=local_project_id,
                        link_id=link_id,
                        item=_pushed_view(
                            request,
                            response,
                            account_id=held.account_id,
                            device_id=held.device_id,
                        ),
                        origin="pushed",
                    )
        try:
            refreshed = cloud_context.show(endpoint(), held.access_token, organization_id, link_id)
        except CliFailure:
            if replayed:
                warnings.append(
                    "refreshing the cached link failed, "
                    "so the local link view is stale until `project link show` succeeds"
                )
            else:
                warnings.append(
                    "the revision was pushed; refreshing the cached link failed, "
                    "so the local link view is stale until `project link show` succeeds"
                )
        else:
            if refreshed.local_project_id == local_project_id:
                with transaction(connection):
                    project_links.cache_link(connection, refreshed)
            else:
                warnings.append(
                    "the revision was pushed; the server link names another local project, "
                    "so this device did not replace its cached binding"
                )
    return Answer(response, tuple(warnings))


def revision_pull(parameters: Mapping[str, object]) -> Answer[ProjectRevisionPullResponse]:
    """Read the tenant ledger and remember the redacted nodes on this device."""
    organization_id = _required(parameters, "organization-id")
    link_id = _required(parameters, "link-id")
    local_project_id = _required(parameters, "local-project-id")
    if not is_valid_id(local_project_id, "project"):
        raise CliFailure("AI_STP_VALIDATION_ERROR", "--local-project-id must be a project id")
    held = cloud_auth.required("project revision pull")
    with closing(open_registry(configured_path())) as connection:
        _rebind_empty_link(
            connection,
            parameters=parameters,
            access_token=held.access_token,
            local_project_id=local_project_id,
        )
        response = cloud_context.revision_pull(
            endpoint(),
            held.access_token,
            organization_id,
            link_id,
            _required(parameters, "authorization-revision"),
        )
        with transaction(connection):
            for item in response.items:
                project_ledger.cache_revision(
                    connection,
                    local_project_id=local_project_id,
                    link_id=link_id,
                    item=item,
                    origin="pulled",
                )
    return Answer(response)


def _checked_locally(
    cached: project_links.CachedSyncPlan | None,
    *,
    held_link: project_links.CachedLink | None,
    parameters: Mapping[str, object],
    plan_id: str,
    request: ProjectSyncApplyRequest,
) -> project_links.CachedSyncPlan:
    """Refuse before the effect, not after it.

    Everything here is knowable without the network, and each of these reaching
    the server would spend a remote operation to be told what this device
    already held.
    """
    if cached is None:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "this device holds no cached sync plan with that identifier",
            details={"plan_id": plan_id},
            next_actions=[_link_show(parameters), _sync_help()],
        )
    _same_link(cached, held_link, parameters=parameters, plan_id=plan_id)
    if cached.plan_digest != request.plan_digest:
        raise CliFailure(
            "AI_STP_PLAN_STALE",
            "the supplied digest is not the one this device cached for that plan",
            details={"plan_id": plan_id},
            next_actions=[_link_show(parameters), _sync_help()],
        )
    if (
        cached.apply_idempotency_key is not None
        and cached.apply_idempotency_key != request.idempotency_key
        and cached.apply_state in {"pending", "unknown", "applied"}
    ):
        raise CliFailure(
            "AI_STP_CONFLICT",
            "that plan already carries an apply under a different idempotency key",
            details={"plan_id": plan_id, "idempotency_key": cached.apply_idempotency_key},
            next_actions=[_link_show(parameters)],
        )
    return cached


def _same_link(
    cached: project_links.CachedSyncPlan,
    held_link: project_links.CachedLink | None,
    *,
    parameters: Mapping[str, object],
    plan_id: str,
) -> None:
    """The plan, the link and the organization named here must be one binding.

    A local project id was the whole key of the cache, so a plan created for one
    link could be applied under another link's identifiers without anything
    local disagreeing. Rows written before this device recorded the link carry
    an empty id: inventing the binding would be the same defect, so they must
    be re-observed rather than guessed at.
    """
    link_id = _required(parameters, "link-id")
    organization_id = _required(parameters, "organization-id")
    if not cached.link_id or (held_link is not None and not held_link.link_id):
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "this device must re-observe the project link before applying a plan",
            details={"plan_id": plan_id, "link_id": link_id},
            next_actions=[_link_show(parameters), _sync_help()],
        )
    mismatched = (
        cached.link_id != link_id
        or (held_link is not None and held_link.link_id != link_id)
        or (held_link is not None and held_link.organization_id != organization_id)
    )
    if mismatched:
        raise CliFailure(
            "AI_STP_CONFLICT",
            "that plan belongs to another project link on this device",
            details={"plan_id": plan_id, "link_id": link_id},
            next_actions=[_link_show(parameters)],
        )


def _link_show(parameters: Mapping[str, object]) -> str:
    """Read the authority on the link, with the identifiers this call used."""
    return (
        f"project link show --organization-id {_required(parameters, 'organization-id')} "
        f"--link-id {_required(parameters, 'link-id')} --json"
    )


def _sync_help() -> str:
    """The family that constructs a fresh plan, without pretending the argv is complete."""
    return "help --path project --json"


def _revision_help() -> str:
    """The family that moves passport projections through the organization ledger."""
    return "help --path project --json"


def _rebind_empty_link(
    connection: sqlite3.Connection,
    *,
    parameters: Mapping[str, object],
    access_token: str,
    local_project_id: str,
) -> project_links.CachedLink:
    """Confirm an empty migrated binding with the server, then stamp it locally.

    Schema 40 added `link_id` with an empty default. Inventing the binding from
    the flags would be the original defect; asking the authority and checking
    that the named local project is the one on that link is re-observation.
    """
    link_id = _required(parameters, "link-id")
    organization_id = _required(parameters, "organization-id")
    held_link = project_links.cached_link(connection, local_project_id=local_project_id)
    if held_link is not None and held_link.link_id:
        if held_link.link_id != link_id or held_link.organization_id != organization_id:
            raise CliFailure(
                "AI_STP_CONFLICT",
                "that local project is bound to another project link on this device",
                details={"link_id": link_id, "local_project_id": local_project_id},
                next_actions=[_link_show(parameters)],
            )
        with transaction(connection):
            project_links.bind_empty_link_ids(
                connection, local_project_id=local_project_id, link_id=held_link.link_id
            )
        rebound = project_links.cached_link(connection, local_project_id=local_project_id)
        return rebound if rebound is not None else held_link
    try:
        live = cloud_context.show(endpoint(), access_token, organization_id, link_id)
    except CliFailure as failure:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "this device must re-observe the project link before continuing",
            details={"link_id": link_id, "local_project_id": local_project_id},
            next_actions=[_link_show(parameters), _sync_help()],
        ) from failure
    if live.local_project_id != local_project_id or live.organization_id != organization_id:
        raise CliFailure(
            "AI_STP_CONFLICT",
            "that link belongs to another local project",
            details={"link_id": link_id, "local_project_id": local_project_id},
            next_actions=[_link_show(parameters)],
        )
    with transaction(connection):
        project_links.cache_link(connection, live)
        project_links.bind_empty_link_ids(
            connection, local_project_id=local_project_id, link_id=live.link_id
        )
    rebound = project_links.cached_link(connection, local_project_id=local_project_id)
    if rebound is None or not rebound.link_id:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "this device must re-observe the project link before continuing",
            details={"link_id": link_id, "local_project_id": local_project_id},
            next_actions=[_link_show(parameters), _sync_help()],
        )
    return rebound


def _key_conflicts(
    cached: ProjectRevisionPushRequest,
    parameters: Mapping[str, object],
) -> bool:
    """Whether this key is being reused for a different operation.

    The stored request *is* the operation. Implicit parents and expected head
    are filled from the link after a successful push, so re-deriving a document
    would refuse the receipt the key already owns. A caller that still has no
    passport can still read that receipt, and an unknown effect retries the
    stored body rather than asking the passport to exist again.
    """
    if cached.event_id != _required(parameters, "event-id"):
        return True
    if cached.authorization_revision != _required(parameters, "authorization-revision"):
        return True
    given_parents = _repeated(parameters, "parent-revision-id")
    if given_parents and list(cached.parent_revision_ids) != given_parents:
        return True
    given_expected = parameters.get("expected-head-revision-id")
    return given_expected not in (None, "") and cached.expected_head_revision_id != str(
        given_expected
    )


def _push_request(
    connection: sqlite3.Connection,
    *,
    parameters: Mapping[str, object],
    binding: project_links.CachedLink,
) -> ProjectRevisionPushRequest:
    """Build the exact ledger document this device is about to send."""
    local_project_id = _required(parameters, "local-project-id")
    stored = revisions.head(connection, local_project_id)
    if stored is None:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "this local project has no passport revision to publish",
            details={"local_project_id": local_project_id},
            next_actions=["project passport --root <path> --json", _revision_help()],
        )
    try:
        projection = project_ledger.projection_from_passport(
            stored, remote_project_id=binding.remote_project_id
        )
    except ValueError as error:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the local passport cannot be projected onto the public allowlist",
            details={"reason": str(error)},
            next_actions=["project passport --root <path> --json"],
        ) from error
    parents = _repeated(parameters, "parent-revision-id")
    if not parents:
        if project_ledger.is_revision_id(binding.remote_revision):
            parents = [binding.remote_revision]
        else:
            previous = project_ledger.latest_accepted_revision(
                connection, local_project_id=local_project_id, link_id=binding.link_id
            )
            parents = [previous] if previous is not None else []
    expected = _optional(parameters, "expected-head-revision-id")
    if expected is None and len(parents) == 1:
        expected = parents[0]
    revision_id, content_digest = project_ledger.signed_revision(
        remote_project_id=binding.remote_project_id,
        parent_revision_ids=parents,
        operation="upsert",
        projection=projection,
    )
    try:
        return ProjectRevisionPushRequest(
            event_id=_required(parameters, "event-id"),
            revision_id=revision_id,
            parent_revision_ids=parents,
            operation="upsert",
            content_digest=content_digest,
            projection=projection,
            expected_head_revision_id=expected,
            authorization_revision=_required(parameters, "authorization-revision"),
            idempotency_key=_required(parameters, "idempotency-key"),
        )
    except ValidationError as error:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the revision push request is not a valid ledger document",
            details={"reason": str(error)},
            next_actions=[_revision_help()],
        ) from error


def _pushed_view(
    request: ProjectRevisionPushRequest,
    response: ProjectRevisionPushResponse,
    *,
    account_id: str,
    device_id: str,
) -> ProjectRevisionView:
    """A local cache row for a push the server addressed."""
    revision_id = response.receipt.revision_id or request.revision_id
    return ProjectRevisionView(
        revision_id=revision_id,
        parent_revision_ids=list(request.parent_revision_ids),
        operation=request.operation,
        content_digest=request.content_digest,
        projection=dict(request.projection),
        actor_account_id=account_id,
        device_id=device_id,
        created_at=moment(),
    )


def _with_push_effect(
    failure: CliFailure,
    parameters: Mapping[str, object],
    request: ProjectRevisionPushRequest,
    *,
    unknown: bool,
) -> CliFailure:
    """Say what is known about the push, and how to finish the same operation."""
    if not unknown:
        return failure
    details = dict(failure.details)
    details["effect"] = "unknown"
    retry = [
        "project revision push",
        f"--organization-id {_required(parameters, 'organization-id')}",
        f"--link-id {_required(parameters, 'link-id')}",
        f"--local-project-id {_required(parameters, 'local-project-id')}",
        f"--authorization-revision {request.authorization_revision}",
        f"--event-id {request.event_id}",
        f"--idempotency-key {request.idempotency_key}",
    ]
    for parent in request.parent_revision_ids:
        retry.append(f"--parent-revision-id {parent}")
    if request.expected_head_revision_id is not None:
        retry.append(f"--expected-head-revision-id {request.expected_head_revision_id}")
    retry.append("--confirm --json")
    return CliFailure(
        failure.code,
        failure.message,
        retryable=failure.retryable,
        details=details,
        next_actions=[_link_show(parameters), " ".join(retry)],
    )


def _repeated(parameters: Mapping[str, object], name: str) -> list[str]:
    value = parameters.get(name, ())
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if not isinstance(value, tuple | list):
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a required option must be repeatable text",
            details={"option": f"--{name}"},
        )
    return [str(item) for item in cast(tuple[object, ...] | list[object], value) if str(item)]


def _effect_unknown(failure: CliFailure) -> bool:
    """Whether the server may have acted despite this failure.

    The registry's own disposition decides it: a dependency that did not answer,
    a call that timed out, a body outside the contract and an internal fault are
    all failures the caller cannot conclude anything from. A refusal the server
    *decided* — bad input, a stale precondition, a missing grant — is an answer,
    and an answer means no effect.
    """
    entry = ERROR_CODES.get(failure.code)
    return entry is None or entry.handling in {
        "retry_if_retryable",
        "inspect_effect",
        "report_bug",
    }


def _with_effect(
    failure: CliFailure, parameters: Mapping[str, object], *, unknown: bool
) -> CliFailure:
    """Say what is known about the effect, and how to finish the same operation."""
    if not unknown:
        return failure
    details = dict(failure.details)
    details["effect"] = "unknown"
    retry = " ".join(
        [
            "project sync apply",
            f"--organization-id {_required(parameters, 'organization-id')}",
            f"--link-id {_required(parameters, 'link-id')}",
            f"--plan-id {_required(parameters, 'plan-id')}",
            f"--local-project-id {_required(parameters, 'local-project-id')}",
            f"--plan-digest {_required(parameters, 'plan-digest')}",
            f"--expected-link-revision {_required(parameters, 'expected-link-revision')}",
            f"--authorization-revision {_required(parameters, 'authorization-revision')}",
            # The same key, deliberately. A fresh one would ask the server for a
            # second effect on a plan that may already have had one.
            f"--idempotency-key {_required(parameters, 'idempotency-key')}",
            "--confirm --json",
        ]
    )
    return CliFailure(
        failure.code,
        failure.message,
        retryable=failure.retryable,
        details=details,
        next_actions=[_link_show(parameters), retry],
    )


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
