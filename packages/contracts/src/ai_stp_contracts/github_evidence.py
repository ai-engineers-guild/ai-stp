"""Local GitHub repository lifecycle evidence (SPEC-044)."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_stp_contracts.http import Timestamp


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class GitHubArchiveEvidence(_Closed):
    schema_version: Literal[1] = 1
    observation_id: Annotated[int, Field(gt=0)] | None
    stable_id: Annotated[str, Field(min_length=1)]
    version: Annotated[str, Field(pattern=r"^[0-9]+\.[0-9]+$")]
    passport_digest: Annotated[str, Field(min_length=1)]
    source_repository: Annotated[str, Field(pattern=r"^https://github\.com/[^/]+/[^/]+$")]
    repository_id: Annotated[int, Field(gt=0)] | None
    repository_full_name: Annotated[str, Field(pattern=r"^[^/\s]+/[^/\s]+$")] | None
    repository_state: Literal["active", "archived", "unavailable"]
    archived: bool | None
    fetched_at: Timestamp | None
    expires_at: Timestamp | None
    freshness: Literal["fresh", "stale", "unavailable"]
    proposal: Literal["none", "deprecated"] = "none"
    attribution: Literal["github-rest-repository/2022-11-28"] = "github-rest-repository/2022-11-28"

    @model_validator(mode="after")
    def _coherent_state(self) -> "GitHubArchiveEvidence":
        missing = self.repository_state == "unavailable"
        if missing != (self.archived is None):
            raise ValueError("unavailable repository state alone omits archived")
        if missing != (self.repository_id is None or self.repository_full_name is None):
            raise ValueError("unavailable repository state alone omits repository identity")
        if missing != (self.fetched_at is None or self.expires_at is None):
            raise ValueError("unavailable repository state alone omits observation time")
        if (self.proposal == "deprecated") != (self.archived is True):
            raise ValueError("only archived evidence proposes deprecation")
        return self


class GitHubArchiveHistory(_Closed):
    schema_version: Literal[1] = 1
    stable_id: Annotated[str, Field(min_length=1)]
    version: Annotated[str, Field(pattern=r"^[0-9]+\.[0-9]+$")]
    observations: list[GitHubArchiveEvidence]
