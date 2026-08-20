"""An apply killed mid-flight, and what the next process is allowed to say.

`#173` asks for resumption to pass the failure matrix. Every other row of that
matrix can be driven in-process, because a provider reporting `failed` is just a
provider answering. This row cannot: the thing being proved is that the record
survives the process that was writing it, and a test that never loses a process
proves the opposite of what it claims.

So the CLI is started as a real process, the provider blocks, and the whole
process group is killed with `SIGKILL` — no handler, no `finally`, no chance to
tidy up. Then a **different** process reads the registry and has to say
something honest about what it found.

The honest thing is `applying`. Not `verified`, because nobody checked; not
`failed`, because the provider may well have finished its work in the instant
before the kill. `operation.md` is explicit that an external call that did not
come back does not prove the absence of an effect, and this is that sentence
made into a process.
"""

import json
import os
import signal
import stat
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest

from ai_stp_cli.provider import protocol

pytestmark = pytest.mark.skipif(
    os.name == "nt",
    reason="the restart oracle requires POSIX process groups and SIGKILL",
)

HARNESS = "claude-code"
TARGET = "sha256:" + "a" * 64

#: How long the blocked provider stays blocked. Long enough that the kill is
#: never a race with it finishing, short enough that an orphan cannot outlive
#: the test session by much.
BLOCK_SECONDS = 60

#: Answers every provider here gives, apart from the one that blocks.
ANSWERS: dict[str, object] = {
    "provider-info": {
        "protocol_version": 1,
        "harness_id": HARNESS,
        "provider_version": "1.0.0",
        "supported_actions": list(protocol.COMMANDS),
        "bundle_formats": ["ai-stp-bundle/1"],
        "supported_os": ["linux", "macos"],
        "supported_arch": ["x86_64", "arm64"],
        "limits": {},
    },
    "status": {"state": "verified", "target_digest": TARGET},
}

_PROVIDER_LOGIC = """
def answer(command, arguments):
    values = dict(zip(arguments[0::2], arguments[1::2], strict=True))
    common = {
        'bundle_format': values.get('--bundle-format', ''),
        'bundle_digest': values.get('--bundle-digest', ''),
        'artifact_digest': values.get('--artifact-digest', ''),
        'bundle_size': int(values.get('--bundle-size', '0')),
    }
    if command in ANSWERS:
        return ANSWERS[command]
    if command == 'validate-bundle':
        return {**common, 'valid': True}
    if command == 'plan-bundle':
        raw = json.dumps(arguments, separators=(',', ':')).encode()
        return {
            **common,
            'state': 'planned',
            'plan_digest': 'sha256:' + hashlib.sha256(raw).hexdigest(),
            'expected_target_digest': values['--expected-target-digest'],
            'effects': ['write exact HarnessBundle'],
        }
    if command == 'apply-bundle':
        return {
            **common,
            'state': 'verified',
            'backup_ref': 'backup_1',
            'plan_digest': values['--plan-digest'],
            'expected_target_digest': values['--expected-target-digest'],
        }
    return {'answered': command}
"""


@dataclass(frozen=True)
class Ready:
    """A home with one confirmed composition, and the providers to install it."""

    home: Path
    work: Path
    quick: Path
    blocking: Path
    started: Path
    component_id: str


def _environment(home: Path) -> dict[str, str]:
    return {
        **os.environ,
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / "config"),
        "XDG_DATA_HOME": str(home / "data"),
        "DBUS_SESSION_BUS_ADDRESS": "unix:path=/nonexistent",
        "AI_STP_FORCE_FILE_CREDENTIAL_STORE": "1",
    }


def _ok(*argv: str, home: Path) -> dict[str, Any]:
    finished = subprocess.run(
        [sys.executable, "-m", "ai_stp_cli", *argv, "--json"],
        capture_output=True,
        text=True,
        env=_environment(home),
        check=False,
    )
    assert finished.stdout, f"{argv}: nothing on stdout; stderr {finished.stderr[:400]}"
    answer = json.loads(finished.stdout)
    assert answer["ok"] is True, f"{argv}: {json.dumps(answer.get('error'))}"
    return answer["data"]


def _executable(place: Path, body: str) -> Path:
    place.write_text(body, encoding="utf-8")
    place.chmod(place.stat().st_mode | stat.S_IXUSR)
    return place


def _quick(place: Path) -> Path:
    return _executable(
        place,
        "#!/usr/bin/env python3\n"
        "import hashlib, json, sys\n"
        f"ANSWERS = json.loads(r'''{json.dumps(ANSWERS)}''')\n"
        f"{_PROVIDER_LOGIC}\n"
        "print(json.dumps(answer(sys.argv[1], sys.argv[4:])))\n",
    )


