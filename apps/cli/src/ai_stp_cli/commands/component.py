"""`ai-stp component` — finding native components and adopting them (`#158`, `#159`).

Discovery and adoption are two commands because `SPEC-005` REQ-518 makes them
two acts. Looking is free and changes nothing; taking something into the local
registry is a decision, and a single command with a flag would let an agent make
that decision by getting the flag wrong.
"""

import hashlib
import sqlite3
from collections.abc import Mapping
from contextlib import closing
from pathlib import Path
from typing import Any, cast

from ai_stp_cli import identity
from ai_stp_cli.answer import Answer
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import (
    acquired_trust,
    authoring,
    cache,
    component_passports,
    components,
    consent,
    external_sources,
    github_evidence,
    lifecycle,
    path_inventory,
    revisions,
    search,
    skill_package,
    source_discovery,
    versions,
)
from ai_stp_cli.local.database import configured_path, open_readonly, open_registry, transaction
from ai_stp_cli.local.passports import moment, owner
from ai_stp_cli.paths import redact_home
from ai_stp_contracts.authoring import ComponentScaffoldPlan, ComponentScaffoldResult
from ai_stp_contracts.github_evidence import GitHubArchiveEvidence, GitHubArchiveHistory
from ai_stp_contracts.machine_help import (
    ComponentPassportSuggestion,
    ComponentPassportSuggestions,
    ComponentPassportValidation,
    ComponentQualityCheck,
    ComponentQualityDimension,
    ComponentQualityReport,
    ComponentScaffoldView,
    ComponentTemplateView,
    ConsentRecord,
    ConsentSummary,
    ExternalSourceIdentity,
    LocalSearchResults,
    NativeComponent,
    NativeComponentProvenance,
    NativeComponents,
    NativeDiscoveryDiagnostic,
    PassportView,
    PathInventory,
    RecordedVersion,
    SearchHit,
    SkillPackageFinding,
    SkillPackageReport,
    SourceSearchResult,
    VersionLine,
)
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.ids import new_id


def source_search(parameters: Mapping[str, object]) -> Answer[SourceSearchResult]:
    """Name-only discovery. Package and GitHub hits require the opt-in flag."""
    from ai_stp_cli.cloud import catalog as cloud_catalog
    from ai_stp_cli.commands.auth import endpoint

    query = str(parameters.get("query") or "")
    flag = bool(parameters.get("registry-discovery"))

    def catalog_search(needle: str) -> object:
        return cloud_catalog.search(endpoint(), "component", query=needle)

    path = configured_path()
    if path.exists():
        with closing(open_readonly(path)) as connection:
            return Answer(
                source_discovery.discover(
                    query,
                    registry_discovery=flag,
                    catalog_search=catalog_search,  # pyright: ignore[reportArgumentType]
                    connection=connection,
                )
            )
    return Answer(
        source_discovery.discover(
            query,
            registry_discovery=flag,
            catalog_search=catalog_search,  # pyright: ignore[reportArgumentType]
            connection=None,
        )
    )


def source_parse(parameters: Mapping[str, object]) -> Answer[ExternalSourceIdentity]:
    """Parse source syntax without claiming that its remote identity is exact."""
    value = _required(parameters, "source", "an external source identity is required")
    cwd = Path(str(parameters.get("root") or Path.cwd())).expanduser()
    return Answer(_source_view(external_sources.parse(value, cwd=cwd)))


def source_resolve(parameters: Mapping[str, object]) -> Answer[ExternalSourceIdentity]:
    """Bind a parsed GitHub intent to a caller-supplied exact commit."""
    value = _required(parameters, "source", "an external source identity is required")
    cwd = Path(str(parameters.get("root") or Path.cwd())).expanduser()
    intent = external_sources.parse(value, cwd=cwd)
    resolved = external_sources.resolve_exact(
        intent, commit=str(parameters["commit"]) if parameters.get("commit") is not None else None
    )
    return Answer(_source_view(resolved))


def _source_view(intent: external_sources.Intent) -> ExternalSourceIdentity:
    return ExternalSourceIdentity(
        **intent.__dict__, provenance_proven=intent.kind == "github/exact"
    )


def source_evidence_refresh(parameters: Mapping[str, object]) -> Answer[GitHubArchiveEvidence]:
    """Append one official GitHub repository lifecycle observation."""
    stable_id = _required(parameters, "id", "a stable id is required")
    version = _required(parameters, "version", "an exact version is required")
    with closing(open_registry(configured_path(), create=False)) as connection:
        return _source_evidence_answer(
            github_evidence.refresh(connection, stable_id, version, at=moment())
        )


