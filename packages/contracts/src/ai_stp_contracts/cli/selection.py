"""Selection: eligibility, proposals, the setup graph, composition, bundles,
conformance and provider trust.
"""

from typing import Annotated, Literal

from pydantic import ConfigDict, Field

from ai_stp_contracts.http import open_wire_object
from ai_stp_contracts.model import ContractModel
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import DIGEST_PATTERN
from ai_stp_foundation.harnesses import HarnessId


class EligibilityRefusal(ContractModel):
    """One mechanical constraint a candidate failed (`docs/contracts/eligibility-constraints.md`).

    `code` is the machine identity and `summary` is for a person: the text may
    be reworded, the code may not. A caller branching on the sentence would
    break the first time somebody improved the wording.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1

    #: The six families of `SPEC-006` REQ-601, in that requirement's own order.
    family: Literal["compatibility", "access", "trust", "license", "entitlement", "provider"]
    code: Annotated[str, Field(min_length=1)]
    summary: Annotated[str, Field(min_length=1)]

    #: The values that took part in the decision — a capability identifier, a
    #: declared range, a required permission. Never a secret and never the value
    #: of an environment variable.
    details: dict[str, str] = {}


class EligibilityNote(ContractModel):
    """One state worth saying that blocks nothing.

    A separate model rather than a refusal with a flag. A missing mandatory
    environment variable must not stop an install (`SPEC-001` REQ-111,
    `SPEC-008` REQ-816), and the cheapest way to keep that true is to make a
    note structurally incapable of being counted as a refusal.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    code: Literal["required_env_missing", "authorization_required", "credentials_required"]
    summary: Annotated[str, Field(min_length=1)]
    details: dict[str, str] = {}


class CandidateEligibility(ContractModel):
    """What the mechanical stage decided about one candidate, and why.

    Two booleans because there are two questions. `admissible` is "may this be
    installed" and a trust lane never softens it; `auto_selectable` is "may this
    be chosen without asking", and `experimental` answers no to that even with
    consent (`SPEC-006` REQ-603). A single flag would have made a consented
    unverified object silently installable, which is the failure `ADR-0016`
    exists to prevent.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    stable_id: Annotated[str, Field(min_length=1)]
    revision_id: Annotated[str, Field(min_length=1)]
    lane: Literal["authoritative", "local_owner_or_pinned", "experimental"]
    lane_reason: Annotated[str, Field(min_length=1)]
    admissible: bool
    auto_selectable: bool
    refusals: list[EligibilityRefusal] = []
    notes: list[EligibilityNote] = []


class EligibilityReport(ContractModel):
    """Every candidate assessed against one target (`SPEC-006` REQ-601, REQ-621).

    The target is echoed back because a verdict without the facts it was reached
    from cannot be checked. `no_candidate` is an honest state here rather than
    an error: `SPEC-006` says so explicitly, and an empty admissible list with
    the reasons beside it is what makes it honest.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    harness_id: HarnessId
    harness_version: str = ""
    os: Annotated[str, Field(min_length=1)]
    arch: Annotated[str, Field(min_length=1)]

    #: The capability dictionary this run compared against, versioned apart from
    #: the passport schema exactly as the tag dictionary is.
    capability_vocabulary_version: Annotated[str, Field(min_length=1)]

    #: Capabilities the target was found to have. Named so a refusal for a
    #: missing one can be checked rather than taken on trust.
    capabilities: list[str] = []

    candidates: list[CandidateEligibility] = []
    admissible_count: Annotated[int, Field(ge=0)]
    auto_selectable_count: Annotated[int, Field(ge=0)]


