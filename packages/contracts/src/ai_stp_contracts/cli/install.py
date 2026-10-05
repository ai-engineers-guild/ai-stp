"""Installation, recovery, target survey and diff, managed verification,
backups, preserved setups and environment requirements.
"""

from typing import Annotated, Literal, Self

from pydantic import ConfigDict, Field, model_validator

from ai_stp_contracts.cli.toolchain import HarnessSurvey
from ai_stp_contracts.corporate import PlanOutcome
from ai_stp_contracts.http import open_wire_object
from ai_stp_contracts.model import ContractModel
from ai_stp_foundation.digests import DIGEST_PATTERN
from ai_stp_foundation.harnesses import HarnessId


class InstallationStep(ContractModel):
    """One recorded step of an installation. Append-only and safe to show."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    sequence: Annotated[int, Field(ge=1)]
    at: Annotated[str, Field(min_length=1)]
    state_before: str = ""
    state_after: Annotated[str, Field(min_length=1)]
    result: Annotated[str, Field(min_length=1)]


class InstallationView(ContractModel):
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
    provider_release_trust: Literal[
        "verified_publisher", "signed", "build_attested", "unverified"
    ] = "unverified"
    provider_release_trusted: bool = False
    provider_release_recovery: bool = False
    bundle_format: str = ""
    bundle_digest: str = ""
    bundle_artifact_digest: str = ""
    bundle_size: Annotated[int, Field(ge=0)] = 0
    provider_plan_digest: str = ""
    backup_ref: str | None = None
    preserved_setup_id: str | None = None

    #: Declared by the exact SetupVersion before apply. It is a requirement,
    #: never proof that the provider target has completed it (`ADR-0052`).
    required_authorization: Literal["none", "user_account", "external_service"] = "none"

    #: What the plan says it will do, enumerated. `REQ-805` makes a plan's
    #: effects part of what the user is approving, not a summary of them.
    effects: list[str] = []

    #: What the selected setup is and what it says about itself, at the point
    #: of approval. `effects` enumerates the files a provider will write, which
    #: is exact and says nothing about what changing them means — and for at
    #: least one published setup the meaning is the entire content. `full-auto`
    #: turns off a product's sandbox and its prompting, and its description is
    #: where the qualifications live, including which parts of that claim hold
    #: on which platform.
    #:
    #: The browse card clamps to two lines and cannot install from there, and
    #: the detail page shows the whole text — but the CLI is the primary
    #: consumer here and carried none of it, so the one surface that actually
    #: precedes an install was the one that said least.
    setup_name: str = ""
    setup_description: str = ""
    managed_paths: list[str] = []
    recovery_action: str = ""
    expires_at: Annotated[str, Field(min_length=1)]
    steps: list[InstallationStep] = []


class RecoveryView(ContractModel):
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


class InstallationStatus(ContractModel):
    """Every operation that stopped without a settled outcome.

    `partial` appears here even though it is terminal: it is an outcome that
    still needs a person, and an operation nobody is told about is one nobody
    recovers.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    stopped: list[RecoveryView] = []


class MultiRootChildView(ContractModel):
    """One scope-specific operation owned by a multi-root transaction."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    scope: Literal["global", "user_root", "project"]
    operation_id: Annotated[str, Field(min_length=1)]
    target_id: Annotated[str, Field(min_length=1)]
    plan_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    state: Annotated[str, Field(min_length=1)]
    backup_ref: str | None = None
    harness_id: HarnessId | None = None
    setup_stable_id: str | None = None
    setup_version: str | None = None


class MultiRootTransactionView(ContractModel):
    """One recoverable decision spanning several provider-owned roots."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    transaction_id: Annotated[str, Field(min_length=1)]
    transaction_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    transaction_kind: Literal["single_setup", "environment"] = "single_setup"
    setup_stable_id: Annotated[str, Field(min_length=1)] | None
    setup_version: Annotated[str, Field(min_length=1)] | None
    harness_id: HarnessId | None
    state: Literal[
        "planned",
        "applying",
        "compensating",
        "recovery_required",
        "verified",
        "rolled_back",
        "cancelled",
    ]
    approved: bool
    children: Annotated[list[MultiRootChildView], Field(min_length=2, max_length=21)]
    next_actions: list[str] = []


