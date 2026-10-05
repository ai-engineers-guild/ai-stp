"""The CLI's own update: check, plan, result and status."""

from typing import Annotated, Literal

from pydantic import ConfigDict, Field

from ai_stp_contracts.http import open_wire_object
from ai_stp_contracts.model import ContractModel
from ai_stp_foundation.digests import DIGEST_PATTERN

type CliInstallMethod = Literal[
    "uv_tool",
    "pipx",
    "pip_venv",
    "shared_environment",
    "system_environment",
    "source_managed",
]


type CliUpdateCheckState = Literal[
    "current",
    "available",
    "unknown",
    "stale",
    "unsupported",
    "source_managed",
]


type CliUpdateJournalState = Literal[
    "idle",
    "planned",
    "downloaded",
    "applying",
    "pending",
    "verified",
    "recovery_required",
    "rolled_back",
    "failed",
]


type CliUpdateApplyOutcome = Literal[
    "replaced",
    "unchanged",
    "pending",
    "recovered",
    "rolled_back",
    "refused",
]


class CliSelfUpdateCheck(ContractModel):
    """What `update check` observed, including why nothing is offered."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    state: CliUpdateCheckState
    distribution: Literal["ai-stp-cli"] = "ai-stp-cli"
    installed_version: Annotated[str, Field(min_length=1)]
    python_version: Annotated[str, Field(pattern=r"^\d+\.\d+\.\d+")]
    install_method: CliInstallMethod
    executable: Annotated[str, Field(min_length=1)]
    install_root: Annotated[str, Field(min_length=1)]
    channel: Literal["stable", "prerelease"]
    candidate_version: str = ""
    candidate_filename: str = ""
    candidate_digest: Annotated[str, Field(pattern=rf"^(?:{DIGEST_PATTERN})?$")] = ""
    index_origin: Annotated[str, Field(min_length=1)]
    simple_index_ready: bool = False
    cache_age_seconds: Annotated[int, Field(ge=0)] | None = None
    reason: Annotated[str, Field(min_length=1)]


class CliSelfUpdatePlan(ContractModel):
    """Exact replacement of this CLI distribution (`SPEC-072`)."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    plan_id: Annotated[str, Field(min_length=1)]
    source_version: Annotated[str, Field(min_length=1)]
    target_version: Annotated[str, Field(min_length=1)]
    python_version: Annotated[str, Field(pattern=r"^\d+\.\d+\.\d+")]
    install_method: CliInstallMethod
    executable: Annotated[str, Field(min_length=1)]
    install_root: Annotated[str, Field(min_length=1)]
    receipt_fingerprint: Annotated[str, Field(min_length=1)]
    distribution: Literal["ai-stp-cli"] = "ai-stp-cli"
    artifact_filename: Annotated[str, Field(min_length=1)]
    artifact_url: Annotated[str, Field(min_length=1)]
    artifact_bytes: Annotated[int, Field(ge=0)]
    artifact_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    index_origin: Annotated[str, Field(min_length=1)]
    channel: Literal["stable", "prerelease"]
    installer_argv: Annotated[list[str], Field(min_length=1)]
    installer_environment: dict[str, str] = Field(default_factory=dict)
    restart_effect: Literal["new_process_required"] = "new_process_required"
    data_backup: Annotated[str, Field(min_length=1)]
    rollback_available: bool
    apply_ready: bool
    reason: Annotated[str, Field(min_length=1)]
    plan_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]


class CliSelfUpdateResult(ContractModel):
    """Outcome of apply, recover or rollback."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    outcome: CliUpdateApplyOutcome
    journal_state: CliUpdateJournalState
    installed_version: Annotated[str, Field(min_length=1)]
    target_version: Annotated[str, Field(min_length=1)]
    executable: Annotated[str, Field(min_length=1)]
    plan_digest: Annotated[str, Field(pattern=rf"^(?:{DIGEST_PATTERN})?$")] = ""
    rollback_digest: Annotated[str, Field(pattern=rf"^(?:{DIGEST_PATTERN})?$")] = ""
    reason: Annotated[str, Field(min_length=1)]


class CliSelfUpdateStatus(ContractModel):
    """Journal plus the distribution a new process actually imported."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    journal_state: CliUpdateJournalState
    installed_version: Annotated[str, Field(min_length=1)]
    target_version: str = ""
    previous_version: str = ""
    install_method: CliInstallMethod
    executable: Annotated[str, Field(min_length=1)]
    plan_digest: Annotated[str, Field(pattern=rf"^(?:{DIGEST_PATTERN})?$")] = ""
    rollback_digest: Annotated[str, Field(pattern=rf"^(?:{DIGEST_PATTERN})?$")] = ""
    reason: Annotated[str, Field(min_length=1)]
