"""Durable agent tasks: intents, inputs, questions, outcomes and the task view."""

from typing import Annotated, Literal, Self

from pydantic import ConfigDict, Field, model_validator

from ai_stp_contracts.auth import OAuthProvider
from ai_stp_contracts.cli.publication import PublicationSetView
from ai_stp_contracts.cli.registry import ParameterType
from ai_stp_contracts.cli.runtime import DoctorReport
from ai_stp_contracts.cli.sync import SyncPullView, SyncPushView
from ai_stp_contracts.cli.technology import CliTechnologyUnmappedItem
from ai_stp_contracts.http import Timestamp, open_wire_object
from ai_stp_contracts.model import ContractModel
from ai_stp_contracts.technology import TechnologyUnmappedEntry
from ai_stp_foundation.digests import DIGEST_PATTERN
from ai_stp_foundation.harnesses import HarnessId
from ai_stp_foundation.ids import stable_id_pattern
from ai_stp_foundation.versioning import VERSION_PATTERN
from ai_stp_passports.versions import ComponentType

type TaskState = Literal["planned", "blocked", "running", "completed", "failed", "cancelled"]


type TaskIntent = Literal[
    "inspect",
    "initialize",
    "install",
    "change",
    "author",
    "switch",
    "account",
    "publish",
    "technology",
]


type TaskId = Annotated[str, Field(pattern=stable_id_pattern("task"))]


type TaskActor = Literal["human", "external"]


class TaskQuestion(ContractModel):
    """One typed question the task engine still needs before it can continue."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    question_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]*$")]
    prompt: Annotated[str, Field(min_length=1)]
    value_type: ParameterType
    choices: list[str]
    recommended: str = ""
    why: str = ""
    actor: TaskActor = "human"


class TaskOrientation(ContractModel):
    """Slim inspect facts. No command registry dump."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    cli_version: Annotated[str, Field(min_length=1)]
    wire_schema_version: Literal[1] = 1
    registry_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    local_schema_version: Annotated[int, Field(ge=1)]
    installation: Literal["distribution", "source"]
    supported_harnesses: Annotated[list[HarnessId], Field(min_length=1)]
    catalog_enabled: bool
    sync_enabled: bool
    intents: list[str]


class TaskInspectInput(ContractModel):
    """Inspect takes no caller facts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1


class TaskInitializeInput(ContractModel):
    """Optional harness pin. Omitted means the engine asks once."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    harness_id: HarnessId | None = None


class TaskInstallInput(ContractModel):
    """Pins and scope. Omitted pins mean one justified pick, not a catalog quiz."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    harness_id: HarnessId | None = None
    project_root: str | None = None
    setup_id: Annotated[str, Field(pattern=stable_id_pattern("setup"))] | None = None
    setup_version: Annotated[str, Field(pattern=VERSION_PATTERN)] | None = None
    #: Explicit `family:value` grants the caller gives the install target, in
    #: the spelling component passports use. Without a grant the target permits
    #: nothing and the plan refuses an escalating composition.
    allowed_permissions: list[str] | None = None


class TaskChangeInput(ContractModel):
    """Source setup plus one member delta. Omitted source means the harness baseline."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    harness_id: HarnessId | None = None
    project_root: str | None = None
    setup_id: Annotated[str, Field(pattern=stable_id_pattern("setup"))] | None = None
    setup_version: Annotated[str, Field(pattern=VERSION_PATTERN)] | None = None
    component_id: Annotated[str, Field(pattern=stable_id_pattern("component"))] | None = None
    component_version: Annotated[str, Field(pattern=VERSION_PATTERN)] | None = None
    action: Literal["add", "remove"] | None = None


class TaskAuthorInput(ContractModel):
    """Directory plus typed authoring fields. One component and one setup identity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    directory: str | None = None
    harness_id: HarnessId | None = None
    component_type: ComponentType | None = None
    name: str | None = None
    license_spdx: str | None = None


class TaskSwitchInput(ContractModel):
    """Restore last user working config. Omitted snapshot means the latest preserved setup."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    harness_id: HarnessId | None = None
    project_root: str | None = None
    preserved_setup_id: Annotated[str, Field(pattern=stable_id_pattern("setup"))] | None = None
    reload_session: str | None = None


