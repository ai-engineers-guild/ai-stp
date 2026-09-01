"""`ai-stp select` — the mechanical stage and the recommendation session.

`SPEC-006` REQ-601 puts mechanical constraints before an agent chooses, and
`eligibility` is where that stage becomes observable (#163). It decides nothing
about which candidate is best: it answers which ones are allowed to be
considered at all, and names the stable reason behind every refusal from
`docs/contracts/eligibility-constraints.md`.

`propose`, `confirm` and `cancel` are the session of `ADR-0027` (#164). Showing
a composition creates nothing; one explicit confirmation freezes exactly one
private `SetupVersion` with its trace and its pin, atomically. That asymmetry is
the point — an agent may show as many compositions as it likes, and only the
user's confirmation puts one in the registry.

The target and the context are assembled the way REQ-621 requires — from the
developer, device and project passports and the chosen harness — and every fact
they were built from comes back in the answer. A verdict whose inputs are
invisible cannot be checked, and this stage exists precisely to be checkable.
"""

import platform
import sqlite3
from collections.abc import Mapping, Sequence
from contextlib import closing
from datetime import timedelta
from pathlib import Path, PurePosixPath
from typing import Final, cast

from ai_stp_cli.answer import Answer
from ai_stp_cli.config import effective_config
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import (
    acquired_trust,
    bundle,
    components,
    composition,
    consent,
    content,
    contribution,
    eligibility,
    graph,
    harnesses,
    impact,
    lifecycle,
    passports,
    project_index,
    project_passport,
    provider_releases,
    revisions,
    selection,
    versions,
)
from ai_stp_cli.local.database import configured_path, open_readonly, open_registry
from ai_stp_cli.local.passports import moment, owner
from ai_stp_cli.paths import redact_home
from ai_stp_cli.provider import (
    attested_bind,
    conformance,
    conformance_v2,
    conformance_v3,
    invocation,
    invocation_v2,
    network_launcher,
    protocol,
    protocol_v2,
    protocol_v3,
    release,
)
from ai_stp_cli.toolchain import install
from ai_stp_cli.toolchain import load as load_manifest
from ai_stp_contracts.impact import BlastRadiusReport, SelectionImpactReport
from ai_stp_contracts.machine_help import (
    BundleFile,
    BundleRefusal,
    CandidateEligibility,
    CompositionChoice,
    CompositionConflict,
    CompositionRejection,
    CompositionReports,
    ConfirmationView,
    ConformanceCase,
    ConformanceReport,
    ConversionEntry,
    EligibilityMatrix,
    EligibilityNote,
    EligibilityRefusal,
    EligibilityReport,
    GraphNode,
    GraphReference,
    GraphRefusal,
    HarnessBundle,
    PinnedRelease,
    ProposalMember,
    ProposalSession,
    ProposalView,
    ProviderBoundRelease,
    ProviderNetworkCapability,
    ProviderTrust,
    ReleaseRefusal,
    SetupGraph,
    TrustedBuildAttestation,
)
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.harnesses import HARNESS_IDS
from ai_stp_foundation.timestamps import format_timestamp, parse_timestamp


def eligible(parameters: Mapping[str, object]) -> Answer[EligibilityReport]:
    """Assess every local candidate against one harness on this machine.

    Reads and reports. Nothing here writes a passport, a version or a target:
    `ADR-0027` makes a durable object the result of an explicit confirmation,
    and looking at what is allowed must not be a way to create one.
    """
    harness = str(parameters.get("harness") or "")
    if harness not in HARNESS_IDS:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a supported harness identifier is required",
            details={"supported": ", ".join(sorted(HARNESS_IDS))},
            next_actions=["toolchain harnesses --json"],
        )

    root = _project_root(parameters)
    registry = configured_path()
    redistribution = bool(parameters.get("for-redistribution"))
    if not registry.exists():
        return Answer(
            _eligibility_report(
                _target(harness, root, for_redistribution=redistribution, owner_id=""),
                (),
            )
        )

    def work(connection: sqlite3.Connection) -> EligibilityReport:
        target = _target(
            harness,
            root,
            for_redistribution=redistribution,
            owner_id=_registry_owner_id(connection),
        )
        assessed = eligibility.assess_all(
            _candidates(connection, flagged=bool(parameters.get("include-unverified"))),
            target,
        )
        return _eligibility_report(target, assessed)

    with closing(open_readonly(registry)) as connection:
        return Answer(work(connection))


def eligible_everywhere(parameters: Mapping[str, object]) -> Answer[EligibilityMatrix]:
    """Assess every local candidate against every supported harness.

    `select eligibility` answers for the harness it was given, which is right
    for "compose this for Codex" and wrong for "where does this object fit".
    With only the first available, an agent answered the second question with
    the harness its own session happened to run in, and a portable skill
    acquired that `harness_id` on the way into a draft passport (`#380`).

    What this does **not** read is whether a harness is installed here. Whether
    an object fits Pi is a property of the object; a machine without Pi still
    gets a Pi row, with a reason from the constraint families rather than
    silence. Installation is an input to running something, not to whether it
    may be composed.
    """
    # `not named`, not `is None`: the option is repeatable, so Click delivers
    # an omitted `--harness` as an empty tuple (`#384`), and the empty tuple
    # means the same thing absence means — every supported harness.
    named = parameters.get("harness")
    if not named:
        requested = tuple(sorted(HARNESS_IDS))
    else:
        supplied: tuple[object, ...] = (
            tuple(cast(list[object] | tuple[object, ...], named))
            if isinstance(named, list | tuple)
            else (named,)
        )
        requested = tuple(str(item) for item in supplied)
        unknown = sorted(set(requested) - set(HARNESS_IDS))
        if unknown or not requested:
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                "a supported harness identifier is required",
                details={
                    "unknown": ", ".join(unknown),
                    "supported": ", ".join(sorted(HARNESS_IDS)),
                },
                next_actions=["toolchain harnesses --json"],
            )
        requested = tuple(sorted(set(requested)))

    root = _project_root(parameters)
    registry = configured_path()
    redistribution = bool(parameters.get("for-redistribution"))
    flagged = bool(parameters.get("include-unverified"))

    def rows(connection: sqlite3.Connection | None) -> list[EligibilityReport]:
        owner = _registry_owner_id(connection) if connection is not None else ""
        held: tuple[eligibility.CandidateFacts, ...] = (
            () if connection is None else _candidates(connection, flagged=flagged)
        )
        reports: list[EligibilityReport] = []
        for harness in requested:
            # Built once per harness rather than once: the target carries the
            # harness version, capabilities and OS facts the assessment reads,
            # and reusing one row's target for another is how a matrix quietly
            # answers the same question five times.
            target = _target(harness, root, for_redistribution=redistribution, owner_id=owner)
            reports.append(_eligibility_report(target, eligibility.assess_all(held, target)))
        return reports

    def matrix(reports: list[EligibilityReport]) -> EligibilityMatrix:
        return EligibilityMatrix(
            harnesses=reports,
            requested=list(requested),  # pyright: ignore[reportArgumentType]
        )

    if not registry.exists():
        return Answer(matrix(rows(None)))
    with closing(open_readonly(registry)) as connection:
        return Answer(matrix(rows(connection)))


def impact_report(parameters: Mapping[str, object]) -> Answer[SelectionImpactReport]:
    """Report context, cost and capability effects for exact local setup versions."""
    registry = configured_path()
    if not registry.exists():
        raise CliFailure("AI_STP_NOT_FOUND", "the local registry does not exist")
    setup_id = str(parameters.get("setup-id") or "")
    setup_version = str(parameters.get("setup-version") or "")
    if not setup_id or not setup_version:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR", "an exact candidate setup id and version are required"
        )
    raw_price = str(parameters.get("price-profile") or "")
    with closing(open_readonly(registry)) as connection:
        return Answer(
            impact.selection_report(
                connection,
                setup_id=setup_id,
                setup_version=setup_version,
                baseline_id=str(parameters.get("against-setup-id") or ""),
                baseline_version=str(parameters.get("against-setup-version") or ""),
                project_id=str(parameters.get("project-id") or ""),
                estimator_profile=str(
                    parameters.get("tokenizer-profile") or "ai-stp:unicode-chars-div4/1"
                ),
                price_profile_path=None if not raw_price else Path(raw_price),
                at=moment(),
            )
        )


def blast_radius(parameters: Mapping[str, object]) -> Answer[BlastRadiusReport]:
    """Report exact local reverse references for one component and scenario."""
    registry = configured_path()
    if not registry.exists():
        raise CliFailure("AI_STP_NOT_FOUND", "the local registry does not exist")
    component_id = str(parameters.get("component-id") or "")
    component_version = str(parameters.get("component-version") or "")
    if not component_id or not component_version:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "an exact component id and version are required",
            next_actions=[
                "component version list --id <stable_id> --json",
                "select blast-radius --component-id <stable_id> --component-version <X.Y> --json",
            ],
        )
    with closing(open_readonly(registry)) as connection:
        return Answer(
            impact.blast_radius(
                connection,
                component_id=component_id,
                component_version=component_version,
                scenario=str(parameters.get("scenario") or "update"),
                at=moment(),
            )
        )


