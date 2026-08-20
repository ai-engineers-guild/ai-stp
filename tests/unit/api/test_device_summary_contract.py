"""Golden contract for device summary closed field list (SPEC-002 REQ-214)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from ai_stp_api.slices.devices.domain import (
    FORBIDDEN_SUMMARY_FIELDS,
    SUMMARY_FIELDS,
    DeviceSummary,
    assert_summary_keys,
    reject_forbidden_fields,
)
from ai_stp_api.slices.devices.dto import DeviceSummaryDTO, RegisterDeviceRequest

pytestmark = pytest.mark.platform


def test_summary_as_dict_only_exposes_closed_list() -> None:
    summary = DeviceSummary(
        id="device_01HZYEXAMPLE0000000000000",
        state="active",
        last_seen_at=datetime(2026, 8, 6, tzinfo=UTC),
        display_name="laptop",
        os="windows",
        architecture="x86_64",
        harnesses=({"name": "claude-code", "version": "1.0.0"},),
        toolset_profile_version="mvp-full@1",
        summary_updated_at=datetime(2026, 8, 6, tzinfo=UTC),
    )
    data = summary.as_dict()
    assert set(data) == SUMMARY_FIELDS
    assert_summary_keys(data)
    for forbidden in FORBIDDEN_SUMMARY_FIELDS:
        assert forbidden not in data


def test_reject_full_passport_and_private_path_fields() -> None:
    with pytest.raises(ValueError, match="forbidden"):
        reject_forbidden_fields({"id": "x", "absolute_path": "/home/user/secret"})
    with pytest.raises(ValueError, match="forbidden"):
        reject_forbidden_fields({"env": {"TOKEN": "x"}})
    with pytest.raises(ValueError, match="forbidden"):
        reject_forbidden_fields({"private_key": "x", "full_passport": {}})


def test_register_request_rejects_private_fields() -> None:
    with pytest.raises(ValidationError):
        RegisterDeviceRequest.model_validate(
            {
                "public_key": "a" * 43,
                "nonce": "n" * 20,
                "signature": "s" * 20,
                "absolute_path": "/Users/me/.ssh",
            }
        )


def test_summary_dto_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        DeviceSummaryDTO.model_validate(
            {
                "id": "device_01HZYEXAMPLE0000000000000",
                "state": "active",
                "private_key": "nope",
            }
        )


def test_register_request_rejects_unknown_public_fields() -> None:
    with pytest.raises(ValidationError, match="unknown fields"):
        RegisterDeviceRequest.model_validate(
            {
                "public_key": "a" * 43,
                "nonce": "n" * 20,
                "signature": "s" * 20,
                "nickname": "unexpected",
            }
        )


def test_register_request_non_mapping_input_uses_standard_model_validation() -> None:
    with pytest.raises(ValidationError):
        RegisterDeviceRequest.model_validate("not-a-mapping")


def test_summary_dto_rejects_unknown_state_and_dumps_closed_list() -> None:
    with pytest.raises(ValidationError, match="active or revoked"):
        DeviceSummaryDTO(id="device_example", state="pending")

    summary = DeviceSummaryDTO(id="device_example", state="revoked")
    assert set(summary.model_dump_summary()) == SUMMARY_FIELDS

    with pytest.raises(ValueError, match="summary contains"):
        assert_summary_keys({"private": "leak"})
