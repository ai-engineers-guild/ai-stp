"""The command registry as data: descriptors, machine help, capabilities and
the schema index (`SPEC-011`). Every invocation loads this module, so it
imports no contract family, only the foundation and the wire helpers.
"""

from typing import Annotated, Literal, Self

from pydantic import ConfigDict, Field, model_validator

from ai_stp_contracts.http import open_wire_object
from ai_stp_contracts.model import ContractModel
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import DIGEST_PATTERN
from ai_stp_foundation.errors import ErrorHandling, ExitClass
from ai_stp_foundation.harnesses import HarnessId

#: State effects are independent of task authority and the confirmation binding
#: (`SPEC-011`, `docs/agent/interaction-policy.md`).
#:
#: - `read` observes; explicitly documented caches may be refreshed;
#: - `plan` computes and stores an exact plan without applying its target effect;
#: - `apply` performs the requested effect within the user's task authority;
#: - `destructive` removes state; irreversible removal follows the decision policy.
type MutabilityClass = Literal["read", "plan", "apply", "destructive"]


#: How a caller binds an already-authorized effect. This is not another approval
#: question within the user's task. The CLI never asks in the
#: terminal — a decision arrives as an explicit flag or as the exact digest of a
#: stored plan, and its absence is answered with `needs_user_action` rather than
#: a prompt. That keeps one execution path for a human and for an agent, and
#: leaves nothing to hang in CI or in a container.
type ConfirmationKind = Literal["none", "explicit_flag", "plan_digest"]


type ParameterKind = Literal["option", "argument"]


type ParameterType = Literal["string", "boolean", "integer"]


#: Command paths are the machine identity of a command: `["config", "show"]`.
type CommandPath = Annotated[list[str], Field(min_length=1, max_length=4)]


class CommandParameter(ContractModel):
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


class CommandParameterRule(ContractModel):
    """A cross-parameter invocation rule that consumers must not parse from prose.

    `exactly_one` of the named parameters must be present; `at_most_one`
    allows none but refuses two; `required_when` makes the named parameters
    required; `forbidden_when` refuses the named parameters while its
    condition holds. A rule carrying `when_parameter` and `when_values`
    applies only while that parameter takes one of those values —
    `install plan`'s source rule holds for `install`, `update` and `remove`,
    and on `backup` and `rollback` the same pair relaxes to `at_most_one`,
    because those actions bind to a target, not to a graph (`REQ-1207`).
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    kind: Literal["exactly_one", "at_most_one", "required_when", "forbidden_when"]
    parameters: Annotated[list[str], Field(min_length=1)]
    when_parameter: str = ""
    when_values: list[str] = []


class CommandDescriptor(ContractModel):
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
            conditional = bool(rule.when_parameter or rule.when_values)
            if rule.kind in {"exactly_one", "at_most_one"} and len(rule.parameters) < 2:
                raise ValueError(f"{rule.kind} requires two or more parameter names")
            if rule.kind in {"required_when", "forbidden_when"} and not conditional:
                raise ValueError(f"{rule.kind} has an invalid condition")
            if conditional and (
                rule.when_parameter not in names
                or not rule.when_values
                or rule.when_parameter in rule.parameters
            ):
                raise ValueError("parameter rule has an invalid condition")
        return self


class MachineErrorDescriptor(ContractModel):
    """One stable failure and the first disposition an agent should take."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    code: Annotated[str, Field(pattern=r"^AI_STP_[A-Z0-9]+(?:_[A-Z0-9]+)*$")]
    exit_class: ExitClass
    handling: ErrorHandling
    description: Annotated[str, Field(min_length=1)]


class MachineHelp(ContractModel):
    """The whole command registry, rendered for an agent."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    cli_version: Annotated[str, Field(min_length=1)]

    #: The exact machine surface this answer describes. A distribution version
    #: does not identify it: a source build and a released wheel report the same
    #: string while their registries differ by a command, a flag or an error
    #: code, and a caller that cached help "for this version" then constructs
    #: calls the running build does not accept. Compare this instead.
    registry_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]

    #: Options every command accepts. Declared once rather than repeated on each
    #: descriptor: `--json` is not a property of any one command, and repeating
    #: it would make the registry look like it varies when it does not.
    global_options: Annotated[list[CommandParameter], Field(min_length=1)]

    commands: Annotated[list[CommandDescriptor], Field(min_length=1)]
    error_codes: Annotated[list[MachineErrorDescriptor], Field(min_length=1)]


class Capabilities(ContractModel):
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

    #: The same fingerprint `help --agent` reports, so a caller can tell whether
    #: the help it kept still describes the build in front of it without
    #: fetching the whole registry again.
    registry_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]

    #: The local registry schema this build reads and writes. Data written by a
    #: newer build is refused rather than downgraded, and saying so here lets a
    #: caller see the mismatch before a command hits it.
    local_schema_version: Annotated[int, Field(ge=1)]

    #: Whether this process loaded the published distribution or this checkout.
    #: A source tree and a released wheel can report one version string.
    installation: Literal["distribution", "source"]

    supported_harnesses: Annotated[list[HarnessId], Field(min_length=1)]
    catalog_enabled: bool
    sync_enabled: bool
    command_paths: Annotated[list[str], Field(min_length=1)]


class CliSchemaEntry(ContractModel):
    """One exported schema id this build resolves."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    name: Annotated[str, Field(min_length=1)]
    urn: Annotated[str, Field(min_length=1)]


class CliSchemaIndex(ContractModel):
    """Every exported schema id this build resolves.

    `input_schema` and `result_schema` URNs inside machine payloads name
    entries in this index; `schema show` resolves one id to its document, so
    every URN the CLI emits is answerable through the CLI itself.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    cli_version: Annotated[str, Field(min_length=1)]
    schemas: list[CliSchemaEntry]


class CliSchemaDocument(ContractModel):
    """One exported schema resolved to its JSON Schema document."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    cli_version: Annotated[str, Field(min_length=1)]
    name: Annotated[str, Field(min_length=1)]
    urn: Annotated[str, Field(min_length=1)]
    document: dict[str, JsonValue]
