"""Provider installation checks and provider replacement."""

from typing import Annotated, Literal

from pydantic import ConfigDict, Field

from ai_stp_contracts.http import open_wire_object
from ai_stp_contracts.model import ContractModel
from ai_stp_foundation.digests import DIGEST_PATTERN


class ProviderInstallationCheck(ContractModel):
    """One harness's provider installation against its pinned release source (`#452`).

    `status` is one word and every one of them is an outcome, including the ones
    that are not answers: a release source that cannot be reached is
    `source_unavailable`, not silence and not a guess at the newest version.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    harness_id: Annotated[str, Field(min_length=1)]

    status: Literal[
        "up_to_date",
        "update_available",
        "unknown_version",
        "source_unavailable",
        "unsupported_platform",
        "unmanaged",
        "missing",
        "ambiguous",
    ]

    #: Absolute path to the executable that would run, and how it was chosen.
    #: Empty when nothing resolved, which the status already says.
    path: str = ""
    source: Literal["argument", "config", "chosen", "discovered", ""] = ""

    provider_id: str = ""
    provider_version: str = ""

    #: The newest suitable release, when the source could be asked. `latest`,
    #: `main` and pre-releases never appear here: `#452` requires an exact tag,
    #: and a floating name is not one.
    latest_tag: str = ""
    latest_commit: str = ""
    repository: str = ""

    #: Why this status, in the user's terms. Always present, because a status
    #: nobody can act on is a status that has not been reported.
    reason: Annotated[str, Field(min_length=1)]

    #: Every provider found when more than one was, so an ambiguous machine
    #: shows its candidates instead of having one picked for it.
    candidates: list[str] = []

    checked_at: str = ""


class ProviderInstallationReport(ContractModel):
    """Every harness asked about, in a fixed order (`#452`)."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    installations: list[ProviderInstallationCheck] = []

    #: Whether the release source was consulted at all. False after `--offline`
    #: or a source that could not be reached, and it is reported rather than
    #: inferred from empty tags.
    source_consulted: bool = False


class ProviderReplacementPlan(ContractModel):
    """What replacing one provider executable would do, exactly (`#452`).

    A plan, not an installation. Every field a user needs to decide is here —
    where it would write, what it would replace, the exact bytes it would fetch
    and the trust verdict on them — because a confirmation given against a
    summary is a confirmation of something else.

    Replacing a provider does not touch a harness target. That is still the
    provider's own operation, planned and confirmed on its own.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    harness_id: Annotated[str, Field(min_length=1)]
    operation: Literal["update", "reinstall"]

    #: Where the executable would be written, and what is there now. `path` is
    #: absolute so it can be acted on; the home directory is folded only when
    #: a human reads it.
    path: Annotated[str, Field(min_length=1)]
    current_version: str = ""
    current_digest: str = ""

    #: Exactly what would be installed. A floating name never appears: the tag
    #: is resolved before the plan is made, so the digest belongs to it.
    repository: Annotated[str, Field(min_length=1)]
    tag: Annotated[str, Field(min_length=1)]
    commit: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    provider_id: Annotated[str, Field(min_length=1)]
    provider_version: Annotated[str, Field(min_length=1)]
    artifact_url: Annotated[str, Field(min_length=1)]
    artifact_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    artifact_bytes: Annotated[int, Field(ge=0)] = 0
    trust_level: Literal["verified_publisher", "build_attested"]

    #: Where the replaced executable would be kept, so a failed replacement has
    #: something to come back to.
    backup: str = ""

    #: Whether the executable being replaced was put there by something other
    #: than `ai-stp`. Such a file is never overwritten without `--adopt`.
    foreign: bool = False

    #: The digest `apply` must be given. Recomputed there rather than trusted,
    #: so a plan that has gone stale refuses instead of installing.
    plan_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    idempotency_key: Annotated[str, Field(min_length=1)]


class ProviderReplacementResult(ContractModel):
    """What replacing a provider actually did (`#452`)."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    harness_id: Annotated[str, Field(min_length=1)]
    operation: Literal["update", "reinstall"]

    #: `replaced`, or `unchanged` when the exact bytes were already in place.
    #: Idempotent by digest: running it twice installs once.
    outcome: Literal["replaced", "unchanged"]

    path: Annotated[str, Field(min_length=1)]
    previous_version: str = ""
    provider_version: Annotated[str, Field(min_length=1)]
    tag: Annotated[str, Field(min_length=1)]
    artifact_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    backup: str = ""
    plan_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
