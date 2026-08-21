"""The whole of this CLI's analytics egress: one consented, anonymous GET.

`ADR-0112` decided the shape and `SPEC-013` `REQ-1316`-`REQ-1319` state the
behaviour. The field list is closed and lives in `docs/contracts/cli-telemetry.md`;
adding one means editing all three, which is the point.

Two rules shape almost every decision here.

Consent is an *event*, not a value. It is recorded where the CLI keeps state
rather than where it keeps settings, so "enabled" cannot appear by editing a
file with nobody able to say where it came from. `config set` may switch the
feature off; it may not switch it on.

Refusal and never-having-been-asked are observably identical on the network.
They differ only in whether anything asks again, and that difference never
leaves the machine — otherwise the absence of a ping would itself be a signal
about the operator.
"""

from __future__ import annotations

import contextlib
import json
import os
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast
from urllib.parse import urlsplit

from ai_stp_cli.paths import data_dir

#: Never asked. No request, and the next `doctor` or Skill start may ask once.
STATE_NOT_ASKED: Final[str] = "not_asked"
#: Asked and refused. No request, and nothing asks again.
STATE_DECLINED: Final[str] = "declined"
#: Asked and accepted. Requests are sent while `telemetry.enabled` stays true.
STATE_ACCEPTED: Final[str] = "accepted"

#: The closed set, in the order `docs/contracts/cli-telemetry.md` states it. A
#: tuple rather than a comment: the builder below refuses anything outside it,
#: so widening the request means widening this and the contract together.
PING_FIELDS: Final[tuple[str, ...]] = (
    "os",
    "harness",
    "harness_version",
    "ai_stp_version",
    "component_type",
    "name",
    "source",
    "id",
    "version",
    "anon",
)

#: Short on purpose. A collector that is slow is a collector that is not
#: answering, and an install must not wait on one.
TIMEOUT_SECONDS: Final[float] = 2.0

#: Set by the test suite and by anything rehearsing an install. Nothing here
#: reaches the network while it is set, which is what keeps `just check` from
#: touching a live collector.
SUPPRESS_ENVIRONMENT: Final[str] = "AI_STP_TELEMETRY_SUPPRESS"


@dataclass(frozen=True)
class Consent:
    """What the operator answered, and the identifier that answer created."""

    state: str
    anon: str = ""

    @property
    def accepted(self) -> bool:
        return self.state == STATE_ACCEPTED and bool(self.anon)


def record_path() -> Path:
    """Where the answer lives: local state, deliberately not the config file."""
    return data_dir() / "telemetry-consent.json"


def consent() -> Consent:
    """The recorded answer, or "never asked" when there is nothing to read.

    Unreadable is treated as never asked rather than as an error. This is not a
    path anybody invoked; it is consulted while an install is settling, and a
    corrupt byte there must not become a failed installation.
    """
    path = record_path()
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Consent(STATE_NOT_ASKED)
    if not isinstance(document, dict):
        return Consent(STATE_NOT_ASKED)
    held = cast(dict[str, object], document)
    state = str(held.get("state") or STATE_NOT_ASKED)
    if state not in {STATE_NOT_ASKED, STATE_DECLINED, STATE_ACCEPTED}:
        return Consent(STATE_NOT_ASKED)
    return Consent(state, str(held.get("anon") or ""))


def accept() -> Consent:
    """Record acceptance and mint a fresh anonymous identifier.

    Fresh every time. Re-consenting after a refusal must not resurrect the
    previous identifier, or turning the feature off and on again would link the
    two periods together — which is exactly what an operator switching it off
    was avoiding.
    """
    answer = Consent(STATE_ACCEPTED, str(uuid.uuid4()))
    _write(answer)
    return answer


def decline() -> Consent:
    """Record refusal and forget the identifier.

    The state is kept and the identifier is not. Keeping the state is what stops
    the question being asked again; keeping the identifier would leave behind
    the one thing consent was needed for.
    """
    answer = Consent(STATE_DECLINED)
    _write(answer)
    return answer


def forget() -> None:
    """Drop the identifier while leaving the recorded answer alone.

    Switching the feature off through `config set` is not the same as being
    asked and refusing, so it does not overwrite the answer — but it must still
    remove the identifier, because "off" that keeps one is off in name only.
    """
    answer = consent()
    if answer.anon:
        _write(Consent(answer.state))


def _write(answer: Consent) -> None:
    path = record_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    document: dict[str, str] = {"state": answer.state}
    if answer.anon:
        document["anon"] = answer.anon
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    # Windows decides by ACL and the mode call means nothing there. The file
    # holds no secret in any case: a random identifier is not one.
    with contextlib.suppress(OSError):
        path.chmod(0o600)


def suppressed() -> bool:
    """Whether anything at all may reach the network from here."""
    return bool(os.environ.get(SUPPRESS_ENVIRONMENT))


def address_allowed(url: str) -> bool:
    """Whether this collector address may be used at all.

    The same rule the catalogue address follows, for the same reason: cleartext
    is acceptable only where the packets never leave the machine.
    """
    parsed = urlsplit(url)
    if parsed.scheme == "https":
        return bool(parsed.hostname)
    if parsed.scheme != "http" or not parsed.hostname:
        return False
    host = parsed.hostname.lower()
    return host == "localhost" or host in {"127.0.0.1", "::1"}


def ping(
    *,
    operating_system: str,
    harness: str,
    harness_version: str,
    ai_stp_version: str,
    component_type: str,
    name: str,
    source: str,
    identifier: str,
    version: str,
    anon: str,
) -> dict[str, str] | None:
    """The exact query for one installed component, or nothing to send.

    Nothing to send is a real answer rather than a degraded one. An object with
    no public name and no kind cannot be described without describing the
    machine it was found on, so the request simply does not happen — which is
    the rule `REQ-1317` states and the reason this returns `None` instead of
    filling a field with a placeholder.
    """
    if source not in {"platform", "github"}:
        return None
    fields = {
        "os": operating_system,
        "harness": harness,
        "harness_version": harness_version,
        "ai_stp_version": ai_stp_version,
        "component_type": component_type,
        "name": name,
        "source": source,
        "id": identifier,
        "version": version,
        "anon": anon,
    }
    if any(not str(value).strip() for value in fields.values()):
        return None
    # Belt and braces against a future edit adding a key here and forgetting the
    # contract. The set is closed, and this is where that is enforced.
    if tuple(fields) != PING_FIELDS:
        return None
    return fields


def send(url: str, fields: Mapping[str, str]) -> bool:
    """Send one ping. Never raises, and says only whether it went.

    Fail-open is a requirement rather than a convenience (`REQ-1318`): the
    result of an installation is a property of the target, not of somebody's
    network. A collector that is down, slow or answering 500 changes nothing
    about whether the setup is installed, so nothing here can be allowed to
    surface as a failure or to retry in a batch.
    """
    if suppressed() or not address_allowed(url):
        return False
    try:
        import httpx

        response = httpx.get(url, params=dict(fields), timeout=TIMEOUT_SECONDS)
    except Exception:
        # Deliberately everything. `REQ-1318` makes this fail-open, and an
        # exception class nobody anticipated is exactly the case that would
        # otherwise turn a healthy install into a red one.
        return False
    return 200 <= response.status_code < 300
