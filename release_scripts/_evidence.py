"""What every evidence slice needs, owned once.

Three scripts prove different things against the same deployed environment —
the anonymous catalogue, two-device synchronisation, and the publication and
authorisation surface — and each of them needs the same four mechanics: refuse
anything that is not a bare origin, run one machine command in an isolated home,
read its envelope, and refuse to print a report that gained a credential.

They were written twice and would have been written a third time. A guard copied
per script is a guard that stops matching, and the one it protects is the one
that matters: an evidence artefact is meant to be pasted into an issue.
"""

from __future__ import annotations

import json
import os
import subprocess
import urllib.parse
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

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


def origin(value: str) -> str:
    """A bare https origin, or a refusal naming what is wrong with it."""
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise EvidenceError("origin must be a bare https origin, for example https://example.com")
    if parsed.path.rstrip("/") or parsed.query or parsed.fragment:
        raise EvidenceError("origin carries a path, query or fragment; pass the bare origin")
    return f"https://{parsed.netloc}"


def cli(
    arguments: Sequence[str],
    *,
    home: Path,
    python: str,
    allow_failure: bool = False,
    offline: bool = False,
) -> dict[str, Any]:
    """Run one machine command in one home and return its envelope.

    `allow_failure` is for a scenario whose expected outcome is a typed refusal:
    a conflict is the proof, not an error, and only the caller knows which of the
    two it asked for.

    `offline` denies the route rather than asking the CLI for an offline switch.
    Inventing a switch would test the switch; a proxy on a closed port fails
    every outbound call the way a lost network does.
    """
    environment = dict(os.environ)
    environment["HOME"] = str(home)
    environment["USERPROFILE"] = str(home)
    environment["XDG_CONFIG_HOME"] = str(home / "config")
    environment["XDG_DATA_HOME"] = str(home / "data")
    environment["AI_STP_FORCE_FILE_CREDENTIAL_STORE"] = "1"
    proxies = ("https_proxy", "HTTPS_PROXY", "http_proxy", "HTTP_PROXY")
    if offline:
        for name in proxies:
            environment[name] = "http://127.0.0.1:9"
    else:
        for name in proxies:
            environment.pop(name, None)

    result = subprocess.run(
        [python, "-m", "ai_stp_cli", *arguments, "--json"],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    try:
        envelope = json.loads(result.stdout)
    except ValueError as error:
        detail = result.stderr.strip().splitlines()
        suffix = detail[-1] if detail else "no stderr"
        raise EvidenceError(f"{' '.join(arguments)} emitted no envelope: {suffix}") from error
    if not isinstance(envelope, dict):
        raise EvidenceError(f"{' '.join(arguments)} answered something that is not an envelope")
    typed = cast(dict[str, Any], envelope)
    if typed.get("ok") is not True and not allow_failure:
        raise EvidenceError(f"{' '.join(arguments)} refused: {result.stdout.strip()[:200]}")
    return typed


def data(envelope: Mapping[str, Any], command: str) -> dict[str, Any]:
    held = envelope.get("data")
    if not isinstance(held, dict):
        raise EvidenceError(f"{command} answered an envelope without data")
    return cast(dict[str, Any], held)


def error_code(envelope: Mapping[str, Any]) -> str:
    """The typed code of a refusal, or an empty string when the call succeeded."""
    held = envelope.get("error")
    if not isinstance(held, dict):
        return ""
    code = cast(dict[str, Any], held).get("code")
    return code if isinstance(code, str) else ""


def without_credentials(report: dict[str, Any]) -> dict[str, Any]:
    """Refuse to print a report that gained something no artefact may hold."""
    serialised = json.dumps(report).lower()
    for marker in FORBIDDEN_IN_REPORT:
        if marker in serialised:
            raise EvidenceError(
                f"the report contains {marker!r}, which no evidence artefact may hold"
            )
    return report


def login_commands(home: Path) -> list[str]:
    """The exact commands that put a session where a slice will look for it.

    `HOME=<home> ai-stp auth login` is not enough and saying so cost a real
    session: `cli()` also sets `XDG_CONFIG_HOME`, `XDG_DATA_HOME` and the forced
    file credential store, so a login run without them writes to the XDG
    defaults under that home and the slice reads a different directory and
    answers `local_only`. Following the instruction could not satisfy the
    instrument that printed it.
    """
    prefix = (
        f"HOME={home} USERPROFILE={home} "
        f"XDG_CONFIG_HOME={home}/config XDG_DATA_HOME={home}/data "
        f"AI_STP_FORCE_FILE_CREDENTIAL_STORE=1"
    )
    return [
        f"{prefix} ai-stp auth login --provider github --json",
        f"{prefix} ai-stp auth complete --wait --json",
    ]
