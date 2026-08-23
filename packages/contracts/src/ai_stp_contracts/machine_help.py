"""Machine help: the contract between the agent and the CLI (issue #72).

`docs/agent/machine-help.md` makes this the source the canonical Skill reads
instead of copying flags by hand, and `SPEC-011` REQ-1106 forbids the Skill from
restating parameters. That makes the shape of machine help a machine boundary of
the same kind as `/v1` — five harness projections depend on it — so it is
declared here, published into `schemas/v1` and held by the same gate, rather
than living inside the application that happens to render it.

The split between the two introspection commands is deliberate:

- `capabilities` answers **what this installation can do right now** — versions,
  supported harnesses, whether the catalogue and sync are switched on. It is a
  cheap optional orientation call; the canonical Skill starts with `doctor` and
  `help --agent`.
- `help --agent` answers **what commands and fields exist**. It is the full
  registry and it is larger.

Both are rendered from one registry inside the CLI, so they cannot disagree
about which commands exist.
"""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_stp_assurance import AuthorAttestation as AssuranceAuthorAttestation
from ai_stp_contracts.auth import AccountId, DeviceId, PublicKey
from ai_stp_contracts.catalog import (
    CatalogTrust,
    ComponentSummary,
    PublicLifecycle,
    SetupSummary,
    VersionListEntry,
)
from ai_stp_contracts.http import Timestamp, open_wire_object
from ai_stp_contracts.publication import ObjectKind as PublicationObjectKind
from ai_stp_contracts.publication import PublicationPlanResponse
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import DIGEST_PATTERN
from ai_stp_foundation.errors import ErrorHandling, ExitClass
from ai_stp_foundation.harnesses import HarnessId
from ai_stp_passports.versions import ComponentType

#: What a command does to state, and therefore whether the agent must ask first
#: (`SPEC-011` REQ-1103/REQ-1104, `docs/agent/interaction-policy.md`).
#:
#: - `read` — observes only; never needs a question;
#: - `plan` — computes an immutable plan and has no effect of its own;
#: - `apply` — carries out a plan and needs the user's explicit decision;
#: - `destructive` — removes data, a target or a backup, and needs a decision of
#:   its own even when the caller already approved the surrounding work.
type MutabilityClass = Literal["read", "plan", "apply", "destructive"]

#: How a caller expresses the user's decision. The CLI never asks in the
#: terminal — a decision arrives as an explicit flag or as the exact digest of a
#: stored plan, and its absence is answered with `needs_user_action` rather than
#: a prompt. That keeps one execution path for a human and for an agent, and
#: leaves nothing to hang in CI or in a container.
type ConfirmationKind = Literal["none", "explicit_flag", "plan_digest"]

type ParameterKind = Literal["option", "argument"]
type ParameterType = Literal["string", "boolean", "integer"]

#: Command paths are the machine identity of a command: `["config", "show"]`.
type CommandPath = Annotated[list[str], Field(min_length=1, max_length=4)]


class CommandParameter(BaseModel):
    """One parameter of one command, as the agent must supply it."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    name: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]*$")]
    kind: ParameterKind
    value_type: ParameterType
    required: bool

    #: Whether the option may be given more than once, and therefore whether the
    #: agent should pass a list. Declared rather than defaulted: every property
    #: of an open wire object is required, so a default here would let the model
    #: accept a document the published schema rejects.
    repeatable: bool

    summary: str

    #: Closed value set when the parameter is an enum. Empty means the value
    #: is free-form. This stays a list in the wire contract so an agent never
    #: has to extract valid values from prose.
    choices: list[str] = []


class CommandParameterRule(BaseModel):
    """A cross-parameter invocation rule that consumers must not parse from prose."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    kind: Literal["exactly_one", "required_when"]
    parameters: Annotated[list[str], Field(min_length=1)]
    when_parameter: str = ""
    when_values: list[str] = []


class CommandDescriptor(BaseModel):
    """Everything the agent needs to invoke one command correctly.

    A command that does not work is absent rather than described: the Skill is
    told not to guess flags, so a declared-but-unimplemented command would let
    it plan a step around something that cannot run.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    path: CommandPath
    summary: str
    mutability: MutabilityClass
    confirmation: ConfirmationKind
    parameters: list[CommandParameter]
    parameter_rules: list[CommandParameterRule] = []

    #: `urn:ai-stp:schema:v1:<name>` of the payload this command puts in the
    #: envelope's `data`, when one is published.
    result_schema: str | None

    #: Commands that are sensible to run next, as their paths joined by a space.
    #: Advice, never a permission: each still enforces its own confirmation.
    next_actions: list[str]

    @model_validator(mode="after")
    def validate_parameter_rules(self) -> Self:
        names = {item.name for item in self.parameters}
        for rule in self.parameter_rules:
            if not set(rule.parameters) <= names:
                raise ValueError("parameter rule names an undeclared parameter")
            if rule.kind == "exactly_one":
                if len(rule.parameters) < 2 or rule.when_parameter or rule.when_values:
                    raise ValueError("exactly_one requires two or more parameter names only")
            elif (
                rule.when_parameter not in names
                or not rule.when_values
                or rule.when_parameter in rule.parameters
            ):
                raise ValueError("required_when has an invalid condition")
        return self


class MachineErrorDescriptor(BaseModel):
    """One stable failure and the first disposition an agent should take."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    code: Annotated[str, Field(pattern=r"^AI_STP_[A-Z0-9]+(?:_[A-Z0-9]+)*$")]
    exit_class: ExitClass
    handling: ErrorHandling
    description: Annotated[str, Field(min_length=1)]


class MachineHelp(BaseModel):
    """The whole command registry, rendered for an agent."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    cli_version: Annotated[str, Field(min_length=1)]

    #: Options every command accepts. Declared once rather than repeated on each
    #: descriptor: `--json` is not a property of any one command, and repeating
    #: it would make the registry look like it varies when it does not.
    global_options: Annotated[list[CommandParameter], Field(min_length=1)]

    commands: Annotated[list[CommandDescriptor], Field(min_length=1)]
    error_codes: Annotated[list[MachineErrorDescriptor], Field(min_length=1)]


class Capabilities(BaseModel):
    """What this installation can do right now.

    Deliberately not a copy of the registry: it carries the few facts that
    decide whether a later call is even worth making. `command_paths` is the
    index into `help --agent`, not a substitute for it.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    cli_version: Annotated[str, Field(min_length=1)]

    #: The `/v1` wire major this build speaks. An agent comparing it against a
    #: server can tell a version mismatch from a missing feature.
    wire_schema_version: Literal[1] = 1

    supported_harnesses: Annotated[list[HarnessId], Field(min_length=1)]
    catalog_enabled: bool
    sync_enabled: bool
    command_paths: Annotated[list[str], Field(min_length=1)]