def source_evidence_show(parameters: Mapping[str, object]) -> Answer[GitHubArchiveEvidence]:
    """Read the latest local GitHub observation without network access."""
    stable_id = _required(parameters, "id", "a stable id is required")
    version = _required(parameters, "version", "an exact version is required")
    with closing(open_readonly(configured_path())) as connection:
        return _source_evidence_answer(
            github_evidence.show(connection, stable_id, version, at=moment())
        )


def source_evidence_history(parameters: Mapping[str, object]) -> Answer[GitHubArchiveHistory]:
    """Read bounded append-only GitHub observation history without network access."""
    stable_id = _required(parameters, "id", "a stable id is required")
    version = _required(parameters, "version", "an exact version is required")
    requested_limit = parameters.get("limit")
    limit = requested_limit if isinstance(requested_limit, int) else 100
    with closing(open_readonly(configured_path())) as connection:
        return Answer(
            github_evidence.history(connection, stable_id, version, at=moment(), limit=limit)
        )


def _source_evidence_answer(evidence: GitHubArchiveEvidence) -> Answer[GitHubArchiveEvidence]:
    warning = (
        "the source repository is archived; review a deprecated lifecycle transition"
        if evidence.archived is True
        else None
    )
    return Answer(evidence, () if warning is None else (warning,))


def scaffold_plan(parameters: Mapping[str, object]) -> Answer[ComponentScaffoldPlan]:
    """Preview every byte of one versioned component authoring directory."""
    component_type = _required(parameters, "type", "a component type is required")
    name = _required(parameters, "name", "a component name is required")
    language = _required(parameters, "language", "a scaffold language is required")
    harness = _required(parameters, "harness", "a harness variant is required")
    output = Path(_required(parameters, "output", "an output path is required")).expanduser()
    plan, _files = authoring.scaffold_plan(
        component_type=component_type,
        name=name,
        language=language,
        harness_variant=harness,
        output=output,
    )
    return Answer(plan)


def scaffold_apply(parameters: Mapping[str, object]) -> Answer[ComponentScaffoldResult]:
    """Create exactly one confirmed scaffold directory from its recomputed plan."""
    component_type = _required(parameters, "type", "a component type is required")
    name = _required(parameters, "name", "a component name is required")
    language = _required(parameters, "language", "a scaffold language is required")
    harness = _required(parameters, "harness", "a harness variant is required")
    output = Path(_required(parameters, "output", "an output path is required")).expanduser()
    # No `--confirm` beside the digest. Creating a new directory is local and
    # reversible, so `ADR-0118` puts it inside the task's authority, and the
    # exact plan digest is already the stronger confirmation: it says *which*
    # scaffold, where a boolean says only "yes". `apply_scaffold` refuses a
    # digest that no longer matches the recomputed plan.
    expected = _required(
        parameters, "expected-plan-digest", "the exact scaffold plan digest is required"
    )
    plan, files = authoring.scaffold_plan(
        component_type=component_type,
        name=name,
        language=language,
        harness_variant=harness,
        output=output,
    )
    return Answer(authoring.apply_scaffold(plan, files, expected_digest=expected))


def adaptation_add(parameters: Mapping[str, object]) -> Answer[ComponentScaffoldView]:
    """Render one extra concrete harness projection into an existing authoring tree."""
    import json

    root = Path(_required(parameters, "root", "an authoring directory is required")).expanduser()
    harness = _required(parameters, "harness", "a concrete harness is required")
    written = authoring.add_adaptation(root, harness)
    template = json.loads((root / ".ai-stp-template.json").read_text(encoding="utf-8"))
    return Answer(
        ComponentScaffoldView(
            component_type=template["component_type"],
            component_name=root.name,
            output=str(root.resolve()),
            byte_length=sum(len(payload) for payload in written.values()),
        )
    )


def template_render(parameters: Mapping[str, object]) -> Answer[ComponentTemplateView]:
    """Render a portable template for exactly one closed-registry harness."""
    source_path = Path(
        _required(parameters, "template", "a template path is required")
    ).expanduser()
    harness_id = _required(parameters, "harness", "a harness identifier is required")
    name = _required(parameters, "name", "a component name is required")
    root = _required(parameters, "component-root", "a relative component root is required")
    source = authoring.read_template(source_path)
    rendered = authoring.render(
        source, harness_id=harness_id, component_name=name, component_root=root
    )

    def digest(value: str) -> str:
        return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"

    return Answer(
        ComponentTemplateView(
            harness_id=harness_id,  # pyright: ignore[reportArgumentType]
            component_name=name,
            component_root=rendered.component_root,
            source_digest=digest(source),
            rendered_digest=digest(rendered.content),
            placeholders=list(rendered.placeholders),
            content=rendered.content,
        )
    )


def _view(stored: revisions.StoredRevision) -> PassportView:
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