class ShadowedSurface(ContractModel):
    """A name the product reads that the provider does not own."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1] = 1
    #: The name the product reads.
    name: Annotated[str, Field(min_length=1)]
    #: The owned surface it takes precedence over.
    over: Annotated[str, Field(min_length=1)]
    #: What the product does as a result, in the provider's own words.
    effect: Annotated[str, Field(min_length=1)]


class TargetSurvey(ContractModel):
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

    #: Names the product obeys that the provider does not own, from its `status`.
    #:
    #: `installed` with a matching digest says the bytes the provider wrote are
    #: intact. It says nothing about which file the product reads, and the two
    #: differ — a `.jsonc` beside an owned `.json`, or a plural spelling of a
    #: globbed directory, takes precedence over the owned copy. Without this the
    #: survey called such a target clean.
    #:
    #: Empty means nothing shadows, or an older provider that was never asked;
    #: those are not distinguished here because both leave the operator with
    #: nothing to act on. The list is reported and never acted on, like
    #: `catalog_drift`: which file should win belongs to whoever put it there.
    shadowed_by: list[ShadowedSurface] = []


class ManagedPathChange(ContractModel):
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


class TargetDiff(ContractModel):
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


class ManagedVerificationItem(ContractModel):
    """One managed line or drifted path, classified against authorized records.

    Setup and component items carry the expected coordinates; path items carry
    the file-level proof. Coordinates, relative paths and digests only — never
    file content, never an absolute local path.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1] = 1
    subject: Literal["setup", "component", "path"]
    stable_id: str = ""
    component_kind: str = ""
    version: str = ""
    revision_id: str = ""
    passport_digest: str = ""
    path: str = ""
    change: Literal["", "added", "modified", "deleted"] = ""
    expected_digest: str = ""
    observed_digest: str = ""
    classification: Literal[
        "unchanged",
        "locally_modified",
        "missing",
        "extra",
        "unverifiable",
        "expected_change",
    ]
    #: The corporate plan outcome for the line, when the assignment layer was
    #: reached. Empty means the verdict rests on local evidence alone.
    outcome: PlanOutcome | Literal[""] = ""
    diagnostic: str = ""


