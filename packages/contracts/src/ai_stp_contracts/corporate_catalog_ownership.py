"""Tenant operational ownership is independent of immutable catalog authorship."""

import re
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_stp_contracts.corporate import AccountId, OrganizationId
from ai_stp_contracts.http import IdempotencyKey, open_wire_object, strict_request_object
from ai_stp_foundation.ids import stable_id_pattern
from ai_stp_foundation.versioning import VERSION_PATTERN


class CorporateCatalogOwnershipQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    object_kind: Literal["setup", "component"]
    stable_id: Annotated[str, Field(min_length=1, max_length=64)]
    version: Annotated[str, Field(pattern=VERSION_PATTERN)]

    @model_validator(mode="after")
    def typed_identity(self) -> Self:
        if not re.fullmatch(stable_id_pattern(self.object_kind), self.stable_id):
            raise ValueError("catalog identity does not match its kind")
        return self


class CorporateCatalogOwnershipRequest(CorporateCatalogOwnershipQuery):
    schema_version: Literal[1] = 1
    owner_account_id: AccountId | None
    expected_revision: Annotated[int, Field(ge=0)]
    authorization_revision: Annotated[int, Field(ge=1)]
    idempotency_key: IdempotencyKey

    @model_validator(mode="after")
    def retained_clear(self) -> Self:
        if self.owner_account_id is None and self.expected_revision == 0:
            raise ValueError("clearing ownership requires its retained revision")
        return self


class CorporateCatalogOwnership(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    organization_id: OrganizationId
    object_kind: Literal["setup", "component"]
    stable_id: str
    owner_account_id: AccountId | None
    revision: Annotated[int, Field(ge=0)]
    owner_display_name: str | None
    can_edit: bool
