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
import signal
import subprocess
import urllib.parse
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

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
    timeout: float = DEFAULT_CLI_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Run one machine command in one home and return its envelope.

    `allow_failure` is for a scenario whose expected outcome is a typed refusal:
    a conflict is the proof, not an error, and only the caller knows which of the
    two it asked for.

    `offline` denies the route rather than asking the CLI for an offline switch.
    Inventing a switch would test the switch; a proxy on a closed port fails
    every outbound call the way a lost network does.

    The OS exit and the JSON `ok` field must agree. A hang is a failure, not a
    missing report: the child is started in its own session so a timeout can
    stop the process group.
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

    argv = [python, "-m", "ai_stp_cli", *arguments, "--json"]
    if os.name != "nt":
        process = subprocess.Popen(
            argv,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
    else:
        process = subprocess.Popen(
            argv,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as error:
        if os.name != "nt":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except OSError:
                process.kill()
        else:
            process.kill()
        process.communicate()
        raise EvidenceError(f"{' '.join(arguments)} timed out after {timeout:.0f}s") from error
    result = subprocess.CompletedProcess(argv, process.returncode or 0, stdout, stderr)
    try:
        envelope = json.loads(result.stdout)
    except ValueError as error:
        detail = result.stderr.strip().splitlines()
        suffix = detail[-1] if detail else f"exit {result.returncode}, no stderr"
        raise EvidenceError(f"{' '.join(arguments)} emitted no envelope: {suffix}") from error
    if not isinstance(envelope, dict):
        raise EvidenceError(f"{' '.join(arguments)} answered something that is not an envelope")
    typed = cast(dict[str, Any], envelope)
    ok = typed.get("ok") is True
    if ok and result.returncode != 0:
        raise EvidenceError(f"{' '.join(arguments)} claimed ok with exit {result.returncode}")
    if not ok and result.returncode == 0:
        raise EvidenceError(f"{' '.join(arguments)} claimed failure with exit 0")
    if not ok and not allow_failure:
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


def error_details(envelope: Mapping[str, Any]) -> dict[str, Any]:
    """The refusal's typed details, or an empty mapping when there are none.

    Details are where a refusal carries its evidence — for a postcondition
    miss, *which* reading disagreed — and they are typed product output that
    redacts home paths at the source, same as the message beside them.
    """
    held = envelope.get("error")
    if not isinstance(held, dict):
        return {}
    details = cast(dict[str, Any], held).get("details")
    return cast(dict[str, Any], details) if isinstance(details, dict) else {}


def contribution_probe_present(target: Path, relative: str) -> bool:
    """Whether the native surface still carries the `mcp01` probe as files.

    0.0.66 remove deletes the files the provider recorded writing, not the
    namespace they sat in. An empty leftover `extensions/mcp01` is not the
    component still being there; a `package.json` under that path is.
    """
    host = target / relative
    if not relative or not host.exists():
        return False
    if host.is_file():
        return "mcp01" in host.read_text(encoding="utf-8", errors="replace")
    return any(
        item.is_file() and "mcp01" in item.relative_to(host).as_posix() for item in host.rglob("*")
    )


def error_message(envelope: Mapping[str, Any]) -> str:
    """The refusal's sentence, or an empty string when the call succeeded.

    A code names the class and the message names the instance. The first
    windows/x86_64 consumer run failed one harness with a bare
    `AI_STP_PRECONDITION_FAILED` — a code with over twenty sources in the
    install path — and the row could not say which one, so the diagnosis had
    to wait for a second run. Messages are typed product output and redact
    home paths at the source; keeping them costs nothing a report may not
    hold, and `without_credentials` still refuses anything that slips.
    """
    held = envelope.get("error")
    if not isinstance(held, dict):
        return ""
    message = cast(dict[str, Any], held).get("message")
    return message if isinstance(message, str) else ""


#: Facts a local adopted draft still lacks after `component adopt`. Adoption
#: records observed native facts only. The immutable version passport then
#: requires these declared fields — measured 2026-09-06 when the config and
#: contribution slices jumped from adopt to release: first `name, description,
#: tags`, then `license` on the version snapshot itself.
RELEASE_DRAFT_FIELDS: tuple[str, ...] = ("name", "description", "tags", "license")


def release_draft_patch(*, name: str, description: str | None = None) -> dict[str, object]:
    """The closed passport patch a local draft needs before it can be released.

    Kept as a function rather than inlined in each slice so the three places
    that release an adopted probe cannot drift from each other, and so a test
    can ask the patch rather than grep a script.
    """
    return {
        "name": name,
        "description": description
        or (
            "Evidence-slice probe: a local native surface taken into management "
            "so a released provider can install and remove it."
        ),
        "tags": ["evidence"],
        "license": {
            "spdx_id": "AGPL-3.0-or-later",
            "redistribution_allowed": True,
        },
    }


def write_release_draft_patch(
    path: Path,
    *,
    name: str,
    description: str | None = None,
) -> Path:
    """Write `release_draft_patch` as canonical JSON at `path`."""
    path.write_text(
        json.dumps(release_draft_patch(name=name, description=description), indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def release_draft_update_arguments(stable_id: str, revision_id: str, patch: Path) -> list[str]:
    """The exact `component passport update` argv that binds one closed patch."""
    return [
        "component",
        "passport",
        "update",
        "--id",
        stable_id,
        "--expected-revision",
        revision_id,
        "--from",
        str(patch),
    ]


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
