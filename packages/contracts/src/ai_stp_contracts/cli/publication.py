"""Publication plans, publication sets, promotion and signed attestations."""

from typing import Annotated, Literal

from pydantic import ConfigDict, Field

from ai_stp_assurance import AuthorAttestation as AssuranceAuthorAttestation
from ai_stp_contracts.http import Timestamp, open_wire_object
from ai_stp_contracts.model import ContractModel
from ai_stp_contracts.publication import EvidenceBindingView, PublicationPlanResponse
from ai_stp_contracts.publication import ObjectKind as PublicationObjectKind
from ai_stp_foundation.digests import DIGEST_PATTERN


class PublicationPlanView(PublicationPlanResponse):
    """The wire publication plan returned unchanged through the CLI boundary."""


class PublicationSetMemberView(ContractModel):
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
    visibility: Literal["public", "private"] = "public"
    stable_id: str
    version: Annotated[str, Field(min_length=3, max_length=32)]

    #: Absent when this member needs no plan because it is public already.
    #: Distinguished from a plan that exists and has not been confirmed: one is
    #: nothing left to do, the other is the whole of what confirm will do.
    plan_id: str = ""
    plan_hash: str = ""
    state: str = ""
    evidence: list[EvidenceBindingView] = Field(default_factory=list[EvidenceBindingView])
    error_code: str | None = None

    #: Public before this set existed. Confirm skips it rather than replanning
    #: it, and it is listed anyway so the set describes the whole graph.
    already_published: bool = False


class PublicationSetView(ContractModel):
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


class ComponentPromotionPlan(ContractModel):
    """Ordinary publication plan produced from one embedded component (REQ-5714)."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    setup_id: Annotated[str, Field(min_length=1)]
    setup_version: Annotated[str, Field(pattern=r"^\d+\.\d+$")]
    source_component_id: Annotated[str, Field(min_length=1)]
    catalog_stable_id: Annotated[str, Field(min_length=1)]
    catalog_version: Annotated[str, Field(pattern=r"^\d+\.\d+$")]
    reused_passport: bool
    still_embedded: bool
    plan_id: str = ""
    plan_hash: str = ""
    state: str = ""


class CliSignedAttestation(AssuranceAuthorAttestation):
    """Locally signed full attestation plus its owner-only output location."""

    # Extends the assurance model rather than `ContractModel`; defers the same way.
    model_config = ConfigDict(defer_build=True)

    output_path: Annotated[str, Field(min_length=1)]
    attestation_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
