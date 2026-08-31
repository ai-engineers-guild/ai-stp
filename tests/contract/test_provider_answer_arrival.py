"""Every key a provider answers must be read by something here.

Conformance tests that a provider *answers*. Nothing tested that an answer
*arrives*, and the gap is not symmetric: the estate that owns the providers can
see every field it emits, while this side's set of read keys is invisible to it
without reading this build. Nothing on either side fails when a field is
dropped.

Three went that way in one day. `recovered` was accepted by `extra="allow"` and
discarded, so a prefix the provider had to repair read like a clean one.
`shadowed_by` was fetched and dropped, so a target obeying a file the provider
never wrote was reported installed. `cleanup_state` was read under two
different invented vocabularies while no provider emitted it at all, which left
`recover-operation` unreachable from the daily path against all seven.

The instrument came from the other estate and was four lines of grep. This is
that, made into something that fails on the next field rather than on the next
person who thinks to look.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import cast

import pytest

from ai_stp_cli.provider import protocol_v3

#: Keys a v3 provider may put in a `status` answer. Not every one needs a
#: reader — but a key nobody names is a decision, and this is where it gets
#: made rather than noticed a release later.
#: Derived from the closed kit schema. The former six-key hand-written set was
#: the exact class this test exists to prevent: current providers answer 33
#: keys, and nothing failed when the other 27 stopped arriving.
STATUS_KEYS: frozenset[str] = frozenset(
    cast(dict[str, object], protocol_v3.STATUS_WIRE_SCHEMA["properties"])
)

#: Named and deliberately unread, with the reason. Emptying this list is not the
#: goal; leaving something out of both lists is the defect.
UNREAD: dict[str, str] = {}

PACKAGE = Path(__file__).resolve().parents[2] / "apps" / "cli" / "src" / "ai_stp_cli"


def _mentions(key: str) -> bool:
    found = subprocess.run(
        ["grep", "-rq", key, str(PACKAGE)],
        capture_output=True,
        check=False,
    )
    return found.returncode == 0


@pytest.mark.parametrize("key", sorted(STATUS_KEYS))
def test_every_status_key_a_provider_answers_is_named_here(key: str) -> None:
    """A field the provider sends and nothing here names is a silent drop."""
    if key in UNREAD:
        pytest.skip(f"deliberately unread: {UNREAD[key]}")
    assert _mentions(key), (
        f"providers answer {key!r} and nothing in the CLI package names it; "
        "read it, or record why not in UNREAD"
    )


def test_the_search_can_fail() -> None:
    """The control, without which every line above passes for free.

    A grep that always succeeds and a package that names everything look
    identical from the outside. This is the invented key the other estate used
    for the same reason.
    """
    assert not _mentions("nothing_answers_this_key_ai_stp_control")