class EligibilityMatrix(ContractModel):
    """One eligibility report per supported harness, whether or not it is here.

    `EligibilityReport` answers for the harness that was named, which is the
    right answer to "compose this for Codex" and the wrong one to "where does
    this object fit". Asked the second way with only the first available, an
    agent answered with the harness its own session happened to run in, and a
    portable skill acquired that `harness_id` on the way into a draft passport
    (`#380`).

    Every row of the closed harness set is present. A harness absent from this
    machine is a row with a reason, never a missing row: whether an object fits
    Pi is a property of the object, and deleting the question because nobody
    installed Pi answers a different one. Installation is an input to *running*
    something, not to whether it may be composed.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1

    #: Ordered by harness id so two runs of the same machine compare directly.
    harnesses: list[EligibilityReport] = []

    #: The harness set this answer covers, echoed so a caller can tell a
    #: narrowed request from a complete one without diffing the rows.
    requested: list[HarnessId] = []


class ProposalMember(ContractModel):
    """One exact reference inside a proposal, and why it was allowed in.

    The lane travels with the member rather than being recomputed when the
    proposal is confirmed. `REQ-616` wants the trace to record the lane of each
    candidate, and a lane derived later could differ from the one the user was
    actually shown.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    stable_id: Annotated[str, Field(min_length=1)]
    version: Annotated[str, Field(pattern=r"^\d+\.\d+$")]
    passport_digest: Annotated[str, Field(min_length=1)]
    lane: Literal["authoritative", "local_owner_or_pinned", "experimental"]
    lane_reason: Annotated[str, Field(min_length=1)]

    #: How an unverified candidate was allowed in, when one was. Empty where no
    #: consent was needed — `REQ-627` requires the source to reach the trace.
    consent_source: str = ""

    #: The bounded overlay's revision, when this member is derived (`REQ-605`).
    overlay_revision_id: str = ""


class ProposalView(ContractModel):
    """One short-lived composition proposal (`ADR-0027`).

    Showing this creates nothing. `state` distinguishes the four situations a
    caller must act on differently — still open, already confirmed, cancelled,
    or expired — because "not open" would leave all three failures looking the
    same.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    proposal_id: Annotated[str, Field(min_length=1)]
    project_id: Annotated[str, Field(min_length=1)]
    harness_id: HarnessId
    state: Literal["open", "confirmed", "cancelled", "expired"]

    #: The digest of the input this proposal is bound to. Confirming recomputes
    #: it, so a caller can see in advance what would make the answer stale.
    snapshot: Annotated[str, Field(min_length=1)]
    members: list[ProposalMember] = []
    created_at: Annotated[str, Field(min_length=1)]
    expires_at: Annotated[str, Field(min_length=1)]

    #: Set once confirmed. Present so a repeat of a confirmation is visibly the
    #: same version rather than a new one (`REQ-624`).
    confirmed_stable_id: str | None = None
    confirmed_version: str | None = None


class ProposalSession(ContractModel):
    """What one project-and-harness pair currently has open and selected."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    project_id: Annotated[str, Field(min_length=1)]
    harness_id: HarnessId
    policy_version: Annotated[str, Field(min_length=1)]
    proposals: list[ProposalView] = []

    #: The proposal the answering call recorded, when it recorded one.
    #: `select propose` answers with the whole session, and several proposals
    #: may be open for one pair at once; a caller that took the first row
    #: confirmed an older proposal and installed nothing. `select session`
    #: records none and leaves this empty.
    proposal_id: str | None = None

    #: The version selected for this pair, if one has been confirmed. Selected
    #: and installed are different facts: `pending_install` is the ordinary
    #: window between them, not a drift.
    selected_stable_id: str | None = None
    selected_version: str | None = None
    selected_state: Literal["pending_install", "installed"] | None = None