def _eligibility_report(
    target: eligibility.Target,
    assessed: tuple[eligibility.Assessment, ...],
) -> EligibilityReport:
    return EligibilityReport(
        harness_id=target.harness_id,  # pyright: ignore[reportArgumentType]
        harness_version=target.harness_version,
        os=target.os,
        arch=target.arch,
        capability_vocabulary_version=eligibility.CAPABILITY_VOCABULARY_VERSION,
        capabilities=sorted(target.capabilities),
        candidates=[_view(item) for item in assessed],
        admissible_count=len(eligibility.admissible(assessed)),
        auto_selectable_count=len(eligibility.selectable(assessed)),
    )


def _registry_owner_id(connection: sqlite3.Connection) -> str:
    local = passports.known_owner()
    if local is not None:
        return local.account_id
    stable_id = passports.developer_stable_id(connection)
    stored = None if stable_id is None else revisions.head(connection, stable_id)
    return "" if stored is None else stored.envelope.owner_id


def _target(
    harness: str,
    root: Path,
    *,
    for_redistribution: bool,
    owner_id: str | None = None,
) -> eligibility.Target:
    """Build the target from what this machine and project actually show.

    The harness version is read from the installation rather than assumed. It is
    allowed to come back empty — `REQ-1415` has `unknown_version` — and the
    engine treats that as unreadable rather than as "any version", which is why
    it is passed through instead of being defaulted to something plausible.

    The languages come from the index and not from a symbol survey. The survey
    was 1.16s of this command's 2.9s (`#453`) and answered a question the index
    had already answered: it is *handed* `(path, language)` from the index and
    `_summarised` groups every outline it received, readable or not, so the
    languages it reports are the languages it was given.

    They were not quite, and that was the second defect: `survey` stops at
    `MAX_OUTLINED_FILES` and reports only the languages before the cut. A
    project whose Go files all sorted past the two-thousandth file lost
    `language:go` from its capabilities and had Go components refused for a
    capability it has. Reading the index directly is both cheaper and complete.
    """
    resolved = root.resolve()
    # Names, languages and whether `.git` exists — no digest is read below, so
    # none is computed. That was three quarters of the walk (`#453`).
    index = project_index.build(resolved, digests=False)
    detector = next(item for item in harnesses.DETECTORS if item.harness_id == harness)

    return eligibility.Target(
        harness_id=harness,
        os=_operating_system(),
        arch=platform.machine().lower(),
        harness_version=_version_of(harnesses.detect(detector)),
        capabilities=eligibility.observed_capabilities(
            languages=sorted({item.language for item in index.entries if item.language}),
            surfaces=[Path(item.path).name for item in index.entries],
            git=(index.root / ".git").exists(),
            tools_current=[
                tool.tool_id
                for tool in load_manifest().tools
                if install.current_target(tool.tool_id) is not None
            ],
        ),
        owner_id=owner().account_id if owner_id is None else owner_id,
        # A provider covers the closed set of supported harnesses and nothing
        # else. `undefined` reaches no provider by construction, and phase 6
        # narrows this to what it releases without the engine changing.
        provider_harnesses=frozenset(HARNESS_IDS),
        for_redistribution=for_redistribution,
    )


def _operating_system() -> str:
    system = platform.system().lower()
    return {"darwin": "darwin", "linux": "linux", "windows": "windows"}.get(system, system)


def _version_of(found: harnesses.Found) -> str:
    """The version of the installation this machine would actually use.

    The first on `PATH`, because that is the one a harness command resolves to.
    The survey spells an unreadable version `unknown`, and that word is turned
    back into nothing here: passed through, it would travel as though it were a
    version and be reported as one in the answer.
    """
    for installation in found.installations:
        if installation.version and installation.version != "unknown":
            return installation.version
    return ""


def _candidates(
    connection: sqlite3.Connection,
    *,
    flagged: bool = False,
    at_version: Mapping[str, str] | None = None,
) -> tuple[eligibility.CandidateFacts, ...]:
    """Every locally registered object, as the constraint engine sees it.

    Everything here is the user's own: it was adopted or authored on this
    machine and no platform ever confirmed it. Claiming otherwise would invent
    a confirmation, so the trust axes stay false and `owned_or_pinned` carries
    the truth — which is also what keeps a licence and a grant from being
    demanded of somebody for their own work.

    What it did **not** do until 2026-08-29 is read anything else. Three fields
    reached the engine — harness, kind, owner — so `os_unsupported`,
    `arch_unsupported`, `capability_*`, `license_undeclared`,
    `entitlement_not_granted` and the rest of `SPEC-006` `REQ-601` were
    implemented, unit-tested and unreachable from `select propose`. It also read
    `revisions.head` while a proposal names an exact `X.Y`, so a member could be
    admitted on the facts of a different version.

    `at_version` names the revision to assess for the objects a caller is asking
    about. Anything not named is still read at its head, because that is what
    `select eligibility` without arguments is asking about.

    `flagged` is the per-command `--include-unverified`, and it belongs to
    `select eligibility` alone: `select propose` has no such flag, because
    proposing is a step towards installing and only a durable decision should
    carry it. Durable records are read either way, and **per candidate** — one
    boolean for the whole set could not express consent given to one publisher,
    which is the only kind the contract defines.
    """
    rows = connection.execute(
        "SELECT stable_id FROM entity WHERE kind IN ('component', 'setup')"
    ).fetchall()
    recorded = acquired_trust.verdicts(connection)
    wanted = dict(at_version or {})
    held: list[eligibility.CandidateFacts] = []
    for row in rows:
        stable_id = str(row["stable_id"])
        stored = _revision_at(connection, stable_id, wanted.get(stable_id))
        if stored is None:
            continue
        verdict = recorded.get(
            (stable_id, str(stored.envelope.model_dump(mode="json").get("version") or ""))
        )
        document = cast(dict[str, JsonValue], stored.envelope.model_dump(mode="json"))
        facts = cast(dict[str, JsonValue], document.get("facts") or {})
        agreed = consent.consulted(
            connection,
            stable_id=stored.stable_id,
            owner_id=str(document.get("owner_id") or ""),
            version=str(document.get("version") or ""),
            capabilities={name: _value(fact) for name, fact in facts.items()},
        )
        held.append(
            eligibility.CandidateFacts(
                stable_id=stored.stable_id,
                revision_id=stored.revision_id,
                harness_id=str(document.get("harness_id") or _value(facts.get("harness_id")) or ""),
                component_type=str(
                    document.get("component_type") or _value(facts.get("component_type")) or ""
                ),
                owner_id=str(document.get("owner_id") or ""),
                version=str(document.get("version") or ""),
                visibility=str(document.get("visibility") or "private"),
                supported_os=frozenset(_document_strings(document, facts, "supported_os")),
                supported_arch=frozenset(_document_strings(document, facts, "supported_arch")),
                requires_capabilities=tuple(
                    _document_strings(document, facts, "requires_capabilities")
                ),
                required_env=tuple(_required_env_names(document, facts)),
                requires_credentials=bool(document.get("requires_credentials") or False),
                requires_authorization=str(document.get("requires_authorization") or "none"),
                license_id=_license_id(document),
                # The user's own work — **unless the catalogue said otherwise**.
                # `registry acquire` materialises a published graph into these
                # same tables, and before `#447` those rows also read as the
                # user's own: `lane_of` checks ownership first, so an acquired
                # object never reached `experimental` and skipped consent, the
                # licence and the grant together. An excess permission, not a
                # missing refusal, so the repair records what the catalogue said
                # rather than adding a check.
                owned_or_pinned=verdict is None,
                author_verified=verdict.author_verified if verdict else False,
                component_verified=verdict.component_verified if verdict else False,
                registrable=lifecycle.registrable(connection, stored),
                consented=flagged or agreed.covered,
                consent_source=(
                    agreed.source
                    if agreed.covered
                    else "request flag, for this command only"
                    if flagged
                    else ""
                ),
            )
        )
    return tuple(held)


def _revision_at(
    connection: sqlite3.Connection, stable_id: str, version: str | None
) -> revisions.StoredRevision | None:
    """The revision of the exact version asked for, or the head when none is."""
    if version:
        recorded = versions.held(connection, stable_id, version)
        if recorded is not None:
            return revisions.get(connection, recorded.revision_id)
    return revisions.head(connection, stable_id)


def _required_env_names(
    document: Mapping[str, JsonValue], facts: Mapping[str, JsonValue]
) -> list[str]:
    """The *names* only. `REQ-1108` keeps values out of every agent-reachable path."""
    raw = document.get("required_env")
    if not isinstance(raw, list):
        return []
    names: list[str] = []
    for item in cast(list[object], raw):
        if isinstance(item, dict):
            name = cast(dict[str, object], item).get("name")
            if isinstance(name, str) and name:
                names.append(name)
        elif isinstance(item, str) and item:
            names.append(item)
    return names


def _license_id(document: Mapping[str, JsonValue]) -> str:
    licence = document.get("license")
    if isinstance(licence, dict):
        value = cast(dict[str, object], licence).get("spdx_id")
        return str(value) if isinstance(value, str) else ""
    return ""


def _value(fact: JsonValue) -> JsonValue:
    return fact.get("value") if isinstance(fact, dict) else fact


