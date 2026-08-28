"""The parser and the schema providers build against must agree, both ways.

`provider-info.schema.json` in `provider-kit/` sets `additionalProperties: false`
and is the artifact a provider is told to build against — shipped with a checksum
manifest so a provider can prove it did. The parser in this repository decides
what a consumer accepts. When they disagree, a provider has no rule for which
wins, and both directions have now been wrong within a week:

- `PROJECTION_SCOPES` gained `user_root`; the schema's `target_scope` enum was
  written out by hand and did not. A provider declaring the scope the parser
  accepted failed the schema it was checked against.
- `OPTIONAL_INFO_FIELDS` gained `plan_request_fields`; the wire schema did not
  emit it at all. The provider author found it before this test did, and their
  report is what this file exists to make unnecessary.

Both were invisible to the generated-versus-source check, because the generator
and the artifact agreed with each other — they were wrong together, which is the
same shape as two projection tables agreeing on a path no product reads.

So this compares the schema against the **parser's own constants** rather than
against the generator's output.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from ai_stp_cli.provider import protocol_v3

KIT = Path("provider-kit/v3/provider-info.schema.json")


def _schema() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(KIT.read_text(encoding="utf-8")))


def _properties() -> dict[str, Any]:
    return cast(dict[str, Any], _schema()["properties"])


def test_every_field_the_parser_accepts_is_a_field_the_schema_allows() -> None:
    """`additionalProperties: false` makes an omission a refusal, not a gap."""
    allowed = set(_properties())
    accepted = set(protocol_v3.INFO_FIELDS) | protocol_v3.OPTIONAL_INFO_FIELDS
    assert accepted <= allowed, sorted(accepted - allowed)


def test_the_schema_allows_nothing_the_parser_would_refuse() -> None:
    """The other direction: a blessed field the consumer rejects is worse.

    A provider that builds against the kit and is then refused has done exactly
    what it was told to do.
    """
    allowed = set(_properties())
    accepted = set(protocol_v3.INFO_FIELDS) | protocol_v3.OPTIONAL_INFO_FIELDS
    assert allowed <= accepted, sorted(allowed - accepted)


def test_closed_value_sets_are_the_parser_s_own_rather_than_a_copy() -> None:
    """Enums the schema publishes must be the sets the parser checks against.

    Written out, they drift on the first member added — which is exactly how
    `user_root` came to be accepted by the parser and refused by the schema.
    """
    properties = _properties()
    request = cast(dict[str, Any], properties["plan_request_fields"])
    assert set(cast(list[str], request["items"]["enum"])) == protocol_v3.PLAN_REQUEST_FIELDS

    scoped = cast(dict[str, Any], properties["scoped_projection_profiles"])
    scope = cast(dict[str, Any], scoped["items"]["properties"]["target_scope"])
    assert set(cast(list[str], scope["enum"])) == protocol_v3.PROJECTION_SCOPES - {"global"}


def test_the_schema_is_still_closed() -> None:
    """The guarantee the two tests above depend on."""
    assert _schema()["additionalProperties"] is False
