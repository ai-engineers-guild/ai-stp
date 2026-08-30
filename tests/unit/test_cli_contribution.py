"""Assembling a host file a component owns one key of (`ADR-0129`).

The property that matters is not that the key lands. It is that **nothing else
moves** — a `config.toml` is a file its user maintains, and a contribution that
tidied it would be destroying work nobody asked us to touch.
"""

from __future__ import annotations

import pytest

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import contribution

COMMENTED_TOML = b"""# The model this project uses, and why.
model = "sonnet"

# Kept deliberately: the sandbox is off because CI already isolates.
[sandbox]
enabled = false
"""


def test_a_toml_contribution_keeps_every_comment_and_unrelated_key() -> None:
    """The whole reason for a format-preserving writer rather than a round trip.

    `tomllib` reads and cannot write; writing values back through a plain
    serialiser erases the two comments above. Losing a comment in a file we did
    not create is data damage, and it is invisible until its owner looks.
    """
    assembled = contribution.assemble(
        host="config.toml",
        current=COMMENTED_TOML,
        key="mcp_servers",
        value={"context7": {"command": "npx"}},
    ).decode("utf-8")

    assert "# The model this project uses, and why." in assembled
    assert "# Kept deliberately: the sandbox is off because CI already isolates." in assembled
    assert 'model = "sonnet"' in assembled
    assert "enabled = false" in assembled
    assert "mcp_servers" in assembled and "context7" in assembled


def test_the_owned_key_is_replaced_rather_than_merged() -> None:
    """Ownership, not "newer wins".

    The key belongs to the component, so what was under it goes. Everything
    outside it is untouched, which is the difference between this and merging
    two setups.
    """
    # `model` first, and that ordering is the point rather than style: in TOML
    # everything after a table header belongs to that table, so a top-level key
    # written below `[mcp_servers.stale]` would be a member of it and would
    # correctly disappear with it. The first version of this fixture had it
    # below and the test failed — catching the fixture, not the code.
    existing = b'model = "sonnet"\n\n[mcp_servers.stale]\ncommand = "gone"\n'
    assembled = contribution.assemble(
        host="config.toml",
        current=existing,
        key="mcp_servers",
        value={"fresh": {"command": "kept"}},
    ).decode("utf-8")

    assert "stale" not in assembled
    assert "fresh" in assembled
    assert 'model = "sonnet"' in assembled


def test_an_absent_host_is_a_first_install_rather_than_an_error() -> None:
    """A target with no such file yet gets one holding just this key."""
    assembled = contribution.assemble(
        host="opencode.json", current=None, key="mcp", value={"one": {"command": "x"}}
    )
    assert b'"mcp"' in assembled and b'"one"' in assembled


def test_an_unparsable_host_is_refused_rather_than_replaced() -> None:
    """The one outcome worse than not installing.

    Overwriting a file whose contents could not be read discards everything the
    component does not know about, and nothing would say so afterwards. Both
    formats refuse, because both can be handed bytes that are not what they
    claim.
    """
    for host, broken in (("config.toml", b"[unclosed\n"), ("opencode.json", b"{,}")):
        with pytest.raises(CliFailure) as raised:
            contribution.assemble(host=host, current=broken, key="k", value={})
        assert raised.value.code == "AI_STP_PRECONDITION_FAILED"


def test_a_jsonc_host_is_refused_because_comments_are_what_it_is_for() -> None:
    """Refusing is the format-preserving requirement, not an omission.

    A `.jsonc` exists so its owner can comment it, and there is no writer here
    that keeps them. Writing it with a plain JSON serialiser would be exactly
    the damage the TOML dependency was taken on to avoid, so it is refused
    until a writer exists that can do it honestly.

    Not hypothetical: opencode reads `opencode.jsonc` in preference to
    `opencode.json` when both are present.
    """
    with pytest.raises(CliFailure, match="cannot be assembled"):
        contribution.assemble(host="opencode.jsonc", current=b"{}", key="mcp", value={})


def test_a_json_host_that_is_not_an_object_is_refused() -> None:
    """A list or a scalar has no key to own, and setting one would invent a shape."""
    with pytest.raises(CliFailure, match="not an object"):
        contribution.assemble(host="opencode.json", current=b"[1, 2]", key="mcp", value={})


def test_a_contribution_must_name_its_key() -> None:
    """An empty key would replace nothing while reporting that it had."""
    with pytest.raises(CliFailure, match="name the key"):
        contribution.assemble(host="config.toml", current=None, key="", value={})