def _view(assessment: eligibility.Assessment) -> CandidateEligibility:
    return CandidateEligibility(
        stable_id=assessment.stable_id,
        revision_id=assessment.revision_id,
        lane=assessment.lane,  # pyright: ignore[reportArgumentType]
        lane_reason=assessment.lane_reason,
        admissible=assessment.admissible,
        auto_selectable=assessment.auto_selectable,
        refusals=[
            EligibilityRefusal(
                family=item.family,  # pyright: ignore[reportArgumentType]
                code=item.code,
                summary=item.summary,
                details=item.details,
            )
            for item in assessment.refusals
        ],
        notes=[
            EligibilityNote(
                code=item.code,  # pyright: ignore[reportArgumentType]
                summary=item.summary,
                details=item.details,
            )
            for item in assessment.notes
        ],
    )


#: How long a proposal stays open. Long enough for an agent to show several and
#: a person to read them; short enough that a stale one is refused rather than
#: silently confirmed against context that has moved on.
PROPOSAL_TTL_SECONDS: Final[int] = 3600


def propose(parameters: Mapping[str, object]) -> Answer[ProposalSession]:
    """Record one composition proposal. Creates no version and no target.

    `REQ-622` in full: this writes a session row and nothing else. Whether to
    show one proposal or five is the agent's decision, so several may be open
    for the same pair at once and none of them is more real than the others
    until the user confirms exactly one.

    `--empty` composes a setup that projects no files (`REQ-630`). It exists
    because the alternative was worse in both directions: without it a zero
    member setup could only be made by writing the registry by hand, and with a
    bare zero-member call it would be indistinguishable from a search that
    matched nothing. Naming it separates the two, and `select confirm` still
    supplies the decision that freezes it.
    """
    harness = _harness_of(parameters)
    root = _project_root(parameters)
    wanted = _members_named(parameters)
    empty = parameters.get("empty") is True

    def work(connection: sqlite3.Connection) -> ProposalSession:
        context = context_for_project(connection, harness, root)
        at = moment()
        members = _resolve(connection, wanted, harness=harness, root=root)
        recorded = selection.propose(
            connection,
            context=context,
            members=members,
            at=at,
            expires_at=_plus(at, PROPOSAL_TTL_SECONDS),
            empty=empty,
        )
        return _session(connection, context, at, recorded=recorded.proposal_id)

    with closing(open_registry(configured_path(), create=True)) as connection:
        return Answer(work(connection))


def confirm(parameters: Mapping[str, object]) -> Answer[ConfirmationView]:
    """Freeze exactly one proposal as a private `SetupVersion` (`REQ-623`).

    The only path from a shown composition to a stored object. Repeating it
    returns the version already created rather than making a second one, which
    `REQ-624` makes a success and not a conflict.

    Naming the exact proposal is the decision. What this freezes is private,
    local and reversible by composing again, so the `--confirm` flag it once
    demanded beside the proposal was a second question about one answer — the
    class `ADR-0118` removes rather than adds to.
    """
    proposal_id = str(parameters.get("proposal") or "")
    if not proposal_id:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the proposal being confirmed must be named",
            next_actions=["select propose --harness <id> --json"],
        )

    def work(connection: sqlite3.Connection) -> ConfirmationView:
        proposal = selection.held(connection, proposal_id)
        if proposal is None:
            raise CliFailure(
                "AI_STP_NOT_FOUND",
                "no proposal with that identifier is held by this session",
                details={"proposal_id": proposal_id},
                next_actions=["select propose --harness <id> --json"],
            )
        context = context_for_project(
            connection, proposal.harness_id, _root_of(connection, proposal)
        )
        confirmed = selection.confirm(
            connection,
            proposal_id,
            context=context,
            owner_id=owner().account_id,
            device_id=_device(connection),
            at=moment(),
        )
        return ConfirmationView(
            stable_id=confirmed.stable_id,
            version=confirmed.version,
            revision_id=confirmed.revision_id,
            state=confirmed.state,  # pyright: ignore[reportArgumentType]
            created=confirmed.created,
            trace=selection.trace_of(connection, confirmed.stable_id, confirmed.version),
        )

    with closing(open_registry(configured_path(), create=True)) as connection:
        return Answer(work(connection))


def cancel(parameters: Mapping[str, object]) -> Answer[ProposalSession]:
    """Close one proposal, persisting only its idempotent session outcome."""
    proposal_id = str(parameters.get("proposal") or "")
    if not proposal_id:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the proposal being cancelled must be named",
            next_actions=["select session --harness <id> --json"],
        )

    def work(connection: sqlite3.Connection) -> ProposalSession:
        at = moment()
        proposal = selection.cancel(connection, proposal_id, at=at)
        context = context_for_project(
            connection, proposal.harness_id, _root_of(connection, proposal)
        )
        return _session(connection, context, at)

    with closing(open_registry(configured_path(), create=True)) as connection:
        return Answer(work(connection))


def session(parameters: Mapping[str, object]) -> Answer[ProposalSession]:
    """What one project and harness currently has open, and what is selected."""
    harness = _harness_of(parameters)
    root = _project_root(parameters)

    def work(connection: sqlite3.Connection) -> ProposalSession:
        return _session(connection, context_for_project(connection, harness, root), moment())

    registry = configured_path()
    if not registry.exists():
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "this project has no passport, so there is nothing to compose against",
            details={"root": redact_home(root.resolve())},
            next_actions=[f"project passport --root {root} --json"],
        )
    with closing(open_readonly(registry)) as connection:
        return Answer(work(connection))


def _project_root(parameters: Mapping[str, object]) -> Path:
    """The directory `--project` names here, refused by name when it is not one.

    `--project` is a **directory root** in this group and a **stable id** in
    `target status/diff/backups/rollback`. One flag name, two types, and machine
    help spells both with the same word — so an agent that has just read a
    project's id and reaches for the next command has a natural way to be wrong.

    Without this check that mistake produced an invented fact rather than a
    refusal: `Path("project_01M1F…")` is a relative path, `.resolve()` anchored it
    to the working directory, and the answer named
    `<cwd>/project_01M1F…` as a project without a passport — a directory nobody
    mentioned and that never existed — then offered
    `project passport --root project_01M1F… --json`, which fails the same way.
    Measured in the functional sweep of 2026-09-02.

    An absent `--project` still means the working directory, which is the
    ordinary case and stays untouched.
    """
    named = parameters.get("project")
    if named is None or str(named) == "":
        return Path.cwd()
    root = Path(str(named))
    if root.is_dir():
        return root
    raise CliFailure(
        "AI_STP_VALIDATION_ERROR",
        "this option names the project directory, not its stable id",
        details={"project": str(named)},
        next_actions=[
            "select session --project <directory> --harness <id> --json",
            "target status --project <stable id> --harness <id> --json",
        ],
    )


def _harness_of(parameters: Mapping[str, object]) -> str:
    harness = str(parameters.get("harness") or "")
    if harness not in HARNESS_IDS:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a supported harness identifier is required",
            details={"supported": ", ".join(sorted(HARNESS_IDS))},
            next_actions=["toolchain harnesses --json"],
        )
    return harness


def _members_named(parameters: Mapping[str, object]) -> tuple[tuple[str, str], ...]:
    """Read `--member id@X.Y` values. Exact references only, never a range.

    A member is named by an exact version because a setup pins exact versions —
    a floating reference would make two machines compose different things from
    the same proposal.
    """
    given: object = parameters.get("member")
    if given is None:
        raw: tuple[str, ...] = ()
    elif isinstance(given, list | tuple):
        raw = tuple(str(item) for item in cast(list[object], given))
    else:
        raw = (str(given),)

    named: list[tuple[str, str]] = []
    for item in raw:
        stable_id, separator, version = item.partition("@")
        if not separator or not stable_id or not version:
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                "a member is named as <stable_id>@<X.Y>",
                details={"given": item},
                next_actions=["component version list --id <stable_id> --json"],
            )
        named.append((stable_id, version))
    return tuple(named)


def _resolve(
    connection: sqlite3.Connection,
    named: tuple[tuple[str, str], ...],
    *,
    harness: str,
    root: Path,
) -> tuple[selection.Member, ...]:
    """Turn named references into members, refusing anything inadmissible.

    The digest is read from the registry rather than accepted from the caller:
    a digest supplied alongside the reference would be a second statement about
    the same bytes, and the two could disagree.

    Eligibility runs here rather than only at confirmation because a proposal
    that cannot be confirmed is not worth showing — `REQ-601` puts the
    mechanical stage before selection, and a proposal *is* a selection.
    """
    target = _target(harness, root, for_redistribution=False)
    # The exact versions being proposed, not the entity heads. A proposal pins
    # `X.Y`, so assessing the head could admit a member on another version's
    # declared facts — and did, until 2026-08-29.
    assessed = {
        item.stable_id: item
        for item in eligibility.assess_all(_candidates(connection, at_version=dict(named)), target)
    }

    members: list[selection.Member] = []
    for stable_id, version in named:
        recorded = versions.held(connection, stable_id, version)
        if recorded is None:
            raise CliFailure(
                "AI_STP_NOT_FOUND",
                "no such exact version is recorded on this machine",
                details={"stable_id": stable_id, "version": version},
                next_actions=["component version list --id <stable_id> --json"],
            )
        verdict = assessed.get(stable_id)
        if verdict is None or not verdict.admissible:
            reasons = "; ".join(item.code for item in verdict.refusals) if verdict else "unknown"
            raise CliFailure(
                "AI_STP_PRECONDITION_FAILED",
                "a named member is not admissible for this harness",
                details={"stable_id": stable_id, "refusals": reasons},
                next_actions=[f"select eligibility --harness {harness} --json"],
            )
        members.append(
            selection.Member(
                stable_id=stable_id,
                version=version,
                passport_digest=recorded.passport_digest,
                lane=verdict.lane,
                lane_reason=verdict.lane_reason,
            )
        )
    return tuple(members)


