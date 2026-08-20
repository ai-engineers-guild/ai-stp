"""Prove the publication and authorisation surface against a deployed environment.

`#182` asks that the machine commands for publication, author attestation,
grants, reports and owner reads pass the contract against the deployed
environment, and that they carry neither credentials nor source code out of the
allowed set. The client half has been implemented for a while; what was missing
is a run somebody else can repeat.

The split here is deliberate and is the whole design. Reading what an account
owns changes nothing and runs by default. Publishing a version, inviting a
person, or filing a report changes the deployed catalogue or somebody's access,
and one of them is irreversible in the way that matters — a published `X.Y` is
immutable. Those are reported as `not_verified` with the reason unless the
operator names the object and passes `--allow-writes`, which is a decision the
script must not make on their behalf.

Authentication is not automated, for the same reason as the sync slice: the
device-code flow needs a person, and a script able to mint a session would prove
a path nobody ships.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

from release_scripts._evidence import EvidenceError, cli, data, error_code, without_credentials
from release_scripts._evidence import origin as bare_origin

# Read-only commands, each named with the surface it proves. A command that
# changes nothing can run against production without a decision.
READS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("owner_objects", ("owner", "objects")),
    ("grant_list", ("grant", "list")),
    ("report_list", ("report", "list")),
)

# Everything that mutates. Named rather than omitted, so the artefact shows what
# a full run would still need.
WRITES: tuple[tuple[str, str], ...] = (
    (
        "publication",
        "publication plan/confirm writes an immutable X.Y into the deployed catalogue",
    ),
    ("attestation", "attestation sign needs an exact check, policy and harness identity to sign"),
    ("grants", "grant invite/direct/revoke changes another person's access to an object"),
    ("report", "report preview/confirm files a moderation record against a published version"),
)


def _point_at(home: Path, origin: str, *, python: str) -> None:
    cli(
        ["config", "set", "--set", "sync.enabled=true", "--set", f"catalog.url={origin}"],
        home=home,
        python=python,
    )


def _auth_state(home: Path, *, python: str) -> str:
    state = data(cli(["auth", "status"], home=home, python=python), "auth status").get("state")
    if not isinstance(state, str):
        raise EvidenceError("auth status answered without a state")
    return state


def _rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    for field in ("items", "objects", "grants", "reports"):
        held = payload.get(field)
        if isinstance(held, list):
            return [row for row in cast(list[Any], held) if isinstance(row, dict)]
    return []


def _read(name: str, arguments: Sequence[str], home: Path, *, python: str) -> dict[str, Any]:
    envelope = cli(list(arguments), home=home, python=python, allow_failure=True)
    if envelope.get("ok") is not True:
        return {
            "state": "failed",
            "command": " ".join(arguments),
            "error_code": error_code(envelope),
        }
    payload = data(envelope, " ".join(arguments))
    rows = _rows(payload)
    return {
        "state": "verified",
        "command": " ".join(arguments),
        # Identities and counts only. The criterion forbids carrying source code
        # out, and a report that pasted an object's content would be the thing it
        # is meant to rule out.
        "rows": len(rows),
        "identities": [
            row.get("stable_id") for row in rows if isinstance(row.get("stable_id"), str)
        ][:5],
    }


def _owned_detail(home: Path, identities: Sequence[str], *, python: str) -> dict[str, Any]:
    """One owned object read whole, which is the authorised-read half of `#182`."""
    if not identities:
        return {
            "state": "not_verified",
            "reason": "the account owns no object yet, so there is nothing to read back",
        }
    stable_id = identities[0]
    envelope = cli(
        ["owner", "object", "show", "--kind", "component", "--id", stable_id],
        home=home,
        python=python,
        allow_failure=True,
    )
    if envelope.get("ok") is not True:
        return {
            "state": "failed",
            "stable_id": stable_id,
            "error_code": error_code(envelope),
        }
    payload = data(envelope, "owner object show")
    return {
        "state": "verified",
        "stable_id": stable_id,
        "versions": len(cast(list[Any], payload.get("versions") or [])),
    }


def verify_publication_slice(
    origin: str,
    home: Path,
    *,
    python: str,
    allow_writes: bool = False,
) -> dict[str, Any]:
    home.mkdir(parents=True, exist_ok=True)
    _point_at(home, origin, python=python)
    state = _auth_state(home, python=python)

    scenarios: dict[str, Any] = {}
    if state != "authenticated":
        reason = f"the home reports auth state {state!r}"
        commands = [
            f"HOME={home} ai-stp auth login --provider github --json",
            f"HOME={home} ai-stp auth complete --wait --json",
        ]
        for name, _arguments in READS:
            scenarios[name] = {"state": "not_verified", "reason": reason, "commands": commands}
        scenarios["owner_object_show"] = {
            "state": "not_verified",
            "reason": reason,
            "commands": commands,
        }
    else:
        owned: list[str] = []
        for name, arguments in READS:
            result = _read(name, arguments, home, python=python)
            if name == "owner_objects":
                owned = cast(list[str], result.get("identities") or [])
            scenarios[name] = result
        scenarios["owner_object_show"] = _owned_detail(home, owned, python=python)

    for name, reason in WRITES:
        scenarios[name] = {
            "state": "not_verified",
            "reason": (
                reason + ". Pass --allow-writes with the exact object to run it"
                if not allow_writes
                else reason + ". --allow-writes was given, but this slice does not drive it yet"
            ),
        }

    return without_credentials(
        {
            "schema_version": 1,
            "origin": origin,
            "auth_state": state,
            "writes_allowed": allow_writes,
            "scenarios": scenarios,
        }
    )


def refused(report: Mapping[str, Any]) -> bool:
    """A run that proved none of the read surface must not exit zero.

    The write scenarios are `not_verified` by design rather than by accident, so
    they never decide the exit code: a code that is always red is a code nobody
    reads.
    """
    writes = {name for name, _reason in WRITES}
    scenarios = cast(Mapping[str, Mapping[str, Any]], report["scenarios"])
    for name, held in scenarios.items():
        if name in writes:
            continue
        if held.get("state") in {"failed", "not_verified"}:
            return True
    return False


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", default="https://nddev.asia", help="Bare https origin.")
    parser.add_argument("--home", required=True, help="Device home, already signed in.")
    parser.add_argument(
        "--allow-writes",
        action="store_true",
        help="Permit the scenarios that change the deployed catalogue or somebody's access.",
    )
    parser.add_argument("--python", default=sys.executable, help="Interpreter running the CLI.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        report = verify_publication_slice(
            bare_origin(arguments.origin),
            Path(arguments.home).expanduser(),
            python=arguments.python,
            allow_writes=arguments.allow_writes,
        )
    except EvidenceError as error:
        print(f"publication-slice: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 1 if refused(report) else 0


if __name__ == "__main__":
    raise SystemExit(main())
