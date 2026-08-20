"""Device boundary DTOs."""

from __future__ import annotations

from datetime import datetime
from typing import cast

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ai_stp_api.slices.devices.domain import (
    FORBIDDEN_SUMMARY_FIELDS,
    assert_summary_keys,
    reject_forbidden_fields,
)


def _empty_harnesses() -> list[dict[str, str]]:
    return []


class ChallengeRequest(BaseModel):
    """Request a signed registration nonce for a candidate public key."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int | None = Field(default=None, ge=1, le=1)
    public_key: str = Field(min_length=32, max_length=512)


class ChallengeResponse(BaseModel):
    """Stateless signed challenge returned to the device."""

    nonce: str
    expires_in: int


class RegisterDeviceRequest(BaseModel):
    """Register or re-register a device by Ed25519 proof over a challenge."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int | None = Field(default=None, ge=1, le=1)
    public_key: str = Field(min_length=32, max_length=512)
    nonce: str = Field(min_length=16, max_length=2048)
    signature: str = Field(min_length=16, max_length=512)
    display_name: str | None = Field(default=None, max_length=120)

    @model_validator(mode="before")
    @classmethod
    def _reject_forbidden(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        # Registration accepts public_key/nonce/signature; still reject
        # full-passport and private-path fields (REQ-214).
        data_map = cast(dict[str, object], data)
        allowed = {
            "schema_version",
            "public_key",
            "nonce",
            "signature",
            "display_name",
        }
        private = sorted(set(data_map) & (FORBIDDEN_SUMMARY_FIELDS - allowed))
        if private:
            msg = f"forbidden device fields: {', '.join(private)}"
            raise ValueError(msg)
        extra = sorted(set(data_map) - allowed)
        if extra:
            msg = f"unknown fields: {', '.join(extra)}"
            raise ValueError(msg)
        return data_map


class DeviceSummaryDTO(BaseModel):
    """Closed-list device summary returned by list endpoints."""

    model_config = ConfigDict(extra="forbid")

    id: str
    state: str
    last_seen_at: datetime | None = None
    display_name: str | None = None
    os: str | None = None
    architecture: str | None = None
    harnesses: list[dict[str, str]] = Field(default_factory=_empty_harnesses)
    toolset_profile_version: str | None = None
    summary_updated_at: datetime | None = None

    @field_validator("state")
    @classmethod
    def _state_ok(cls, value: str) -> str:
        if value not in {"active", "revoked"}:
            msg = "state must be active or revoked"
            raise ValueError(msg)
        return value

    def model_dump_summary(self) -> dict[str, object]:
        data = self.model_dump(mode="json")
        assert_summary_keys(data)
        reject_forbidden_fields(data)
        return data


class DeviceListData(BaseModel):
    """List payload for GET /v1/devices."""

    devices: list[DeviceSummaryDTO]


class RegisterDeviceData(BaseModel):
    """Registration result."""

    device: DeviceSummaryDTO
    created: bool


class RevokeDeviceData(BaseModel):
    """Revocation result."""

    id: str
    state: str