def context_for_project(
    connection: sqlite3.Connection, harness: str, root: Path
) -> selection.Context:
    """Assemble the session input from the three passports (`REQ-621`).

    Each one is required rather than defaulted. A session built without the
    device passport would silently drop the environment facts REQ-621 names as
    its source, and a default is exactly how that goes unnoticed.
    """
    project_id = project_passport.stable_id_for(connection, root.resolve())
    if project_id is None:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "this project has no passport, so there is nothing to compose against",
            details={"root": redact_home(root.resolve())},
            next_actions=[f"project passport --root {root} --json"],
        )
    return selection.Context(
        project_id=project_id,
        harness_id=harness,
        developer_revision=_revision(
            connection, passports.developer_stable_id(connection), "developer"
        ),
        device_revision=_revision(connection, passports.device_stable_id(connection), "device"),
        project_revision=_revision(connection, project_id, "project"),
        policy_version=_policy_version(),
    )


def _revision(connection: sqlite3.Connection, stable_id: str | None, kind: str) -> str:
    if stable_id is not None:
        stored = revisions.head(connection, stable_id)
        if stored is not None:
            return stored.revision_id
    raise CliFailure(
        "AI_STP_PRECONDITION_FAILED",
        "the required context passport is missing",
        details={"missing": kind},
        next_actions=[passports.CREATES_PASSPORT.get(kind, "doctor --json")],
    )


def _policy_version() -> str:
    """The effective selection policy, spelled so a person can read it.

    Derived from configuration rather than pinned in code: `REQ-620` wants the
    limit changed without an edit here, and `REQ-624` then makes every open
    proposal stale on its own when it changes. A digest would satisfy both and
    tell nobody which setting moved.
    """
    values = {item.path: item.value for item in effective_config().values}
    return f"selection-policy/1;result_limit={values.get('search.result_limit')}"


def _device(connection: sqlite3.Connection) -> str:
    stable_id = passports.device_stable_id(connection)
    if stable_id is None:  # pragma: no cover - `_context` already required it
        raise CliFailure("AI_STP_PRECONDITION_FAILED", "this installation has no device passport")
    return stable_id


def _root_of(connection: sqlite3.Connection, proposal: selection.Proposal) -> Path:
    row = connection.execute(
        "SELECT root FROM project_root WHERE stable_id = ?", (proposal.project_id,)
    ).fetchone()
    if row is None:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the project this proposal belongs to is no longer known",
            details={"project_id": proposal.project_id},
            next_actions=["project passport --root <path> --json"],
        )
    return Path(str(row["root"]))


def _session(
    connection: sqlite3.Connection,
    context: selection.Context,
    now: str,
    *,
    recorded: str | None = None,
) -> ProposalSession:
    pinned = selection.selected(
        connection, project_id=context.project_id, harness_id=context.harness_id
    )
    open_now = selection.open_proposals(
        connection, project_id=context.project_id, harness_id=context.harness_id, now=now
    )
    return ProposalSession(
        project_id=context.project_id,
        harness_id=context.harness_id,  # pyright: ignore[reportArgumentType]
        policy_version=context.policy_version,
        proposal_id=recorded,
        proposals=[_proposal(item, now) for item in open_now],
        selected_stable_id=None if pinned is None else pinned[0],
        selected_version=None if pinned is None else pinned[1],
        selected_state=None if pinned is None else pinned[2],  # pyright: ignore[reportArgumentType]
    )


def _proposal(proposal: selection.Proposal, now: str) -> ProposalView:
    return ProposalView(
        proposal_id=proposal.proposal_id,
        project_id=proposal.project_id,
        harness_id=proposal.harness_id,  # pyright: ignore[reportArgumentType]
        state=proposal.state(now),  # pyright: ignore[reportArgumentType]
        snapshot=proposal.snapshot,
        members=[
            ProposalMember(
                stable_id=item.stable_id,
                version=item.version,
                passport_digest=item.passport_digest,
                lane=item.lane,  # pyright: ignore[reportArgumentType]
                lane_reason=item.lane_reason,
                consent_source=item.consent_source,
                overlay_revision_id=item.overlay_revision_id,
            )
            for item in proposal.members
        ],
        created_at=proposal.created_at,
        expires_at=proposal.expires_at,
        confirmed_stable_id=proposal.confirmed_stable_id,
        confirmed_version=proposal.confirmed_version,
    )


def _plus(at: str, seconds: int) -> str:
    return format_timestamp(parse_timestamp(at) + timedelta(seconds=seconds))


def dependency_graph(parameters: Mapping[str, object]) -> Answer[SetupGraph]:
    """Resolve the exact dependency closure of a composition (`REQ-605`).

    Roots come from a named proposal or from `--member` values directly, so a
    closure can be checked before anything is proposed as well as after. Both
    forms give the resolver the same thing: exact references with digests.

    Reads and reports. A closure is a question about what is already stored, and
    answering it must not change what is stored.
    """
    proposal_id = str(parameters.get("proposal") or "")
    named = _members_named(parameters)
    if bool(proposal_id) == bool(named):
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "name either one proposal or one or more members, not both and not neither",
            next_actions=["select session --harness <id> --json"],
        )

    def work(connection: sqlite3.Connection) -> SetupGraph:
        roots = (
            _roots_of_proposal(connection, proposal_id)
            if proposal_id
            else _roots_of_members(connection, named)
        )
        return _graph(graph.resolve(connection, roots))

    with closing(open_readonly(configured_path())) as connection:
        return Answer(work(connection))


def _roots_of_proposal(
    connection: sqlite3.Connection, proposal_id: str
) -> tuple[graph.Reference, ...]:
    proposal = selection.held(connection, proposal_id)
    if proposal is None:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "no proposal with that identifier is held by this session",
            details={"proposal_id": proposal_id},
            next_actions=["select propose --harness <id> --json"],
        )
    return tuple(
        graph.Reference(
            stable_id=item.stable_id,
            version=item.version,
            passport_digest=item.passport_digest,
        )
        for item in proposal.members
    )


def _roots_of_members(
    connection: sqlite3.Connection, named: tuple[tuple[str, str], ...]
) -> tuple[graph.Reference, ...]:
    """Named members as roots, with the digest read from the registry.

    The digest is never accepted from the caller. Supplied alongside the
    reference it would be a second statement about the same bytes, and the two
    could disagree — which is precisely the mismatch the resolver exists to
    catch, arriving from the one place it cannot.
    """
    roots: list[graph.Reference] = []
    for stable_id, version in named:
        recorded = versions.held(connection, stable_id, version)
        if recorded is None:
            raise CliFailure(
                "AI_STP_NOT_FOUND",
                "no such exact version is recorded on this machine",
                details={"stable_id": stable_id, "version": version},
                next_actions=["component version list --id <stable_id> --json"],
            )
        roots.append(
            graph.Reference(
                stable_id=stable_id, version=version, passport_digest=recorded.passport_digest
            )
        )
    return tuple(roots)


def _graph(closure: graph.Closure) -> SetupGraph:
    return SetupGraph(
        resolved=closure.resolved,
        nodes=[
            GraphNode(
                stable_id=item.stable_id,
                version=item.version,
                passport_digest=item.passport_digest,
                revision_id=item.revision_id,
                depth=item.depth,
                requires=[_reference(edge) for edge in item.requires],
            )
            for item in closure.nodes
        ],
        order=list(closure.order),
        refusals=[
            GraphRefusal(code=item.code, summary=item.summary, details=item.details)
            for item in closure.refusals
        ],
        max_depth=closure.max_depth,
        max_nodes=closure.max_nodes,
    )


def _reference(reference: graph.Reference) -> GraphReference:
    return GraphReference(
        stable_id=reference.stable_id,
        version=reference.version,
        passport_digest=reference.passport_digest,
        required_by=reference.required_by,
    )