class SyncPreview(BaseModel):
    """A read-only decision over the local heads of one syncable entity."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    stable_id: Annotated[str, Field(min_length=1)]
    state: Literal[
        "up_to_date",
        "fast_forward",
        "merge_ready",
        "conflict",
        "manual_resolution",
    ]
    head_revision_ids: Annotated[list[str], Field(min_length=1)]
    common_ancestor_revision_id: str | None
    candidate_revision_id: str | None
    #: The head the server last named in a refusal this device stored, when the
    #: device does not hold it. Null whenever local heads are the whole story.
    server_head_revision_id: str | None

    #: JSON Pointer paths only. Values remain in the owner-only registry and
    #: never enter a generic command envelope or log by accident.
    affected_fields: list[str] = Field(default_factory=list)


class SyncPushView(BaseModel):
    """Durable outcome of pushing one exact local revision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    stable_id: Annotated[str, Field(min_length=1)]
    processed_events: Annotated[int, Field(ge=1)]
    local_revision_id: Annotated[str, Field(min_length=1)]
    event_id: Annotated[str, Field(min_length=8)]
    remote_revision_id: Annotated[str, Field(min_length=1)]
    state: Literal["accepted", "rejected", "conflict", "superseded"]
    server_head_revision_id: str | None
    conflict_fields: list[str] = Field(default_factory=list)
    #: The identity the account already holds, when this push was refused for
    #: carrying a second one of a kind that admits exactly one. Without it the
    #: refusal is correct and the next move is unnameable.
    conflicting_entity_id: str | None


class SyncPullView(BaseModel):
    """One atomically applied page from the private account stream."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    received: Annotated[int, Field(ge=0)]
    applied: Annotated[int, Field(ge=0)]
    replayed: Annotated[int, Field(ge=0)]
    #: Events the caller named and this pull walked past without applying. An
    #: abandoned revision is not a quiet outcome, so it is counted separately
    #: from `applied` and the ids are answered back.
    skipped: Annotated[list[str], Field(max_length=64)] = Field(default_factory=list)
    next_cursor: str | None


#: Primary setup state (`SPEC-011`, states section). `doctor` reports it in the
#: body and still exits `0`: an installation that is merely not configured yet
#: is a normal outcome, not a failure, and answering non-zero would make the
#: first run after installation look broken and break `set -e`.
type SetupState = Literal["ready", "needs_user_action", "partial", "failed"]


class DoctorCheck(BaseModel):
    """One thing `doctor` looked at."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    name: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$")]
    state: SetupState
    detail: str


class DoctorReport(BaseModel):
    """What `doctor` found.

    A report, not a verdict. `state` is the worst state among the checks, so a
    caller that reads one field still gets the truth.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    state: SetupState
    checks: Annotated[list[DoctorCheck], Field(min_length=1)]


class VersionReport(BaseModel):
    """Which build is running, and which contracts it speaks."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    cli_version: Annotated[str, Field(min_length=1)]
    wire_schema_version: Literal[1] = 1
    python_version: Annotated[str, Field(pattern=r"^\d+\.\d+\.\d+")]


class ConfigValue(BaseModel):
    """One effective configuration value and where it came from.

    `SPEC-011` REQ-1116 requires the effective value **and** its source, because
    "it is 20 because that is the default" and "it is 20 because you wrote 20"
    lead to different next actions. No secret is representable: the config
    carries none by contract (`docs/contracts/cli-config.md`).
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    path: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.]*$")]
    value: str | int | bool | list[str] | None
    source: Literal["default", "config_file", "command_argument"]


class ConfigReport(BaseModel):
    """The effective configuration, field by field."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    values: Annotated[list[ConfigValue], Field(min_length=1)]

    #: Absent until a file exists. Its absence is not an error: defaults are a
    #: complete configuration (`docs/contracts/cli-config.md`).
    config_path: str | None


#: Where a secret actually lives on this installation (`ADR-0058`). Reported
#: rather than assumed: a caller that believes a refresh token is encrypted at
#: rest when it is a file has been told something false, and the difference
#: changes what it is safe to do on a shared machine.
type CredentialStore = Literal["os_keyring", "file"]

#: Local view of one device identity. `revoked` is set locally by an explicit
#: reset and by a server answer once #75 can ask; it stops future cloud work and
#: leaves local reads alone (`SPEC-002` REQ-205).
type LocalDeviceState = Literal["active", "revoked"]


class DeviceIdentity(BaseModel):
    """This installation's device identity, as the CLI can see it offline.

    Created on first run without an account: the key proves which device a
    later sync event or attestation came from, and it exists before any cloud
    login. Only public material is representable — the private key has no field
    here and cannot be printed by construction.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    device_id: DeviceId
    public_key: PublicKey

    #: A short, human-comparable form of the public key, so a person can check
    #: the device list in the web against this machine without reading 43
    #: base64 characters.
    key_fingerprint: Annotated[str, Field(pattern=r"^[0-9a-f]{2}(:[0-9a-f]{2}){15}$")]

    created_at: Timestamp
    state: LocalDeviceState

    #: Where the private key is kept, and why that tier was chosen. Never
    #: silent: `ADR-0058` makes the tier part of the answer.
    credential_store: CredentialStore
    credential_store_detail: Annotated[str, Field(min_length=1)]

    #: Identities this installation has retired, oldest first. Kept and reported
    #: so a retired identifier cannot come back and so the account owner can
    #: match a device row they no longer recognise against this machine.
    retired_device_ids: list[DeviceId]


#: What this installation's relationship with the platform actually is
#: (`SPEC-011`, issue #75). Four values rather than a boolean, because the
#: repairs differ: `expired` is fixed by signing in again, `revoked` needs a new
#: device key as well (`SPEC-002` REQ-207), and `local_only` is not a problem at
#: all — the whole local contour works without an account.
type SessionState = Literal["local_only", "authenticated", "expired", "revoked"]


class PublicationPlanView(PublicationPlanResponse):
    """The wire publication plan returned unchanged through the CLI boundary."""


class PublicationSetMemberView(BaseModel):
    """One object inside a setup's publication, and why it is there.

    `role` is what separates the setup from the components it pins, and it is
    stated rather than inferred from `object_kind`: a set holds exactly one
    setup, and a reader deciding what becomes public should not have to work
    that out by counting.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1

    role: Literal["setup", "pinned_component"]
    object_kind: PublicationObjectKind
    stable_id: str
    version: Annotated[str, Field(min_length=3, max_length=32)]

    #: Absent when this member needs no plan because it is public already.
    #: Distinguished from a plan that exists and has not been confirmed: one is
    #: nothing left to do, the other is the whole of what confirm will do.
    plan_id: str = ""
    plan_hash: str = ""
    state: str = ""

    #: Public before this set existed. Confirm skips it rather than replanning
    #: it, and it is listed anyway so the set describes the whole graph.
    already_published: bool = False


class PublicationSetView(BaseModel):
    """Every plan one setup's publication needs, as a single decision.

    A setup cannot be published before the components it pins are, so a person
    publishing one had to publish each component first and confirm each hash
    separately. Locally the two are already one act — `setup import register`
    commits the component passports and the setup graph together or not at all —
    and this carries that same rule across the publication boundary
    (`ADR-0114`).

    The guarantee that survives is the one that matters: publication still takes
    an explicit confirmation of an exact hash. `set_digest` covers every plan in
    order, so confirming it is confirming all of them and nothing else.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1

    #: Over the ordered `(role, object_kind, stable_id, version, plan_hash)` of
    #: every member. Any difference — a member added, a plan replaced, an order
    #: changed — is a different digest and therefore a different decision.
    set_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]

    setup_stable_id: str
    setup_version: Annotated[str, Field(min_length=3, max_length=32)]

    #: Components first, the setup last. The order is the confirmation order,
    #: because a setup confirmed before its pins would be refused by the
    #: platform's own pin aggregate.
    members: Annotated[list[PublicationSetMemberView], Field(min_length=1)]

    #: `planned` until confirmed; `published` when every member is; `partial`
    #: when confirmation stopped part-way, which is a resumable state and not a
    #: failure — the members already published stay published.
    state: Literal["planned", "published", "partial"] = "planned"

    #: The earliest expiry among the plans. A set is only as fresh as its
    #: shortest-lived member, and reporting the latest would promise time the
    #: first member no longer has.
    expires_at: Timestamp | None = None


class AuthStatus(BaseModel):
    """Whether this installation currently holds cloud credentials.

    Distinct from `DeviceIdentity`: a device identity always exists, a session
    may not. Reporting them as one fact would make "no account yet" and "no
    device identity" indistinguishable, and their next actions differ.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1

    #: One field, not a boolean beside it: `signed_in` and a state can disagree,
    #: and then a caller has to decide which to believe.
    state: SessionState

    #: Present only while signed in. Absent is not an error: the whole local
    #: contour works without an account (`offline-capability.md`).
    account_id: AccountId | None

    #: When the stored access credential stops being usable, if one is held.
    expires_at: Timestamp | None

    #: Where a held credential is kept. Absent when none is held — naming a
    #: store for a secret that does not exist would suggest one does.
    credential_store: CredentialStore | None