def discover(parameters: Mapping[str, object]) -> Answer[NativeComponents]:
    """List native components in harness roots, or only in a named project.

    An explicit `--root` is the path workflow: it does not add global homes.
    Reads no file's content and writes nothing at all. A path whose *name* says
    it holds a credential is listed and flagged, never opened: opening it to
    find out whether it holds a secret is the harm the rule exists to prevent.
    """
    given = parameters.get("root")
    project = Path(str(given)) if given is not None else None
    token = parameters.get("cursor")
    continuation = None if token is None else str(token)
    if continuation is not None and project is None:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a discovery continuation requires the same --root",
            next_actions=["component discover --root <path> --json"],
        )
    report = components.discover_report(project=project, continuation=continuation)
    return Answer(
        NativeComponents(
            project=None if project is None else str(project),
            complete=report.complete,
            continuation=report.continuation,
            components=[
                NativeComponent(
                    component_type=item.component_type,  # pyright: ignore[reportArgumentType]
                    native_role=item.native_role,  # pyright: ignore[reportArgumentType]
                    harness_id=item.harness_id or None,
                    scope=item.scope,  # pyright: ignore[reportArgumentType]
                    candidate_id=item.candidate_id,
                    layout_source=item.layout_source,
                    source_path=item.source_path,
                    provenance=NativeComponentProvenance(
                        kind=item.provenance.kind,  # pyright: ignore[reportArgumentType]
                        state=item.provenance.state,  # pyright: ignore[reportArgumentType]
                        repository=item.provenance.repository,
                        revision=item.provenance.revision,
                        subpath=item.provenance.subpath,
                        package_name=item.provenance.package_name,
                        package_version=item.provenance.package_version,
                        digest=item.provenance.digest,
                        evidence=list(item.provenance.evidence),
                    ),
                    entry_points=list(item.entry_points),
                    transport_capabilities=list(item.transport_capabilities),  # pyright: ignore[reportArgumentType]
                    evidence_refs=list(item.evidence_refs),
                    byte_length=item.byte_length,
                    holds_secret=item.holds_secret,
                    reason=item.reason,
                )
                for item in report.components
            ],
            diagnostics=[
                NativeDiscoveryDiagnostic(
                    code=item.code,  # pyright: ignore[reportArgumentType]
                    source=item.source,
                    reason=item.reason,
                )
                for item in report.diagnostics
            ],
        )
    )


def inventory(parameters: Mapping[str, object]) -> Answer[PathInventory]:
    """Passport-first inventory of one explicit root. Changes nothing."""
    token = parameters.get("cursor")
    return Answer(
        path_inventory.inventory_root(
            Path(str(parameters["root"])),
            cursor=None if token is None else str(token),
        )
    )


def adopt(parameters: Mapping[str, object]) -> Answer[PassportView]:
    """Register one discovered component, by the exact path discovery reported.

    Named by path rather than by an index into a previous listing: an index is
    only meaningful against a listing that has not changed, and nothing here can
    promise that between two commands.
    """
    given = parameters.get("path")
    if given is None:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a component path is required",
            next_actions=["component discover --json"],
        )
    wanted = Path(str(given)).expanduser()
    # The root is named, not guessed. Guessing it as the file's parent works for
    # `AGENTS.md` sitting in a project root and for nothing else: a component
    # under `.claude/skills/` would have its own directory taken as the root,
    # and discovery would then look for `.claude/skills/.claude/skills`. Every
    # directory-shaped rule was unadoptable that way, which is most of them.
    named = parameters.get("root")
    project = (
        Path(str(named)).expanduser()
        if named is not None
        else (wanted.parent if wanted.parent.is_dir() else None)
    )
    matches = [
        item
        for item in components.discover(project=project, include_global=True)
        if item.absolute == wanted
    ]
    if not matches:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "no discovered component sits at that path",
            details={"path": str(wanted), "root": str(project) if project else "none"},
            next_actions=["component discover --root <path> --json"],
        )
    # One path can answer to more than one documented surface: `.agents/skills`
    # is both the portable cross-product convention and antigravity's own
    # project skills. Taking the first claim silently gave the adopted
    # component an empty `harness_id` that `select propose` then refused as
    # `harness_mismatch`, with no flag anywhere to name the other claim. More
    # than one answer is a decision — the provider-resolution rule, applied
    # here.
    claimed = str(parameters.get("harness") or "")
    if claimed:
        wanted_harness = "" if claimed == "portable" else claimed
        matches = [item for item in matches if item.harness_id == wanted_harness]
        if not matches:
            raise CliFailure(
                "AI_STP_NOT_FOUND",
                "no surface of that harness claims this path",
                details={"path": str(wanted), "harness": claimed},
                next_actions=["component discover --root <path> --json"],
            )
    # A kind is the second axis of the same decision, and one harness can hold
    # both: `~/.codex/config.toml` answers to the `mcp` layout over its
    # `mcp_servers` key and to the `setting` layout over the whole file, so
    # `--harness codex` narrows nothing. Every `declared_key` harness has this
    # shape. Without the selector the `setting` half of such a file was
    # unreachable — `matches[0]` is the `mcp` claim, and no flag named the
    # other.
    kind = str(parameters.get("kind") or "")
    if kind:
        matches = [item for item in matches if item.component_type == kind]
        if not matches:
            raise CliFailure(
                "AI_STP_NOT_FOUND",
                "no surface of that kind claims this path",
                details={"path": str(wanted), "kind": kind},
                next_actions=["component discover --root <path> --json"],
            )
    # Distinct harnesses, not raw claim count: `~/.claude/CLAUDE.md` is claimed
    # by claude-code's global layout and by its project layout at once, and
    # that is one answer twice, not a decision. The decision exists exactly
    # when the claims name different harnesses — which is what the adopted
    # passport's `harness_id` fact will carry forward.
    if len({item.harness_id for item in matches}) > 1:
        raise CliFailure(
            "AI_STP_USER_DECISION_REQUIRED",
            "that path answers to more than one surface; name the harness to adopt it for",
            details={
                "path": str(wanted),
                "claims": ", ".join(sorted({item.harness_id or "portable" for item in matches})),
            },
            next_actions=[
                "component adopt --path <path> --root <root> --harness <id> --json",
            ],
        )
    if len({item.component_type for item in matches}) > 1:
        raise CliFailure(
            "AI_STP_USER_DECISION_REQUIRED",
            "that path answers to more than one kind; name the kind to adopt",
            details={
                "path": str(wanted),
                "kinds": ", ".join(sorted({item.component_type for item in matches})),
            },
            next_actions=[
                "component adopt --path <path> --root <root> --kind <kind> --json",
            ],
        )
    found = matches[0]

    current, _warning = identity.load_or_create()
    with closing(open_registry(configured_path(), create=True)) as connection:
        return Answer(_view(components.adopt(connection, found, device_id=current.device_id)))


