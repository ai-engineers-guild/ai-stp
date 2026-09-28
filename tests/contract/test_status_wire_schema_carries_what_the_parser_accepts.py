"""The status-side mirror of the provider-info parity check.

`status-response.schema.json` in `provider-kit/` is what a provider builds a
`status` answer against, with `additionalProperties: false`. The parser in
`protocol_v3` decides what the consumer accepts. They disagreed exactly the way
the provider-info side did: `authorization` was documented by the contract and
ADR-0052 and parsed by the consumer, while the shipped schema refused it — a
provider emitting the member it was told about failed validation for telling
the truth.

So this compares the schema against the parser's own constants, both ways,
the same rule the provider-info sibling file names.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from ai_stp_cli.provider import protocol_v3

KIT = Path("provider-kit/v3/status-response.schema.json")


def _schema() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(KIT.read_text(encoding="utf-8")))


def _properties() -> dict[str, Any]:
    return cast(dict[str, Any], _schema()["properties"])


def test_every_member_the_parser_reads_is_a_member_the_schema_allows() -> None:
    allowed = set(_properties())
    accepted = (
        set(protocol_v3.STATUS_ALWAYS_FIELDS)
        | set(protocol_v3.STATUS_VERIFIED_FIELDS)
        | set(protocol_v3.STATUS_OPTIONAL_FIELDS)
    )
    assert accepted <= allowed, sorted(accepted - allowed)


def test_the_schema_allows_nothing_the_parser_would_refuse() -> None:
    allowed = set(_properties())
    accepted = (
        set(protocol_v3.STATUS_ALWAYS_FIELDS)
        | set(protocol_v3.STATUS_VERIFIED_FIELDS)
        | set(protocol_v3.STATUS_OPTIONAL_FIELDS)
    )
    assert allowed <= accepted, sorted(allowed - accepted)


def test_authorization_is_the_closed_pair_the_contract_documents() -> None:
    authorization = cast(dict[str, Any], _properties()["authorization"])
    assert authorization["additionalProperties"] is False
    assert set(cast(dict[str, Any], authorization["required"]).__iter__()) == {
        "kind",
        "state",
    }
    nested = cast(dict[str, Any], authorization["properties"])
    assert set(cast(list[str], nested["kind"]["enum"])) == {
        "user_account",
        "external_service",
    }
    assert set(cast(list[str], nested["state"]["enum"])) == {"pending", "ready"}


def test_the_schema_is_still_closed() -> None:
    assert _schema()["additionalProperties"] is False
