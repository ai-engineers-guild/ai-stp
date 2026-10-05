"""Public complaint intake, distinct from authenticated report cases."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import ConfigDict, Field

from ai_stp_contracts.http import Timestamp, open_wire_object, strict_request_object
from ai_stp_contracts.model import ContractModel
from ai_stp_foundation.ids import stable_id_pattern

type ComplaintTargetKind = Literal["author", "component", "setup", "other"]
type ComplaintId = Annotated[str, Field(pattern=stable_id_pattern("complaint"))]


class ComplaintCreateRequest(ContractModel):
    """POST /v1/complaints body. Anonymous callers omit a session."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    target_kind: ComplaintTargetKind
    target: Annotated[str, Field(min_length=1, max_length=256)]
    sender_name: Annotated[str, Field(min_length=1, max_length=120)]
    reply_email: Annotated[
        str,
        Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$"),
    ]
    subject: Annotated[str, Field(min_length=1, max_length=160)]
    message: Annotated[str, Field(min_length=10, max_length=4000)]


class ComplaintCreateResponse(ContractModel):
    """Acceptance of a stored complaint. The message is not echoed."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    complaint_id: ComplaintId
    accepted: Literal[True] = True
    created_at: Timestamp
