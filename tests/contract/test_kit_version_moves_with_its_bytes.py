"""A version that does not move when the bytes do is worse than no version.

`provider-kit/v3/` is the artifact every provider vendors and verifies against
its own `SHA256SUMS`. It carries a `kit_version` and an `aggregate_digest`, and
`KIT_VERSION` is a hand-maintained constant — so regenerating the kit changes
the digest and leaves the version alone unless somebody remembers.

That happened. `0.2.4` was vendored twice with different aggregates
(`1d117032…` and `8e6f4fa1…`) after `plan_request_fields` was added to the
schema. The provider author caught it by comparing what they had vendored
against what they vendored next; nothing here noticed, because the generator
and its output agreed, which is the whole of the existing check.

This is the same hazard this repository already reasons about twice elsewhere —
an immutable published `X.Y` whose bytes change (`REQ-2606`), and a container
tag republished under the same name — arriving in the artifact that decides what
every provider is allowed to say.

The pair below is recorded rather than computed. Recomputing it would assert
that the generator agrees with itself, which is the thing that was already true
while the version was wrong. A regeneration fails this test, and the failure is
the reminder to bump.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

IDENTITY = Path("provider-kit/v3/KIT-IDENTITY.json")

#: Update **both** together, or not at all.
EXPECTED_VERSION = "0.2.8"
EXPECTED_AGGREGATE = "sha256:2a8777184eb1c4e3a445606dfb591c41f92df89fff795649d330b9ff4db066fa"


def _identity() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(IDENTITY.read_text(encoding="utf-8")))


def test_the_published_kit_is_the_version_and_bytes_recorded_here() -> None:
    identity = _identity()
    assert (identity["kit_version"], identity["aggregate_digest"]) == (
        EXPECTED_VERSION,
        EXPECTED_AGGREGATE,
    ), (
        "the kit's bytes or version moved. If the bytes moved, raise "
        f"KIT_VERSION in release_scripts/provider_kit.py above {EXPECTED_VERSION} "
        "and update both constants here: a provider that vendored the previous "
        "kit has no way to tell it is holding different bytes under one name."
    )


def test_the_generator_and_the_published_kit_agree_on_the_version() -> None:
    """The constant and the artifact, which `back-gen` keeps together."""
    from release_scripts.provider_kit import KIT_VERSION

    assert _identity()["kit_version"] == KIT_VERSION
