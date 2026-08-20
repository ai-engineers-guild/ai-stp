"""The shared fixture corpus agrees with the models and covers the surface.

The corpus is the one artifact both tracks replay, so it is worth more than the
sum of its cases only if it is provably consistent with the contract. These
tests are what make it so: every positive body must validate, every
`invalid_response` body must fail, every rejection must name a registered code
whose status matches the closed registry, and every operation must be covered.
"""

import json
from pathlib import Path
from typing import cast

import pytest
from jsonschema import Draft202012Validator
from pydantic import BaseModel, ValidationError

from ai_stp_contracts.fixtures import FixtureCase, cases_of_kind, load_cases
from ai_stp_contracts.http import http_status_for
from ai_stp_contracts.openapi import AUTHENTICATED_ERRORS, COMMON_ERRORS, OPERATIONS, Operation
from ai_stp_contracts.schemas import CONTRACT_MODELS
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.errors import ERROR_CODES
from ai_stp_passports.envelope import derive_revision_id

BY_ID = {operation.operation_id: operation for operation in OPERATIONS}

#: Both kinds carry a body a conforming server may send, so both must validate.
#: They differ only in whether a request can select them.
VALIDATING = cases_of_kind("positive") + cases_of_kind("example")


def response_model(operation: Operation, status: int) -> type[BaseModel]:
    """The model a conforming server uses for this status.

    Every fixture describes a JSON answer, so a route that streams bytes has no
    case here and never reaches this. Asserting that rather than returning
    `None` keeps the corpus honest: a binary fixture would be a fixture nothing
    could validate.
    """
    extra = operation.extra_responses.get(status)
    if extra is not None:
        return extra
    assert operation.response is not None, (
        f"{operation.operation_id} answers with bytes and cannot have a JSON fixture"
    )
    return operation.response


def ids(cases: tuple[FixtureCase, ...]) -> list[str]:
    return [case.case_id for case in cases]


def test_the_corpus_is_not_empty() -> None:
    assert len(load_cases()) >= 20


def test_case_ids_are_unique() -> None:
    all_ids = ids(load_cases())
    assert sorted(all_ids) == sorted(set(all_ids))


def test_every_case_names_a_real_operation() -> None:
    for case in load_cases():
        assert case.operation_id in BY_ID, case.case_id


@pytest.mark.parametrize("case", VALIDATING, ids=ids(VALIDATING))
def test_a_valid_body_validates_against_its_response_model(case: FixtureCase) -> None:
    operation = BY_ID[case.operation_id]
    model = response_model(operation, case.status)
    assert case.body is not None, case.case_id
    model.model_validate(dict(case.body))


@pytest.mark.parametrize("case", VALIDATING, ids=ids(VALIDATING))
def test_a_valid_status_is_one_the_operation_declares(case: FixtureCase) -> None:
    operation = BY_ID[case.operation_id]
    allowed = {operation.status} | set(operation.extra_responses)
    assert case.status in allowed, case.case_id


@pytest.mark.parametrize(
    "case", cases_of_kind("invalid_response"), ids=ids(cases_of_kind("invalid_response"))
)
def test_an_invalid_response_is_actually_rejected(case: FixtureCase) -> None:
    # These are the cases that prove the CLI does not quietly accept a broken
    # server. A case that silently started validating would be worse than
    # missing: it would look like coverage.
    operation = BY_ID[case.operation_id]
    model = response_model(operation, case.status)
    assert case.body is not None, case.case_id
    with pytest.raises(ValidationError):
        model.model_validate(dict(case.body))


@pytest.mark.parametrize(
    "case", cases_of_kind("rejected_request"), ids=ids(cases_of_kind("rejected_request"))
)
def test_a_rejection_names_a_registered_code_at_its_declared_status(case: FixtureCase) -> None:
    assert case.error_code is not None, case.case_id
    assert case.error_code in ERROR_CODES, case.case_id
    assert http_status_for(case.error_code) == case.status, case.case_id