class PassportView(BaseModel):
    """One local passport at its current head.

    A view, not the passport itself: the envelope and its facts are owned by
    `packages/passports` and `passport-envelope.md`. What this adds is the local
    position — which revision is current, and what it descends from — because an
    agent deciding whether to write needs to know what it would be writing on
    top of.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    #: Every passport kind, matching `ai_stp_passports.envelope.PassportKind`.
    #: One view rather than one per kind: they are the same shape — an identity,
    #: a position in a revision chain, and facts — and separate models would be
    #: the same fields maintained five times. The set is the *whole* set on
    #: purpose; a subset of it silently rejects a passport the envelope accepts,
    #: which is a failure this has already had twice.
    kind: Literal["developer", "device", "project", "component", "setup"]
    stable_id: Annotated[str, Field(min_length=1)]
    revision_id: Annotated[str, Field(min_length=1)]
    parent_revision_ids: list[str]
    created_at: Timestamp

    #: The owner as this installation records it. Before sign-in that is a
    #: locally minted identifier and not an account the platform knows
    #: (`ADR-0060`); `#75` transfers ownership as an ordinary revision.
    owner_id: AccountId

    #: Facts at this revision, exactly as the envelope holds them.
    facts: dict[str, JsonValue]


class ComponentPassportValidation(BaseModel):
    """Whether one local component head is complete enough to publish.

    This is a local structural verdict, not permission to write to the cloud.
    Publication still requires its own authenticated exact plan after the
    platform contract exists.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    stable_id: Annotated[str, Field(min_length=1)]
    revision_id: Annotated[str, Field(min_length=1)]
    for_publication: Literal[True] = True
    ready: bool
    missing_fields: list[str]
    invalid_fields: list[str]


class ComponentQualityCheck(BaseModel):
    """One deterministic authoring hint, never a verification result."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1] = 1
    code: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{2,63}$")]
    status: Literal["passed", "hint"]
    fields: list[Annotated[str, Field(min_length=1, max_length=64)]] = []
    message: Annotated[str, Field(min_length=1, max_length=240)]


class ComponentQualityDimension(BaseModel):
    """Mechanical checks grouped under one author-facing quality dimension."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1] = 1
    dimension: Literal["safety", "clarity", "reusability", "completeness", "actionability"]
    status: Literal["passed", "hint"]
    checks: Annotated[list[ComponentQualityCheck], Field(min_length=1)]

    @model_validator(mode="after")
    def status_matches_checks(self) -> Self:
        expected = "passed" if all(item.status == "passed" for item in self.checks) else "hint"
        if self.status != expected:
            raise ValueError("quality dimension status disagrees with its checks")
        if len({item.code for item in self.checks}) != len(self.checks):
            raise ValueError("quality check codes must be unique within a dimension")
        return self


class ComponentQualityReport(BaseModel):
    """Optional mechanical guidance separated from trust and publication readiness."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    profile_version: Literal["mechanical/1"] = "mechanical/1"
    stable_id: Annotated[str, Field(min_length=1)]
    revision_id: Annotated[str, Field(min_length=1)]
    component_type: ComponentType
    informational_only: Literal[True] = True
    affects_publication_readiness: Literal[False] = False
    affects_component_verified: Literal[False] = False
    affects_trust_lane: Literal[False] = False
    dimensions: Annotated[list[ComponentQualityDimension], Field(min_length=5, max_length=5)]

    @model_validator(mode="after")
    def all_dimensions_are_present_once(self) -> Self:
        expected = {"safety", "clarity", "reusability", "completeness", "actionability"}
        if {item.dimension for item in self.dimensions} != expected:
            raise ValueError("quality report must contain every dimension exactly once")
        return self


class ComponentPassportSuggestion(BaseModel):
    """One exact fact copied from named immutable evidence, awaiting confirmation."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    field: Annotated[str, Field(min_length=1, max_length=64)]
    value: JsonValue
    source_refs: Annotated[list[str], Field(min_length=1, max_length=8)]
    requires_confirmation: Literal[True] = True


