"""Reading server names out of a setting file, and refusing to guess."""

from pathlib import Path

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