def test_only_a_rejection_carries_an_error_code() -> None:
    # A rejection without its code would let two implementations fail
    # differently and both look correct; a code on a success is meaningless.
    for case in load_cases():
        if case.kind == "rejected_request":
            assert case.error_code is not None, case.case_id
            assert case.body is None, case.case_id
        else:
            assert case.error_code is None, case.case_id
            assert case.body is not None, case.case_id


def test_every_operation_has_at_least_one_positive_case() -> None:
    # An operation the corpus never exercises is one the platform can implement
    # any way it likes without a test noticing.
    covered = {case.operation_id for case in cases_of_kind("positive")}
    # A route that streams bytes has no JSON body to pin, and a fixture holding
    # an artifact would be a fixture nothing could validate. Its behaviour —
    # digest, size, an interrupted stream — is exercised against a transport in
    # `tests/unit/test_cli_catalog.py`, which is where those cases actually are.
    describable = {
        operation.operation_id for operation in OPERATIONS if operation.response is not None
    }
    missing = sorted(describable - covered)
    assert missing == [], f"operations with no positive fixture: {missing}"


def test_every_rejection_targets_an_operation_that_can_answer_it() -> None:
    # A fixture demanding a code the route never declares would be a test of
    # something the contract does not promise.
    for case in cases_of_kind("rejected_request"):
        operation = BY_ID[case.operation_id]
        declared = set(operation.errors) | set(COMMON_ERRORS)
        if operation.authenticated:
            declared |= set(AUTHENTICATED_ERRORS)
        assert case.error_code in declared, f"{case.case_id} expects an undeclared code"


def test_fixture_data_is_language_neutral() -> None:
    # A fixture that reads as prose invites being translated, and a translated
    # fixture no longer matches the bytes it pins. The `why` field is
    # documentation for a human and is excluded.
    for case in load_cases():
        payload = json.dumps(
            {"request": case.request.model_dump(), "body": case.body}, ensure_ascii=False
        )
        assert all(character.isascii() for character in payload), case.case_id


def test_every_passport_in_the_corpus_is_correctly_sealed() -> None:
    # A passport whose revision id does not seal its own content is a lie about
    # the domain, and a convincing one: the pattern would still match.
    checked = 0
    for case in load_cases():
        if case.body is None:
            continue
        passport = cast("dict[str, JsonValue] | None", dict(case.body).get("passport"))
        if passport is None:
            continue
        assert passport["revision_id"] == derive_revision_id(passport), case.case_id
        checked += 1
    assert checked >= 2, "the corpus should exercise at least one sealed passport per outcome"


def test_no_two_replayable_cases_answer_the_same_request() -> None:
    # A deterministic mock must be able to pick exactly one case per request.
    # Two replayable cases with the same request would make it order-dependent
    # and let a test pass on whichever happened to sort first. A body that
    # depends on server state rather than on the call is an `example`, which is
    # validated but never served - readiness is the case in point.
    seen: dict[tuple[str, str], str] = {}
    for item in load_cases():
        if item.kind not in {"positive", "rejected_request"}:
            continue
        key = (
            item.operation_id,
            json.dumps(item.request.model_dump(mode="json"), sort_keys=True),
        )
        clash = seen.get(key)
        assert clash is None, f"{item.case_id} and {clash} answer the same request"
        seen[key] = item.case_id


SCHEMAS_DIR = Path(__file__).parents[2] / "schemas" / "v1"

#: model class name -> the file that publishes its schema.
_SCHEMA_FILE: dict[str, str] = {
    getattr(model, "__name__", ""): name for name, model in CONTRACT_MODELS.items()
}