class ComponentPassportSuggestions(BaseModel):
    """Read-only enrichment candidates for one exact component revision."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    stable_id: Annotated[str, Field(min_length=1)]
    revision_id: Annotated[str, Field(min_length=1)]
    suggestions: list[ComponentPassportSuggestion]
    unresolved_fields: list[str]


class DeviceApproval(BaseModel):
    """What a person must approve before a sign-in can complete (issue #75).

    Returned rather than waited on. `#72` fixed that the CLI never blocks for a
    human decision — a command that polled until someone walked to their browser
    would hang in CI and in a container, which is the same reason the sign-in is
    a device-code flow and not a loopback redirect. So this is the first half of
    the answer, and `auth login --await` is the second.

    No secret is representable here. The device code the client polls with is
    kept in the credential store, not published: it is the bearer of the
    pending authorization.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    provider: Literal["google", "github"]

    #: Typed by a human from a terminal into a browser.
    user_code: Annotated[str, Field(min_length=1)]

    verification_uri: Annotated[str, Field(min_length=1)]

    #: The same page with the code already filled in. Useless on a machine that
    #: cannot open a browser, which is why the plain pair above stays required.
    verification_uri_complete: Annotated[str, Field(min_length=1)]

    expires_in: Annotated[int, Field(ge=1)]

    #: Whether a browser was actually opened. Not an error when false — that is
    #: the normal case over SSH — but the agent needs to know whether to tell
    #: the user to open the address themselves.
    browser_opened: bool

    device_id: DeviceId


#: Which half of the catalogue an answer is about. Components and setups are
#: separate routes with separate cursors (`#71`), so a single call is about one
#: of them and saying which is not decoration.
type CatalogKind = Literal["component", "setup"]

#: Where an answer came from. `cache` is not a degraded `online`: it is a
#: statement about a moment in the past, and `checked_at` says which moment.
#: Presenting a cached answer as current is the failure `offline-capability.md`
#: forbids.
type AnswerSource = Literal["online", "cache"]


class CatalogSearchResult(BaseModel):
    """One page of public catalogue results, and where it came from."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    kind: CatalogKind
    source: AnswerSource

    #: When the platform actually answered. On a cached result this is in the
    #: past, and it is the field that stops the answer claiming to be current.
    checked_at: Timestamp

    items: list[ComponentSummary | SetupSummary]

    #: Results from the `experimental` lane, in their own section. `ADR-0016`
    #: keeps them out of the main list: an experimental candidate that appeared
    #: among authoritative ones would have been silently promoted.
    experimental: list[ComponentSummary | SetupSummary]

    #: Absent when there is no further page. Opaque: a client echoes it back and
    #: never constructs one.
    next_cursor: str | None


class CatalogObjectView(BaseModel):
    """One catalogue object with its published versions."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    kind: CatalogKind
    source: AnswerSource
    checked_at: Timestamp
    summary: ComponentSummary | SetupSummary

    #: Every offered version, newest first. Numbers are not contiguous by
    #: design: hiding a version does not free its number.
    versions: list[VersionListEntry]


class CatalogVersionView(BaseModel):
    """One exact published version and the passport it promises (issue #76).

    The digest travels with the passport because a client verifies one against
    the other: a passport offered under a digest that does not describe it is a
    truncated download or a substituted body, and both are refused rather than
    cached.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    kind: CatalogKind
    source: AnswerSource
    checked_at: Timestamp
    passport_digest: Annotated[str, Field(min_length=1)]
    lifecycle: PublicLifecycle
    trust: CatalogTrust
    published_at: Timestamp

    #: The passport itself, exactly as the catalogue published it. Kept as the
    #: document rather than re-modelled: its shape is owned by
    #: `passport-envelope.md`, and a second model here could drift from it.
    passport: dict[str, JsonValue]


class ProjectCandidate(BaseModel):
    """One directory that could be registered as a project (`SPEC-004`)."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1

    #: Rendered with the home directory folded away, like every reported path.
    root: Annotated[str, Field(min_length=1)]

    #: `project`, or `nested_repository` for a repository inside another one.
    #: A nested repository is reported so the user can see it and registered only
    #: on an explicit choice (REQ-410).
    kind: Literal["project", "nested_repository"]

    #: `new` covers an empty folder, an empty repository and a folder holding
    #: only documentation — none of them has anything to index yet (REQ-402).
    state: Literal["new", "established"]

    #: What identified it: manifest file names, `git`, or nothing.
    markers: list[str]

    #: Why it is classified this way, in words a caller can show a person.
    reason: Annotated[str, Field(min_length=1)]


class DiscoveryDiagnostic(BaseModel):
    """One path skipped while examining an explicit project discovery root."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    path: Annotated[str, Field(min_length=1)]
    code: Literal["excluded", "entry_limit", "symlink", "unreadable"]
    reason: Annotated[str, Field(min_length=1)]


class ProjectCandidates(BaseModel):
    """Everything found inside one directory the user named."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    discovery_root: Annotated[str, Field(min_length=1)]
    complete: bool
    candidates: list[ProjectCandidate]
    diagnostics: list[DiscoveryDiagnostic]


class IndexedFile(BaseModel):
    """One file the index knows about, described without keeping its content."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1

    #: Relative to the project root, POSIX form. No absolute path reaches a
    #: passport, and two machines indexing the same tree agree.
    path: Annotated[str, Field(min_length=1)]
    kind: Literal["manifest", "lock", "agent_surface", "source", "document", "config", "text"]
    language: str | None = None
    size_bytes: Annotated[int, Field(ge=0)]

    #: `None` when the file was too large to read; its size is still known.
    digest: str | None = None
    lines: int | None = None


class ExcludedPath(BaseModel):
    """One path left out of the index, and why."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    path: Annotated[str, Field(min_length=1)]
    reason: Annotated[str, Field(min_length=1)]


class ProjectIndex(BaseModel):
    """The bounded second-level index of one project root (`SPEC-004`).

    `state` is `partial` when a size, depth, entry or time bound was reached.
    Saying so is the point: a short answer that looks complete is worse than a
    complete answer that says where it stopped.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    root: Annotated[str, Field(min_length=1)]
    state: Literal["complete", "partial"]
    stopped_by: str | None = None
    files: list[IndexedFile]
    excluded: list[ExcludedPath]


class ToolInstallation(BaseModel):
    """The outcome of one managed install (`SPEC-014` REQ-1405, REQ-1410, REQ-1411).

    `action` is what happened, not what was attempted. `needs_user_action` means
    something outside the managed directory would have to change, and the plan
    says exactly what — `REQ-1410` forbids the agent obtaining a password to do
    it instead.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    tool_id: Annotated[str, Field(min_length=1)]
    version: Annotated[str, Field(min_length=1)]
    action: Literal["installed", "already_installed", "needs_user_action", "removed"]
    reason: Annotated[str, Field(min_length=1)]

    #: The exact path the tool is invoked by (`REQ-1404`). Never a bare name:
    #: the surrounding `PATH` is not a source of truth for a managed toolchain.
    binary: str | None = None

    #: Whether this could be carried out with no network (`REQ-1413`).
    offline_capable: bool = False

    #: Every path created or removed (`REQ-1411`). An uninstall reads this list
    #: rather than deciding what looks like ours.
    paths: list[str] = []

    #: Paths deliberately left alone, with the reason. A user's own file inside
    #: a tool directory is theirs.
    kept: list[str] = []


class NativeComponentProvenance(BaseModel):
    """Allowlisted origin evidence for one native discovery candidate."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    kind: Literal["filesystem", "github", "package"]
    state: Literal["local", "exact", "observed"]
    repository: (
        Annotated[
            str,
            Field(pattern=r"^https://github\.com/[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9_.-]+$"),
        ]
        | None
    ) = None
    revision: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")] | None = None
    subpath: Annotated[str, Field(min_length=1)] | None = None
    package_name: Annotated[str, Field(min_length=1)] | None = None
    package_version: Annotated[str, Field(min_length=1)] | None = None
    digest: Annotated[str, Field(pattern=r"^(?:sha1:[0-9a-f]{40}|sha256:[0-9a-f]{64})$")] | None = (
        None
    )
    evidence: list[Annotated[str, Field(min_length=1)]] = Field(default_factory=list)

    @model_validator(mode="after")
    def consistent_origin(self) -> Self:
        if self.kind == "github":
            if (
                self.state != "exact"
                or self.repository is None
                or not self.repository.startswith("https://github.com/")
                or self.revision is None
            ):
                raise ValueError("GitHub provenance requires an exact repository and revision")
        elif self.kind == "package":
            if (
                self.state != "observed"
                or self.package_name is None
                or any(
                    value is not None for value in (self.repository, self.revision, self.subpath)
                )
            ):
                raise ValueError("package provenance requires observed package identity only")
        elif self.state != "local" or any(
            value is not None
            for value in (
                self.repository,
                self.revision,
                self.subpath,
                self.package_name,
                self.package_version,
                self.digest,
            )
        ):
            raise ValueError("filesystem provenance may contain only local layout evidence")
        return self


class NativeDiscoveryDiagnostic(BaseModel):
    """A safe reason an optional provenance adapter could not classify input."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    code: Literal[
        "missing_manifest",
        "invalid_manifest",
        "unsupported_manifest",
        "invalid_record",
        "missing_source_entry",
        "bounded_limit",
    ]
    source: Annotated[str, Field(min_length=1)]
    reason: Annotated[str, Field(min_length=1)]


class ExternalSourceIdentity(BaseModel):
    """A parsed external source intent or separately proven exact identity."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1] = 1
    kind: Literal["published", "github", "github/exact", "local", "collection"]
    canonical: Annotated[str, Field(min_length=1, max_length=2048)]
    owner: str | None = None
    repository: str | None = None
    ref: str | None = None
    subpath: str | None = None
    selector: str | None = None
    local_path: str | None = None
    collection_owner: str | None = None
    collection_handle: str | None = None
    provenance_proven: bool = False


class ComponentScaffoldView(BaseModel):
    """One safely created component authoring template."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1] = 1
    component_type: Literal[
        "instruction", "skill", "mcp", "hook", "command", "agent", "plugin", "setting"
    ]
    component_name: Annotated[str, Field(min_length=1)]
    output: Annotated[str, Field(min_length=1)]
    byte_length: Annotated[int, Field(gt=0)]