class ConfirmationView(ContractModel):
    """The single object a confirmation froze (`REQ-623`).

    `created` separates "this call made it" from "this call found it already
    made". `REQ-624` makes a repeat a success rather than a conflict, and a
    caller still has to be able to tell the two apart.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    stable_id: Annotated[str, Field(min_length=1)]
    version: Annotated[str, Field(pattern=r"^\d+\.\d+$")]
    revision_id: Annotated[str, Field(min_length=1)]
    state: Literal["pending_install", "installed"]
    created: bool

    #: The recorded reasons behind this version (`REQ-616`). Written in the same
    #: transaction as the version itself, so an answer that has one has both.
    trace: dict[str, JsonValue] = {}


class GraphReference(ContractModel):
    """One exact edge inside a closure (`docs/contracts/setup-graph.md`).

    All three fields are required together. A digest without a version cannot be
    looked up and a version without a digest cannot be verified, so either alone
    would be half a statement the resolver could still act on.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    stable_id: Annotated[str, Field(min_length=1)]
    version: Annotated[str, Field(pattern=r"^\d+\.\d+$")]
    passport_digest: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]

    #: Which node stated this requirement. Empty for a root, so a refusal can
    #: name the path a bad reference arrived by rather than only the reference.
    required_by: str = ""


class GraphNode(ContractModel):
    """One exact version the closure holds."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    stable_id: Annotated[str, Field(min_length=1)]
    version: Annotated[str, Field(pattern=r"^\d+\.\d+$")]
    passport_digest: Annotated[str, Field(min_length=1)]
    revision_id: Annotated[str, Field(min_length=1)]

    #: Shortest distance from a root. Descriptive only: the order below is
    #: topological, and depth would order two independent chains arbitrarily.
    depth: Annotated[int, Field(ge=0)]
    requires: list[GraphReference] = []


class GraphRefusal(ContractModel):
    """One reason a closure could not be resolved."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    code: Annotated[str, Field(min_length=1)]
    summary: Annotated[str, Field(min_length=1)]
    details: dict[str, str] = {}


class SetupGraph(ContractModel):
    """The exact dependency closure of a composition (`SPEC-006` REQ-605).

    `nodes` is empty whenever `resolved` is false, and that is deliberate:
    `REQ-608` says an unresolved closure blocks, and returning the part that did
    resolve would read as "almost composed". A composition missing a dependency
    is not composed at all.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    resolved: bool
    nodes: list[GraphNode] = []

    #: Install order, a dependency before whatever requires it. Total: two nodes
    #: that could go in either order always go in the same one.
    order: list[str] = []
    refusals: list[GraphRefusal] = []

    #: The declared bounds. Returned so a caller can tell a closure that reached
    #: one from a complete closure, which a truncated answer could not.
    max_depth: Annotated[int, Field(ge=1)]
    max_nodes: Annotated[int, Field(ge=1)]


class CompositionConflict(ContractModel):
    """One reason a composition cannot be built (`SPEC-006` REQ-606).

    Nothing resolves it automatically. `REQ-626` forbids semantic merging,
    equivalent selection and composition optimisation, so this is a statement
    for a person to act on rather than a step in a repair.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    code: Annotated[str, Field(min_length=1)]
    summary: Annotated[str, Field(min_length=1)]
    details: dict[str, str] = {}


class CompositionChoice(ContractModel):
    """One component in the composition, with the lane it came in on."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    stable_id: Annotated[str, Field(min_length=1)]
    version: Annotated[str, Field(pattern=r"^\d+\.\d+$")]
    lane: Literal["authoritative", "local_owner_or_pinned", "experimental"]
    reason: Annotated[str, Field(min_length=1)]


class CompositionRejection(ContractModel):
    """One candidate considered and not chosen, with a stable reason."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    stable_id: Annotated[str, Field(min_length=1)]
    version: Annotated[str, Field(pattern=r"^\d+\.\d+$")]
    reason: Annotated[str, Field(min_length=1)]