def passport_show(parameters: Mapping[str, object]) -> Answer[PassportView]:
    """Show one component head without creating or changing local state."""
    stable_id = _required(parameters, "id", "a component stable id is required")
    with closing(open_readonly(configured_path())) as connection:
        stored = revisions.head(connection, stable_id)
        if stored is None:
            raise CliFailure(
                "AI_STP_NOT_FOUND",
                "that component has no local passport",
                details={"id": stable_id},
                next_actions=["component discover --json"],
            )
        if stored.envelope.kind != "component":
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                "that identifier does not name a component passport",
                details={"id": stable_id, "kind": stored.envelope.kind},
            )
        return Answer(_view(stored))


def passport_update(parameters: Mapping[str, object]) -> Answer[PassportView]:
    """Apply one confirmed closed-schema JSON patch as a child revision."""
    stable_id = _required(parameters, "id", "a component stable id is required")
    expected = _required(
        parameters, "expected-revision", "the current revision must be named explicitly"
    )
    source = _required(parameters, "from", "a JSON passport patch path is required")
    patch = component_passports.load_patch(Path(source).expanduser())
    current, _warning = identity.load_or_create()
    with closing(open_registry(configured_path(), create=False)) as connection:
        stored = component_passports.update(
            connection,
            stable_id,
            expected,
            patch,
            device_id=current.device_id,
        )
        return Answer(_view(stored))


def passport_suggest(parameters: Mapping[str, object]) -> Answer[ComponentPassportSuggestions]:
    """Report exact manifest facts without writing or confirming any of them."""
    stable_id = _required(parameters, "id", "a component stable id is required")
    with closing(open_readonly(configured_path())) as connection:
        found = component_passports.suggest(connection, stable_id)
    return Answer(
        ComponentPassportSuggestions(
            stable_id=found.stable_id,
            revision_id=found.revision_id,
            suggestions=[
                ComponentPassportSuggestion(
                    field=item.field,
                    value=item.value,
                    source_refs=list(item.source_refs),
                )
                for item in found.facts
            ],
            unresolved_fields=list(found.unresolved_fields),
        )
    )


def passport_validate(parameters: Mapping[str, object]) -> Answer[ComponentPassportValidation]:
    """List every local structural blocker to a future public publication plan."""
    stable_id = _required(parameters, "id", "a component stable id is required")
    # `--for-publication` names the only profile this command has, so it is
    # accepted and changes nothing: refusing without it asked the caller to
    # repeat the command's one meaning back before being answered.
    with closing(open_readonly(configured_path())) as connection:
        readiness = component_passports.validate_for_publication(connection, stable_id)
    return Answer(
        ComponentPassportValidation(
            stable_id=readiness.stable_id,
            revision_id=readiness.revision_id,
            ready=readiness.ready,
            missing_fields=list(readiness.missing_fields),
            invalid_fields=list(readiness.invalid_fields),
        )
    )