class ComponentTemplateView(BaseModel):
    """A deterministic concrete projection of one authoring template."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1] = 1
    harness_id: Literal["claude-code", "codex", "pi", "opencode", "grok-build"]
    component_name: Annotated[str, Field(min_length=1)]
    component_root: Annotated[str, Field(min_length=1)]
    source_digest: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    rendered_digest: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    placeholders: list[str]
    content: Annotated[str, Field(max_length=65536)]


class NativeComponent(BaseModel):
    """One native component found on this machine (`SPEC-005` REQ-517).

    Reported without its content being read. `holds_secret` is decided from the
    path's *name*: opening a file to learn whether it holds a credential is the
    harm REQ-518 exists to prevent, so the flag says "named as one", never
    "contains one".
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    component_type: Literal[
        "instruction", "skill", "mcp", "hook", "command", "agent", "plugin", "setting"
    ]
    native_role: Literal["mcp_client_config", "mcp_server"] | None = None

    #: `None` for a cross-harness convention such as a project `AGENTS.md`,
    #: which belongs to no single harness.
    harness_id: str | None = None
    scope: Literal["global", "project"]
    candidate_id: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    layout_source: Annotated[str, Field(min_length=1)]
    source_path: Annotated[str, Field(min_length=1)]
    provenance: NativeComponentProvenance
    entry_points: list[Annotated[str, Field(min_length=1)]] = Field(default_factory=list)
    transport_capabilities: list[Literal["stdio", "http"]] = Field(
        default_factory=list[Literal["stdio", "http"]]
    )
    evidence_refs: list[Annotated[str, Field(min_length=1)]] = Field(default_factory=list)

    #: `None` when the entry could not be measured, which includes every
    #: directory. Discovery never opens a file to find out.
    byte_length: int | None = None
    holds_secret: bool = False
    reason: Annotated[str, Field(min_length=1)]


class NativeComponents(BaseModel):
    """Everything discovery found, and nothing it changed (`REQ-518`)."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1

    #: The project searched beside the global harness roots, when one was named.
    project: str | None = None
    components: list[NativeComponent]
    diagnostics: list[NativeDiscoveryDiagnostic] = Field(
        default_factory=list[NativeDiscoveryDiagnostic]
    )


class ConsentRecord(BaseModel):
    """One durable consent to unverified objects (`unverified-consent.md`).

    `fingerprint` is what the candidate required when the user agreed, and it is
    stored rather than recomputed: the whole mechanism is "does this now need
    more than it did then", which cannot be answered without the older answer.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    consent_id: Annotated[str, Field(min_length=1)]

    #: Two forms and no third. "Everything unverified, forever" does not exist.
    scope: Literal["publisher", "object_major"]
    target: Annotated[str, Field(min_length=1)]
    decided_by: Annotated[str, Field(min_length=1)]
    origin: Annotated[str, Field(min_length=1)]
    created_at: Annotated[str, Field(min_length=1)]
    revoked_at: str | None = None
    fingerprint: dict[str, JsonValue] = {}


class ConsentSummary(BaseModel):
    """Every consent still in force."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    records: list[ConsentRecord]


class RecordedVersion(BaseModel):
    """One immutable `X.Y` version (`SPEC-005` REQ-503, REQ-504).

    The number and the digest travel together because that pairing is the whole
    guarantee: one number stands for one hash, and an exact reference means
    something only while that holds.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    version: Annotated[str, Field(pattern=r"^\d+\.\d+$")]
    passport_digest: Annotated[str, Field(min_length=1)]
    revision_id: Annotated[str, Field(min_length=1)]
    created_at: Annotated[str, Field(min_length=1)]


class VersionLine(BaseModel):
    """Every recorded version of one object, and what comes next.

    `next_minor` is computed from what is stored rather than remembered, so two
    machines with the same history propose the same number. There is no
    `next_major`: `REQ-507` makes that a decision, and a field offering it would
    read as a suggestion to take it.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    stable_id: Annotated[str, Field(min_length=1)]
    versions: list[RecordedVersion]
    next_minor: Annotated[str, Field(pattern=r"^\d+\.\d+$")]

    #: Set on a fork. Held by the copy, never written on the original.
    forked_from: str | None = None
    forked_from_version: str | None = None

    #: Whether this may be published, and why not when it may not (`REQ-522` to
    #: `REQ-524`). Answered at the fork rather than at publication, so an
    #: unmodified clone is a rule the caller meets early instead of a surprise.
    publishable: bool | None = None
    publish_reason: str | None = None


class SearchHit(BaseModel):
    """One local object a search matched, and the lane it is in (`ADR-0016`)."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    stable_id: Annotated[str, Field(min_length=1)]
    revision_id: Annotated[str, Field(min_length=1)]

    #: Three lanes and no fourth. Nothing promotes a candidate between them:
    #: `experimental` never becomes `authoritative`, automatically or by an
    #: agent's decision, and `local_owner_or_pinned` is installable without ever
    #: being displayed as platform-confirmed.
    lane: Literal["authoritative", "local_owner_or_pinned", "experimental"]
    reason: Annotated[str, Field(min_length=1)]
    fields: dict[str, JsonValue] = {}


class LocalSearchResults(BaseModel):
    """What a local search found, one section per trust lane.

    Separate lists rather than one labelled list: `SPEC-006` REQ-603 requires
    the unverified candidates to come back as a *separate section*, and a caller
    rendering a flat list of rows has already lost the distinction it asks for.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    authoritative: list[SearchHit]
    local_owner_or_pinned: list[SearchHit]
    experimental: list[SearchHit]

    #: Why the experimental section holds what it holds. "Nothing matched" and
    #: "nothing was allowed" are different answers and an empty list is both.
    experimental_reason: Annotated[str, Field(min_length=1)]

    #: Whether the result was cut at the bound. Silence here would read as
    #: "that is all there is".
    truncated: bool = False


class EligibilityRefusal(BaseModel):
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


class EligibilityNote(BaseModel):
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


class CandidateEligibility(BaseModel):
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


class EligibilityReport(BaseModel):
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


class EligibilityMatrix(BaseModel):
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


class ProposalMember(BaseModel):
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


class ProposalView(BaseModel):
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


class ProposalSession(BaseModel):
    """What one project-and-harness pair currently has open and selected."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    project_id: Annotated[str, Field(min_length=1)]
    harness_id: HarnessId
    policy_version: Annotated[str, Field(min_length=1)]
    proposals: list[ProposalView] = []

    #: The version selected for this pair, if one has been confirmed. Selected
    #: and installed are different facts: `pending_install` is the ordinary
    #: window between them, not a drift.
    selected_stable_id: str | None = None
    selected_version: str | None = None
    selected_state: Literal["pending_install", "installed"] | None = None


class ConfirmationView(BaseModel):
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


class GraphReference(BaseModel):
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


class GraphNode(BaseModel):
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


