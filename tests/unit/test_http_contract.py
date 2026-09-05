"""Shared /v1 wire conventions (issue #71, docs/contracts/http-api.md)."""

import re

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from ai_stp_contracts.http import (
    API_BASE_PATH,
    CURSOR_PATTERN,
    IDEMPOTENCY_KEY_PATTERN,
    PAGE_SIZE_DEFAULT,
    PAGE_SIZE_MAX,
    SCHEMA_VERSION,
    PageInfo,
    http_status_for,
)
from ai_stp_foundation.errors import ERROR_CODES

#: The exact status of every registered code. Spelled out rather than derived,
#: because the derivation is the thing under test: an assertion computed from
#: the same table it checks cannot fail.
EXPECTED_STATUS: dict[str, int] = {
    "AI_STP_VALIDATION_ERROR": 400,
    "AI_STP_UNSUPPORTED_APPLY": 400,
    "AI_STP_NOT_FOUND": 404,
    "AI_STP_SCHEMA_UNSUPPORTED": 400,
    "AI_STP_AUTH_REQUIRED": 401,
    "AI_STP_AUTHORIZATION_PENDING": 400,
    "AI_STP_AUTHORIZATION_EXPIRED": 400,
    "AI_STP_AUTHORIZATION_DECLINED": 400,
    "AI_STP_PERMISSION_DENIED": 403,
    "AI_STP_DEVICE_REVOKED": 403,
    "AI_STP_CONFLICT": 409,
    "AI_STP_PLAN_STALE": 409,
    "AI_STP_PRECONDITION_FAILED": 412,
    "AI_STP_USER_DECISION_REQUIRED": 409,
    "AI_STP_RATE_LIMITED": 429,
    "AI_STP_DEPENDENCY_UNAVAILABLE": 503,
    "AI_STP_TIMEOUT_UNCONFIRMED": 504,
    "AI_STP_PARTIAL_OPERATION": 500,
    "AI_STP_CATALOG_INTEGRITY": 500,
    "AI_STP_SEO_FACTS_INVALID": 400,
    "AI_STP_SEO_OUTPUT_INVALID": 400,
    "AI_STP_SEO_ENRICHMENT_UNAVAILABLE": 503,
    "AI_STP_SEO_SOURCE_STALE": 409,
    "AI_STP_SEO_RENDER_FAILED": 500,
    "AI_STP_CONTENT_INVALID": 400,
    "AI_STP_CONTENT_SOURCE_CONFLICT": 409,
    "AI_STP_CONTENT_STALE": 409,
    "AI_STP_CONTENT_IMPORT_FORBIDDEN": 403,
    "AI_STP_HANDLE_CONFLICT": 409,
    "AI_STP_ACCOUNT_DISPLAY_NAME_CONFLICT": 409,
    "AI_STP_CANONICAL_NAME_CONFLICT": 409,
    "AI_STP_FOREIGN_LINE_OWNERSHIP": 409,
    "AI_STP_STALE_OWNERSHIP_REVISION": 409,
    "AI_STP_LOCALIZED_NAME_CONFLICT": 409,
    "AI_STP_MIGRATION_CONFLICT": 409,
    "AI_STP_MANIFEST_MISMATCH": 409,
    "AI_STP_SYNC_DELIVERY": 503,
    "AI_STP_INTERNAL": 500,
}


def valid_page() -> dict[str, str | int | None]:
    return {"schema_version": 1, "next_cursor": None, "page_size": PAGE_SIZE_DEFAULT}


def schema_accepts(schema: dict[str, object], instance: object) -> bool:
    """Validate through the published schema, as an external consumer would."""
    validator = Draft202012Validator(schema)  # pyright: ignore[reportArgumentType]
    return validator.is_valid(instance)  # pyright: ignore[reportUnknownMemberType, reportArgumentType]


def test_the_expected_table_covers_the_registry_exactly() -> None:
    # A new code without a decided status must fail here, not at the first
    # route that tries to return it.
    assert set(EXPECTED_STATUS) == set(ERROR_CODES)


@pytest.mark.parametrize(("code", "status"), sorted(EXPECTED_STATUS.items()))
def test_each_code_maps_to_its_exact_status(code: str, status: int) -> None:
    assert http_status_for(code) == status


def test_rate_limiting_is_not_collapsed_into_unavailable() -> None:
    # Clients and proxies special-case 429 for backoff; answering 503 makes
    # them hammer the platform through the outage.
    assert http_status_for("AI_STP_RATE_LIMITED") == 429
    assert http_status_for("AI_STP_DEPENDENCY_UNAVAILABLE") == 503


def test_device_flow_states_keep_their_own_codes_on_a_shared_status() -> None:
    # RFC 8628 puts all three on 400; the stable code stays the machine
    # identifier, so a shared status never collapses distinct outcomes.
    states = (
        "AI_STP_AUTHORIZATION_PENDING",
        "AI_STP_AUTHORIZATION_EXPIRED",
        "AI_STP_AUTHORIZATION_DECLINED",
    )
    assert {http_status_for(code) for code in states} == {400}
    assert len(set(states)) == 3


def test_unregistered_code_has_no_status() -> None:
    with pytest.raises(KeyError):
        http_status_for("AI_STP_NOT_A_REAL_CODE")