def passport_quality(parameters: Mapping[str, object]) -> Answer[ComponentQualityReport]:
    """Return optional deterministic authoring guidance without a trust verdict."""
    stable_id = _required(parameters, "id", "a component stable id is required")
    with closing(open_readonly(configured_path())) as connection:
        report = component_passports.evaluate_quality(connection, stable_id)
    return Answer(
        ComponentQualityReport(
            stable_id=report.stable_id,
            revision_id=report.revision_id,
            component_type=report.component_type,
            dimensions=[
                ComponentQualityDimension(
                    dimension=dimension.name,  # pyright: ignore[reportArgumentType]
                    status=(
                        "passed" if all(check.passed for check in dimension.checks) else "hint"
                    ),
                    checks=[
                        ComponentQualityCheck(
                            code=check.code,
                            status="passed" if check.passed else "hint",
                            fields=list(check.fields),
                            message=check.message,
                        )
                        for check in dimension.checks
                    ],
                )
                for dimension in report.dimensions
            ],
        )
    )


def forget(parameters: Mapping[str, object]) -> Answer[PassportView]:
    """Mark a registered component deleted, keeping its history (`SPEC-013` REQ-1308).

    A mark, not a removal. Replaying it is safe, and a user who asks why an
    object stopped appearing gets an answer rather than silence.
    """
    given = parameters.get("id")
    if given is None:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a stable id is required",
            next_actions=["component discover --json"],
        )
    reason = str(parameters.get("reason") or "removed by the user")

    def work(connection: sqlite3.Connection) -> PassportView:
        stable_id = str(given)
        lifecycle.entomb(connection, stable_id, reason=reason, at=moment())
        stored = revisions.head(connection, stable_id)
        if stored is None:
            raise CliFailure(
                "AI_STP_NOT_FOUND",
                "that identifier has no revisions to report",
                details={"id": stable_id},
            )
        return _view(stored)

    with closing(open_registry(configured_path(), create=True)) as connection:
        return Answer(work(connection))


def consent_allow(parameters: Mapping[str, object]) -> Answer[ConsentRecord]:
    """Record a durable consent to unverified objects, or full-task authority.

    There is deliberately no form covering everything unverified forever: the
    `search.include_unverified` key was exactly that and was removed. `task`
    names the authorized full-auto profile, not a wildcard publisher.
    """
    scope = parameters.get("scope")
    target = parameters.get("target")
    if scope is None or target is None:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "both a scope and a target are required",
            details={"scopes": ", ".join(sorted(consent.SCOPES))},
        )
    # Before anything else is asked about the target. An unknown scope used to
    # fall through to that later question's refusal, sending the operator to
    # hunt a registration problem when the mistake was the scope word itself.
    if str(scope) not in consent.SCOPES:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "that consent scope is not one this contract defines",
            details={"scope": str(scope), "allowed": ", ".join(sorted(consent.SCOPES))},
        )

    def work(connection: sqlite3.Connection) -> ConsentRecord:
        if str(scope) == consent.SCOPE_TASK:
            # Task authority is a named profile, not a fingerprint of objects.
            # Requiring a matching registration would make the grant unwritable
            # until an unverified object already existed — the opposite of
            # authorizing the task that will meet those objects.
            record = consent.grant(
                connection,
                consent_id=new_id("request"),
                scope=str(scope),
                target=str(target),
                fingerprint=consent.fingerprint_of({}),
                observed=(),
                decided_by=owner().account_id,
                origin="component consent allow",
                at=moment(),
            )
            return _record(record)
        # The contract asks for "the fingerprint of the candidate at the moment
        # of consent", so the shape is read from the objects the target
        # actually covers right now. It used to record `fingerprint_of({})`
        # regardless, which is not an empty ceiling but no observation at all —
        # and compared as a ceiling it refused every candidate needing
        # anything, which is every candidate worth consenting to.
        seen = _covered_by(connection, scope=str(scope), target=str(target))
        if not seen:
            raise CliFailure(
                "AI_STP_PRECONDITION_FAILED",
                "no registered object matches that target, so there is no shape to consent to",
                details={
                    "scope": str(scope),
                    "target": str(target),
                    "remedy": "acquire or register the object first, then record the consent",
                },
            )
        record = consent.grant(
            connection,
            consent_id=new_id("request"),
            scope=str(scope),
            target=str(target),
            fingerprint=consent.ceiling_of(tuple(fields for _, fields in seen)),
            observed=tuple(stable_id for stable_id, _ in seen),
            decided_by=owner().account_id,
            origin="component consent allow",
            at=moment(),
        )
        return _record(record)

    with closing(open_registry(configured_path(), create=True)) as connection:
        return Answer(work(connection))