class GraphRefusal(BaseModel):
    """One reason a closure could not be resolved."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    code: Annotated[str, Field(min_length=1)]
    summary: Annotated[str, Field(min_length=1)]
    details: dict[str, str] = {}


class SetupGraph(BaseModel):
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


class CompositionConflict(BaseModel):
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


class CompositionChoice(BaseModel):
    """One component in the composition, with the lane it came in on."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    stable_id: Annotated[str, Field(min_length=1)]
    version: Annotated[str, Field(pattern=r"^\d+\.\d+$")]
    lane: Literal["authoritative", "local_owner_or_pinned", "experimental"]
    reason: Annotated[str, Field(min_length=1)]


class ConversionEntry(BaseModel):
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


class CompositionReports(BaseModel):
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
    conflicts: list[CompositionConflict] = []

    #: Only from the closed set `REQ-625` allows. Naming the whole set every
    #: time would prove nothing about what actually happened.
    operations: list[str] = []

    conversion: list[ConversionEntry] = []
    conversion_complete: bool = True


class BundleFile(BaseModel):
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


class BundleRefusal(BaseModel):
    """One reason a bundle could not be compiled."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    code: Annotated[str, Field(min_length=1)]
    summary: Annotated[str, Field(min_length=1)]
    details: dict[str, str] = {}


class HarnessBundle(BaseModel):
    """A compiled bundle, or every reason it could not be compiled.

    `digest` and `files` are empty exactly when `compiled` is false. A manifest
    beside a list of refusals would read as "almost built", and a bundle holding
    a file that was not accepted is not installable at all.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    compiled: bool
    harness_id: HarnessId
    bundle_format: Literal["ai-stp-bundle/1"] = "ai-stp-bundle/1"

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


class ConformanceCase(BaseModel):
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


class ConformanceReport(BaseModel):
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


class ProviderNetworkCapability(BaseModel):
    """Observed protocol-v2 network boundary on this exact machine.

    The report never turns absence into support. Evidence names the launcher
    version/digest and transport probes when enforcement is observed; an
    unavailable result remains actionable machine data rather than a log line.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    protocol_version: Literal[2] = 2
    os_name: Annotated[str, Field(min_length=1)]
    network_enforcement: Literal["enforced", "unavailable"]
    launcher_id: str = ""
    evidence: Annotated[list[str], Field(min_length=1)]
    local_actions_available: bool


class ReleaseRefusal(BaseModel):
    """One reason a provider release is not acceptable."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    code: Annotated[str, Field(min_length=1)]
    summary: Annotated[str, Field(min_length=1)]
    details: dict[str, str] = {}


class PinnedRelease(BaseModel):
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


class ProviderTrust(BaseModel):
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

    #: Exact releases this machine approved, bound to the provider and
    #: repository that may present them. Empty means nothing is installable:
    #: an approved-bytes list that approves everything when empty would not be
    #: a list anybody could rely on. `latest` is forbidden by the contract.
    pinned_releases: list[PinnedRelease] = []

    #: Present only when a manifest was given to check. `null` means the policy
    #: was reported and nothing was verified, which is not the same as accepted.
    accepted: bool | None = None
    known_sequence: Annotated[int, Field(ge=0)] | None = None
    refusals: list[ReleaseRefusal] = []


class InstallationStep(BaseModel):
    """One recorded step of an installation. Append-only and safe to show."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    sequence: Annotated[int, Field(ge=1)]
    at: Annotated[str, Field(min_length=1)]
    state_before: str = ""
    state_after: Annotated[str, Field(min_length=1)]
    result: Annotated[str, Field(min_length=1)]


class InstallationView(BaseModel):
    """One installation operation: its plan, its state and how it got there.

    `plan_digest` is what a confirmation is given against. `operation.md` binds
    an approval to an exact hash and says it does not carry to a new plan, so a
    caller approving must send this value back rather than a flag.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    operation_id: Annotated[str, Field(min_length=1)]
    action: Literal["install", "update", "backup", "remove", "rollback"]
    state: Literal[
        "planned",
        "approved",
        "applying",
        "applied_unverified",
        "verified",
        "partial",
        "failed",
        "stale",
        "cancelled",
        "rolled_back",
    ]
    plan_digest: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    target_id: Annotated[str, Field(min_length=1)]
    expected_target_digest: Annotated[str, Field(min_length=1)]
    provider_version: str = ""
    provider_protocol_version: Annotated[int, Field(ge=1)] = 1
    provider_target: str = ""
    provider_release_trusted: bool = False
    provider_release_recovery: bool = False
    bundle_format: str = ""
    bundle_digest: str = ""
    bundle_artifact_digest: str = ""
    bundle_size: Annotated[int, Field(ge=0)] = 0
    provider_plan_digest: str = ""
    backup_ref: str | None = None

    #: Declared by the exact SetupVersion before apply. It is a requirement,
    #: never proof that the provider target has completed it (`ADR-0052`).
    required_authorization: Literal["none", "user_account", "external_service"] = "none"

    #: What the plan says it will do, enumerated. `REQ-805` makes a plan's
    #: effects part of what the user is approving, not a summary of them.
    effects: list[str] = []
    managed_paths: list[str] = []
    recovery_action: str = ""
    expires_at: Annotated[str, Field(min_length=1)]
    steps: list[InstallationStep] = []


class RecoveryView(BaseModel):
    """What a stopped operation left behind, and what may be done next.

    All four things `operation.md` asks a recovery report for. Three of them
    without the fourth leaves a person to guess at the one thing they must not
    guess at.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    operation_id: Annotated[str, Field(min_length=1)]
    state: Annotated[str, Field(min_length=1)]
    effects_recorded: list[str] = []

    #: The provider owns the backup bytes; this is the exact reference to them.
    backup_ref: str | None = None
    next_actions: list[str] = []


class InstallationStatus(BaseModel):
    """Every operation that stopped without a settled outcome.

    `partial` appears here even though it is terminal: it is an outcome that
    still needs a person, and an operation nobody is told about is one nobody
    recovers.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    stopped: list[RecoveryView] = []


class ImportedFile(BaseModel):
    """One configuration file an inspection read."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    path: Annotated[str, Field(min_length=1)]
    byte_length: Annotated[int, Field(ge=0)]
    digest: str = ""

    #: Key names whose value was removed. Names only: `SPEC-008` REQ-815 allows
    #: the name of a mandatory variable into a passport and nothing else, and a
    #: list of what was redacted would be a list of secrets.
    redacted_keys: list[str] = []

    #: Why the file was not read, when it was not. Kept apart from "no secrets
    #: found": one is a clean file and the other is a file nobody looked at.
    unreadable: str = ""

    #: Set when the file was read and hashed but is larger than an imported
    #: configuration file may be. It is excluded from every proposed component
    #: and it is not a blocker: the import bound is a declared policy, not a
    #: failure to see the file.
    oversized: bool = False


class ImportInspection(BaseModel):
    """What one native configuration holds, read and nothing more (`REQ-813`).

    `detection_rule` says how secrets were looked for. A report that will not
    say how it looked cannot be told apart from one that looked properly, and
    this one is deliberately partial — it matches key names, so a credential
    stored under a name that says nothing is not found.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    root: Annotated[str, Field(min_length=1)]
    harness_id: HarnessId
    detection_rule: Annotated[str, Field(min_length=1)]
    files: list[ImportedFile] = []
    redacted_keys: list[str] = []
    unreadable: list[str] = []

    #: Files excluded by the import size bound. Separate from `unreadable`
    #: because the remedies differ: an oversized file is excluded by policy,
    #: while an unreadable one means the configuration was not fully seen.
    oversized: list[str] = []