def reports(parameters: Mapping[str, object]) -> Answer[CompositionReports]:
    """Produce the composition and conversion reports for one composition.

    Both together (`REQ-609`). The first says what is in the composition and why
    it is blocked when it is; the second says what survives translation to the
    harness and names every loss. A caller given one of them would have half the
    answer they need before installing anything.

    The closure is resolved first: a composition whose dependencies do not
    resolve has nothing to report on, and reporting anyway would describe a
    state that cannot exist.
    """
    harness = _harness_of(parameters)
    proposal_id = str(parameters.get("proposal") or "")
    if not proposal_id:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the proposal being reported on must be named",
            next_actions=["select session --harness <id> --json"],
        )

    def work(connection: sqlite3.Connection) -> CompositionReports:
        closure = graph.resolve(connection, _roots_of_proposal(connection, proposal_id))
        if not closure.resolved:
            raise CliFailure(
                "AI_STP_PRECONDITION_FAILED",
                "this composition has no reports until its dependency closure resolves",
                details={"refusals": ", ".join(item.code for item in closure.refusals)},
                next_actions=[f"select graph --proposal {proposal_id} --json"],
            )

        proposal = selection.held(connection, proposal_id)
        surfaces = _surfaces(connection, closure, () if proposal is None else proposal.members)
        target = _composition_target(harness, surfaces)
        composed = composition.compose(surfaces, target)
        converted = composition.convert(surfaces, target)
        return CompositionReports(
            harness_id=harness,  # pyright: ignore[reportArgumentType]
            blocked=composed.blocked,
            chosen=[
                CompositionChoice(
                    stable_id=item.stable_id,
                    version=item.version,
                    lane=item.lane,  # pyright: ignore[reportArgumentType]
                    reason=item.reason,
                )
                for item in composed.chosen
            ],
            rejected=[
                CompositionRejection(
                    stable_id=item.stable_id,
                    version=item.version,
                    reason=item.reason,
                )
                for item in composed.rejected
            ],
            conflicts=[
                CompositionConflict(code=item.code, summary=item.summary, details=item.details)
                for item in composed.conflicts
            ],
            operations=list(composed.operations),
            conversion=[
                ConversionEntry(
                    stable_id=item.stable_id,
                    component_type=item.component_type,
                    native_surface=item.native_surface,
                    projection_kind=item.projection_kind,  # pyright: ignore[reportArgumentType]
                    state=item.state,  # pyright: ignore[reportArgumentType]
                    losses=list(item.losses),
                )
                for item in converted.entries
            ],
            conversion_complete=converted.complete,
        )

    with closing(open_readonly(configured_path())) as connection:
        return Answer(work(connection))


def _composition_target(
    harness: str, surfaces: tuple[composition.Surface, ...] = ()
) -> composition.Target:
    """What this machine allows a composition to need.

    Permissions and entitlements start empty: nothing has granted any yet, and
    an empty set refuses honestly rather than permitting by default.

    The declared environment is the **composition's**, which is what
    `composition._environment` says it checks — and it read
    `frozenset(os.environ)` until 2026-08-29. That turned a question about the
    composition into "is this variable exported in the shell that ran the CLI",
    which the same docstring explicitly disclaims: a missing value is an
    advisory at install (`REQ-111`, `REQ-816`) and a note at eligibility, not a
    reason to refuse to build a package. Endpoints were never declared at all,
    so any `external_endpoints` blocked unconditionally.

    Two documented facts about one thing, disagreeing. The composition declares
    what its members declare, so at this call site the check is satisfied by
    construction — deliberately, because there is no independent declaration
    here to compare against. The conflict code stays live for a caller that has
    one, and the user-facing answer lives where it can be given.
    """
    return composition.Target(
        harness_id=harness,
        os=_operating_system(),
        arch=platform.machine().lower(),
        declared_env=frozenset(name for item in surfaces for name in item.required_env),
        declared_endpoints=frozenset(
            endpoint for item in surfaces for endpoint in item.external_endpoints
        ),
        supported_platforms=frozenset(),
        for_redistribution=False,
    )


def _surfaces(
    connection: sqlite3.Connection,
    closure: graph.Closure,
    members: Sequence[selection.Member] = (),
) -> tuple[composition.Surface, ...]:
    """Read what each node in the closure contributes, from its passport.

    Lane and consent travel with the proposal member when one exists, so the
    report names the decision the user was shown (`REQ-616`) rather than a
    lane recomputed from the passport after confirmation. Local registry
    objects without a member are the owner's own: claiming another lane would
    invent a platform confirmation.
    """
    by_member = {item.stable_id: item for item in members}
    surfaces: list[composition.Surface] = []
    for node in closure.nodes:
        stored = revisions.get(connection, node.revision_id)
        if stored is None:  # pragma: no cover - the closure already read it
            continue
        document = cast(dict[str, JsonValue], stored.envelope.model_dump(mode="json"))
        facts = cast(dict[str, JsonValue], document.get("facts") or {})
        source = document.get("source")
        source_path = str(source.get("path") or "") if isinstance(source, dict) else ""
        member = by_member.get(node.stable_id)
        if member is not None and member.lane:
            lane = member.lane
            lane_reason = member.lane_reason
            consented = bool(member.consent_source)
        else:
            lane = "local_owner_or_pinned"
            lane_reason = "your own or exactly pinned; installable after local checks"
            consented = False
        surfaces.append(
            composition.Surface(
                stable_id=node.stable_id,
                version=node.version,
                component_type=str(
                    document.get("component_type") or _value(facts.get("component_type")) or ""
                ),
                harness_id=str(document.get("harness_id") or _value(facts.get("harness_id")) or ""),
                revision_id=node.revision_id,
                source_name=str(_value(facts.get("source_name")) or source_path.rsplit("/", 1)[-1]),
                content_format=str(
                    document.get("artifact_format") or _value(facts.get("content_format")) or ""
                ),
                managed_paths=_document_strings(document, facts, "managed_paths"),
                native_ids=_document_strings(document, facts, "native_ids"),
                permissions=_document_permissions(document, facts),
                required_env=_document_required_env(document, facts),
                external_endpoints=_document_strings(document, facts, "external_endpoints"),
                redistribution=_document_redistribution(document, facts),
                precedence=_number(facts.get("precedence")),
                hook_event=str(_value(facts.get("hook_event")) or ""),
                hook_order=_number(facts.get("hook_order")),
                lane=lane,
                lane_reason=lane_reason,
                consented=consented,
            )
        )
    return tuple(surfaces)


def _strings(fact: JsonValue | None) -> tuple[str, ...]:
    value = _value(fact) if fact is not None else None
    return tuple(str(item) for item in value) if isinstance(value, list) else ()


def _document_strings(
    document: dict[str, JsonValue], facts: dict[str, JsonValue], name: str
) -> tuple[str, ...]:
    direct = document.get(name)
    if isinstance(direct, list):
        return tuple(str(item) for item in direct)
    return _strings(facts.get(name))


def _document_permissions(
    document: dict[str, JsonValue], facts: dict[str, JsonValue]
) -> tuple[str, ...]:
    direct = document.get("permissions")
    if not isinstance(direct, dict):
        return _strings(facts.get("permissions"))
    values: list[str] = []
    for family in ("filesystem", "network", "process"):
        declared = direct.get(family)
        if isinstance(declared, list):
            values.extend(f"{family}:{item}" for item in declared)
    return tuple(values)


def _document_required_env(
    document: dict[str, JsonValue], facts: dict[str, JsonValue]
) -> tuple[str, ...]:
    direct = document.get("required_env")
    if not isinstance(direct, list):
        return _strings(facts.get("required_env"))
    return tuple(
        str(item.get("name"))
        for item in direct
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    )


def _document_redistribution(document: dict[str, JsonValue], facts: dict[str, JsonValue]) -> bool:
    license_info = document.get("license")
    if isinstance(license_info, dict):
        allowed = license_info.get("redistribution_allowed")
        if isinstance(allowed, bool):
            return allowed
    declared = _value(facts.get("redistribution"))
    return declared if isinstance(declared, bool) else True


def _number(fact: JsonValue | None) -> int | None:
    """A declared integer, or `None` when nothing was declared.

    `None` and zero are different: zero is a position somebody chose and can
    collide with another, and absence never collides with anything.
    """
    value = _value(fact) if fact is not None else None
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def harness_bundle(parameters: Mapping[str, object]) -> Answer[HarnessBundle]:
    """Compile the deterministic bundle for one confirmed composition (`#167`).

    Compiles and reports. Nothing here writes to a harness: `ADR-0012` gives the
    final write to the provider alone, and installing these bytes is a separate
    plan with its own confirmation.

    The composition must have reports first. A bundle carries both of them
    (`REQ-609`), so compiling one for a blocked composition would produce a
    package describing conflicts it also claims to have resolved.
    """
    harness = _harness_of(parameters)
    proposal_id = str(parameters.get("proposal") or "")
    if not proposal_id:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the composition being bundled must be named",
            next_actions=["select session --harness <id> --json"],
        )
    host_root = _bundle_host_root(parameters)

    def work(connection: sqlite3.Connection) -> HarnessBundle:
        return _bundle_view(
            compile_harness_bundle(connection, proposal_id, harness, host_root=host_root), harness
        )

    with closing(open_readonly(configured_path())) as connection:
        return Answer(work(connection))


def _bundle_host_root(parameters: Mapping[str, object]) -> Path | None:
    """The installing machine's target, when the caller names one.

    A composition holding a contribution to a file the provider owns needs
    that file's current bytes, and they exist only on the target (`ADR-0129`).
    `install plan` has always taken one; `select bundle` declared none, so a
    composition with an `mcp` server for codex could be planned and installed
    but never bundled on its own — a dead end between two commands. The same
    shape `install plan` accepts: an existing absolute directory, not a link.
    """
    given = str(parameters.get("target") or "")
    if not given:
        return None
    place = Path(given).expanduser()
    if place.is_symlink() or not place.is_absolute() or not place.is_dir():
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the provider target must be an existing absolute directory, not a symlink",
            details={"target": redact_home(place)},
        )
    return place.resolve()