class ConversionEntry(ContractModel):
    """What one component becomes on the target harness, and what is lost.

    `losses` names each one. A report that says something was lost without
    saying what cannot be acted on, and `REQ-609` asks for a loss-aware report
    rather than a loss-counting one.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    stable_id: Annotated[str, Field(min_length=1)]

    #: Empty when the passport declares no kind. Allowed rather than rejected:
    #: such a passport is malformed and the report is where a person finds that
    #: out, so refusing to render it would hide the thing they need to see.
    component_type: str = ""

    #: Where it lands natively. Empty exactly when the state is `unsupported`.
    native_surface: str = ""
    projection_kind: Literal["marketplace", "plugin", "native_files", "package"] = "native_files"
    state: Literal["complete", "partial", "unsupported"]
    losses: list[str] = []


class CompositionReports(ContractModel):
    """The composition and conversion reports a bundle must carry (`REQ-609`).

    Both, always, and together: the first explains what is in the composition
    and the second what survives translation to the harness. A bundle carrying
    one of them would answer half the question a person has before installing.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    harness_id: HarnessId

    #: True when a conflict blocks. `REQ-608`: an unresolved conflict produces
    #: no package, so this is the field a caller branches on before building.
    blocked: bool
    chosen: list[CompositionChoice] = []
    rejected: list[CompositionRejection] = []
    conflicts: list[CompositionConflict] = []

    #: Only from the closed set `REQ-625` allows. Naming the whole set every
    #: time would prove nothing about what actually happened.
    operations: list[str] = []

    conversion: list[ConversionEntry] = []
    conversion_complete: bool = True


class BundleFile(ContractModel):
    """One record in the bundle's file manifest."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    path: Annotated[str, Field(min_length=1)]
    digest: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    byte_length: Annotated[int, Field(ge=0)]

    #: `0644` or `0755` and nothing else. Any other mode is a permissions
    #: decision a bundle has no business making on the user's behalf.
    mode: Literal[420, 493]
    owner: str = ""


class BundleRefusal(ContractModel):
    """One reason a bundle could not be compiled."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    code: Annotated[str, Field(min_length=1)]
    summary: Annotated[str, Field(min_length=1)]
    details: dict[str, str] = {}


class HarnessBundle(ContractModel):
    """A compiled bundle, or every reason it could not be compiled.

    `digest` and `files` are empty exactly when `compiled` is false. A manifest
    beside a list of refusals would read as "almost built", and a bundle holding
    a file that was not accepted is not installable at all.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    compiled: bool
    harness_id: HarnessId
    #: The projection scope the package was compiled for: the harness home
    #: (`global`) or a workspace root (`project`), chosen at `select bundle`.
    target_scope: Literal["global", "project", "user_root"] = "global"
    bundle_format: Literal["ai-stp-bundle/1", "ai-stp-bundle/2"] = "ai-stp-bundle/1"

    #: Domain-separated over the manifest, which covers every file by content.
    #: Nothing that varies between machines is inside it — no build time, no
    #: local path — so two machines compiling one input agree byte for byte.
    digest: Annotated[str, Field(pattern=r"^(|sha256:[0-9a-f]{64})$")] = ""

    #: SHA-256 of the literal ``ai-stp-bundle/1`` ZIP bytes. Empty for a
    #: refused compilation, just like ``digest``.
    artifact_digest: Annotated[str, Field(pattern=r"^(|sha256:[0-9a-f]{64})$")] = ""
    byte_length: Annotated[int, Field(ge=0)] = 0
    builder_version: Annotated[str, Field(min_length=1)]
    protocol_version: Annotated[int, Field(ge=1)]
    files: list[BundleFile] = []
    refusals: list[BundleRefusal] = []

    #: Declared bounds, returned so a bundle that reached one is
    #: distinguishable from a complete one.
    max_files: Annotated[int, Field(ge=1)]
    max_file_bytes: Annotated[int, Field(ge=1)]
    max_bundle_bytes: Annotated[int, Field(ge=1)]


class ConformanceCase(ContractModel):
    """One conformance check and what it decided.

    `detail` names what was wanted and what was got. The audience for a failure
    here is somebody writing a provider against a protocol they cannot see, and
    "failed" alone is nothing to work from.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    name: Annotated[str, Field(min_length=1)]
    passed: bool
    detail: Annotated[str, Field(min_length=1)]

    #: Whose obligation this case is about: `provider` for the protocol,
    #: `consumer` for reach. A provider declaring a component kind this compiler
    #: has no route for has met every obligation v3 places on it, so `conforms`
    #: is decided by provider-subject cases alone. Reporting a consumer gap as
    #: non-conformance names the wrong party in the one field people read.
    subject: str = "provider"

    #: Whether the run actually put this case to the test. False is not a
    #: failure and not a pass — it is "the conditions for asking were not there",
    #: which is a third thing and used to be written as `passed: true` with the
    #: explanation in prose. A machine reading the boolean saw coverage that did
    #: not happen, and prose is not where a machine looks.
    exercised: bool = True


