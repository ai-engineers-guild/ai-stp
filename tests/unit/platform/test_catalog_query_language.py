from __future__ import annotations

import pytest

from ai_stp_platform.catalog_query_language import (
    MAX_DEPTH,
    MAX_IN_VALUES,
    MAX_QUERY_LENGTH,
    MAX_TOKENS,
    QuerySyntaxError,
    matches,
    parse_query,
)

pytestmark = pytest.mark.platform

_PASSPORT = {
    "stable_id": "component_example",
    "name": "Review assistant",
    "description": "Reviews Python changes",
    "tags": ["python", "code-review"],
    "harness_id": "codex",
    "component_type": "skill",
}


@pytest.mark.parametrize(
    "query",
    [
        "python",
        'NAME:"Review assistant"',
        "TAGS IN (python, security) AND HARNESS:codex",
        "TYPE:skill AND AUTHOR:nddev",
        "VERIFIED:true AND NOT TAGS:security",
        "(NAME:missing OR TAGS:code-review) AND HARNESS IN (codex, claude-code)",
    ],
)
def test_query_language_matches_supported_expressions(query: str) -> None:
    assert matches(parse_query(query), _PASSPORT, author="nddev", verified=True)


@pytest.mark.parametrize(
    "query",
    ["NAME:", "TAGS IN python", "VERIFIED:maybe", "(python", "AND python"],
)
def test_query_language_rejects_invalid_syntax_with_offset(query: str) -> None:
    with pytest.raises(QuerySyntaxError) as raised:
        parse_query(query)
    assert raised.value.offset >= 0


def test_query_language_keeps_ordinary_terms_as_implicit_and() -> None:
    assert matches(parse_query("python reviews"), _PASSPORT, author="nddev", verified=True)
    assert not matches(parse_query("python rust"), _PASSPORT, author="nddev", verified=True)


def test_query_language_blank_query_matches_every_passport() -> None:
    assert parse_query(" \n\t") is None
    assert matches(None, {}, author="", verified=False)


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("NAME:review", False),
        ('NAME:"Review assistant"', True),
        ("TAGS:python", True),
        ("HARNESS:codex", True),
        ("TYPE:skill", True),
        ("AUTHOR:nddev", True),
        ("VERIFIED:false", True),
        ("TAGS NOT IN (security, rust)", True),
        ("TAGS NOT IN (python, rust)", False),
    ],
)
def test_query_language_evaluates_every_field_and_operator(query: str, expected: bool) -> None:
    assert matches(parse_query(query), _PASSPORT, author="nddev", verified=False) is expected


def test_query_language_or_short_circuits_after_a_true_left_operand() -> None:
    assert matches(parse_query("python OR missing"), _PASSPORT, author="nddev", verified=True)


@pytest.mark.parametrize(
    "query",
    [
        "x" * (MAX_QUERY_LENGTH + 1),
        " ".join("x" for _ in range(MAX_TOKENS + 1)),
        "(" * (MAX_DEPTH + 2) + "x" + ")" * (MAX_DEPTH + 2),
        "TAGS NOT something",
        "TAGS IN ()",
        "TAGS IN (python",
        'NAME:""',
        "python )",
        'NAME:"unterminated',
        "TAGS IN (" + ",".join(f"tag{index}" for index in range(MAX_IN_VALUES + 1)) + ")",
    ],
)
def test_query_language_enforces_each_resource_and_shape_bound(query: str) -> None:
    with pytest.raises(QuerySyntaxError) as raised:
        parse_query(query)
    assert 0 <= raised.value.offset <= len(query)


def test_query_language_unescapes_a_quoted_value() -> None:
    passport = _PASSPORT | {"name": 'Review "assistant"'}
    assert matches(
        parse_query(r'NAME:"Review \"assistant\""'),
        passport,
        author="nddev",
        verified=True,
    )
