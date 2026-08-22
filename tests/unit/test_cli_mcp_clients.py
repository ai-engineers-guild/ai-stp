"""Reading server names out of a setting file, and refusing to guess."""

import json
import os
from pathlib import Path

import pytest

from ai_stp_cli.local import mcp_clients


def test_a_string_is_stepped_over_rather_than_scanned(tmp_path: Path) -> None:
    """Escapes and comment markers inside a string are content, not syntax."""
    place = tmp_path / "opencode.jsonc"
    place.write_text(
        '{"mcp": {"say \\"hi\\"": {"url": "https://a.b//c", "note": "a, b"}}}',
        encoding="utf-8",
    )

    assert mcp_clients.declared_servers(place, "mcp") == ('say "hi"',)


def test_a_comment_that_ends_at_the_end_of_file_still_parses(tmp_path: Path) -> None:
    """The last line of a hand-written file often carries no newline."""
    place = tmp_path / "opencode.jsonc"
    place.write_text('{"mcp": {"nx": {}}} // no newline after this', encoding="utf-8")

    assert mcp_clients.declared_servers(place, "mcp") == ("nx",)


def test_nothing_is_read_out_of_a_file_that_cannot_be_trusted(tmp_path: Path) -> None:
    """Unterminated, non-UTF-8 and non-mapping files are refused, not guessed at.

    Each of these could be coaxed into a plausible answer. None of them is
    evidence, and a plausible answer is exactly what the discovery contract
    forbids an adapter from inventing.
    """
    unterminated = tmp_path / "opencode.jsonc"
    unterminated.write_text('{"mcp": {"a', encoding="utf-8")
    assert mcp_clients.declared_servers(unterminated, "mcp") == ()

    undecodable = tmp_path / "opencode.json"
    undecodable.write_bytes(b'\xff\xfe{"mcp": {"a": {}}}')
    assert mcp_clients.declared_servers(undecodable, "mcp") == ()

    not_a_mapping = tmp_path / "list.json"
    not_a_mapping.write_text('["mcp"]', encoding="utf-8")
    assert mcp_clients.declared_servers(not_a_mapping, "mcp") == ()

    not_servers = tmp_path / "scalar.json"
    not_servers.write_text('{"mcp": "off"}', encoding="utf-8")
    assert mcp_clients.declared_servers(not_servers, "mcp") == ()

    # The walker offers unreadable entries too, so the declared path is not
    # guaranteed to be a file by the time it gets here.
    not_a_file = tmp_path / "directory.json"
    not_a_file.mkdir()
    assert mcp_clients.declared_servers(not_a_file, "mcp") == ()


def test_a_symlinked_config_is_not_followed(tmp_path: Path) -> None:
    """`REQ-518` bounds this adapter to declared files, and a link escapes that.

    The names this module returns are harmless, but reading is not: a declared
    path pointed at somebody's private key would be opened and pulled into
    memory by a discovery pass that promises to open only what the layout
    names.
    """
    secret = tmp_path / "id_rsa"
    secret.write_text('{"mcp": {"leaked": {}}}', encoding="utf-8")
    place = tmp_path / "opencode.json"
    place.symlink_to(secret)

    assert mcp_clients.declared_servers(place, "mcp") == ()


def test_a_second_hard_link_makes_it_somebody_else_s_file(tmp_path: Path) -> None:
    """A second name for the same inode is a second owner of what we read."""
    real = tmp_path / "elsewhere.json"
    real.write_text('{"mcp": {"shared": {}}}', encoding="utf-8")
    place = tmp_path / "opencode.json"
    try:
        os.link(real, place)
    except (OSError, NotImplementedError, AttributeError):  # pragma: no cover
        pytest.skip("this filesystem does not support hard links")

    assert mcp_clients.declared_servers(place, "mcp") == ()


def test_a_directory_named_like_a_config_is_not_a_config(tmp_path: Path) -> None:
    place = tmp_path / "opencode.json"
    place.mkdir()

    assert mcp_clients.declared_servers(place, "mcp") == ()


def test_more_servers_than_a_person_writes_is_not_a_client_config(tmp_path: Path) -> None:
    """The byte limit alone does not bound this: names are short."""
    servers: dict[str, dict[str, object]] = {
        f"s{index}": {} for index in range(mcp_clients.MAX_CLIENT_ENTRIES + 1)
    }
    place = tmp_path / "opencode.json"
    place.write_text(json.dumps({"mcp": servers}), encoding="utf-8")

    assert mcp_clients.declared_servers(place, "mcp") == ()


def test_a_name_nobody_typed_does_not_reach_evidence(tmp_path: Path) -> None:
    """Names travel into `evidence_refs`; an unbounded one puts text there."""
    place = tmp_path / "opencode.json"
    place.write_text(
        json.dumps({"mcp": {"kept": {}, "x" * (mcp_clients.MAX_ENTRY_NAME_CHARS + 1): {}}}),
        encoding="utf-8",
    )

    assert mcp_clients.declared_servers(place, "mcp") == ("kept",)


def test_a_name_a_person_chose_is_still_returned(tmp_path: Path) -> None:
    """The bound is a length, not a shape — refusing `say "hi"` would report
    that a file declaring one server declares none."""
    place = tmp_path / "opencode.json"
    place.write_text(json.dumps({"mcp": {'say "hi"': {}, "with space": {}}}), encoding="utf-8")

    assert mcp_clients.declared_servers(place, "mcp") == ('say "hi"', "with space")