class TaskAccountInput(ContractModel):
    """Sign in, sign out, or explicitly sync. Login never uploads."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    action: Literal["login", "logout", "sync"] | None = None
    provider: OAuthProvider | None = None
    stable_id: str | None = Field(default=None, description="Exact local account-sync entity id.")
    project_root: str | None = Field(
        default=None,
        description="Legacy input retained for replay; project passports do not sync to accounts.",
    )
    scope: Literal["push", "pull"] | None = None


class TaskPublishInput(ContractModel):
    """Publish a local object through the existing no-binding publication plan."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    object_id: str | None = None
    object_version: Annotated[str, Field(pattern=VERSION_PATTERN)] | None = None
    visibility: Literal["public", "private"] | None = None
    directory: str | None = None
    provider: OAuthProvider | None = None


class TaskTechnologyDecision(ContractModel):
    """One review decision over an unmapped coordinate.

    `technology_id` names an existing registry record; `technology_name`
    creates one first (with `category_ids`/`category_name` for its governing
    categories). `mode` is `propose` — the queue entry gains a candidate and
    stays open for review — or `apply`, which publishes a derived mapping
    snapshot so the coordinate resolves from now on.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["package", "image", "executable", "configuration", "alias"]
    coordinate: Annotated[str, Field(min_length=1, max_length=512)]
    technology_id: Annotated[str, Field(pattern=r"^technology_[0-9A-HJKMNP-TV-Z]{26}$")] | None = (
        None
    )
    technology_name: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    category_ids: list[Annotated[str, Field(pattern=r"^category_[0-9A-HJKMNP-TV-Z]{26}$")]] = []
    category_name: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    description: Annotated[str, Field(max_length=4000)] = ""
    active: bool = False
    mode: Literal["propose", "apply"] = "propose"

    @model_validator(mode="after")
    def one_technology_source(self) -> Self:
        if (self.technology_id is None) == (self.technology_name is None):
            raise ValueError("name either technology_id or technology_name")
        if self.technology_name is None and (self.category_ids or self.category_name is not None):
            raise ValueError("categories only apply when creating a technology")
        return self


class TaskTechnologyInput(ContractModel):
    """Grow the technology registry from detection evidence.

    `unmapped` scans a project and lists what its effective mapping cannot
    resolve — locally and, when an organization is named and a session exists,
    the organization's review queue. `publish-mapping` writes one immutable
    organization snapshot: an explicit entries document, or the bundled seed
    table when `seed` is set. `resolve` applies a decision list: propose
    candidates, create records, publish a derived snapshot.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    action: Literal["unmapped", "publish-mapping", "resolve"] | None = None
    project_root: str | None = None
    scope: str | None = None
    organization_id: str | None = None
    #: Exact immutable snapshot version `publish-mapping` writes.
    mapping_version: str | None = None
    #: Snapshot `resolve` extends; defaults to the cached latest snapshot.
    base_version: str | None = None
    #: JSON/YAML document of mapping entries; `seed` publishes the bundled table.
    mapping_file: str | None = None
    seed: bool | None = None
    #: Review decisions `resolve` executes against the organization's queue.
    decisions: list[TaskTechnologyDecision] | None = None
    authorization_revision: Annotated[int, Field(ge=1)] | None = None
    idempotency_key: str | None = None


class TaskInputField(ContractModel):
    """One field of one intent's `--input` document, flattened for callers.

    `input_schema` names the authoritative JSON Schema, resolvable through
    `schema show`; this flat list exists so choosing an intent takes one call,
    not two. It is derived from the same model, so the two cannot disagree.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    name: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$")]
    required: bool
    value_type: ParameterType
    #: Closed value set when the field is an enum, e.g. `action` on account.
    #: Empty means the value is free-form.
    choices: list[str] = []


class TaskIntentDescriptor(ContractModel):
    """One shipped intent the Skill may start."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    name: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$")]
    when: Annotated[str, Field(min_length=1)]
    input_schema: Annotated[str, Field(min_length=1)]
    input_fields: list[TaskInputField]


class TaskIntentsCatalog(ContractModel):
    """Compact catalog of shipped intents. Not the 203-command registry."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    cli_version: Annotated[str, Field(min_length=1)]
    registry_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    intents: list[TaskIntentDescriptor]


class TaskInspectOutcome(ContractModel):
    """Inspection drained in-process by the inspect intent."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    kind: Literal["inspect"] = "inspect"
    doctor: DoctorReport
    orientation: TaskOrientation


class TaskInitializeOutcome(ContractModel):
    """Initialize drained in-process. The provider writes harness files."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    kind: Literal["initialize"] = "initialize"
    harness_id: HarnessId
    wrote: bool
    limitation: str = ""
    section_digest: Annotated[str, Field(pattern=rf"^(?:{DIGEST_PATTERN[1:-1]})?$")] = ""
    surface: str = ""


class TaskInstallOutcome(ContractModel):
    """Install drained in-process. Plan, approve, and apply never return to the model."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    kind: Literal["install"] = "install"
    harness_id: HarnessId
    setup_id: str
    setup_version: str
    operation_id: str
    state: str
    verified: bool


