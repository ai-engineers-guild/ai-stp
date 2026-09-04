"""GitHub API bearer for component source fetches.

Reads process environment only. The value never enters passports, logs, or
`CliFailure.details`. `GITHUB_TOKEN` is preferred over `GH_TOKEN` so a
fine-grained API PAT does not override `gh`'s active git account.
"""

from __future__ import annotations

import os


def github_api_token() -> str | None:
    """Return a bearer for api.github.com, or None for anonymous HTTPS."""
    for name in ("GITHUB_TOKEN", "GH_TOKEN"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return None