class SetupImportComponent(BaseModel):
    """One native component proposed by a read-only setup import plan."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    candidate_id: Annotated[str, Field(min_length=1)]
    component_type: ComponentType
    native_role: Annotated[str, Field(min_length=1)]
    paths: Annotated[list[str], Field(min_length=1)]
    file_set_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    byte_length: Annotated[int, Field(ge=0)]


class SetupImportPlan(BaseModel):
    """Deterministic read-only decomposition of one native setup candidate."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    root: Annotated[str, Field(min_length=1)]
    harness_id: HarnessId
    inspection_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    plan_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    components: list[SetupImportComponent] = []
    excluded: list[str] = []
    blocked_by: list[str] = []
    effects: list[str] = []


class ImportedSetup(BaseModel):
    """A registered import and the backup it was taken alongside.

    Two identifiers because they are two objects (`REQ-814`). A backup says
    where the old bytes are; a setup says what was made from them. Deleting the
    first must not delete the identity of the second.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    stable_id: Annotated[str, Field(min_length=1)]
    revision_id: Annotated[str, Field(min_length=1)]
    backup_id: Annotated[str, Field(min_length=1)]
    redacted_keys: list[str] = []
    plan_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    component_ids: Annotated[list[str], Field(min_length=1)]


class TargetSurvey(BaseModel):
    """The daily state of one project-and-harness pair (`#177`).

    `states` is a list because a pair can be waiting to install *and* missing a
    variable at once. Answering with one would send somebody to fix a thing and
    meet the other immediately after.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    project_id: Annotated[str, Field(min_length=1)]
    harness_id: HarnessId
    states: Annotated[
        list[
            Literal[
                "not_selected",
                "pending_install",
                "local_drift",
                "catalog_drift",
                "needs_configuration",
                "installed",
            ]
        ],
        Field(min_length=1),
    ]

    selected_stable_id: str = ""
    selected_version: str = ""
    installed_stable_id: str = ""
    installed_version: str = ""

    #: What the target read when it was last verified, and what it reads now.
    #: Local drift is the difference; one of them alone cannot express it.
    verified_target_digest: str = ""
    observed_target_digest: str = ""

    #: Names only, never values.
    missing_env: list[str] = []
    pending_authorization: str = ""

    #: Empty means nobody asked the catalogue, which is not the same as "there
    #: is nothing newer".
    catalog_version: str = ""


class ManagedPathChange(BaseModel):
    """One stable managed-path drift class without an absolute local path."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1] = 1
    code: Literal["modified", "added", "deleted"]
    path: Annotated[str, Field(min_length=1)]
    expected_digest: Annotated[str, Field(pattern=rf"^(?:{DIGEST_PATTERN})?$")] = ""
    observed_digest: Annotated[str, Field(pattern=rf"^(?:{DIGEST_PATTERN}|unsafe)?$")] = ""

    @model_validator(mode="after")
    def validate_change_shape(self) -> Self:
        """Keep each stable code tied to one unambiguous evidence shape."""
        valid = {
            "modified": bool(self.expected_digest) and bool(self.observed_digest),
            "added": not self.expected_digest and bool(self.observed_digest),
            "deleted": bool(self.expected_digest) and not self.observed_digest,
        }
        if not valid[self.code]:
            raise ValueError("managed path evidence does not match its change code")
        return self


class TargetDiff(BaseModel):
    """What moved between two readings of one pair, named field by field.

    Named rather than counted: "three things changed" is not something anybody
    can act on, and finding out *which* is the reason to compare at all.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    project_id: Annotated[str, Field(min_length=1)]
    harness_id: HarnessId
    changes: list[str] = []
    managed_detail: Literal["not_applicable", "available", "unavailable"] = "not_applicable"
    managed_changes: list[ManagedPathChange] = []


class RollbackTarget(BaseModel):
    """The exact previous verified version this pair can go back to.

    "Previous" is the one before the current in verification order, not the
    newest that is not current. The two differ the moment somebody rolls back
    twice, and the second answer walks forwards.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    project_id: Annotated[str, Field(min_length=1)]
    harness_id: HarnessId
    setup_stable_id: Annotated[str, Field(min_length=1)]
    setup_version: Annotated[str, Field(pattern=r"^\d+\.\d+$")]
    verified_at: str = ""

    #: The operation that verified it. A rollback is a new plan, not a replay of
    #: this one; the reference is provenance, not an instruction.
    operation_id: Annotated[str, Field(min_length=1)]


class TelemetryStatus(BaseModel):
    """Whether the anonymous install ping is on, and everything it would send.

    One model for the consent screen and for the status read, because they
    answer the same question and two shapes would let them drift into saying
    different things about the same feature.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1

    #: `not_asked`, `declined` or `accepted`. Observably identical on the
    #: network for the first two; they differ only in whether anything asks
    #: again (`REQ-1316`).
    state: Literal["not_asked", "declined", "accepted"]

    #: Whether a ping would actually be sent. Consent alone is not enough: the
    #: switch in the configuration can turn it off without withdrawing consent.
    enabled: bool = False

    #: Where a ping would go, and whether that came from the configuration or
    #: from the default. Named so an operator can see a redirected collector.
    url: str = ""
    url_source: Literal["default", "config"] = "default"

    #: Exactly the query fields a ping carries, so the screen shows the closed
    #: set rather than describing it. The anonymous identifier is named here as
    #: a field and never printed as a value.
    collected: list[str] = Field(default_factory=list[str])


class TargetBackup(BaseModel):
    """One provider-owned copy of a target, and what the target held when it was taken.

    A reference and never bytes. The provider owns the copy; recording it here
    would give one recovery two owners, and only one of them can restore
    (`REQ-814`).
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1

    #: Exactly what `install plan --action rollback --backup-ref` takes.
    backup_ref: Annotated[str, Field(min_length=1)]

    #: The operation that took the copy. Provenance, not an instruction: a
    #: restore is a new plan rather than a replay of this one.
    operation_id: Annotated[str, Field(min_length=1)]

    #: What was installed when the copy was taken. Empty when the copy predates
    #: any verified setup identity on this pair, which is a fact rather than a
    #: defect: a backup can be taken of a target nobody has installed onto.
    setup_stable_id: str = ""
    setup_version: str = ""

    #: The provider target this copy belongs to. A backup of one target is not
    #: offered for another, and the field is what lets a reader see that.
    provider_target: str = ""
    created_at: str = ""


class TargetBackups(BaseModel):
    """Every provider-owned copy this pair can restore from, oldest first.

    The read half that `SPEC-012` assumed and no command answered: a `BackupRef`
    appeared once, in the answer to `install apply`, and an agent that did not
    keep that stdout could not name the copy again. Restoring is still an
    ordinary plan with an ordinary approval; this only says which copies exist.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    project_id: Annotated[str, Field(min_length=1)]
    harness_id: HarnessId
    backups: list[TargetBackup] = Field(default_factory=list[TargetBackup])