class TaskChangeOutcome(ContractModel):
    """Change drained in-process. A new setup identity; the source id is untouched."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    kind: Literal["change"] = "change"
    harness_id: HarnessId
    source_setup_id: str
    source_setup_version: str
    setup_id: str
    setup_version: str
    minted: bool
    operation_id: str
    state: str
    verified: bool


class TaskAuthorOutcome(ContractModel):
    """Author drained in-process. A local component and one new setup identity."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    kind: Literal["author"] = "author"
    harness_id: HarnessId
    directory: str
    component_type: ComponentType
    name: str
    component_id: str
    component_version: str
    setup_id: str
    setup_version: str
    minted: bool


class TaskSwitchOutcome(ContractModel):
    """Switch drained in-process. Restores last user working config; never kills the caller."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    kind: Literal["switch"] = "switch"
    harness_id: HarnessId
    project_root: str
    preserved_setup_id: str
    drift_preserved_setup_id: str = ""
    operation_id: str
    state: str
    verified: bool
    process_killed: Literal[False] = False
    session_loaded: Literal[False] = False


class TaskAccountOutcome(ContractModel):
    """Account drained in-process. Login never uploads; sync is a separate explicit step."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    kind: Literal["account"] = "account"
    action: Literal["login", "logout", "sync"]
    authenticated: bool
    login_uploaded: Literal[False] = False
    provider: str = ""
    session_state: str = ""
    synced: bool = False
    scope: str = ""
    sync_result: SyncPushView | SyncPullView | None = None


class TaskPublishOutcome(ContractModel):
    """Publish drained in-process. Worker receipt is not a readable catalog result."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    kind: Literal["publish"] = "publish"
    object_id: str
    object_version: str
    visibility: Literal["private", "public"]
    source_binding_id: str = ""
    plan_id: str
    plan_hash: str
    state: str
    readable: bool
    provenance: Literal["filesystem"] = "filesystem"
    publication_set: PublicationSetView | None = None


class TaskTechnologyOutcome(ContractModel):
    """Technology intent drained in-process: the queue, or the published snapshot."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    kind: Literal["technology"] = "technology"
    action: Literal["unmapped", "publish-mapping", "resolve"]
    project_id: str = ""
    scan_id: str = ""
    scan_state: Literal["complete", "partial"] | None = None
    organization_id: str = ""
    coordinates: list[CliTechnologyUnmappedItem] = []
    server_coordinates: list[TechnologyUnmappedEntry] = []
    mapping_version: str = ""
    mapping_digest: str = ""
    #: Coordinates given a review candidate (`resolve`, mode=propose).
    proposed: list[str] = []
    #: Coordinates mapped by the published snapshot (`resolve`, mode=apply).
    applied: list[str] = []
    created_technology_ids: list[str] = []
    created_category_ids: list[str] = []


type TaskOutcome = Annotated[
    TaskInspectOutcome
    | TaskInitializeOutcome
    | TaskInstallOutcome
    | TaskChangeOutcome
    | TaskAuthorOutcome
    | TaskSwitchOutcome
    | TaskAccountOutcome
    | TaskPublishOutcome
    | TaskTechnologyOutcome,
    Field(discriminator="kind"),
]


class TaskView(ContractModel):
    """One durable agent task. Envelope `ok` is independent of `state`."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    task_id: TaskId
    revision: Annotated[int, Field(ge=1)]
    intent: TaskIntent
    state: TaskState
    goal_satisfied: bool
    questions: list[TaskQuestion]
    outcome: TaskOutcome | None
    child_operation_ids: list[str]


class TaskListEntry(ContractModel):
    """One unsettled durable task — enough to choose it and resume.

    A caller that lost its task reference (process restart, compaction) lists
    these instead of starting a second task on a target another open task
    already owns. `task list` never returns settled rows; history is a status
    read, not a resume choice.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    task_id: TaskId
    revision: Annotated[int, Field(ge=1)]
    intent: TaskIntent
    state: Literal["planned", "blocked", "running"]
    #: The binding context the task claims — two open mutating tasks cannot
    #: share all three, so these fields are how a caller tells them apart.
    harness_id: str = ""
    project_root: str = ""
    scope: str = ""
    #: Ids of questions still open; empty means the task waits on CLI or
    #: external progress, not on an answer.
    open_question_ids: list[str]
    updated_at: Timestamp


class TaskListView(ContractModel):
    """The unsettled durable tasks, most recently touched first."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    tasks: list[TaskListEntry]