def _covered_by(
    connection: sqlite3.Connection, *, scope: str, target: str
) -> tuple[tuple[str, dict[str, JsonValue]], ...]:
    """The registered objects a consent target names, with their capabilities.

    One reader for both scopes: a `publisher` target names every object with
    that owner, an `object_major` target names one object's major line. Reading
    the same candidates search does keeps "what you were shown" and "what you
    consented to" the same set.
    """
    found: list[tuple[str, dict[str, JsonValue]]] = []
    for candidate in _candidates(connection):
        if scope == consent.SCOPE_PUBLISHER:
            if candidate.owner_id and candidate.owner_id == target:
                found.append((candidate.stable_id, candidate.fields))
            continue
        major = consent.major_of(candidate.version)
        if major is not None and f"{candidate.stable_id}@{major}" == target:
            found.append((candidate.stable_id, candidate.fields))
    return tuple(found)


def consent_revoke(parameters: Mapping[str, object]) -> Answer[ConsentRecord]:
    """Withdraw a consent. Takes effect immediately for every later request."""
    scope = parameters.get("scope")
    target = parameters.get("target")
    if scope is None or target is None:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "both a scope and a target are required",
            details={"scopes": ", ".join(sorted(consent.SCOPES))},
        )
    # Before anything else is asked about the target. An unknown scope used to
    # fall through to that later question's refusal, sending the operator to
    # hunt a registration problem when the mistake was the scope word itself.
    if str(scope) not in consent.SCOPES:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "that consent scope is not one this contract defines",
            details={"scope": str(scope), "allowed": ", ".join(sorted(consent.SCOPES))},
        )

    def work(connection: sqlite3.Connection) -> ConsentRecord:
        consent.revoke(connection, scope=str(scope), target=str(target), at=moment())
        record = consent.held(connection, scope=str(scope), target=str(target))
        if record is None:
            raise CliFailure(
                "AI_STP_NOT_FOUND",
                "no consent record covers that target",
                details={"scope": str(scope), "target": str(target)},
            )
        return _record(record)

    with closing(open_registry(configured_path(), create=True)) as connection:
        return Answer(work(connection))


def consent_list(_parameters: Mapping[str, object]) -> Answer[ConsentSummary]:
    """Every consent still in force, and what each one covered when it was given."""
    registry = configured_path()
    if not registry.exists():
        return Answer(ConsentSummary(records=[]))
    with closing(open_readonly(registry)) as connection:
        return Answer(
            ConsentSummary(records=[_record(item) for item in consent.active(connection)])
        )


def _record(record: consent.Record) -> ConsentRecord:
    return ConsentRecord(
        consent_id=record.consent_id,
        scope=record.scope,  # pyright: ignore[reportArgumentType]
        target=record.target,
        decided_by=record.decided_by,
        origin=record.origin,
        created_at=record.created_at,
        revoked_at=record.revoked_at,
        fingerprint=record.fingerprint,
        observed=list(record.observed),
    )


def version_list(parameters: Mapping[str, object]) -> Answer[VersionLine]:
    """Every recorded version of one object, oldest first."""
    stable_id = _required(parameters, "id", "a stable id is required")

    def work(connection: sqlite3.Connection) -> VersionLine:
        recorded = versions.line(connection, stable_id)
        origin = versions.forked_from(connection, stable_id)
        return VersionLine(
            stable_id=stable_id,
            versions=[_version(item) for item in recorded],
            next_minor=versions.next_minor(connection, stable_id),
            forked_from=None if origin is None else origin.source_stable_id,
            forked_from_version=None if origin is None else origin.source_version,
        )

    with closing(open_readonly(configured_path())) as connection:
        return Answer(work(connection))