class ConformanceReport(ContractModel):
    """Whether one provider conforms to the frozen protocol (`SPEC-008` REQ-802).

    `reported_version` is kept beside `protocol_version` rather than compared
    away: a provider announcing a version this build does not speak is a
    different situation from one that speaks it and fails a case, and the two
    are fixed by different people.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    harness_id: HarnessId
    protocol_version: Annotated[int, Field(ge=1)]
    reported_version: Annotated[int, Field(ge=0)]
    conforms: bool
    cases: list[ConformanceCase] = []


class ProviderNetworkCapability(ContractModel):
    """The observed network boundary on this exact machine, for both protocols.

    The report never turns absence into support. Evidence names the launcher
    version/digest and transport probes when enforcement is observed; an
    unavailable result remains actionable machine data rather than a log line.

    It answered for protocol v2 alone until 2026-08-27, and v2 is not what
    anything installs with. `#416` allows a **v3** local phase to run with no
    network-denying launcher on a platform that has none, gated on a trusted
    release or an explicit `--unverified-provider` — deliberate security debt,
    and this is the one output someone would check to find it. Describing only
    v2 meant the marker pointed at a protocol nobody runs.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1

    #: The protocol the *enforcement* fields below describe. Unchanged: v2 gets
    #: no exception anywhere, which is what `#423` decided for `target status`,
    #: `diff` and every spawn outside an install plan.
    protocol_version: Literal[2] = 2
    os_name: Annotated[str, Field(min_length=1)]
    network_enforcement: Literal["enforced", "unavailable"]
    launcher_id: str = ""
    evidence: Annotated[list[str], Field(min_length=1)]
    local_actions_available: bool

    #: What a **v3** local phase does on this machine, which is the question the
    #: fields above cannot answer.
    #:
    #: - `network_denied` — a launcher was proved and the phase runs inside it.
    #: - `unisolated_by_trust` — no launcher exists on this platform, so the
    #:   phase runs with the network reachable, permitted only by one of the
    #:   reasons below. This is the debt `#416` accepted, stated where it can be
    #:   found rather than left to be inferred from a v2 answer.
    #: - `refused` — a launcher could exist here and does not, so nothing runs.
    #:   Distinct from the line above on purpose: a missing dependency and a
    #:   missing capability of the operating system are different facts with
    #:   different repairs, and `unisolated_local_phase` refuses to be built on
    #:   a platform that could isolate.
    v3_local_phase: Literal["network_denied", "unisolated_by_trust", "refused"]

    #: The reasons that would permit an unisolated phase, empty unless
    #: `v3_local_phase` is `unisolated_by_trust`. Named rather than counted: a
    #: caller deciding whether to proceed needs to know it must supply one.
    v3_local_phase_reasons: list[str] = []


class ReleaseRefusal(ContractModel):
    """One reason a provider release is not acceptable."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    code: Annotated[str, Field(min_length=1)]
    summary: Annotated[str, Field(min_length=1)]
    details: dict[str, str] = {}


class PinnedRelease(ContractModel):
    """One exact provider artifact this machine approved, and who may deliver it.

    Reported as all three fields because that is what the policy decides on. A
    digest alone would describe a rule the machine does not apply: the same
    approved bytes presented under another provider identity are refused.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    provider_id: Annotated[str, Field(min_length=1)]
    repository: Annotated[str, Field(min_length=1)]
    artifact_digest: Annotated[str, Field(min_length=1)]