def compile_harness_bundle(
    connection: sqlite3.Connection,
    proposal_id: str,
    harness: str,
    host_root: Path | None = None,
) -> bundle.Bundle:
    """Compile exact bytes for a confirmed proposal without opening another registry."""
    proposal = selection.held(connection, proposal_id)
    if proposal is None:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "no proposal with that identifier is held by this session",
            details={"proposal_id": proposal_id},
        )
    if proposal.harness_id != harness:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the requested harness differs from the confirmed composition",
            details={"requested": harness, "proposal": proposal.harness_id},
        )
    if proposal.confirmed_stable_id is None or proposal.confirmed_version is None:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "only a confirmed composition has a SetupVersion passport to bundle",
            details={"proposal_id": proposal_id},
            next_actions=[f"select confirm --proposal {proposal_id} --json"],
        )
    return compile_setup_version_bundle(
        connection,
        proposal.confirmed_stable_id,
        proposal.confirmed_version,
        expected_harness=harness,
        members=proposal.members,
        host_root=host_root,
    )


def compile_setup_version_bundle(
    connection: sqlite3.Connection,
    stable_id: str,
    version: str,
    *,
    expected_harness: str | None = None,
    members: tuple[selection.Member, ...] = (),
    host_root: Path | None = None,
) -> bundle.Bundle:
    """Compile one stored immutable SetupVersion through the canonical bundle path.

    Prepared and newly composed setups meet here.  The former names this exact
    version directly; the latter reaches it through its confirmed proposal.
    Nothing below consults mutable entity heads.
    """
    setup_version = versions.held(connection, stable_id, version)
    if setup_version is None:  # pragma: no cover - confirmation is atomic
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "the exact prepared SetupVersion is not held by this registry",
            details={"stable_id": stable_id, "version": version},
        )
    setup_revision = revisions.get(connection, setup_version.revision_id)
    if setup_revision is None:  # pragma: no cover - version references are constrained
        raise CliFailure(
            "AI_STP_CONFLICT",
            "the exact prepared SetupVersion has no passport revision",
            details={"stable_id": stable_id, "version": version},
        )

    setup_document = cast(dict[str, JsonValue], setup_revision.envelope.model_dump(mode="json"))
    harness = str(setup_document.get("harness_id") or "")
    if not harness or (expected_harness is not None and harness != expected_harness):
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the prepared SetupVersion belongs to another harness",
            details={"expected": expected_harness or "declared", "reported": harness},
        )
    raw_components = setup_document.get("components")
    if not isinstance(raw_components, list):
        raise CliFailure(
            "AI_STP_CONFLICT",
            "the prepared SetupVersion has no exact component graph",
            details={"stable_id": stable_id, "version": version},
        )
    roots: list[graph.Reference] = []
    for item in raw_components:
        if not isinstance(item, dict):
            raise CliFailure(
                "AI_STP_CONFLICT",
                "the prepared SetupVersion contains a malformed component reference",
                details={"stable_id": stable_id, "version": version},
            )
        roots.append(
            graph.Reference(
                stable_id=str(item.get("stable_id") or ""),
                version=str(item.get("version") or ""),
                passport_digest=str(item.get("passport_digest") or ""),
            )
        )
    closure = graph.resolve(connection, tuple(roots))
    if not closure.resolved:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the prepared SetupVersion no longer resolves to its exact component graph",
            details={"refusals": ", ".join(item.code for item in closure.refusals)},
        )

    surfaces = _surfaces(connection, closure, members)
    target = _composition_target(harness, surfaces)
    composed = composition.compose(surfaces, target)
    if composed.blocked:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "this composition has conflicts, so there is no package to build",
            details={"conflicts": ", ".join(item.code for item in composed.conflicts)},
            next_actions=["select eligibility --harness <id> --json"],
        )

    converted = composition.convert(surfaces, target)
    if not converted.complete:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "this composition cannot preserve every component on the native target",
            details={"losses": "; ".join(converted.losses)},
            next_actions=["select eligibility --harness <id> --json"],
        )
    setup_facts = setup_document.get("facts")
    snapshot = ""
    if isinstance(setup_facts, dict):
        snapshot = str(_value(setup_facts.get("snapshot")) or "")
    sources = _bundle_sources(connection, surfaces, target, host_root)
    return bundle.compile_bundle(
        sources,
        setup_stable_id=setup_version.stable_id,
        setup_version=setup_version.version,
        setup_digest=setup_version.passport_digest,
        harness_id=harness,
        declared_paths=_declared_covers(surfaces, sources),
        setup_passport=cast(JsonValue, setup_revision.envelope.model_dump(mode="json")),
        composition_report=_as_json(composed),
        conversion_report=_conversion_json(converted),
        input_digest=snapshot,
    )


def _bundle_view(compiled: bundle.Bundle, harness: str) -> HarnessBundle:
    return HarnessBundle(
        compiled=compiled.compiled,
        harness_id=harness,  # pyright: ignore[reportArgumentType]
        bundle_format=bundle.BUNDLE_FORMAT,
        digest=compiled.digest,
        artifact_digest=compiled.artifact_digest,
        byte_length=len(compiled.archive),
        builder_version=bundle.BUILDER_VERSION,
        protocol_version=bundle.PROTOCOL_VERSION,
        files=[
            BundleFile(
                path=item.path,
                digest=item.digest,
                byte_length=item.byte_length,
                mode=item.mode,  # pyright: ignore[reportArgumentType]
                owner=item.owner,
            )
            for item in compiled.files
        ],
        refusals=[
            BundleRefusal(code=item.code, summary=item.summary, details=item.details)
            for item in compiled.refusals
        ],
        max_files=bundle.MAX_FILES,
        max_file_bytes=bundle.MAX_FILE_BYTES,
        max_bundle_bytes=bundle.MAX_BUNDLE_BYTES,
    )


