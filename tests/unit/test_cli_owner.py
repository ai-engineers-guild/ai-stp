"""The owner command surface: registry shape only.

The journeys — list, object detail, version detail, and the wire→view
conversion — moved to `tests/api/cli/test_owner.py`, where they run against
the real `/v1/owner` routes over the seeded corpus.
"""


def test_owner_registry_declares_three_read_only_commands() -> None:
    from ai_stp_cli.registry import COMMANDS

    found = {item.name: item.descriptor for item in COMMANDS if item.name.startswith("owner ")}
    assert set(found) == {"owner object show", "owner objects", "owner version show"}
    assert all(item.mutability == "read" for item in found.values())
    assert all(item.confirmation == "none" for item in found.values())