def _schema_accepts(model: type[BaseModel], instance: object) -> bool:
    name = _SCHEMA_FILE.get(model.__name__)
    assert name is not None, f"{model.__name__} publishes no schema"
    schema = json.loads((SCHEMAS_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)  # pyright: ignore[reportArgumentType]
    return bool(validator.is_valid(instance))  # pyright: ignore[reportUnknownMemberType, reportArgumentType]


def _model_accepts(model: type[BaseModel], instance: object) -> bool:
    try:
        model.model_validate(instance)
    except ValidationError:
        return False
    return True


@pytest.mark.parametrize("case", load_cases(), ids=ids(load_cases()))
def test_the_model_is_never_more_permissive_than_its_published_schema(case: FixtureCase) -> None:
    # The differential invariant is not equality. Some rules - `authoritative`
    # implies both flags, `ready` implies healthy checks, a public route implies
    # a published passport, a timestamp implies a real date - cannot be
    # expressed in JSON Schema, so the model is deliberately the stricter half.
    #
    # What must never happen is the reverse: if the model accepted something the
    # published schema rejects, a gateway validating with that schema would
    # refuse a payload our own code calls valid. That is an interop break, and
    # it is what this checks.
    if case.body is None:
        pytest.skip("a rejection carries no body")
    model = response_model(BY_ID[case.operation_id], case.status)
    if _model_accepts(model, dict(case.body)):
        assert _schema_accepts(model, dict(case.body)), (
            f"{case.case_id}: the model accepts a body the published schema rejects"
        )


def test_the_corpus_exercises_both_halves_of_the_asymmetry() -> None:
    # A corpus where every negative happened to be schema-catchable would leave
    # the model-only rules untested by this differential.
    schema_caught = 0
    model_only = 0
    for item in cases_of_kind("invalid_response"):
        assert item.body is not None
        model = response_model(BY_ID[item.operation_id], item.status)
        if _schema_accepts(model, dict(item.body)):
            model_only += 1
        else:
            schema_caught += 1
    assert schema_caught >= 1, "no negative is caught by the published schema alone"
    assert model_only >= 1, "no negative exercises a rule only the model can enforce"


@pytest.mark.parametrize("case", VALIDATING, ids=ids(VALIDATING))
def test_an_unknown_schema_major_fails_typed(case: FixtureCase) -> None:
    # docs/engineering/schema-evolution.md: an unknown major is rejected, never
    # coerced to a safe-looking default. `AI_STP_SCHEMA_UNSUPPORTED` is the code
    # a server answers with; the client half is this rejection.
    assert case.body is not None
    if "schema_version" not in case.body:
        pytest.skip("this payload carries no schema version of its own")
    model = response_model(BY_ID[case.operation_id], case.status)
    with pytest.raises(ValidationError):
        model.model_validate(dict(case.body) | {"schema_version": 2})


def test_an_unknown_case_id_fails_loudly() -> None:
    # A typo in a case id must not silently select nothing.
    from ai_stp_contracts.fixtures import case as fixture_case

    with pytest.raises(KeyError):
        fixture_case("noSuchOperation.noSuchCase")


def test_a_case_for_a_body_carrying_operation_sends_a_body() -> None:
    # Without this a case could be written that the mock can never match: the
    # route expects a body, the fixture sends none, and the request silently
    # falls through to "no corpus case" instead of failing where it was written.
    for item in load_cases():
        operation = BY_ID[item.operation_id]
        if operation.body is None or item.kind == "invalid_response":
            continue
        assert item.request.body is not None, f"{item.case_id} sends no body to a body route"


def test_a_case_for_a_bodiless_operation_sends_no_body() -> None:
    for item in load_cases():
        operation = BY_ID[item.operation_id]
        if operation.body is not None or operation.request_media_type != "application/json":
            continue
        assert item.request.body is None, f"{item.case_id} sends a body to a bodiless route"


def test_a_case_carrying_a_passport_and_a_digest_agrees_with_itself() -> None:
    # A placeholder digest teaches a client that integrity verification fails on
    # valid data. Three cases carried one until the check was first wired in.
    from ai_stp_foundation.digests import digest_canonical

    checked = 0
    for case in load_cases():
        body = case.body
        if not isinstance(body, dict) or "passport" not in body or "passport_digest" not in body:
            continue
        checked += 1
        expected = digest_canonical("ai-stp:passport:v1", cast(JsonValue, body["passport"]))
        assert body["passport_digest"] == expected, case.case_id
    assert checked, "no case carries both a passport and its digest"
