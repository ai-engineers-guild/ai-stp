"""Credential-safe reports for native API evidence."""

from __future__ import annotations

import json
from typing import Any

DEFAULT_CLI_TIMEOUT_SECONDS = 300.0

# Anything credential-shaped must not reach a report. Two of the five slices
# hold a session, which makes the guard load-bearing rather than decorative.
#
# It said "two of the three" until 2026-08-29, and was written when there were
# three: `citation` and `provider` arrived on 2026-08-28 and the count was never
# re-measured. The substantive half stayed true — `sync` and `publication` are
# still the two that log in — but the sentence understated the surface the guard
# covers by two whole slices. Counts get typed while the lists they summarise
# get measured, which is why one drifts and the other does not.
FORBIDDEN_IN_REPORT: tuple[str, ...] = (
    "authorization",
    "bearer ",
    "refresh_token",
    "access_token",
)


class EvidenceError(RuntimeError):
    """The deployed environment did not answer as an evidence slice requires."""


#: Facts a local adopted draft still lacks after `component adopt`. Adoption
#: records observed native facts only. The immutable version passport then
#: requires these declared fields — measured 2026-09-06 when the config and
#: contribution slices jumped from adopt to release: first `name, description,
#: tags`, then `license` on the version snapshot itself.
RELEASE_DRAFT_FIELDS: tuple[str, ...] = ("name", "description", "tags", "license")


def without_credentials(report: dict[str, Any]) -> dict[str, Any]:
    """Refuse to print a report that gained something no artefact may hold."""
    serialised = json.dumps(report).lower()
    for marker in FORBIDDEN_IN_REPORT:
        if marker in serialised:
            raise EvidenceError(
                f"the report contains {marker!r}, which no evidence artefact may hold"
            )
    return report
