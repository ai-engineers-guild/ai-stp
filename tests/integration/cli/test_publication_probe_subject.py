"""Publication evidence subjects are complete and repeatable across fresh devices."""

import sys
from pathlib import Path

import pytest
from release_scripts._evidence import cli, data
from release_scripts.verify_publication_slice import (
    _seed_publishable,  # pyright: ignore[reportPrivateUsage]
)

pytestmark = pytest.mark.cli


def test_fresh_publication_devices_have_distinct_names_and_reuse_their_subject(
    tmp_path: Path,
) -> None:
    names: list[str] = []
    identities: list[str] = []
    for home in (tmp_path / "first", tmp_path / "second"):
        stable_id, version = _seed_publishable(home, python=sys.executable)
        assert _seed_publishable(home, python=sys.executable) == (stable_id, version)
        passport = data(
            cli(
                ["component", "passport", "show", "--id", stable_id],
                home=home,
                python=sys.executable,
            ),
            "component passport show",
        )
        names.append(str(passport["facts"]["name"]["value"]))
        identities.append(stable_id)
    assert len(set(identities)) == len(identities)
    assert len(set(names)) == len(names)