class ManagedVerification(ContractModel):
    """Whether a managed target still matches its authorized installed record.

    `status` is the one verdict a CI gate reads; `items` is the evidence behind
    it. The answer binds the check to tenant, account, project, context and
    harness, and carries coordinates, digests and timestamps only — a
    verification report must never contain file content.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    status: Literal[
        "pass",
        "fail",
        "outdated",
        "revoked",
        "unsupported",
        "not_enrolled",
        "unverifiable",
    ]
    project_id: Annotated[str, Field(min_length=1)]
    harness_id: HarnessId
    organization_id: str = ""
    account_id: str = ""
    remote_project_id: str = ""
    technology_id: str = ""
    target_id: str = ""

    #: The verified installation the check compared against, and when the
    #: check itself ran. Both are evidence, never instructions.
    operation_id: str = ""
    verified_at: str = ""
    checked_at: str = ""

    #: `evaluated` — the assignment layer answered; `offline` — the caller
    #: asked to skip it; `unavailable` — it could not be reached. The local
    #: verdict is reported either way.
    corporate: Literal["evaluated", "offline", "unavailable"] = "evaluated"

    verified_target_digest: str = ""
    observed_target_digest: str = ""
    shadowed_surfaces: list[ShadowedSurface] = []
    items: list[ManagedVerificationItem] = []
    diagnostics: list[str] = []


class RollbackTarget(ContractModel):
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


class TargetBackup(ContractModel):
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

    #: Whether the provider is protecting this copy from retention, as the
    #: provider reports it *now*. `None` whenever nobody asked — no provider was
    #: named, or the one named predates the field. Absence is never `false`: a
    #: reader that flattened the two would call an unprotected baseline checked.
    held: bool | None = None

    #: Free text a person typed when placing the hold. Opaque by contract:
    #: display it, never branch on it. The provider stores a fixed placeholder
    #: when the operator gave no reason, so its presence is not evidence that
    #: anybody considered anything.
    hold_reason: str | None = None

    #: Whether the provider still reports this copy at all. `None` when no
    #: provider was consulted. `False` is the answer worth having: this pair's
    #: journal offers a restore source the provider no longer has.
    present: bool | None = None


class PreservedSetupView(ContractModel):
    """A complete local setup and the provider snapshot retaining its native state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    stable_id: str
    operation_id: str
    project_id: str
    harness_id: str
    target_scope: str
    provider_target: str
    provider_id: str
    backup_ref: str
    snapshot_digest: str
    roots: list[str]
    base_root: Literal["target", "parent"] = "target"
    created_at: str
    verification: Literal["recorded_verified", "verified", "unavailable"] = "recorded_verified"
    target_state: Literal["not_observed", "matches", "differs", "unavailable"] = "not_observed"
    held: bool | None = None
    #: A legible name derived at read time: the applied setup's name and
    #: version, `local <date>` when no verified install preceded the capture.
    label: str = ""
    #: The verified setup version that stood on the target when the snapshot
    #: was taken. Empty when the captured state was never installed by a
    #: recorded operation — a hand-built configuration.
    origin_setup_id: str = ""
    origin_version: str = ""
    origin_name: str = ""
    #: True when the captured bytes differ from the origin version's recorded
    #: target digest — the user modified what was installed. None when no
    #: reference digest was recorded to compare against.
    modified: bool | None = None


class EnvironmentRequirement(ContractModel):
    """One exact prerequisite, measured without executing its preparation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal[
        "harness_program",
        "shared_program",
        "environment_variable",
        "authorization",
        "toolchain_tool",
    ]
    identity: str
    version: str = ""
    digest: str = ""
    sources: list[str] = Field(default_factory=list)
    state: Literal["satisfied", "action_required", "not_observed", "blocked"]
    reason: str
    actions: list[list[str]] = Field(default_factory=list[list[str]])


class EnvironmentInspection(ContractModel):
    """Preparation evidence stays distinct from verified native configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: str
    setups: list[str]
    prerequisites_satisfied: bool
    configuration_state: Literal["not_observed"] = "not_observed"
    requirements: list[EnvironmentRequirement]
    detected_harnesses: HarnessSurvey


class PreservedSetupsView(ContractModel):
    """Saved local setups remain addressable after restarting the CLI."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    setups: list[PreservedSetupView] = []


class TargetBackups(ContractModel):
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

    #: Whether a provider answered while building this list. False means every
    #: `held` and `present` below is `None` because nothing was asked, which is
    #: a different answer from a provider that was asked and said no.
    provider_observed: bool = False

    #: Copies the provider reports that this pair's journal does not record,
    #: oldest first. Empty unless a provider answered.
    #:
    #: The mirror of `present: false`, and the reason the reconciliation is not
    #: one-directional. A backup taken with the provider's own CLI — an operator
    #: holding a baseline before an experiment — never reaches our journal, and
    #: `install plan --action rollback --backup-ref` accepts it all the same. So
    #: leaving these out under-answered this command's own summary: they are
    #: provider-owned copies this pair can restore from.
    #:
    #: Refs only, deliberately. A `TargetBackup` carries an `operation_id`
    #: because every row in `backups` came from an operation we ran; a copy we
    #: never saw taken has none, and inventing one would put our name on
    #: somebody else's action. `provider status` holds the detail.
    unjournalled_refs: list[str] = Field(default_factory=list[str])