def version_release(parameters: Mapping[str, object]) -> Answer[VersionLine]:
    """Give the object's current head an immutable version number.

    A minor by default, because `SPEC-005` REQ-506 makes any change of
    composition the next minor. A major only on an explicit decision: it creates
    a separate access boundary, and one nobody chose is worse than one refused.
    """
    stable_id = _required(parameters, "id", "a stable id is required")
    wants_major = bool(parameters.get("major"))

    def work(connection: sqlite3.Connection) -> VersionLine:
        stored = revisions.head(connection, stable_id)
        if stored is None:
            raise CliFailure(
                "AI_STP_NOT_FOUND",
                "that identifier has no revision to release",
                details={"id": stable_id},
                next_actions=["component adopt --path <path> --json"],
            )
        number = (
            versions.next_major(connection, stable_id)
            if wants_major
            else versions.next_minor(connection, stable_id)
        )
        released_at = moment()
        current, _warning = identity.load_or_create()
        passport, revision_id = component_passports.materialize_version_passport(
            connection,
            stable_id,
            number,
            device_id=current.device_id,
            at=released_at,
        )
        versions.record(
            connection,
            stable_id=stable_id,
            version=number,
            # The catalogue's own digest, computed by the one function that
            # knows how: a second way of hashing a passport would verify against
            # nothing and look like a corrupted download.
            passport_digest=cache.digest_of(cast(JsonValue, passport.model_dump(mode="json"))),
            revision_id=revision_id,
            at=released_at,
        )
        return VersionLine(
            stable_id=stable_id,
            versions=[_version(item) for item in versions.line(connection, stable_id)],
            next_minor=versions.next_minor(connection, stable_id),
        )

    # One write transaction from reading the next free number to recording it.
    # In autocommit, two concurrent releases both read the same number and the
    # loser died on the UNIQUE constraint as `AI_STP_INTERNAL` (measured); under
    # `BEGIN IMMEDIATE` it starts after the winner commits and mints the next.
    with (
        closing(open_registry(configured_path(), create=True)) as connection,
        transaction(connection),
    ):
        return Answer(work(connection))


def fork(parameters: Mapping[str, object]) -> Answer[VersionLine]:
    """Copy an object under a new identity, leaving the original untouched.

    The answer says immediately that the copy is not yet publishable. An
    unmodified clone is exactly what `REQ-522` refuses, and a caller learning
    that now rather than at publication is the difference between a rule and a
    surprise.
    """
    stable_id = _required(parameters, "id", "a stable id is required")
    version = _required(parameters, "version", "the version being forked is required")

    def work(connection: sqlite3.Connection) -> VersionLine:
        source = versions.held(connection, stable_id, version)
        if source is None:
            raise CliFailure(
                "AI_STP_NOT_FOUND",
                "that object has no such recorded version",
                details={"id": stable_id, "version": version},
                next_actions=["component version list --id <stable_id> --json"],
            )
        row = connection.execute(
            "SELECT kind FROM entity WHERE stable_id = ?", (stable_id,)
        ).fetchone()
        at = moment()
        copy = versions.fork(
            connection,
            source_stable_id=stable_id,
            source_version=version,
            source_digest=source.passport_digest,
            kind=str(row["kind"]),
            at=at,
        )
        # The copy's content, not just its lineage. Without this first revision
        # the fork answered `ok` and then every follow-up refused it — passport
        # show, update, release and even forget all found nothing — so the
        # object `REQ-521` calls a copy held nothing to edit toward `REQ-522`'s
        # meaningful change.
        stored = revisions.get(connection, source.revision_id)
        if stored is None:
            raise CliFailure(
                "AI_STP_CONFLICT",
                "a component version points to a missing passport",
                details={"id": stable_id, "version": version},
            )
        seeded = cast(dict[str, JsonValue], stored.envelope.model_dump(mode="json"))
        seeded.pop("revision_id", None)
        current, _warning = identity.load_or_create()
        seeded.update(
            {
                "stable_id": copy.stable_id,
                "owner_id": owner().account_id,
                "created_at": at,
                "visibility": "private",
                "parent_revision_ids": [],
            }
        )
        revisions.commit(connection, seeded, device_id=current.device_id)
        verdict = versions.publishable(
            connection, copy.stable_id, passport_digest=source.passport_digest, public=True
        )
        return VersionLine(
            stable_id=copy.stable_id,
            versions=[],
            next_minor=versions.FIRST_VERSION,
            forked_from=copy.source_stable_id,
            forked_from_version=copy.source_version,
            publishable=verdict.allowed,
            publish_reason=verdict.reason,
        )

    # Atomic and serialized like the release above: the fork writes an entity,
    # its lineage row and its first revision, and either all of them exist or
    # none do.
    with (
        closing(open_registry(configured_path(), create=True)) as connection,
        transaction(connection),
    ):
        return Answer(work(connection))


def _required(parameters: Mapping[str, object], name: str, message: str) -> str:
    given = parameters.get(name)
    if given is None:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR", message, next_actions=["component discover --json"]
        )
    return str(given)


def _version(recorded: versions.Recorded) -> RecordedVersion:
    return RecordedVersion(
        version=recorded.version,
        passport_digest=recorded.passport_digest,
        revision_id=recorded.revision_id,
        created_at=recorded.created_at,
    )


