"""Sign-in, account and device payloads (issue #71, SPEC-002, SPEC-010, SPEC-011)."""

import re

import pytest
from pydantic import ValidationError

from ai_stp_contracts.auth import (
    PUBLIC_KEY_PATTERN,
    USER_CODE_PATTERN,
    DeviceAuthorizationRequest,
    DeviceAuthorizationResponse,
    DeviceTokenRequest,
    DeviceTokenResponse,
    OAuthCallbackResult,
)
from ai_stp_contracts.http import PAGE_SIZE_DEFAULT, PageInfo, http_status_for
from ai_stp_contracts.identity import (
    AccountProfile,
    DetectedHarness,
    DeviceListResponse,
    DeviceRecord,
    DeviceRevokeRequest,
    DeviceSummary,
)

ACCOUNT = "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z"
DEVICE = "device_01JQZK7B8N4M6P2R9T5V0X3Y7Z"
KEY = "A" * 43 + "="
MOMENT = "2026-08-05T00:00:00.000Z"


def summary(**overrides: object) -> DeviceSummary:
    fields: dict[str, object] = {
        "display_name": "rldyourmnd-ubuntu-1",
        "operating_system": "linux",
        "architecture": "x86_64",
        "detected_harnesses": [{"harness_id": "claude-code", "version": "2.1.0"}],
        "toolchain_profile_version": "mvp-full/1.0",
        "summary_updated_at": MOMENT,
    }
    return DeviceSummary.model_validate(fields | overrides)


def device_record(**overrides: object) -> DeviceRecord:
    fields: dict[str, object] = {
        "device_id": DEVICE,
        "state": "active",
        "registered_at": MOMENT,
        "last_active_at": MOMENT,
        "device_type": "cli",
        "approximate_location": None,
        "user_agent": None,
        "summary": summary(),
        "etag": 'W/"7"',
    }
    return DeviceRecord.model_validate(fields | overrides)


def authorization(**overrides: object) -> DeviceAuthorizationResponse:
    fields: dict[str, object] = {
        "device_code": "d" * 40,
        "user_code": "BCDF-GHJK",
        "verification_uri": "https://ai-stp.example/device",
        "verification_uri_complete": "https://ai-stp.example/device?code=BCDF-GHJK",
        "expires_in": 600,
        "interval": 5,
    }
    return DeviceAuthorizationResponse.model_validate(fields | overrides)


def token(**overrides: object) -> DeviceTokenResponse:
    fields: dict[str, object] = {
        "access_token": "at-value",
        "refresh_token": "rt-value",
        "expires_in": 3600,
        "account_id": ACCOUNT,
        "device_id": DEVICE,
    }
    return DeviceTokenResponse.model_validate(fields | overrides)


def test_starting_a_sign_in_carries_no_device_identity() -> None:
    # The key binds at exchange: before a human approves there is no account to
    # bind it to, and accepting one earlier would let an unauthenticated caller
    # park keys against pending codes.
    # The key that arrived with idempotency is not identity: it is chosen by the
    # client, opaque to the server and carries nothing about this machine.
    assert set(DeviceAuthorizationRequest.model_fields) == {
        "schema_version",
        "provider",
        "idempotency_key",
    }
    with pytest.raises(ValidationError):
        DeviceAuthorizationRequest.model_validate({"provider": "google", "public_key": KEY})


def test_the_exchange_is_what_binds_the_device_key() -> None:
    fields = set(DeviceTokenRequest.model_fields)
    assert {"device_code", "device_id", "public_key", "display_name"} <= fields


def test_only_the_two_mvp_providers_are_representable() -> None:
    key = "0123456789abcdef0123456789abcdef"
    for provider in ("google", "github"):
        assert (
            DeviceAuthorizationRequest(provider=provider, idempotency_key=key).provider == provider
        )
    with pytest.raises(ValidationError):
        DeviceAuthorizationRequest(provider="gitlab", idempotency_key=key)  # type: ignore[arg-type]


def test_starting_an_authorization_requires_a_key_of_the_declared_shape() -> None:
    # `http-api.md` has always required a key for creates and `DeviceRevokeRequest`
    # has always carried one; this request did not, so a client whose response was
    # lost had no way to retry without asking for a second authorization.
    with pytest.raises(ValidationError):
        DeviceAuthorizationRequest(provider="google")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        DeviceAuthorizationRequest(provider="google", idempotency_key="tooshort")


def test_the_user_code_alphabet_excludes_the_ambiguous_letters() -> None:
    # A human retypes this from a terminal into a browser.
    for ambiguous in ("IBCD-EFGH", "LBCD-EFGH", "OBCD-EFGH", "UBCD-EFGH"):
        assert re.match(USER_CODE_PATTERN, ambiguous) is None
    assert re.match(USER_CODE_PATTERN, "BCDF-GHJK") is not None


def test_the_user_code_separator_is_part_of_the_contract() -> None:
    assert re.match(USER_CODE_PATTERN, "BCDFGHJK") is None


def test_the_public_key_is_ed25519_shaped() -> None:
    assert re.match(PUBLIC_KEY_PATTERN, KEY) is not None
    # 64 bytes is a signature, not a key.
    assert re.match(PUBLIC_KEY_PATTERN, "A" * 86 + "==") is None


