"""Bounded Catalog QL parser and in-memory predicate evaluator (SPEC-034)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal, cast

MAX_QUERY_LENGTH = 500
MAX_TOKENS = 128
MAX_DEPTH = 8
MAX_IN_VALUES = 32


def named_harness_ids(passport: dict[str, Any]) -> list[str]:
    """Every explicitly named harness, de-duplicated without inventing support."""
    primary = str(passport.get("harness_id") or "")
    raw = passport.get("adaptations")
    extra: list[str] = []
    if isinstance(raw, list):
        for item in cast(list[object], raw):
            if isinstance(item, dict):
                harness_id = cast(dict[str, object], item).get("harness_id")
                if isinstance(harness_id, str):
                    extra.append(harness_id)
    ordered: list[str] = []
    for value in [primary, *extra]:
        if value and value not in ordered:
            ordered.append(value)
    return ordered


class QuerySyntaxError(ValueError):
    """A stable, user-correctable query error with a source offset."""

    def __init__(self, message: str, *, offset: int, expected: str | None = None) -> None:
        super().__init__(message)
        self.offset = offset
        self.expected = expected


class TokenKind(StrEnum):
    WORD = "word"
    STRING = "string"
    LPAREN = "lparen"
    RPAREN = "rparen"
    COMMA = "comma"
    COLON = "colon"
    EOF = "eof"


@dataclass(frozen=True)
class Token:
    kind: TokenKind
    value: str
    offset: int


@dataclass(frozen=True)
class TextTerm:
    value: str


@dataclass(frozen=True)
class Predicate:
    field: Literal["NAME", "TAGS", "HARNESS", "TYPE", "AUTHOR", "VERIFIED"]
    operator: Literal[":", "IN", "NOT IN"]
    values: tuple[str, ...]


@dataclass(frozen=True)
class Unary:
    operand: Expression


@dataclass(frozen=True)
class Binary:
    operator: Literal["AND", "OR"]
    left: Expression
    right: Expression


type Expression = TextTerm | Predicate | Unary | Binary
type PredicateField = Literal["NAME", "TAGS", "HARNESS", "TYPE", "AUTHOR", "VERIFIED"]

CATALOG_QL_FIELDS = ("NAME", "TAGS", "HARNESS", "TYPE", "AUTHOR", "VERIFIED")
CATALOG_QL_OPERATORS = ("AND", "OR", "NOT", "IN")
_FIELDS = frozenset(CATALOG_QL_FIELDS)
_KEYWORDS = frozenset(CATALOG_QL_OPERATORS)


def tokenize(source: str) -> list[Token]:
    if len(source) > MAX_QUERY_LENGTH:
        raise QuerySyntaxError("query is too long", offset=MAX_QUERY_LENGTH)
    tokens: list[Token] = []
    index = 0
    while index < len(source):
        char = source[index]
        if char.isspace():
            index += 1
            continue
        punctuation = {
            "(": TokenKind.LPAREN,
            ")": TokenKind.RPAREN,
            ",": TokenKind.COMMA,
            ":": TokenKind.COLON,
        }
        if char in punctuation:
            tokens.append(Token(punctuation[char], char, index))
            index += 1
        elif char in {'"', "'"}:
            quote = char
            start = index
            index += 1
            value: list[str] = []
            while index < len(source) and source[index] != quote:
                if source[index] == "\\" and index + 1 < len(source):
                    index += 1
                value.append(source[index])
                index += 1
            if index >= len(source):
                raise QuerySyntaxError("unterminated quoted value", offset=start, expected=quote)
            index += 1
            tokens.append(Token(TokenKind.STRING, "".join(value), start))
        else:
            start = index
            while (
                index < len(source)
                and not source[index].isspace()
                and source[index] not in "(),:\"'"
            ):
                index += 1
            tokens.append(Token(TokenKind.WORD, source[start:index], start))
        if len(tokens) > MAX_TOKENS:
            raise QuerySyntaxError("query has too many tokens", offset=index)
    tokens.append(Token(TokenKind.EOF, "", len(source)))
    return tokens


class _Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.index = 0

    @property
    def current(self) -> Token:
        return self.tokens[self.index]

    def advance(self) -> Token:
        token = self.current
        self.index += 1
        return token

    def keyword(self, value: str) -> bool:
        return self.current.kind == TokenKind.WORD and self.current.value.upper() == value

    def parse(self) -> Expression:
        expression = self.parse_or(0)
        if self.current.kind != TokenKind.EOF:
            raise QuerySyntaxError(
                "unexpected token", offset=self.current.offset, expected="operator"
            )
        return expression

    def parse_or(self, depth: int) -> Expression:
        expression = self.parse_and(depth)
        while self.keyword("OR"):
            self.advance()
            expression = Binary("OR", expression, self.parse_and(depth))
        return expression

    def parse_and(self, depth: int) -> Expression:
        expression = self.parse_unary(depth)
        while True:
            if self.keyword("AND"):
                self.advance()
                expression = Binary("AND", expression, self.parse_unary(depth))
                continue
            # Adjacent plain terms preserve ordinary search and mean AND.
            if self.current.kind in {
                TokenKind.WORD,
                TokenKind.STRING,
                TokenKind.LPAREN,
            } and not self.keyword("OR"):
                expression = Binary("AND", expression, self.parse_unary(depth))
                continue
            return expression

    def parse_unary(self, depth: int) -> Expression:
        if self.keyword("NOT"):
            self.advance()
            return Unary(self.parse_unary(depth))
        return self.parse_primary(depth)

    def parse_primary(self, depth: int) -> Expression:
        if depth > MAX_DEPTH:
            raise QuerySyntaxError("query nesting is too deep", offset=self.current.offset)
        if self.current.kind == TokenKind.LPAREN:
            opening = self.advance()
            expression = self.parse_or(depth + 1)
            if cast(TokenKind, self.current.kind) != TokenKind.RPAREN:
                raise QuerySyntaxError(
                    "missing closing parenthesis", offset=opening.offset, expected=")"
                )
            self.advance()
            return expression
        if self.current.kind not in {TokenKind.WORD, TokenKind.STRING}:
            raise QuerySyntaxError(
                "expected search term", offset=self.current.offset, expected="term"
            )
        token = self.advance()
        field = token.value.upper()
        if (
            token.kind == TokenKind.WORD
            and field in _FIELDS
            and (self.current.kind == TokenKind.COLON or self.keyword("IN") or self.keyword("NOT"))
        ):
            return self.parse_predicate(field, token.offset)
        if token.kind == TokenKind.WORD and field in _KEYWORDS:
            raise QuerySyntaxError(
                "operator has no left operand", offset=token.offset, expected="term"
            )
        return TextTerm(token.value)

    def parse_predicate(self, field: PredicateField, offset: int) -> Predicate:
        operator: Literal[":", "IN", "NOT IN"]
        if self.current.kind == TokenKind.COLON:
            self.advance()
            operator = ":"
            values = (self.parse_value(),)
        else:
            if self.keyword("NOT"):
                self.advance()
                if not self.keyword("IN"):
                    raise QuerySyntaxError(
                        "expected IN after NOT", offset=self.current.offset, expected="IN"
                    )
                operator = "NOT IN"
            else:
                operator = "IN"
            self.advance()
            if self.current.kind != TokenKind.LPAREN:
                raise QuerySyntaxError(
                    "expected value list", offset=self.current.offset, expected="("
                )
            self.advance()
            collected: list[str] = [self.parse_value()]
            while cast(TokenKind, self.current.kind) == TokenKind.COMMA:
                self.advance()
                collected.append(self.parse_value())
                if len(collected) > MAX_IN_VALUES:
                    raise QuerySyntaxError("IN list is too large", offset=self.current.offset)
            if cast(TokenKind, self.current.kind) != TokenKind.RPAREN:
                raise QuerySyntaxError(
                    "missing closing parenthesis", offset=self.current.offset, expected=")"
                )
            self.advance()
            values = tuple(collected)
        if field == "VERIFIED" and any(
            value.casefold() not in {"true", "false"} for value in values
        ):
            raise QuerySyntaxError(
                "VERIFIED accepts true or false", offset=offset, expected="boolean"
            )
        return Predicate(field, operator, values)

    def parse_value(self) -> str:
        if self.current.kind not in {TokenKind.WORD, TokenKind.STRING}:
            raise QuerySyntaxError("expected value", offset=self.current.offset, expected="value")
        value = self.advance().value.strip()
        if not value:
            raise QuerySyntaxError(
                "value cannot be empty", offset=self.current.offset, expected="value"
            )
        return value


def parse_query(source: str) -> Expression | None:
    """Parse a non-empty query into a bounded AST; blank means no predicate."""
    if not source.strip():
        return None
    return _Parser(tokenize(source)).parse()


def matches(
    expression: Expression | None, passport: dict[str, Any], *, author: str, verified: bool
) -> bool:
    if expression is None:
        return True
    if isinstance(expression, TextTerm):
        tags_value = passport.get("tags")
        tags: list[object] = (
            list(cast(list[object], tags_value)) if isinstance(tags_value, list) else []
        )
        haystack = " ".join(
            [
                str(passport.get("name") or ""),
                str(passport.get("description") or ""),
                str(passport.get("stable_id") or ""),
                " ".join(map(str, tags)),
                author,
            ]
        ).casefold()
        document_terms = set(re.findall(r"\w+", haystack))
        query_terms = set(re.findall(r"\w+", expression.value.casefold()))
        return bool(query_terms) and all(
            any(query in term for term in document_terms) for query in query_terms
        )
    if isinstance(expression, Unary):
        return not matches(expression.operand, passport, author=author, verified=verified)
    if isinstance(expression, Binary):
        left = matches(expression.left, passport, author=author, verified=verified)
        if expression.operator == "AND":
            return left and matches(expression.right, passport, author=author, verified=verified)
        return left or matches(expression.right, passport, author=author, verified=verified)
    raw: object
    if expression.field == "NAME":
        raw = passport.get("name") or ""
    elif expression.field == "TAGS":
        raw = passport.get("tags") or []
    elif expression.field == "HARNESS":
        raw = named_harness_ids(passport)
    elif expression.field == "TYPE":
        raw = passport.get("component_type") or ""
    elif expression.field == "AUTHOR":
        raw = author
    else:
        raw = "true" if verified else "false"
    candidates = (
        [str(item).casefold() for item in cast(list[object], raw)]
        if isinstance(raw, list)
        else [str(raw).casefold()]
    )
    wanted = {value.casefold() for value in expression.values}
    present = bool(wanted.intersection(candidates))
    return not present if expression.operator == "NOT IN" else present