def find(parameters: Mapping[str, object]) -> Answer[LocalSearchResults]:
    """Search the local registry. Offline, deterministic, and no model (`REQ-1118`).

    Every registered component is a candidate; drafts and deleted objects are
    excluded by the store rather than by this function. Trust lanes come back in
    separate sections because `REQ-603` asks for a separate section, and a flat
    list of labelled rows has already lost that.
    """
    # A repeatable option arrives as a list from the parser and as a bare value
    # from a caller that passed one. Both mean the same thing.
    given: object = parameters.get("tag")
    if given is None:
        wanted: tuple[str, ...] = ()
    elif isinstance(given, list | tuple):
        wanted = tuple(str(item) for item in cast(list[object], given))
    else:
        wanted = (str(given),)

    prefix = str(parameters.get("prefix") or "")
    phrase = str(parameters.get("phrase") or "")
    field = str(parameters.get("field") or "")
    value = str(parameters.get("value") or "")
    include_unverified = bool(parameters.get("include-unverified"))
    search.validate_query(prefix=prefix, phrase=phrase, field=field, value=value)

    registry = configured_path()
    if not registry.exists():
        return Answer(
            LocalSearchResults(
                authoritative=[],
                local_owner_or_pinned=[],
                experimental=[],
                experimental_reason=(
                    "no unverified candidate matched"
                    if include_unverified
                    else "no consent was given for any unverified candidate"
                ),
                truncated=False,
            )
        )

    def work(connection: sqlite3.Connection) -> LocalSearchResults:
        found = search.search(
            connection,
            _candidates(connection),
            prefix=prefix,
            phrase=phrase,
            tags=wanted,
            field=field,
            value=value,
            include_unverified=include_unverified,
        )
        return LocalSearchResults(
            authoritative=[_hit(item) for item in found.authoritative],
            local_owner_or_pinned=[_hit(item) for item in found.local],
            experimental=[_hit(item) for item in found.experimental],
            experimental_reason=found.experimental_reason,
            truncated=found.truncated,
        )

    with closing(open_readonly(registry)) as connection:
        return Answer(work(connection))


def _candidates(connection: sqlite3.Connection) -> tuple[search.Candidate, ...]:
    """Every registered component, as search sees it.

    Local *authorship* is `owned_or_pinned`; an acquired version is not.
    `registry acquire` materialises a published graph into these same tables,
    and before `#447` those rows claimed ownership too — which put somebody
    else's object in the `local_owner_or_pinned` lane and past the consent,
    licence and grant questions in one step.

    So the axes come from what the catalogue said when the version was
    acquired, and only a row with no recorded verdict is this user's own work.
    `lane_of` still refuses to promote on one axis alone.
    """
    rows = connection.execute(
        "SELECT stable_id FROM entity WHERE kind IN ('component', 'setup')"
    ).fetchall()
    recorded = acquired_trust.verdicts(connection)
    held: list[search.Candidate] = []
    for row in rows:
        stored = revisions.head(connection, str(row["stable_id"]))
        if stored is None:
            continue
        document = cast(dict[str, JsonValue], stored.envelope.model_dump(mode="json"))
        facts = cast(dict[str, JsonValue], document["facts"])
        verdict = recorded.get((stored.stable_id, str(document.get("version") or "")))
        held.append(
            search.Candidate(
                stable_id=stored.stable_id,
                revision_id=stored.revision_id,
                fields={name: _value(fact) for name, fact in facts.items()},
                owner_id=str(document.get("owner_id") or ""),
                version=str(document.get("version") or ""),
                owned_or_pinned=verdict is None,
                author_verified=verdict.author_verified if verdict else False,
                component_verified=verdict.component_verified if verdict else False,
            )
        )
    return tuple(held)


def _value(fact: JsonValue) -> JsonValue:
    return fact.get("value") if isinstance(fact, dict) else fact


def _hit(hit: search.Hit) -> SearchHit:
    return SearchHit(
        stable_id=hit.stable_id,
        revision_id=hit.revision_id,
        lane=hit.lane,  # pyright: ignore[reportArgumentType]
        reason=hit.reason,
        fields=hit.fields,
    )


def skill_validate(parameters: Mapping[str, object]) -> Answer[SkillPackageReport]:
    """Check a skill package against the Agent Skills Specification (`#455`).

    Reads a directory and changes nothing. Of the closed component kinds this is
    the one with a published standard that exists independently of this estate,
    so every limit it enforces is quoted from that document rather than chosen
    here — which is what makes the answer checkable by somebody who does not
    trust us.
    """
    given = _required(parameters, "path", "a skill package directory is required")
    report = skill_package.validate(Path(given))
    return Answer(
        SkillPackageReport(
            path=redact_home(Path(report.path)),
            packaged_as=cast(Any, report.packaged_as),
            conforms=report.conforms,
            findings=[
                SkillPackageFinding(code=item.code, summary=item.summary, at=item.at)
                for item in report.findings
            ],
            name=report.name,
            description=report.description,
            standard_directories=list(report.standard_directories),
            extension_directories=list(report.extension_directories),
            other_entries=list(report.other_entries),
        )
    )
