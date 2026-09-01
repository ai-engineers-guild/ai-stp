"""Immutable upstream attribution text for official snapshots (SPEC-056 REQ-5605)."""

from __future__ import annotations

OWNERSHIP_NOTICE = (
    "AI STP publishes this snapshot for discovery. AI STP does not claim "
    "upstream authorship or affiliation. A verified maintainer may request "
    "an ownership transfer, which AI STP will review."
)


def build_description(
    *,
    project_name: str,
    maintainer: str,
    repository: str,
    license_spdx: str,
    reviewed_body: str,
) -> str:
    """Leading attribution, reviewed body, trailing ownership notice."""
    lead = f"{project_name} is maintained by {maintainer} at {repository} under {license_spdx}."
    body = reviewed_body.strip()
    return f"{lead}\n\n{body}\n\n{OWNERSHIP_NOTICE}\n"
