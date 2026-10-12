"""Ordered, principal-specific entity menus; never authorization tokens."""

from typing import Annotated, Literal

from pydantic import ConfigDict, Field

from ai_stp_contracts.http import open_wire_object, strict_request_object
from ai_stp_contracts.model import ContractModel

EntityKind = Literal[
    "component",
    "setup",
    "team",
    "project",
    "member",
    "technology",
    "category",
    "area",
    "job_title",
    "role",
    "grant",
    "invitation",
    "finding",
    "publisher",
    "scan",
]


class EntityActionSubject(ContractModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    kind: EntityKind
    id: Annotated[str, Field(min_length=1, max_length=128)]
    organization_id: Annotated[str, Field(min_length=1, max_length=64)] | None = None
    view: Literal["landscape", "detail"] | None = None
    assignment_id: Annotated[str, Field(min_length=1, max_length=64)] | None = None
    finding_kind: Literal["package", "image", "executable", "configuration", "alias"] | None = None
    coordinate: Annotated[str, Field(min_length=1, max_length=512)] | None = None
    usage_context: Literal["production", "development", "testing", "browser_support"] | None = None


class EntityAction(ContractModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    id: str
    group: Literal["navigation", "sharing", "management", "danger", "support"]


class EntityActionMenu(ContractModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    subject: EntityActionSubject
    href: str | None = None
    revision: int | None = None
    authorization_revision: int | None = None
    object_version: str | None = None
    object_name: str | None = None
    visibility: Literal["public", "private"] | None = None
    device_id: str | None = None
    actions: list[EntityAction]


class EntityActionQuery(ContractModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    schema_version: Literal[1] = 1
    subjects: Annotated[list[EntityActionSubject], Field(min_length=1, max_length=256)]


class EntityActionMenus(ContractModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    items: list[EntityActionMenu]