def _bundle_sources(
    connection: sqlite3.Connection,
    surfaces: tuple[composition.Surface, ...],
    target: composition.Target,
    host_root: Path | None = None,
) -> tuple[bundle.Source, ...]:
    """The bytes each component contributes, at the path it lands on.

    Content comes from the content store by digest, so what is bundled is
    exactly what was adopted — reading the original file again could pick up a
    change made since, and the bundle would then describe something nobody
    reviewed.
    """
    sources: list[bundle.Source] = []
    # Applied after every other source, because a contribution has to land on
    # whatever else this setup puts in the same file. A setup carrying both a
    # `setting` component for `config.toml` and an `mcp` component contributing
    # `mcp_servers` to it has one file and two owners of different parts of it;
    # assembling the contribution against the target while the setting also
    # wrote that path would put two sources on one path, and the bundle refuses
    # that — correctly, because it cannot know which one the harness should get.
    contributions: list[tuple[components.Rule, str, components.ComponentFile]] = []
    for item in sorted(surfaces, key=lambda item: item.stable_id):
        stored = revisions.get(connection, item.revision_id)
        if stored is None:  # pragma: no cover - the closure already read it
            continue
        if stored.stable_id != item.stable_id:  # pragma: no cover - revision identity is sealed
            raise CliFailure(
                "AI_STP_CONFLICT",
                "the resolved component revision belongs to another object",
                details={"stable_id": item.stable_id, "revision_id": item.revision_id},
            )
        document = cast(dict[str, JsonValue], stored.envelope.model_dump(mode="json"))
        facts = cast(dict[str, JsonValue], document.get("facts") or {})
        artifact = document.get("artifact")
        direct_digest = artifact.get("digest") if isinstance(artifact, dict) else None
        digest = str(_value(facts.get("content_digest")) or direct_digest or "")
        # Both of these were `continue`, and both silently produced a bundle
        # weaker than the report describing it. The closure resolved the node,
        # the composition report names it under `chosen`, and the plan then
        # counts files that do not include it — every downstream statement stays
        # true about what the writer was handed, which is the same shape as the
        # dropped sibling artifacts of `#438`.
        #
        # An empty graph stays a real graph (`ADR-0124`, `REQ-630`): zero nodes
        # give a zero-file bundle. A *present* node with nothing to write is not
        # emptiness, and the honest answer is a refusal naming it.
        if not digest:
            raise CliFailure(
                "AI_STP_CONFLICT",
                "a resolved component carries no artifact digest to bundle",
                details={"stable_id": item.stable_id, "revision_id": item.revision_id},
            )
        rule = composition.rule_for(item.component_type, target.harness_id)
        if rule is None:
            # `native_surface_lost` blocks this at composition — but only when
            # the component is `required`, so an optional member of a kind this
            # harness cannot hold reached here and disappeared. Confirming a
            # component into a composition is choosing it; `required` decides
            # dependency resolution, not whether the writer may drop it.
            raise CliFailure(
                "AI_STP_CONFLICT",
                "the target harness has no native surface for a chosen component",
                details={
                    "stable_id": item.stable_id,
                    "component_type": item.component_type,
                    "harness_id": target.harness_id,
                },
            )
        name = item.source_name
        content_format = str(
            document.get("artifact_format") or _value(facts.get("content_format")) or ""
        )
        payload = content.get(connection, digest)
        expanded = components.expand(
            payload,
            content_format or components.COMPONENT_FILE_FORMAT,
        )
        if rule.declared_key:
            # `ADR-0129`: this component's landing is a key inside a file the
            # provider already owns, so it compiles into a contribution to that
            # file rather than a surface of its own. The provider is handed the
            # host's complete bytes under the kind it does declare.
            #
            # `host_root` is the installing machine's target, and its absence is
            # a refusal rather than a fallback. A bundle is portable and a
            # merged host file is not: one built without a target would carry
            # another machine's `config.toml`, and the same bundle installed
            # twice would write the first machine's file onto the second.
            if host_root is None:
                raise CliFailure(
                    "AI_STP_PRECONDITION_FAILED",
                    "this component contributes a key to an owned file and needs a named target",
                    details={
                        "stable_id": item.stable_id,
                        "host": rule.relative,
                        "key": rule.declared_key,
                    },
                    next_actions=[
                        "select bundle --target <directory> --json",
                        "install plan --target <directory> --json",
                    ],
                )
            contributions.append((rule, item.stable_id, expanded[0]))
            continue
        if rule.shape == "file":
            if len(expanded) == 1 and not expanded[0].path:
                projection = ((rule.relative, expanded[0]),)
            elif item.component_type == "hook":
                projected = _project_hook_tree(rule, expanded)
                if projected is None:
                    raise CliFailure(
                        "AI_STP_PRECONDITION_FAILED",
                        "a hook artifact has no native manifest",
                        details={"stable_id": item.stable_id, "native_surface": rule.relative},
                    )
                projection = projected
            else:
                raise CliFailure(
                    "AI_STP_PRECONDITION_FAILED",
                    "a directory artifact cannot project onto one native file",
                    details={"stable_id": item.stable_id, "native_surface": rule.relative},
                )
        else:
            root = f"{rule.relative}/{name}" if name else rule.relative
            projection = tuple(
                (f"{root}/{member.path}" if member.path else root, member) for member in expanded
            )
        if item.managed_paths:
            declared = frozenset(item.managed_paths)
            if item.component_type == "hook":
                declared = frozenset(
                    claim for path in declared for claim in composition.claimed_paths(path)
                )
            missing, undeclared = _managed_path_drift(
                declared,
                frozenset(path for path, _ in projection),
            )
            if missing or undeclared:
                raise CliFailure(
                    "AI_STP_PRECONDITION_FAILED",
                    "the component artifact does not contain exactly its declared managed paths",
                    details={
                        "stable_id": item.stable_id,
                        "missing": ", ".join(sorted(missing)),
                        "undeclared": ", ".join(sorted(undeclared)),
                    },
                )
        for place, member in projection:
            sources.append(
                bundle.Source(
                    path=place,
                    content=member.content,
                    owner=item.stable_id,
                    mode=member.mode,
                )
            )
    for rule, contributor, member in contributions:
        # The base is what this setup already puts there, and the target's
        # current bytes only when it puts nothing. That ordering is the whole
        # point: a contribution adds a key, and everything else in the file —
        # whether it came from a sibling component or from the machine — stays.
        existing = next((s for s in sources if s.path == rule.relative), None)
        host = host_root / rule.relative if host_root is not None else None
        if existing is not None:
            base: bytes | None = existing.content
            sources.remove(existing)
        else:
            base = host.read_bytes() if host is not None and host.is_file() else None
        sources.append(
            bundle.Source(
                path=rule.relative,
                content=contribution.assemble(
                    host=rule.relative,
                    current=base,
                    key=rule.declared_key,
                    value=contribution.parse_value(host=rule.relative, content=member.content),
                ),
                owner=contributor,
                mode=member.mode,
            )
        )
    return tuple(sources)


def _project_hook_tree(
    rule: components.Rule, expanded: tuple[components.ComponentFile, ...]
) -> tuple[tuple[str, components.ComponentFile], ...] | None:
    """Land a hook tree onto the file-shaped native surface.

    Discovery sees `hooks.json`. Handlers live in the sibling `hooks/`
    directory. Adoption may capture that as a file-plus-siblings tree
    (``hooks.json``, ``hooks/h01.py``) or as the directory itself
    (``hooks.json``, ``h01.py``). Both have to land at the same native
    places: the manifest on the declared file, handlers under `hooks/`.
    """
    manifest_name = PurePosixPath(rule.relative).name
    if not any(member.path == manifest_name for member in expanded):
        return None
    parent = str(PurePosixPath(rule.relative).parent)
    parent = "" if parent == "." else parent
    projection: list[tuple[str, components.ComponentFile]] = []
    for member in expanded:
        if member.path == manifest_name:
            place = rule.relative
        else:
            relative = member.path if member.path.startswith("hooks/") else f"hooks/{member.path}"
            place = f"{parent}/{relative}".lstrip("/")
        projection.append((place, member))
    return tuple(projection)


def _managed_path_drift(
    declared: frozenset[str], projected: frozenset[str]
) -> tuple[frozenset[str], frozenset[str]]:
    return composition.managed_path_drift(declared, projected)


def _declared_covers(
    surfaces: tuple[composition.Surface, ...], sources: tuple[bundle.Source, ...]
) -> frozenset[str]:
    """Passport roots when declared, otherwise the files this compile projected.

    Passing the source paths alone made `path_undeclared` / `declared_path_absent`
    a tautology: the writer checked the set it had just built. Passport covers
    are roots, so `skills/foo` must still cover `skills/foo/SKILL.md`.
    """
    by_owner: dict[str, list[str]] = {}
    for source in sources:
        by_owner.setdefault(source.owner, []).append(source.path)
    covers: set[str] = set()
    for item in surfaces:
        if item.managed_paths:
            for path in item.managed_paths:
                covers.update(
                    composition.claimed_paths(path) if item.component_type == "hook" else (path,)
                )
        else:
            covers.update(by_owner.get(item.stable_id, ()))
    return frozenset(covers)


def _as_json(report: composition.CompositionReport) -> JsonValue:
    return cast(
        JsonValue,
        {
            "chosen": [
                {
                    "stable_id": item.stable_id,
                    "version": item.version,
                    "lane": item.lane,
                    "reason": item.reason,
                }
                for item in report.chosen
            ],
            "rejected": [
                {
                    "stable_id": item.stable_id,
                    "version": item.version,
                    "reason": item.reason,
                }
                for item in report.rejected
            ],
            "operations": list(report.operations),
            "conflicts": [
                {"code": item.code, "summary": item.summary, "details": item.details}
                for item in report.conflicts
            ],
        },
    )


def _conversion_json(report: composition.ConversionReport) -> JsonValue:
    """The conversion report as the **provider** reads it, not as a person does.

    `component_type` here is the kind the provider is told, which is not always
    the kind the object is. That is the whole of `#454`, and this document is
    where the distinction has to land: the provider checks a bundle's kinds
    against what it implements, and it reads them from exactly this field —
    `harness-runtime/src/wire.rs::check_declared_kinds`. Its own comment says
    so: the kind is not in the manifest and not in the setup passport, it is
    stated once, here.

    This used to emit the *logical* kind and put the told kind beside it in a
    new `provider_kind` field. Nothing on the provider side has ever read that
    name — it appears in no released binary and in no schema of the shared kit —
    so every contribution component arrived as `mcp` at a provider that
    implements `setting`, and was refused `unsupported_component_kind`. The
    field was added on the belief that the other side would read it, which is a
    statement about a mechanism rather than a measurement of one.

    `provider_kind` stays, carrying the same value, because two readers here
    already take `provider_kind or component_type` and a field that vanishes
    silently is worse than one that agrees.

    The person-facing report is a different rendering and keeps the logical
    kind: `contracts.machine_help.ConversionEntry` is built elsewhere, and what
    a component *is* belongs there.
    """
    return {
        "entries": [
            {
                "stable_id": item.stable_id,
                "component_type": item.provider_kind or item.component_type,
                "native_surface": item.native_surface,
                "projection_kind": item.projection_kind,
                "provider_kind": item.provider_kind or item.component_type,
                "state": item.state,
                "losses": list(item.losses),
            }
            for item in report.entries
        ],
        "complete": report.complete,
    }