class LanguageOutline(BaseModel):
    """What one language contributes to a project (`SPEC-004` REQ-404).

    `method` carries the strength of the answer, and it is not decoration.
    `syntax_tree` means a real parser read the file; `line_scan` means the words
    were recognised line by line and a string containing them would be
    indistinguishable from a declaration. Reporting both as plain symbol counts
    would hide that difference exactly where a caller decides how far to trust
    them.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    language: Annotated[str, Field(min_length=1)]

    #: `REQ-412`: a language with no adapter is `not_available` with a reason,
    #: never a partial index presented as a whole one.
    state: Literal["available", "not_available"]
    method: Literal["syntax_tree", "line_scan"] | None = None
    reason: str | None = None
    files: Annotated[int, Field(ge=0)]
    symbols: Annotated[int, Field(ge=0)]
    tests: Annotated[int, Field(ge=0)]
    entry_points: list[str] = []


class ProjectSymbols(BaseModel):
    """The table of contents of one project, and nothing deeper (`REQ-411`).

    No call graph, no vector representations, no symbol bodies. `state` is
    `partial` when the file budget was reached, for the same reason the index
    says so: a short answer that looks complete is the worse failure.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    root: Annotated[str, Field(min_length=1)]
    state: Literal["complete", "partial"]
    stopped_by: str | None = None
    languages: list[LanguageOutline]


class PinnedTool(BaseModel):
    """One tool the managed profile pins (`SPEC-014` REQ-1403)."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    tool_id: Annotated[str, Field(min_length=1)]
    purpose: Annotated[str, Field(min_length=1)]

    #: Exact, never a range: a range would let two installations differ while
    #: both looked pinned.
    version: Annotated[str, Field(min_length=1)]
    license: Annotated[str, Field(min_length=1)]

    #: Exact source and its integrity proof for *this* platform.
    source: Annotated[str, Field(min_length=1)]
    digest: Annotated[str, Field(min_length=1)]

    #: How the proof was obtained. A checksum the vendor published is an
    #: upstream statement about the artifact; one pinned during a single
    #: download only proves nothing changed since. Different strengths, kept
    #: apart so the difference survives into the answer.
    digest_source: Literal["vendor_published", "pinned_on_download"]


class EcosystemCoverage(BaseModel):
    """What the profile offers for one ecosystem, including nothing."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    ecosystem: Annotated[str, Field(min_length=1)]
    title: Annotated[str, Field(min_length=1)]
    state: Literal["available", "not_available"]

    #: Present exactly when `state` is `not_available`. `REQ-1407` asks for the
    #: reason: an agent reading a short list cannot otherwise tell "nothing
    #: needed" from "nothing yet".
    reason: str | None = None
    tools: list[PinnedTool]


class HarnessInstallation(BaseModel):
    """One place a harness was found (`SPEC-014` REQ-1417)."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1

    #: Absolute and verified, rendered with the home directory folded away.
    path: Annotated[str, Field(min_length=1)]

    #: The exact version, or `unknown`. Never a guess: `REQ-1415` allows the
    #: word and not an invented number.
    version: Annotated[str, Field(min_length=1)]
    reason: Annotated[str, Field(min_length=1)]
    surface: Literal["cli", "desktop"] = "cli"
    version_source: Literal[
        "process", "package_metadata", "windows_package_metadata", "unavailable"
    ] = "process"
    diagnostic: Annotated[str, Field(min_length=1)] = "version_reported"


class HarnessPresence(BaseModel):
    """What is known about one harness on this machine (`REQ-1415`)."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    harness_id: Annotated[str, Field(min_length=1)]
    title: Annotated[str, Field(min_length=1)]
    support: Literal["primary", "beta"]
    state: Literal["configured", "installed", "unknown_version", "available"]

    #: Every installation rather than the first: two versions of one harness on
    #: one machine is ordinary, and reporting one hides the other.
    installations: list[HarnessInstallation]

    #: The user configuration root, when there is one.
    configuration: str | None = None
    reason: Annotated[str, Field(min_length=1)]


class HarnessSurvey(BaseModel):
    """Every declared harness, whether or not it is here.

    Total by construction. A harness absent from the answer would be
    indistinguishable from one this build does not support, and `REQ-1414`
    makes the supported set the point.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    harnesses: list[HarnessPresence]


class HarnessCapabilityRow(BaseModel):
    """One executable row from the closed harness capability catalog."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1] = 1
    harness_id: Literal["claude-code", "codex", "pi", "opencode", "grok-build", "undefined"]
    title: Annotated[str, Field(min_length=1)]
    support: Literal["primary", "beta", "portable"]
    component_types: list[
        Literal["instruction", "skill", "mcp", "hook", "command", "agent", "plugin", "setting"]
    ]
    projection_capabilities: list[str]
    global_layouts: list[str]
    project_layouts: list[str]
    layout_sources: list[str]
    gaps: list[str]


class HarnessCapabilityTable(BaseModel):
    """The complete supported harness table, including shared conventions."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1] = 1
    harnesses: list[HarnessCapabilityRow]


class ToolchainProfile(BaseModel):
    """The managed toolchain as it resolves on this machine (`SPEC-014`).

    Policy, not project: `REQ-1402` makes an empty project and a documentation
    project resolve to the same profile, because what a developer needs
    installed is not deducible from what they have written so far.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    profile: Annotated[str, Field(min_length=1)]
    platform: Annotated[str, Field(min_length=1)]
    ecosystems: list[EcosystemCoverage]


class SkillDelivery(BaseModel):
    """Where the canonical Agent Skill is, and whether this build put it there.

    The Skill is what an agent reads to learn how to drive this CLI, so an
    installation that carries the binary and not the procedure has delivered
    half a product. `state` distinguishes a destination this installation owns
    from one somebody else wrote, because replacing the second would be taking
    over a file that is not ours.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1

    #: `absent`, `owned`, `foreign` or `stale`.
    state: Literal["absent", "owned", "foreign", "stale"]

    #: Rendered with the home directory folded away, like every reported path.
    target: Annotated[str, Field(min_length=1)]

    #: `None` when nothing is installed there.
    digest: str | None = None

    #: The harness projection installed, or `None` for the canonical Skill.
    harness: str | None = None

    #: Every harness this build ships a native projection for.
    available_harnesses: list[str]


class CatalogArtifactView(BaseModel):
    """Where the verified bytes of one exact version now are (issue #76).

    Answered after the bytes have been checked against the passport, so a caller
    that receives this knows the file at `path` hashes to `digest` and is
    `size_bytes` long. `source` says whether the network was involved, which is
    what an offline caller needs to know about its own cache.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    kind: CatalogKind
    source: AnswerSource
    checked_at: Timestamp
    stable_id: Annotated[str, Field(min_length=1)]
    version: Annotated[str, Field(min_length=1)]
    digest: Annotated[str, Field(min_length=1)]
    size_bytes: Annotated[int, Field(ge=0)]

    #: Rendered with the home directory folded away, like every other path this
    #: CLI reports: `#73` keeps the account name out of output.
    path: Annotated[str, Field(min_length=1)]


class AcquiredComponentVersion(BaseModel):
    """One exact component made available to the local setup compiler."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    stable_id: Annotated[str, Field(min_length=1)]
    version: Annotated[str, Field(min_length=1)]
    passport_digest: Annotated[str, Field(min_length=1)]
    artifact_digest: Annotated[str, Field(min_length=1)]


class CatalogSetupAcquisition(BaseModel):
    """An exact published setup graph materialized in the local registry."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    source: AnswerSource
    checked_at: Timestamp
    stable_id: Annotated[str, Field(min_length=1)]
    version: Annotated[str, Field(min_length=1)]
    passport_digest: Annotated[str, Field(min_length=1)]
    artifact_digest: Annotated[str, Field(min_length=1)]
    harness_id: Annotated[str, Field(min_length=1)]
    components: list[AcquiredComponentVersion]


class CliSignedAttestation(AssuranceAuthorAttestation):
    """Locally signed full attestation plus its owner-only output location."""

    output_path: Annotated[str, Field(min_length=1)]
    attestation_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
