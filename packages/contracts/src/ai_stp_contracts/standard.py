"""Coordinated standard-family identity, distinct from envelope v1 and protocol v3.

`schema_version: 1`, HTTP `/v1`, kit `protocol_version` 3, and generator
generations such as `component-scaffold/6` are different axes. A textual
rename of any of them to "v1" would collide with objects that already use
that discriminator. The coordinated family is therefore a separate identity
(`ai-stp-standard/1`) with a contract digest over the inventory.

Field owner: this module and `schemas/v1/cli-standard-inventory.schema.json`.
Meaning: `docs/contracts/standard-family.md`. Requirements: SPEC-060.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Annotated, Final, Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from ai_stp_contracts.http import open_wire_object
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import DIGEST_PATTERN, digest_canonical

STANDARD_FAMILY: Final[Literal["ai-stp-standard/1"]] = "ai-stp-standard/1"
STANDARD_INVENTORY_DOMAIN: Final[str] = "ai-stp:standard-inventory:v1"
HTTP_API_IDENTITY: Final[str] = "/v1"
PROVIDER_PROTOCOL_IDENTITY: Final[str] = "3"
KIT_PROTOCOL_IDENTITY: Final[str] = "3"
COMPONENT_TEMPLATE_IDENTITY: Final[str] = "component-scaffold/6"
COMPONENT_GENERATOR_IDENTITY: Final[str] = "ai-stp/6"
SETUP_TEMPLATE_IDENTITY: Final[str] = "setup-scaffold/5"
SETUP_GENERATOR_IDENTITY: Final[str] = "ai-stp/5"

type ContractAxis = Literal[
    "standard_family",
    "http_api",
    "envelope",
    "http_schema",
    "exported_schema",
    "provider_protocol",
    "kit_protocol",
    "component_generator",
    "setup_generator",
    "unknown",
]

_PROTOCOL_AXES: Final[tuple[tuple[ContractAxis, str, str], ...]] = (
    (
        "standard_family",
        STANDARD_FAMILY,
        "Coordinated standard family; not envelope schema_version.",
    ),
    ("http_api", HTTP_API_IDENTITY, "HTTP path major; already named v1 on the wire."),
    (
        "envelope",
        "schema_version:1",
        "Document discriminator already used by old and current envelopes.",
    ),
    (
        "provider_protocol",
        PROVIDER_PROTOCOL_IDENTITY,
        "Capability-negotiated provider protocol (crate still provider-v3).",
    ),
    ("kit_protocol", KIT_PROTOCOL_IDENTITY, "Public provider kit protocol_version."),
    (
        "component_generator",
        COMPONENT_TEMPLATE_IDENTITY,
        "Component scaffold template generation, independent of the standard family.",
    ),
    (
        "setup_generator",
        SETUP_TEMPLATE_IDENTITY,
        "Setup scaffold template generation, independent of the standard family.",
    ),
)


class InventoryAxis(BaseModel):
    """One version axis the estate currently speaks."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    name: ContractAxis
    current_identity: Annotated[str, Field(min_length=1, max_length=128)]
    description: Annotated[str, Field(min_length=1, max_length=256)]


class InventoryMember(BaseModel):
    """One owner-controlled schema or protocol identity."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    axis: ContractAxis
    identity: Annotated[str, Field(min_length=1, max_length=256)]


class StandardInventory(BaseModel):
    """Machine inventory of the coordinated standard family and every other axis."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    standard_family: Literal["ai-stp-standard/1"] = STANDARD_FAMILY
    contract_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    axes: Annotated[list[InventoryAxis], Field(min_length=1)]
    members: Annotated[list[InventoryMember], Field(min_length=1)]


class Classification(BaseModel):
    """Which axis a document belongs to, and whether it is the current identity."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    axis: ContractAxis
    identity: Annotated[str, Field(min_length=1, max_length=256)]
    current: bool
    problems: tuple[str, ...] = ()


def inventory_for(schema_members: Sequence[tuple[str, str]]) -> StandardInventory:
    """Build the inventory from exported schema ids plus the closed protocol axes."""
    axes = [
        InventoryAxis(name=name, current_identity=identity, description=description)
        for name, identity, description in _PROTOCOL_AXES
    ]
    members = [
        InventoryMember(axis=name, identity=identity)
        for name, identity, _description in _PROTOCOL_AXES
    ]
    for axis_name, identity in schema_members:
        axis = cast(ContractAxis, axis_name)
        members.append(InventoryMember(axis=axis, identity=identity))
    members.sort(key=lambda item: (item.axis, item.identity))
    payload: dict[str, JsonValue] = {
        "standard_family": STANDARD_FAMILY,
        "axes": [{"name": axis.name, "current_identity": axis.current_identity} for axis in axes],
        "members": [{"axis": member.axis, "identity": member.identity} for member in members],
    }
    digest = digest_canonical(STANDARD_INVENTORY_DOMAIN, payload)
    return StandardInventory(contract_digest=digest, axes=axes, members=members)


def classify(document: Mapping[str, object]) -> Classification:
    """Assign a document to one axis without treating every integer 1 as the family.

    First match wins. `standard_family` is the only key that selects the
    coordinated family. A kit or provider object that uses `protocol_version: 1`
    after a naive rename is still not the family, and not an envelope.
    """
    family = document.get("standard_family")
    if family is not None:
        identity = str(family)
        problems: list[str] = []
        if identity != STANDARD_FAMILY:
            problems.append("standard_family is not the coordinated family identity")
        digest = document.get("contract_digest")
        if digest is not None and not isinstance(digest, str):
            problems.append("contract_digest is not a string")
        return Classification(
            axis="standard_family",
            identity=identity,
            current=identity == STANDARD_FAMILY and not problems,
            problems=tuple(problems),
        )

    template = document.get("template_version")
    if isinstance(template, str) and template.startswith("component-scaffold/"):
        return Classification(
            axis="component_generator",
            identity=template,
            current=template == COMPONENT_TEMPLATE_IDENTITY,
        )
    if isinstance(template, str) and template.startswith("setup-scaffold/"):
        return Classification(
            axis="setup_generator",
            identity=template,
            current=template == SETUP_TEMPLATE_IDENTITY,
        )

    if "kit_version" in document:
        protocol = document.get("protocol_version")
        identity = str(protocol) if protocol is not None else "unknown"
        return Classification(
            axis="kit_protocol",
            identity=identity,
            current=identity == KIT_PROTOCOL_IDENTITY,
        )

    if "protocol_version" in document:
        identity = str(document.get("protocol_version"))
        return Classification(
            axis="provider_protocol",
            identity=identity,
            current=identity == PROVIDER_PROTOCOL_IDENTITY,
        )

    if "schema_version" in document:
        identity = f"schema_version:{document.get('schema_version')}"
        return Classification(
            axis="envelope",
            identity=identity,
            current=document.get("schema_version") == 1,
        )

    return Classification(axis="unknown", identity="unknown", current=False)
