"""What this installation reports about itself: `version`, `config show`,
`doctor`, `telemetry status` and the delivered Agent Skill.
"""

from typing import Annotated, Literal

from pydantic import ConfigDict, Field

from ai_stp_contracts.http import open_wire_object
from ai_stp_contracts.model import ContractModel
from ai_stp_contracts.standard import STANDARD_FAMILY
from ai_stp_foundation.digests import DIGEST_PATTERN

#: Primary setup state (`SPEC-011`, states section). `doctor` reports it in the
#: body and still exits `0`: an installation that is merely not configured yet
#: is a normal outcome, not a failure, and answering non-zero would make the
#: first run after installation look broken and break `set -e`.
type SetupState = Literal["ready", "needs_user_action", "partial", "failed"]


class DoctorCheck(ContractModel):
    """One thing `doctor` looked at."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    name: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$")]
    state: SetupState
    detail: str


class DoctorReport(ContractModel):
    """What `doctor` found.

    A report, not a verdict. `state` is the worst state among the checks, so a
    caller that reads one field still gets the truth.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    state: SetupState
    checks: Annotated[list[DoctorCheck], Field(min_length=1)]


class VersionReport(ContractModel):
    """Which build is running, and which contracts it speaks."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    cli_version: Annotated[str, Field(min_length=1)]
    wire_schema_version: Literal[1] = 1
    python_version: Annotated[str, Field(pattern=r"^\d+\.\d+\.\d+")]
    standard_family: Literal["ai-stp-standard/1"] = STANDARD_FAMILY
    contract_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    http_api_version: Literal["v1"] = "v1"
    provider_protocol_version: Literal[3] = 3


class ConfigValue(ContractModel):
    """One effective configuration value and where it came from.

    `SPEC-011` REQ-1116 requires the effective value **and** its source, because
    "it is 20 because that is the default" and "it is 20 because you wrote 20"
    lead to different next actions. No secret is representable: the config
    carries none by contract (`docs/contracts/cli-config.md`).
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    # A hyphen is admitted because a harness identifier carries one, and
    # `provider.paths.<harness_id>` (`#452`) has to spell it the way every
    # other surface does. A config key of `claude_code` beside a `--harness
    # claude-code` would be a second spelling of one identifier, which is the
    # kind of divergence that is cheap now and expensive at every later use.
    path: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]*$")]
    value: str | int | bool | list[str] | None
    source: Literal["default", "config_file", "command_argument"]


class ConfigReport(ContractModel):
    """The effective configuration, field by field."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    values: Annotated[list[ConfigValue], Field(min_length=1)]

    #: Absent until a file exists. Its absence is not an error: defaults are a
    #: complete configuration (`docs/contracts/cli-config.md`).
    config_path: str | None


class TelemetryStatus(ContractModel):
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


class SkillDelivery(ContractModel):
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

    #: `en` or `ru` when this installation wrote a locale, else `None`.
    locale: str | None = None

    #: Owned relative paths of the installed package. Empty when absent.
    files: list[str] = Field(default_factory=list[str])

    #: Every harness this build ships a native projection for.
    available_harnesses: list[str]