def _blocking(place: Path, started: Path) -> Path:
    """Answers everything but `apply-bundle`, where it announces itself and waits.

    The marker matters: killing on a timer would sometimes kill before the
    provider was ever reached, and that is a different situation with the same
    appearance.
    """
    return _executable(
        place,
        "#!/usr/bin/env python3\n"
        "import hashlib, json, sys, time\n"
        f"ANSWERS = json.loads(r'''{json.dumps(ANSWERS)}''')\n"
        f"{_PROVIDER_LOGIC}\n"
        "if sys.argv[1] == 'apply-bundle':\n"
        f"    open({str(started)!r}, 'w').write('reached')\n"
        f"    time.sleep({BLOCK_SECONDS})\n"
        "print(json.dumps(answer(sys.argv[1], sys.argv[4:])))\n",
    )


@pytest.fixture(scope="module")
def ready(tmp_path_factory: pytest.TempPathFactory) -> Ready:
    root = tmp_path_factory.mktemp("restart")
    home, work = root / "home", root / "work"
    home.mkdir()
    (work / ".git").mkdir(parents=True)
    (work / "pyproject.toml").write_text('[project]\nname = "thing"\n', encoding="utf-8")
    (work / "CLAUDE.md").write_text("# Project rules\n\nBe careful.\n", encoding="utf-8")

    for argv in (
        ("device", "init"),
        ("passport", "developer", "init"),
        ("passport", "device", "refresh"),
    ):
        _ok(*argv, home=home)
    _ok("project", "passport", "--root", str(work), home=home)

    adopted = _ok(
        "component", "adopt", "--path", str(work / "CLAUDE.md"), "--root", str(work), home=home
    )
    component_id = str(adopted["stable_id"])
    _ok("component", "version", "release", "--id", component_id, "--confirm", home=home)

    started = root / "provider-was-reached"
    return Ready(
        home=home,
        work=work,
        quick=_quick(root / "quick"),
        blocking=_blocking(root / "blocking", started),
        started=started,
        component_id=component_id,
    )


def _installable(ready: Ready) -> str:
    """One freshly confirmed composition, so each kill gets its own operation.

    A plan is idempotent on its composition and target (`REQ-805`), so asking
    twice about one proposal returns the operation already recorded — which is
    right, and which would make every test after the first inspect the corpse
    of the first one's kill.
    """
    proposed = _ok(
        "select",
        "propose",
        "--harness",
        HARNESS,
        "--project",
        str(ready.work),
        "--member",
        f"{ready.component_id}@1.0",
        home=ready.home,
    )
    proposal_id = str(proposed["proposals"][0]["proposal_id"])
    _ok("select", "confirm", "--proposal", proposal_id, "--confirm", home=ready.home)
    _ok(
        "select",
        "bundle",
        "--harness",
        HARNESS,
        "--proposal",
        proposal_id,
        "--project",
        str(ready.work),
        home=ready.home,
    )
    return proposal_id