def provider_conformance(parameters: Mapping[str, object]) -> Answer[ConformanceReport]:
    """Run one explicitly selected conformance kit against a provider (`#169`).

    Reads and reports. Every case runs even after one fails, because the
    audience for a failure is somebody writing a provider against a protocol
    they cannot see, and one line of it is not enough to work from.

    Frozen v1 uses the common process boundary without a network claim. V2 adds
    an exact phase and requires observed network enforcement before every local
    spawn. A provider answer never selects its own protocol version.
    """
    executable = str(parameters.get("executable") or "")
    harness = _harness_of(parameters)
    if not executable:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the provider executable to check must be named",
            next_actions=["toolchain harnesses --json"],
        )
    place = Path(executable).expanduser()
    try:
        resolved_executable = conformance.resolve_executable(executable)
    except FileNotFoundError:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "no executable sits at that path",
            details={"executable": redact_home(place)},
        ) from None
    except PermissionError:
        raise CliFailure(
            "AI_STP_DEPENDENCY_UNAVAILABLE",
            "the provider artifact exists but is not executable on this host",
            details={"executable": redact_home(place)},
            next_actions=["provider trust --json"],
        ) from None

    requested = parameters.get("protocol-version")
    version = 1 if requested is None else int(cast(int, requested))
    if version not in (protocol.VERSION, protocol_v2.VERSION, protocol_v3.VERSION):
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "only provider protocol version 1, 2 or 3 can be checked",
            details={"protocol_version": str(version)},
        )
    target = Path(str(parameters.get("target") or Path.cwd())).resolve()
    if version == protocol.VERSION:
        report = conformance.run(
            conformance.subprocess_invoker(resolved_executable, str(target)),
            harness_id=harness,
        )
    else:
        if target.is_symlink() or not target.is_dir():
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                "provider protocol v2/v3 requires an existing real target directory",
                details={"target": redact_home(target)},
            )
        if version == protocol_v3.VERSION:
            # The shared invoker, not a copy of it. The reason is the operator's
            # own — `--unverified-provider` — because that is the only one of the
            # two this command can establish: it loads no release manifest and
            # takes whatever path it is handed. Without the flag it refuses
            # exactly as before, so nothing is weaker by default (`ADR-0126`).
            report = conformance_v3.run(
                invocation.provider_invoker(
                    resolved_executable,
                    str(target),
                    version,
                    unisolated_reason=(
                        network_launcher.EXPLICIT_UNVERIFIED_PROVIDER
                        if parameters.get("unverified-provider") is True
                        else None
                    ),
                ),
                harness_id=harness,
                target=target,
            )
            return Answer(
                ConformanceReport(
                    harness_id=harness,  # pyright: ignore[reportArgumentType]
                    protocol_version=version,
                    reported_version=report.protocol_version,
                    conforms=report.conforms,
                    cases=[
                        ConformanceCase(
                            name=item.name,
                            passed=item.passed,
                            detail=item.detail,
                            subject=item.subject,
                        )
                        for item in report.cases
                    ],
                )
            )

        launcher, capability = network_launcher.discover_launcher()

        def invoke_v2(
            command: str,
            phase: protocol_v2.ActionPhase,
            arguments: Sequence[str],
        ) -> invocation_v2.InvocationResult:
            return invocation_v2.invoke(
                resolved_executable,
                str(target),
                command,
                phase,
                arguments,
                launcher=launcher,
                capability=capability,
            )

        try:
            report = conformance_v2.run(invoke_v2, harness_id=harness)
        except protocol_v2.NetworkCapabilityUnavailable as error:
            decision = error.decision
            raise CliFailure(
                error.error_code,
                "provider protocol v2 network isolation is unavailable before invocation",
                details={
                    "command": decision.command,
                    "phase": decision.phase.value,
                    "network_enforcement": decision.enforcement.value,
                },
                next_actions=["provider network --json"],
            ) from None
    return Answer(
        ConformanceReport(
            harness_id=harness,  # pyright: ignore[reportArgumentType]
            protocol_version=version,
            reported_version=report.protocol_version,
            conforms=report.conforms,
            cases=[
                ConformanceCase(
                    name=item.name,
                    passed=item.passed,
                    detail=item.detail,
                    subject=item.subject,
                    exercised=item.exercised,
                )
                for item in report.cases
            ],
        )
    )


def provider_network(_parameters: Mapping[str, object]) -> Answer[ProviderNetworkCapability]:
    """Report observed v2 network enforcement without launching a provider."""
    launcher, capability = network_launcher.discover_launcher()
    decision = protocol_v2.decide(
        "provider-info",
        protocol_v2.ActionPhase.EXECUTE,
        capability,
    )
    try:
        protocol_v2.require_execution(decision)
    except protocol_v2.NetworkCapabilityUnavailable:
        available = False
    else:
        available = launcher is not None
    enforcement = (
        "enforced"
        if decision.enforcement is protocol_v2.NetworkEnforcement.ENFORCED
        else "unavailable"
    )
    # What a v3 local phase does here, which the v2 fields above cannot say.
    # Three answers, and the third is deliberately not the second: on a platform
    # that could deny the network, its absence is a missing dependency, and
    # `unisolated_local_phase` refuses to be built there for the same reason.
    if launcher is not None:
        phase, reasons = "network_denied", []
    elif capability.os_name in network_launcher.UNISOLATED_PLATFORMS:
        phase = "unisolated_by_trust"
        reasons = sorted(network_launcher.UNISOLATED_REASONS)
    else:
        phase, reasons = "refused", []
    return Answer(
        ProviderNetworkCapability(
            os_name=capability.os_name,
            network_enforcement=enforcement,
            launcher_id=capability.launcher_id or "",
            evidence=list(capability.evidence),
            local_actions_available=available,
            v3_local_phase=phase,  # pyright: ignore[reportArgumentType]
            v3_local_phase_reasons=reasons,
        )
    )


def provider_trust(parameters: Mapping[str, object]) -> Answer[ProviderTrust]:
    """Report the pinned trust policy, and check one release against it (`#172`).

    Reads and reports. Nothing here installs, and nothing removes a target: a
    revoked key blocks new installs and leaves what is running alone
    (`REQ-812`), and there is no argument shape that says otherwise.

    Without `--manifest` the policy is reported and `accepted` stays absent.
    Absent is not `false`: nothing was checked, and saying "not accepted" about
    a release nobody named would be a verdict on nothing.
    """
    policy = release.pinned_policy()
    view = ProviderTrust(
        policy_id=policy.policy_id,
        policy_schema_version=policy.schema_version,
        signature_subject=policy.signature_subject,
        allowed_publishers=sorted(policy.allowed_publishers),
        allowed_keys=sorted(policy.allowed_keys),
        allowed_repositories=sorted(policy.allowed_repositories),
        revoked_keys=sorted(policy.revoked_keys),
        minimum_sequence=policy.minimum_sequence,
        pinned_releases=[
            PinnedRelease(
                provider_id=pin.provider_id,
                repository=pin.repository,
                artifact_digest=pin.artifact_digest,
            )
            # Sorted rather than file order: the report is read by a machine,
            # and a set has no order to preserve honestly.
            for pin in sorted(
                policy.pinned_releases,
                key=lambda pin: (pin.provider_id, pin.artifact_digest),
            )
        ],
        # The shipped policy pins no bytes and allows no publisher: every
        # install goes through an attested build bound by `provider fetch`.
        # Leaving these out reported an empty policy for a machine that trusts
        # seven repositories, and this function already reads them below.
        build_attestations=[
            TrustedBuildAttestation(
                repository=rule.repository,
                signer_workflow=rule.signer_workflow,
                verified_publisher=rule.verified_publisher,
            )
            for _, rule in sorted(policy.build_attestations.items())
        ],
    )

    given = parameters.get("manifest")
    if given is None:
        return Answer(view)

    place = Path(str(given)).expanduser()
    if not place.is_file():
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "no release manifest sits at that path",
            details={"manifest": redact_home(place)},
        )
    manifest = release.parse_manifest(place.read_text("utf-8"))
    known_sequence = 0
    registry = configured_path()
    if registry.exists():
        with closing(open_readonly(registry)) as connection:
            known_sequence = provider_releases.observed_minimum_sequence(
                connection, manifest.provider_id
            )
    if manifest.repository in policy.build_attestations:
        verdict = release.verify_attested(
            manifest,
            policy,
            known_sequence=known_sequence,
            observed_digest="",
            observed_size=0,
            platform=release.current_platform(),
        )
    else:
        verdict = release.verify(manifest, policy, known_sequence=known_sequence)
    return Answer(
        view.model_copy(
            update={
                "accepted": verdict.accepted,
                "known_sequence": known_sequence,
                "refusals": [
                    ReleaseRefusal(code=item.code, summary=item.summary, details=item.details)
                    for item in verdict.refusals
                ],
            }
        )
    )


def provider_fetch(parameters: Mapping[str, object]) -> Answer[ProviderBoundRelease]:
    """Materialise a closed release manifest from attested OpenNetwork bytes.

    Writes the artifact and the bound JSON. Install still plans against that
    file; this command does not change a harness target.
    """
    harness = _harness_of(parameters)
    tag = str(parameters.get("tag") or "") or None
    directory_raw = str(parameters.get("directory") or "")
    artifact_raw = str(parameters.get("artifact") or "")
    bundle_raw = str(parameters.get("attestation-bundle") or "")
    bound = attested_bind.fetch(
        harness=harness,
        tag=tag,
        directory=Path(directory_raw).expanduser() if directory_raw else None,
        artifact=Path(artifact_raw).expanduser() if artifact_raw else None,
        attestation_bundle=Path(bundle_raw).expanduser() if bundle_raw else None,
    )
    return Answer(
        ProviderBoundRelease(
            harness_id=bound.harness_id,
            repository=bound.repository,
            tag=bound.tag,
            commit=bound.commit,
            provider_id=bound.provider_id,
            provider_version=bound.provider_version,
            protocol_version=bound.protocol_version,
            sequence=bound.sequence,
            artifact=redact_home(bound.artifact),
            manifest=redact_home(bound.manifest_path),
            artifact_digest=bound.artifact_digest,
            artifact_url=bound.artifact_url,
            trust_level=bound.trust_level,
        )
    )