class TrustedBuildAttestation(ContractModel):
    """One repository whose attested builds this machine will bind (`ADR-0121`).

    Reported with the signer workflow, not just the repository: the rule is
    satisfied by an attestation naming that exact workflow, so a report giving
    only the repository would describe a looser rule than the one enforced.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    repository: Annotated[str, Field(min_length=1)]
    signer_workflow: Annotated[str, Field(min_length=1)]
    verified_publisher: bool = False


class TrustedIndexPublisher(ContractModel):
    """One PyPI project whose PEP 740 publisher this machine will bind (`ADR-0141`)."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    pypi_project: Annotated[str, Field(min_length=1)]
    repository: Annotated[str, Field(min_length=1)]
    workflow: Annotated[str, Field(min_length=1)]
    environment: Annotated[str, Field(min_length=1)]
    verified_publisher: bool = False


class ProviderTrust(ContractModel):
    """What this machine will accept from a provider, and why (`SPEC-008` REQ-811).

    The policy is reported as it is pinned, not as a manifest describes itself.
    An empty `allowed_keys` accepts nothing and is the correct state before the
    owner pins a real signing key — an invented key would be a trust anchor
    nobody chose.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    policy_id: Annotated[str, Field(min_length=1)]
    policy_schema_version: Annotated[int, Field(ge=1)]
    signature_subject: Annotated[str, Field(min_length=1)]
    allowed_publishers: list[str] = []
    allowed_keys: list[str] = []
    allowed_repositories: list[str] = []
    revoked_keys: list[str] = []
    minimum_sequence: Annotated[int, Field(ge=0)]

    #: Exact releases this machine approved on the Ed25519 path, bound to the
    #: provider and repository that may present them. An approved-bytes list
    #: that approved everything when empty would not be a list anybody could
    #: rely on, so empty accepts nothing *on that path*. `latest` is forbidden
    #: by the contract.
    pinned_releases: list[PinnedRelease] = []

    #: Repositories whose attested builds may be bound by `provider fetch`
    #: without a signed manifest. This is the other half of the answer, and on
    #: the shipped policy it is the only populated one: `pinned_releases` and
    #: `allowed_publishers` are both empty there while seven attested
    #: repositories are trusted. Reporting the empty halves alone told an agent
    #: that nothing was installable, which was the opposite of the truth.
    build_attestations: list[TrustedBuildAttestation] = []

    #: PyPI projects whose PEP 740 publisher triple may bind a wheel. Empty is
    #: the rollback: every index-delivered provider stays `unverified`.
    index_publishers: list[TrustedIndexPublisher] = []

    #: Present only when a manifest was given to check. `null` means the policy
    #: was reported and nothing was verified, which is not the same as accepted.
    accepted: bool | None = None
    known_sequence: Annotated[int, Field(ge=0)] | None = None
    refusals: list[ReleaseRefusal] = []


class ProviderBoundRelease(ContractModel):
    """Closed release manifest bound from attested OpenNetwork bytes (`SPEC-008` REQ-847).

    The JSON is a local binding record, not a second trust anchor. Trust remains
    the pinned `build_attestations` rule plus GitHub attestation of exact bytes.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    harness_id: Annotated[str, Field(min_length=1)]
    repository: Annotated[str, Field(min_length=1)]
    tag: Annotated[str, Field(min_length=1)]
    commit: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    provider_id: Annotated[str, Field(min_length=1)]
    provider_version: Annotated[str, Field(min_length=1)]
    protocol_version: Annotated[int, Field(ge=1)]
    sequence: Annotated[int, Field(ge=0)]
    artifact: Annotated[str, Field(min_length=1)]
    manifest: Annotated[str, Field(min_length=1)]
    artifact_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    artifact_url: Annotated[str, Field(min_length=1)]
    trust_level: Literal["verified_publisher", "build_attested"]
