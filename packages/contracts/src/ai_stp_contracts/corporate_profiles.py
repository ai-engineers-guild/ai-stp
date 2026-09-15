"""Shared tenant presentation editor; ownership is not authorship or responsibility."""

import re
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ai_stp_contracts.corporate import AccountId, OrganizationId
from ai_stp_contracts.http import open_wire_object, strict_request_object
from ai_stp_contracts.owner import OwnerPresentationMedia
from ai_stp_contracts.public_profile import ProfileLink
from ai_stp_contracts.technology import TechnologyMutation
from ai_stp_contracts.text_safety import validate_public_text
from ai_stp_foundation.ids import stable_id_pattern

EntityProfileKind = Literal["team", "project", "employee", "technology"]


class EntityProfileSubject(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    subject_kind: EntityProfileKind
    subject_id: Annotated[str, Field(min_length=1, max_length=64)]

    @model_validator(mode="after")
    def typed_identity(self) -> Self:
        prefix = {
            "team": "operation",
            "project": "remote_project",
            "employee": "account",
            "technology": "technology",
        }[self.subject_kind]
        if not re.fullmatch(stable_id_pattern(prefix), self.subject_id):
            raise ValueError("profile identity does not match subject kind")
        return self


class EntityProfileMedia(OwnerPresentationMedia):
    @model_validator(mode="after")
    def validate_source(self) -> Self:
        if re.fullmatch(r"/v1/media/avatars/avatar_[a-f0-9]{24}", self.url):
            if self.kind == "youtube":
                raise ValueError("YouTube media requires a video ID")
            return self
        OwnerPresentationMedia.model_validate(self.model_dump())
        return self


class EntityProfileUploadResponse(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    avatar_asset_id: str
    media_id: str
    public_url: str
    kind: Literal["image", "video"]
    state: Literal["ready"] = "ready"
    size_bytes: Annotated[int, Field(gt=0)]


class EntityProfileUploadQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    purpose: Literal["avatar", "media"]
    expected_revision: Annotated[int, Field(ge=0)]
    authorization_revision: Annotated[int, Field(ge=1)]


class EntityProfileFields(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    description: Annotated[str, Field(max_length=20000)] = ""
    avatar_asset_id: Annotated[str, Field(pattern=r"^avatar_[a-f0-9]{24}$")] | None = None
    links: Annotated[list[ProfileLink], Field(max_length=8)] = []
    media: Annotated[list[EntityProfileMedia], Field(max_length=5)] = []

    @field_validator("description")
    @classmethod
    def safe_description(cls, value: str) -> str:
        return validate_public_text(value, allow_empty=True)

    @field_validator("links")
    @classmethod
    def distinct_links(cls, value: list[ProfileLink]) -> list[ProfileLink]:
        if len({link.url for link in value}) != len(value):
            raise ValueError("duplicate link URL")
        return value


class EntityProfileWriteRequest(TechnologyMutation):
    fields: EntityProfileFields


class EntityProfileView(EntityProfileSubject):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    organization_id: OrganizationId
    name: str
    fields: EntityProfileFields
    revision: Annotated[int, Field(ge=0)]
    can_edit: bool
    avatar_url: str | None = None
    owner_account_id: AccountId | None = None


class TechnologyOwnerRequest(TechnologyMutation):
    owner_account_id: AccountId | None
