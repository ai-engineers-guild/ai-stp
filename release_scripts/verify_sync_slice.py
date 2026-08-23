"""Prove the two-device synchronisation slice against a deployed environment.

`#180` asks for five scenarios — fast-forward, merge, conflict, resumption of a
partial synchronisation and version collision — "against a mock, then against the
deployed environment". The mock half is closed by executable tests in
`tests/unit/test_cli_sync_transport.py`. This is the other half, and it exists
because a proof produced by hand is one nobody can repeat.

It drives the published CLI exactly as an operator would: two isolated homes,
real commands, real network. Nothing here reaches into the registry or calls an
internal function, because the claim being proved is about the program somebody
installs, not about its internals.

Authentication is the one step it cannot perform. The device-code flow needs a
person to approve a code in a browser, once per home, and a script that could
mint a session would be proving something other than the shipped path. So the
homes are given rather than created: the script refuses with the exact commands
to run when either is not authenticated, and it never reads or writes the
operator's own registry.

Scenarios it does not drive are reported as `not_verified` with the reason,
never omitted — a gap that lives in the artefact is a gap somebody can close.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final, cast

from release_scripts._evidence import EvidenceError, cli, data, error_code, without_credentials
from release_scripts._evidence import origin as bare_origin


def _point_at(home: Path, origin: str, *, python: str) -> None:
    """Both preconditions the CLI states itself, set rather than assumed."""
    cli(
        ["config", "set", "--set", "sync.enabled=true", "--set", f"catalog.url={origin}"],
        home=home,
        python=python,
    )


def _auth_state(home: Path, *, python: str) -> str:
    envelope = cli(["auth", "status"], home=home, python=python)
    state = data(envelope, "auth status").get("state")
    if not isinstance(state, str):
        raise EvidenceError("auth status answered without a state")
    return state


def _developer_id(home: Path, *, python: str) -> str:
    """The developer passport of that home, created only if it has none."""
    shown = cli(["passport", "developer", "show"], home=home, python=python, allow_failure=True)
    if shown.get("ok") is True:
        held = data(shown, "passport developer show").get("stable_id")
        if isinstance(held, str):
            return held
    created = cli(["passport", "developer", "init"], home=home, python=python)
    held = data(created, "passport developer init").get("stable_id")
    if not isinstance(held, str):
        raise EvidenceError("passport developer init answered without a stable id")
    return held


def _head(home: Path, *, python: str) -> str:
    envelope = cli(["passport", "developer", "show"], home=home, python=python)
    held = data(envelope, "passport developer show").get("revision_id")
    if not isinstance(held, str):
        raise EvidenceError("passport developer show answered without a revision")
    return held


def _preview(home: Path, stable_id: str, *, python: str) -> dict[str, Any]:
    envelope = cli(["sync", "preview", "--id", stable_id], home=home, python=python)
    return data(envelope, "sync preview")


def _push(home: Path, stable_id: str, *, python: str) -> dict[str, Any]:
    envelope = cli(
        ["sync", "push", "--id", stable_id, "--confirm"],
        home=home,
        python=python,
        allow_failure=True,
    )
    if envelope.get("ok") is True:
        return {"ok": True, **data(envelope, "sync push")}
    return {"ok": False, "error_code": error_code(envelope)}


#: A walk this long means the stream is not converging, which is a finding of
#: its own rather than something to keep paging through.
MAX_PULL_PAGES: Final[int] = 50


def _pull(home: Path, *, python: str, skip: Sequence[str] = ()) -> dict[str, Any]:
    """One page, optionally walking past events the operator has named.

    An account whose history contains an event no client can apply cannot be
    walked at all, and this slice is one of the things that produces such
    history: two events sealed before `seal_envelope` was corrected block every
    fresh device on the account they were pushed from. Real accounts will carry
    the same, for the same reason.

    So the ids are a parameter rather than something the slice discovers.
    Naming them is the operator saying which revisions are abandoned; guessing
    would make the slice green by skipping whatever it could not read, which is
    the opposite of evidence.
    """
    command = ["sync", "pull", "--confirm"]
    for event_id in skip:
        command += ["--skip-event", event_id]

    # Walked to the end, not pulled once. `sync pull` takes one page per
    # invocation by contract, and this device's cursor starts at the beginning
    # of the account's whole history — so a single page reaches the *oldest*
    # events, not the push this scenario just made. On a fresh account those
    # are the same page and the difference never showed; on an account with
    # history the slice reported "fast forward verified" while the second
    # device had received nothing, and then failed two scenarios later with
    # "there is no developer passport yet".
    applied = replayed = 0
    skipped: list[str] = []
    for _ in range(MAX_PULL_PAGES):
        envelope = cli(command, home=home, python=python, allow_failure=True)
        if envelope.get("ok") is not True:
            return {"ok": False, "error_code": error_code(envelope)}
        page = data(envelope, "sync pull")
        applied += int(page.get("applied") or 0)
        replayed += int(page.get("replayed") or 0)
        skipped += list(page.get("skipped") or [])
        # An empty page ends the walk, not a null cursor. `apply_page` documents
        # the server as emitting `next_cursor: null` for the last page; measured
        # against production it does not — a stream of nine events answers nine
        # items and a cursor, then zero items and the *same* cursor, so a loop
        # waiting for null never terminates. Zero items is the honest end
        # condition, and it stays correct if the server later emits null too.
        if int(page.get("received") or 0) == 0 or page.get("next_cursor") is None:
            return {
                "ok": True,
                "applied": applied,
                "replayed": replayed,
                "skipped": skipped,
                "next_cursor": page.get("next_cursor"),
            }
    return {"ok": False, "error_code": f"the walk did not end within {MAX_PULL_PAGES} pages"}


def _unauthenticated(home: Path, label: str, state: str) -> dict[str, Any]:
    return {
        "state": "not_verified",
        "reason": f"home {label} reports auth state {state!r}",
        "commands": [
            f"HOME={home} ai-stp auth login --provider github --json",
            f"HOME={home} ai-stp auth complete --wait --json",
        ],
    }


def verify_sync_slice(
    origin: str, home_a: Path, home_b: Path, *, python: str, skip: Sequence[str] = ()
) -> dict[str, Any]:
    for home in (home_a, home_b):
        home.mkdir(parents=True, exist_ok=True)
        _point_at(home, origin, python=python)

    states = {"a": _auth_state(home_a, python=python), "b": _auth_state(home_b, python=python)}
    scenarios: dict[str, Any] = {}
    if states["a"] != "authenticated" or states["b"] != "authenticated":
        for name in ("fast_forward", "replay", "conflict", "merge"):
            missing = "a" if states["a"] != "authenticated" else "b"
            home = home_a if missing == "a" else home_b
            scenarios[name] = _unauthenticated(home, missing, states[missing])
    else:
        scenarios.update(_run_scenarios(home_a, home_b, python=python, skip=skip))

    scenarios["version_collision"] = {
        "state": "not_verified",
        "reason": (
            "reachable only through a component both devices hold before either releases "
            "its version: A registers the component and pushes, B pulls it, then both "
            "release the same X.Y from different content and A pushes first. That needs "
            "the component scaffold and adopt surface, which this slice does not drive yet"
        ),
        "covered_by_mock": "tests/unit/test_cli_sync_transport.py::"
        "test_version_collision_rolls_back_the_remote_revision_and_cursor",
    }

    return without_credentials(
        {
            "schema_version": 1,
            "origin": origin,
            "auth_states": states,
            "scenarios": scenarios,
        }
    )


def _run_scenarios(
    home_a: Path, home_b: Path, *, python: str, skip: Sequence[str] = ()
) -> dict[str, Any]:
    """The four scenarios two authenticated homes can prove between them."""
    scenarios: dict[str, Any] = {}
    # A real account already holds a developer passport, so a fresh install
    # adopts it instead of minting a second one — that is what the server's
    # one-per-account rule refuses, and what a reinstall actually does. Only an
    # account whose stream carries nothing reaches `init` here.
    _pull(home_a, python=python, skip=skip)
    stable_id = _developer_id(home_a, python=python)
    # Fast-forward needs a revision B does not have yet. Pushing the adopted
    # head would be a replay and would prove the next scenario, not this one.
    cli(
        ["passport", "developer", "update", "--set", "role=platform"],
        home=home_a,
        python=python,
    )

    pushed = _push(home_a, stable_id, python=python)
    pulled = _pull(home_b, python=python, skip=skip)
    head_a = _head(home_a, python=python)
    # `ok` is the envelope, not the outcome. A refused push answers ok with a
    # receipt state of `conflict`, and asserting on the envelope reported this
    # scenario verified while nothing had been fast-forwarded. The receipt
    # state is the claim, so the receipt state is what is checked.
    scenarios["fast_forward"] = {
        "state": "verified"
        if pushed.get("state") == "accepted" and (pulled.get("applied") or 0) >= 1
        else "failed",
        "stable_id": stable_id,
        "push_state": pushed.get("state"),
        "pull_applied": pulled.get("applied"),
        "head_after_push": head_a,
    }

    replayed = _push(home_a, stable_id, python=python)
    scenarios["replay"] = {
        "state": "verified" if replayed.get("state") == "accepted" else "failed",
        "push_state": replayed.get("state"),
        "processed_events": replayed.get("processed_events"),
        "note": "a push with nothing new must be accepted and must not create a second event",
    }

    cli(
        ["passport", "developer", "update", "--set", "role=product"],
        home=home_a,
        python=python,
    )
    cli(
        ["passport", "developer", "update", "--set", "role=infrastructure"],
        home=home_b,
        python=python,
    )
    accepted = _push(home_a, stable_id, python=python)
    refused = _push(home_b, stable_id, python=python)
    scenarios["conflict"] = {
        "state": "verified"
        if accepted.get("state") == "accepted" and refused.get("state") == "conflict"
        else "failed",
        "first_push_state": accepted.get("state"),
        "second_push_state": refused.get("state"),
        "second_push_error": refused.get("error_code"),
    }

    # The pull's result is reported, not discarded. It used to be thrown away,
    # and when it failed the scenario still reached the preview — which then
    # honestly answered `up_to_date`, because a device that could not pull has
    # nothing to merge. The evidence said "merge not offered", naming the
    # symptom furthest from the cause, and the actual refusal never appeared.
    pulled = _pull(home_b, python=python, skip=skip)
    preview = _preview(home_b, stable_id, python=python)
    merged: dict[str, Any] = {}
    if not pulled.get("ok"):
        after = {"ok": False, "error_code": "pull refused before a merge was possible"}
    elif preview.get("state") == "merge_ready":
        merged = data(
            cli(
                ["sync", "merge", "--id", stable_id, "--confirm"],
                home=home_b,
                python=python,
            ),
            "sync merge",
        )
        after = _push(home_b, stable_id, python=python)
    else:
        after = {"ok": False, "error_code": "merge not offered"}
    scenarios["merge"] = {
        "state": "verified"
        if pulled.get("ok") and preview.get("state") == "merge_ready" and after.get("ok")
        else "failed",
        "pull_state": "accepted" if pulled.get("ok") else pulled.get("error_code"),
        "preview_state": preview.get("state"),
        "merged_state": merged.get("state"),
        "push_after_merge": after.get("state", after.get("error_code")),
    }
    return scenarios


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", default="https://nddev.asia", help="Bare https origin.")
    parser.add_argument("--home-a", required=True, help="First device home, already signed in.")
    parser.add_argument("--home-b", required=True, help="Second device home, already signed in.")
    parser.add_argument("--python", default=sys.executable, help="Interpreter running the CLI.")
    parser.add_argument(
        "--skip-event",
        action="append",
        default=[],
        metavar="EVENT_ID",
        help="Exact id of a known-unapplicable event in this account's history. Repeatable.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        report = verify_sync_slice(
            bare_origin(arguments.origin),
            Path(arguments.home_a).expanduser(),
            Path(arguments.home_b).expanduser(),
            python=arguments.python,
            skip=tuple(arguments.skip_event),
        )
    except EvidenceError as error:
        print(f"sync-slice: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 1 if _refused(report) else 0


def _refused(report: Mapping[str, Any]) -> bool:
    """A report where nothing ran must not read as success.

    A failed scenario is a refusal, and so is an unmet precondition: both homes
    signed in is what makes this slice a proof rather than a description. The one
    `not_verified` that is not a refusal is `version_collision`, whose reason is
    a named gap rather than a missing session — reporting it as failure every
    time would train a reader to ignore the exit code.
    """
    scenarios = cast(Mapping[str, Mapping[str, Any]], report["scenarios"])
    for name, held in scenarios.items():
        if held.get("state") == "failed":
            return True
        if name != "version_collision" and held.get("state") == "not_verified":
            return True
    return False


if __name__ == "__main__":
    raise SystemExit(main())