def _killed_mid_apply(ready: Ready) -> str:
    """Plan, approve, then lose the process while the provider holds the call."""
    planned = _ok(
        "install",
        "plan",
        "--proposal",
        _installable(ready),
        "--provider",
        str(ready.quick),
        home=ready.home,
    )
    operation = str(planned["operation_id"])
    _ok(
        "install",
        "approve",
        "--operation",
        operation,
        "--plan-digest",
        str(planned["plan_digest"]),
        home=ready.home,
    )

    running = subprocess.Popen(
        [
            *(sys.executable, "-m", "ai_stp_cli"),
            *("install", "apply", "--operation", operation),
            *("--provider", str(ready.blocking), "--json"),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_environment(ready.home),
        # Its own group, so the kill takes the provider with it rather than
        # leaving a child sleeping for a minute after the test has finished.
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 60
        while not ready.started.exists():
            assert running.poll() is None, "the apply finished before the provider was reached"
            assert time.monotonic() < deadline, "the provider was never reached"
            time.sleep(0.05)
        # SIGKILL, not SIGTERM: a signal that can be handled proves that the
        # handler works, and there is no handler here to prove anything about.
        getpgid = cast(Callable[[int], int], getattr(os, "getpgid"))  # noqa: B009
        killpg = cast(Callable[[int, int], None], getattr(os, "killpg"))  # noqa: B009
        sigkill = cast(int, getattr(signal, "SIGKILL"))  # noqa: B009
        killpg(getpgid(running.pid), sigkill)
    finally:
        running.wait(timeout=30)
    ready.started.unlink()
    return operation


def test_the_provider_really_was_reached_before_the_kill(ready: Ready) -> None:
    """Otherwise every assertion below is about a process that never got started."""
    operation = _killed_mid_apply(ready)
    report = _ok("install", "recover", "--operation", operation, home=ready.home)
    assert report["effects_recorded"], (
        "the apply was killed before it recorded reaching the provider"
    )


def test_a_killed_apply_is_still_applying_and_claims_nothing(ready: Ready) -> None:
    """The one answer that is true: we started, and we do not know the rest."""
    operation = _killed_mid_apply(ready)
    report = _ok("install", "recover", "--operation", operation, home=ready.home)

    assert report["state"] == "applying"
    assert report["state"] not in {"verified", "failed", "rolled_back", "cancelled"}
    assert report["next_actions"], "an operation nobody is told what to do about"


def test_the_next_process_finds_it_without_being_told_where_to_look(ready: Ready) -> None:
    """Recovery that needs the identifier the lost process printed is no recovery."""
    operation = _killed_mid_apply(ready)
    stopped = _ok("install", "status", home=ready.home)
    assert operation in {str(item["operation_id"]) for item in stopped["stopped"]}


def test_the_record_written_before_the_kill_survived_it(ready: Ready) -> None:
    """A durable journal is the whole claim; SIGKILL is how it gets checked."""
    operation = _killed_mid_apply(ready)
    report = _ok("install", "recover", "--operation", operation, home=ready.home)
    assert report["operation_id"] == operation
    # The plan and the approval were written by a process that no longer exists.
    assert report["state"] == "applying"


def test_a_later_process_can_settle_what_the_killed_one_left(ready: Ready) -> None:
    """Resumption, which is the check the lost process owed and never made.

    `install resume` sends no bundle. It asks the provider what the target is
    now and writes down the answer — the postcondition check that `verified`
    has always required. Without it an operation killed mid-apply would sit in
    `applying` forever: cancelling is gone once an effect may have happened,
    and applying again is the retry `operation.md` forbids.
    """
    operation = _killed_mid_apply(ready)
    settled = _ok(
        "install",
        "resume",
        "--operation",
        operation,
        "--provider",
        str(ready.quick),
        home=ready.home,
    )
    assert settled["state"] == "verified"
    states = [str(item["state_after"]) for item in settled["steps"]]
    # Through `applied_unverified`, never around it: the provider was called,
    # so "the effect may have happened" is the only honest way past.
    assert states[-3:] == ["applying", "applied_unverified", "verified"]

    stopped = _ok("install", "status", home=ready.home)
    assert operation not in {str(item["operation_id"]) for item in stopped["stopped"]}


def test_a_provider_that_cannot_confirm_the_target_leaves_it_partial(ready: Ready) -> None:
    """`partial`, not `failed`: after the call, "nothing was done" is not ours to say."""
    operation = _killed_mid_apply(ready)
    unsure = _executable(
        ready.home.parent / "unsure",
        "#!/usr/bin/env python3\nimport json, sys\n"
        f"ANSWERS = json.loads(r'''{json.dumps(ANSWERS)}''')\n"
        "if sys.argv[1] == 'status':\n"
        "    print(json.dumps({'state': 'partial', 'target_digest': ''}))\n"
        "    raise SystemExit(0)\n"
        'print(json.dumps(ANSWERS.get(sys.argv[1], {"answered": sys.argv[1]})))\n',
    )
    settled = _ok(
        "install", "resume", "--operation", operation, "--provider", str(unsure), home=ready.home
    )
    assert settled["state"] == "partial"


def test_a_settled_operation_cannot_be_resumed(ready: Ready) -> None:
    """Resuming a finished operation would rewrite an answer somebody already has."""
    operation = _killed_mid_apply(ready)
    _ok(
        "install",
        "resume",
        "--operation",
        operation,
        "--provider",
        str(ready.quick),
        home=ready.home,
    )
    finished = subprocess.run(
        [
            *(sys.executable, "-m", "ai_stp_cli"),
            *("install", "resume", "--operation", operation),
            *("--provider", str(ready.quick), "--json"),
        ],
        capture_output=True,
        text=True,
        env=_environment(ready.home),
        check=False,
    )
    answer = json.loads(finished.stdout)
    assert answer["ok"] is False
    assert answer["error"]["code"] == "AI_STP_PRECONDITION_FAILED"


def test_a_second_apply_does_not_quietly_start_over(ready: Ready) -> None:
    """`operation.md`: a partial or unfinished operation is not retried by itself.

    Re-running `apply` against the same operation must not walk it back to the
    beginning as though nothing had been recorded. Whatever it answers, it may
    not produce a fresh `applying` after the one already in the journal.
    """
    operation = _killed_mid_apply(ready)
    finished = subprocess.run(
        [
            *(sys.executable, "-m", "ai_stp_cli"),
            *("install", "apply", "--operation", operation),
            *("--provider", str(ready.quick), "--json"),
        ],
        capture_output=True,
        text=True,
        env=_environment(ready.home),
        check=False,
    )
    answer = json.loads(finished.stdout)
    if answer["ok"] is False:
        assert str(answer["error"]["code"]).startswith("AI_STP_")
        return
    states = [str(item["state_after"]) for item in answer["data"]["steps"]]
    assert states.count("applying") == 1, states