def test_the_verification_uri_is_ours_and_https() -> None:
    with pytest.raises(ValidationError):
        authorization(verification_uri="http://ai-stp.example/device")


def test_both_verification_forms_are_required() -> None:
    # The pre-filled URL is useless on a machine that cannot open a browser, so
    # the plain URI and the code stay required beside it.
    assert authorization().user_code == "BCDF-GHJK"
    with pytest.raises(ValidationError):
        DeviceAuthorizationResponse.model_validate(
            {
                "device_code": "d" * 40,
                "user_code": "BCDF-GHJK",
                "verification_uri_complete": "https://ai-stp.example/device?code=BCDF-GHJK",
                "expires_in": 600,
                "interval": 5,
            }
        )


def test_a_code_can_neither_be_immortal_nor_expire_before_a_human_acts() -> None:
    with pytest.raises(ValidationError):
        authorization(expires_in=59)
    with pytest.raises(ValidationError):
        authorization(expires_in=1801)


def test_the_poll_interval_is_bounded() -> None:
    with pytest.raises(ValidationError):
        authorization(interval=0)
    with pytest.raises(ValidationError):
        authorization(interval=61)


def test_secrets_are_kept_out_of_repr() -> None:
    # The commonest accident is an object interpolated into a log line.
    assert "at-value" not in repr(token())
    assert "rt-value" not in repr(token())
    assert "d" * 40 not in repr(authorization())


def test_a_pending_poll_is_a_typed_error_not_an_empty_token() -> None:
    # A client must never be able to mistake "not yet" for "no credentials".
    for code in (
        "AI_STP_AUTHORIZATION_PENDING",
        "AI_STP_AUTHORIZATION_EXPIRED",
        "AI_STP_AUTHORIZATION_DECLINED",
    ):
        assert http_status_for(code) == 400
    with pytest.raises(ValidationError):
        token(access_token="")


def test_a_conflict_names_no_account() -> None:
    # SPEC-002 REQ-202 forbids a silent merge, and naming the account a
    # conflicting address belongs to would disclose that it exists.
    result = OAuthCallbackResult(
        provider="google", status="conflict", account_id=None, completed_at=MOMENT
    )
    assert result.account_id is None


def test_the_device_summary_is_the_closed_five_facts() -> None:
    declared = set(DeviceSummary.model_fields) - {"schema_version"}
    assert declared == {
        "display_name",
        "operating_system",
        "architecture",
        "detected_harnesses",
        "toolchain_profile_version",
        "summary_updated_at",
    }


def test_the_summary_cannot_carry_environment_values_or_paths() -> None:
    # device-passport.md excludes secret values, environment variable values and
    # absolute user paths from anything that leaves the device.
    forbidden = {"env", "environment", "paths", "source_paths", "home", "secrets", "facts"}
    assert forbidden.isdisjoint(DeviceSummary.model_fields)


def test_an_unknown_harness_is_not_itemised_in_the_summary() -> None:
    # SPEC-011 REQ-1109: it stays a local observation and creates no managed
    # object, so it has nothing to say on the wire.
    with pytest.raises(ValidationError):
        DetectedHarness(harness_id="undefined", version="1.0")  # type: ignore[arg-type]


def test_a_device_without_a_summary_is_still_listed() -> None:
    # Synchronisation is off by default; the owner must still be able to see and
    # revoke a device that never published one.
    listed = DeviceListResponse(items=[device_record(summary=None)], page=page())
    assert listed.items[0].summary is None


def test_a_revoked_device_keeps_its_record_and_summary() -> None:
    # SPEC-002 REQ-205/REQ-215: revocation is forward-acting. The summary is
    # marked revoked, not deleted, and local data is untouched.
    revoked = device_record(state="revoked")
    assert revoked.state == "revoked"
    assert revoked.summary is not None


def test_revocation_requires_an_idempotency_key() -> None:
    with pytest.raises(ValidationError):
        DeviceRevokeRequest.model_validate({})
    with pytest.raises(ValidationError):
        DeviceRevokeRequest(idempotency_key="short")


def test_a_stale_precondition_is_distinct_from_a_conflict() -> None:
    assert http_status_for("AI_STP_PRECONDITION_FAILED") == 412
    assert http_status_for("AI_STP_CONFLICT") == 409


def test_the_account_read_carries_no_address() -> None:
    # Knowing an address is not an authorization, and the route exists to answer
    # "who am I" rather than to hand back personal data (SPEC-013).
    profile = AccountProfile(
        account_id=ACCOUNT,
        created_at=MOMENT,
        show_profile_publicly=True,
        allow_publisher_listing=True,
        identities=[
            {
                "provider": "github",
                "linked_at": MOMENT,
                "avatar_url": None,
                "display_name": None,
            }
        ],  # type: ignore[list-item]
    )
    assert {"email", "emails", "address"}.isdisjoint(AccountProfile.model_fields)
    assert {"email", "address"}.isdisjoint(type(profile.identities[0]).model_fields)


def test_an_account_always_has_at_least_one_identity() -> None:
    with pytest.raises(ValidationError):
        AccountProfile(
            account_id=ACCOUNT,
            created_at=MOMENT,
            identities=[],
            show_profile_publicly=True,
            allow_publisher_listing=True,
        )


def page() -> PageInfo:
    return PageInfo(next_cursor=None, page_size=PAGE_SIZE_DEFAULT)