def test_base_path_and_schema_version_are_the_declared_major() -> None:
    assert API_BASE_PATH == "/v1"
    assert SCHEMA_VERSION == 1


# Asserted with `re.match`, never `re.fullmatch`: fullmatch supplies the
# anchoring these tests exist to verify, so a pattern that lost its ^ and $
# would still reject every case below and the suite would stay green.
@pytest.mark.parametrize("value", ["a", "A_b-c", "0" * 512])
def test_cursor_accepts_opaque_url_safe_tokens(value: str) -> None:
    assert re.match(CURSOR_PATTERN, value) is not None


@pytest.mark.parametrize("value", ["", "0" * 513, "has space", "has/slash", "has=pad"])
def test_cursor_rejects_unbounded_or_unsafe_tokens(value: str) -> None:
    assert re.match(CURSOR_PATTERN, value) is None


def test_cursor_pattern_is_anchored_at_both_ends() -> None:
    # The de-anchored form would accept a prefix of every reject-case above.
    deanchored = CURSOR_PATTERN.removeprefix("^").removesuffix("$")
    assert re.match(deanchored, "has space") is not None
    assert re.match(CURSOR_PATTERN, "has space") is None


@pytest.mark.parametrize("value", ["0123456789abcdef", "a" * 128, "a.b~c-d_e" + "f" * 7])
def test_idempotency_key_accepts_bounded_client_tokens(value: str) -> None:
    assert re.match(IDEMPOTENCY_KEY_PATTERN, value) is not None


@pytest.mark.parametrize("value", ["short", "a" * 129, "has space"])
def test_idempotency_key_rejects_short_or_unbounded_tokens(value: str) -> None:
    assert re.match(IDEMPOTENCY_KEY_PATTERN, value) is None


def test_trailing_newline_divergence_is_pinned_not_accidental() -> None:
    # `$` matches before a trailing newline in Python's `re` — what a JSON
    # Schema validator runs — but not in the Rust regex pydantic runs. It
    # cannot be closed in one pattern string: \Z/\z are not ECMA-262 and a
    # (?![\s\S]) lookahead makes pydantic fail to build the validator at all.
    # Pin both sides so a later "fix" cannot silently pick the other one.
    assert schema_accepts({"pattern": CURSOR_PATTERN}, "abc\n")
    with pytest.raises(ValidationError):
        PageInfo(next_cursor="abc\n", page_size=PAGE_SIZE_DEFAULT)


def test_page_size_is_bounded_on_both_ends() -> None:
    assert PageInfo(next_cursor=None, page_size=PAGE_SIZE_MAX).page_size == PAGE_SIZE_MAX
    with pytest.raises(ValidationError):
        PageInfo(next_cursor=None, page_size=PAGE_SIZE_MAX + 1)
    with pytest.raises(ValidationError):
        PageInfo(next_cursor=None, page_size=0)


def test_cursor_and_page_size_are_required_not_defaulted() -> None:
    # A default would let the model accept a document the published schema
    # rejects, and a dropped next_cursor would read as "last page" — turning a
    # truncated search into a confident "no such component".
    with pytest.raises(ValidationError):
        PageInfo.model_validate({})
    with pytest.raises(ValidationError):
        PageInfo.model_validate({"page_size": PAGE_SIZE_DEFAULT})


def test_the_model_and_the_published_schema_accept_the_same_document() -> None:
    schema = PageInfo.model_json_schema()
    assert schema_accepts(schema, valid_page())
    assert PageInfo.model_validate(valid_page()).next_cursor is None
    # The empty document must be rejected by both halves, not just one.
    assert not schema_accepts(schema, {})
    with pytest.raises(ValidationError):
        PageInfo.model_validate({})


def test_schema_version_is_the_one_documented_default() -> None:
    # The wire policy allows a Python default only on a constant discriminant.
    # The model therefore fills schema_version while the schema still requires
    # it - a bounded, deliberate divergence: Literal[1] admits exactly one
    # value, so absence cannot mask a server error the way a dropped cursor can.
    without = {key: value for key, value in valid_page().items() if key != "schema_version"}
    assert PageInfo.model_validate(without).schema_version == 1
    assert not schema_accepts(PageInfo.model_json_schema(), without)
    defaulted = [name for name, field in PageInfo.model_fields.items() if not field.is_required()]
    assert defaulted == ["schema_version"]


def test_an_additive_field_is_accepted_and_preserved() -> None:
    # The schema says additionalProperties:true, so the model must agree, and
    # schema-evolution.md requires a reader to preserve an unknown optional
    # value rather than drop it.
    page = PageInfo.model_validate(valid_page() | {"next_page_hint": "later"})
    assert page.model_dump()["next_page_hint"] == "later"


def test_page_info_exposes_no_total_count() -> None:
    # A total would let a caller detect objects it is not allowed to read.
    assert {"total", "total_count", "count"}.isdisjoint(PageInfo.model_fields)


def test_wire_schema_requires_declared_fields_and_tolerates_additions() -> None:
    schema = PageInfo.model_json_schema()
    assert schema["required"] == sorted(schema["properties"])
    assert schema["additionalProperties"] is True
