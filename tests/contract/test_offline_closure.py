"""The whole declared offline surface, with the network genuinely switched off.

`offline-capability.md` names nine areas that must work without a network once
the first setup has succeeded. Every earlier proof of that switched the
*catalogue* off in configuration and trusted the code not to reach out anyway —
which proves the code did not take the path it was asked not to take, and
nothing about the paths nobody thought of.

Here the network is taken away instead. Every child process starts with a
`sitecustomize` that refuses to create an `AF_INET` or `AF_INET6` socket at all,
so an accidental call fails loudly wherever it is made, including inside a
library. Two controls keep that honest: one proves the guard stops a real
connection, and one proves it leaves local work alone — without the second, a
suite where everything is equally broken would pass just as quietly.

The cache is warmed *with* the network available and the proof runs *after* it
is taken away, which is the shape `#178` asks for: getting the bytes and using
the bytes are different questions. "On the exact cached bytes" is checked by
digest — the bundle compiled offline has to be the one compiled during warm-up,
not merely another bundle that also compiles.

The provider is a real executable rather than a stub, and it records which
protocol commands it was asked for, so `launch` being exercised is evidence
rather than an assertion. It runs under the frozen boundary, which passes it
`PATH` and `HOME` and nothing else — so the guard does not reach it, and that is
correct: a provider is somebody else's program, and its own offline behaviour is
its own contract. `#178` is about what `ai_stp` needs.
"""

import json
import os
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from ai_stp_cli import paths
from ai_stp_cli.provider import conformance, protocol

#: Raised by the guard, and distinctive enough that a test can tell our refusal
#: from a connection that merely failed for its own reasons.
REFUSAL = "ai-stp-offline-proof: the network is switched off"

#: Imported by `site` in every child before anything else runs. Blocks socket
#: *creation* rather than `connect`, because a datagram never connects, and
#: name resolution too, because a lookup is already a round trip.
GUARD = f'''"""Take the network away from this interpreter."""

import socket
import os
import threading

MESSAGE = {REFUSAL!r}

# `-1` is the sentinel CPython turns into `AF_INET`, so a bare `socket.socket()`
# has to be caught here as well as the spelled-out families.
_BLOCKED = frozenset({{-1, int(socket.AF_INET), int(socket.AF_INET6)}})
_real = socket.socket
_real_socketpair = socket.socketpair
_local = threading.local()


class _Offline(_real):
    def __init__(self, family=-1, *arguments, **named):
        if os.name != "nt" and int(family) in _BLOCKED:
            raise OSError(MESSAGE)
        super().__init__(family, *arguments, **named)

    def connect(self, address):
        if not getattr(_local, "socketpair", False):
            raise OSError(MESSAGE)
        return super().connect(address)

    def connect_ex(self, address):
        if not getattr(_local, "socketpair", False):
            raise OSError(MESSAGE)
        return super().connect_ex(address)


def _refuse(*_arguments, **_named):
    raise OSError(MESSAGE)


def _socketpair(*arguments, **named):
    _local.socketpair = True
    try:
        return _real_socketpair(*arguments, **named)
    finally:
        _local.socketpair = False


# A subclass rather than a function: libraries subclass `socket.socket`, and one
# that could no longer be subclassed would fail for the wrong reason.
socket.socket = _Offline
socket.socketpair = _socketpair
socket.create_connection = _refuse
socket.getaddrinfo = _refuse
'''

HARNESS = "claude-code"

#: What the provider answers, by command. Only static bytes: a provider that
#: computed anything would be proving its own behaviour rather than ours.
PROVIDER_ANSWERS: dict[str, object] = {
    "provider-info": {
        "protocol_version": 1,
        "harness_id": HARNESS,
        "provider_version": "1.0.0",
        "supported_actions": list(protocol.COMMANDS),
        "bundle_formats": ["ai-stp-bundle/1"],
        # Host platform included so Windows and Linux CI both pass the OS gate.
        "supported_os": ["linux", "macos", "windows"],
        "supported_arch": ["x86_64", "arm64"],
        "limits": {},
    },
    "status": {"state": "verified", "target_digest": "sha256:" + "a" * 64},
    "restore": {"state": "rolled_back"},
    "launch": {"state": "verified", "launched": True},
}
PROVIDER_REASONS = {item.name: item.refusal for item in conformance.MALICIOUS_BUNDLES}


@dataclass(frozen=True)
class Warm:
    """A home that has already been set up, and what was recorded while it was."""

    home: Path
    work: Path
    guard: Path
    provider: Path
    log: Path
    project_id: str
    component_id: str
    proposal_id: str
    bundle_digest: str
    bundle_artifact_digest: str
    bundle_files: str
    passport_digest: str


def _environment(home: Path, *, guard: Path | None) -> dict[str, str]:
    """The child's whole environment. `HOME` is inside the sandbox on purpose.

    `component discover` reads the harness directories of the account it runs
    as, so a real `HOME` would make this test read whatever the developer
    happens to have installed — and pass or fail accordingly.
    """
    environment = {
        **os.environ,
        "HOME": str(home),
        # Windows Path.home()/expanduser prefer USERPROFILE over HOME.
        "USERPROFILE": str(home),
        "XDG_CONFIG_HOME": str(home / "config"),
        "XDG_DATA_HOME": str(home / "data"),
        "DBUS_SESSION_BUS_ADDRESS": "unix:path=/nonexistent",
        "AI_STP_FORCE_FILE_CREDENTIAL_STORE": "1",
    }
    if os.name == "nt":
        drive = Path(home).drive or "C:"
        tail = str(home)[len(drive) :] if drive and str(home).startswith(drive) else str(home)
        environment["HOMEDRIVE"] = drive
        environment["HOMEPATH"] = tail or "\\"
    if guard is None:
        environment.pop("PYTHONPATH", None)
        return environment
    environment["PYTHONPATH"] = str(guard)
    return environment


def _run(*argv: str, home: Path, guard: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "ai_stp_cli", *argv],
        capture_output=True,
        text=True,
        env=_environment(home, guard=guard),
        check=False,
    )


def _answer(finished: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    """One envelope, parsed. A traceback is a failure of a different kind."""
    assert finished.stdout, f"nothing on stdout; stderr was: {finished.stderr[:400]}"
    return json.loads(finished.stdout)


def _ok(*argv: str, home: Path, guard: Path | None = None) -> dict[str, Any]:
    finished = _run(*argv, home=home, guard=guard)
    answer = _answer(finished)
    assert answer["ok"] is True, f"{argv}: {json.dumps(answer.get('error'))}"
    assert finished.returncode == 0, argv
    return answer["data"]


def _refused(*argv: str, home: Path, guard: Path | None = None) -> dict[str, Any]:
    """A typed refusal: a registered code, a non-zero class, and no traceback."""
    finished = _run(*argv, home=home, guard=guard)
    answer = _answer(finished)
    assert answer["ok"] is False, f"{argv} was expected to refuse"
    assert finished.returncode != 0, argv
    assert "Traceback" not in finished.stderr, finished.stderr[:400]
    error = answer["error"]
    assert str(error["code"]).startswith("AI_STP_"), error
    return error


def _provider(place: Path, log: Path) -> Path:
    """A real executable speaking the protocol, which records what it was asked.

    The answers are parsed from JSON rather than written as a Python literal:
    a literal containing `true` is not Python, and finding that out through a
    provider that fails to start is a slow way to learn it.
    """
    place.write_text(
        "#!/usr/bin/env python3\n"
        "import hashlib, json, pathlib, sys\n"
        f"ANSWERS = json.loads(r'''{json.dumps(PROVIDER_ANSWERS)}''')\n"
        f"REASONS = json.loads(r'''{json.dumps(PROVIDER_REASONS)}''')\n"
        f"open({str(log)!r}, 'a').write(sys.argv[1] + chr(10))\n"
        "command = sys.argv[1]\n"
        "arguments = sys.argv[4:]\n"
        "values = (dict(zip(arguments[0::2], arguments[1::2], strict=True)) "
        "if '--bundle' in arguments else {})\n"
        "common = {\n"
        "  'bundle_format': values.get('--bundle-format', ''),\n"
        "  'bundle_digest': values.get('--bundle-digest', ''),\n"
        "  'artifact_digest': values.get('--artifact-digest', ''),\n"
        "  'bundle_size': int(values.get('--bundle-size', '0')),\n"
        "}\n"
        "if command in ANSWERS:\n"
        "  answer = ANSWERS[command]\n"
        "elif command == 'validate-bundle' and values:\n"
        "  case = pathlib.Path(values['--bundle']).parent.name\n"
        "  answer = ({**common, 'rejected': True, 'reason': REASONS[case]} "
        "if case in REASONS else {**common, 'valid': True})\n"
        "elif command == 'plan-bundle' and values:\n"
        "  raw = json.dumps(arguments, separators=(',', ':')).encode()\n"
        "  answer = {**common, 'state': 'planned', "
        "'plan_digest': 'sha256:' + hashlib.sha256(raw).hexdigest(), "
        "'expected_target_digest': values['--expected-target-digest'], "
        "'effects': ['write exact HarnessBundle']}\n"
        "elif command == 'apply-bundle' and values:\n"
        "  answer = {**common, 'state': 'verified', 'backup_ref': 'backup_1', "
        "'plan_digest': values['--plan-digest'], "
        "'expected_target_digest': values['--expected-target-digest']}\n"
        "elif command == 'validate-bundle':\n"
        "  answer = {'rejected': True, 'reason': 'digest_mismatch'}\n"
        "else:\n"
        "  answer = {'answered': command}\n"
        "print(json.dumps(answer))\n",
        encoding="utf-8",
    )
    place.chmod(place.stat().st_mode | stat.S_IXUSR)
    return place


@pytest.fixture(scope="module")
def warm(tmp_path_factory: pytest.TempPathFactory) -> Warm:
    """Everything the offline path is allowed to depend on, fetched while online.

    Built once and shared by the checks that only read. Anything that changes
    local state takes a copy of its own through `private`: the setup a
    composition confirms is derived from the three passports (`REQ-621`), so a
    test that edited one here would move the compiled bundle underneath a test
    comparing digests — which is a fact about test order, not about the product.
    """
    root = tmp_path_factory.mktemp("offline")
    home, work = root / "home", root / "work"
    (work / ".git").mkdir(parents=True)
    home.mkdir()
    (home / ".claude").mkdir()
    (home / ".claude" / "CLAUDE.md").write_text("# Global rules\n\nBe careful.\n", encoding="utf-8")
    (work / "pyproject.toml").write_text('[project]\nname = "thing"\n', encoding="utf-8")
    (work / "CLAUDE.md").write_text("# Project rules\n\nBe careful.\n", encoding="utf-8")
    (work / "src").mkdir()
    (work / "src" / "app.py").write_text("def main() -> None: ...\n", encoding="utf-8")

    guard = root / "guard"
    guard.mkdir()
    (guard / "sitecustomize.py").write_text(GUARD, encoding="utf-8")

    log = root / "provider.log"
    provider = _provider(root / "provider", log)

    for argv in (
        ("device", "init"),
        ("passport", "developer", "init"),
        ("passport", "device", "refresh"),
    ):
        _ok(*argv, "--json", home=home)

    project = _ok("project", "index", "--root", str(work), "--json", home=home)
    assert project
    passport = _ok("project", "passport", "--root", str(work), "--json", home=home)
    component = _ok(
        "component",
        "adopt",
        "--path",
        str(home / ".claude" / "CLAUDE.md"),
        "--json",
        home=home,
    )
    component_id = str(component["stable_id"])
    component_patch = root / "component-patch.json"
    component_patch.write_text(
        json.dumps(
            {
                "name": "project-rules",
                "description": "Project instructions used by the offline closure.",
                "tags": ["offline"],
                "license": {"spdx_id": "MIT", "redistribution_allowed": True},
            }
        ),
        encoding="utf-8",
    )
    _ok(
        "component",
        "passport",
        "update",
        "--id",
        component_id,
        "--expected-revision",
        str(component["revision_id"]),
        "--from",
        str(component_patch),
        "--json",
        home=home,
    )
    released = _ok("component", "version", "release", "--id", component_id, "--json", home=home)

    # Compiled once here so that the offline compile has something exact to be
    # compared against. A bundle that merely compiles offline proves nothing
    # about which bytes went into it.
    proposal = _proposal(home, work, component_id)
    _ok("select", "confirm", "--proposal", proposal, "--json", home=home)
    bundle = _ok(
        "select",
        "bundle",
        "--harness",
        HARNESS,
        "--proposal",
        proposal,
        "--project",
        str(work),
        "--json",
        home=home,
    )

    return Warm(
        home=home,
        work=work,
        guard=guard,
        provider=provider,
        log=log,
        project_id=str(passport["stable_id"]),
        component_id=component_id,
        proposal_id=proposal,
        bundle_digest=str(bundle["digest"]),
        bundle_artifact_digest=str(bundle["artifact_digest"]),
        bundle_files=json.dumps(bundle["files"], sort_keys=True),
        passport_digest=str(released["versions"][0]["passport_digest"]),
    )


def _proposal(home: Path, work: Path, component_id: str, *, guard: Path | None = None) -> str:
    """One fresh proposal naming the adopted component. Ephemeral by `ADR-0027`."""
    answer = _ok(
        "select",
        "propose",
        "--harness",
        HARNESS,
        "--project",
        str(work),
        "--member",
        f"{component_id}@1.0",
        "--json",
        home=home,
        guard=guard,
    )
    return str(answer["proposals"][0]["proposal_id"])


@pytest.fixture
def private(warm: Warm, tmp_path: Path) -> Warm:
    """A private copy of the warmed home, for any check that changes it.

    A copy rather than a second warm-up: the point of the whole file is that
    the bytes were fetched once, and warming again per test would quietly make
    each test its own first run.
    """
    home = tmp_path / "home"
    shutil.copytree(warm.home, home)
    if not paths.POSIX:
        # `copytree` carries POSIX modes through `copystat` and carries no
        # Windows DACL at all, so the copy of a private home inherits the
        # temp directory's default grants — and `read_private` then refuses
        # it, correctly: the copy really is readable by more than its owner.
        # Re-stamp what the real first run stamps.
        from ai_stp_cli import windows_private

        for place in sorted(home.rglob("*")):
            windows_private.make_private(place)
        windows_private.make_private(home)
    log = tmp_path / "provider.log"
    return Warm(
        home=home,
        work=warm.work,
        guard=warm.guard,
        provider=_provider(tmp_path / "provider", log),
        log=log,
        project_id=warm.project_id,
        component_id=warm.component_id,
        proposal_id=warm.proposal_id,
        bundle_digest=warm.bundle_digest,
        bundle_artifact_digest=warm.bundle_artifact_digest,
        bundle_files=warm.bundle_files,
        passport_digest=warm.passport_digest,
    )


# The controls. Without these, a green suite below could mean the guard never
# loaded, or that it broke everything equally.
def test_the_guard_refuses_a_real_connection(warm: Warm) -> None:
    attempt = "import socket; socket.create_connection(('127.0.0.1', 9), timeout=1)"
    finished = subprocess.run(
        [sys.executable, "-c", attempt],
        capture_output=True,
        text=True,
        env=_environment(warm.home, guard=warm.guard),
        check=False,
    )
    assert finished.returncode != 0
    assert REFUSAL in finished.stderr


def test_without_the_guard_the_same_attempt_is_not_ours_to_refuse(warm: Warm) -> None:
    """Otherwise the refusal above might be the host's, and prove nothing."""
    attempt = "import socket; socket.create_connection(('127.0.0.1', 9), timeout=1)"
    finished = subprocess.run(
        [sys.executable, "-c", attempt],
        capture_output=True,
        text=True,
        env=_environment(warm.home, guard=None),
        check=False,
    )
    assert REFUSAL not in finished.stderr


def test_the_guard_leaves_local_work_alone(warm: Warm) -> None:
    """A suite where everything is broken passes an offline proof just as well."""
    attempt = (
        "import socket, sqlite3, pathlib;"
        "a, b = socket.socketpair();"
        "a.send(b'x');"
        "assert b.recv(1) == b'x';"
        "sqlite3.connect(':memory:').execute('select 1');"
        "print(socket.gethostname() and 'local work is fine')"
    )
    finished = subprocess.run(
        [sys.executable, "-c", attempt],
        capture_output=True,
        text=True,
        env=_environment(warm.home, guard=warm.guard),
        check=False,
    )
    assert finished.returncode == 0, finished.stderr
    assert "local work is fine" in finished.stdout


def test_the_command_line_itself_still_runs_with_the_network_gone(warm: Warm) -> None:
    """The guard must not simply break the interpreter the CLI starts in."""
    assert _ok("version", "--json", home=warm.home, guard=warm.guard)


# One test per declared offline row of `offline-capability.md`.
def test_passports_are_read_and_changed_offline(private: Warm) -> None:
    """Row: developer and project passports — read, change, revisions.

    On a copy: changing a passport changes what a composition is derived from
    (`REQ-621`), and the shared home is what the digest checks compare against.
    """
    warm = private
    for argv in (
        ("passport", "developer", "show"),
        ("passport", "device", "show"),
        ("passport", "device", "refresh"),
    ):
        assert _ok(*argv, "--json", home=warm.home, guard=warm.guard)

    changed = _ok(
        "passport",
        "developer",
        "update",
        "--set",
        "role=backend",
        "--json",
        home=warm.home,
        guard=warm.guard,
    )
    assert changed, "a passport change produced nothing offline"


def test_the_project_index_rescans_offline(warm: Warm) -> None:
    """Row: project index — full scan and rescanning."""
    for argv in (
        ("project", "discover", "--root", str(warm.work.parent)),
        ("project", "index", "--root", str(warm.work)),
        ("project", "symbols", "--root", str(warm.work)),
    ):
        assert _ok(*argv, "--json", home=warm.home, guard=warm.guard)


def test_a_rescan_offline_reads_the_same_bytes(warm: Warm) -> None:
    """ "Exact cached bytes": the identity may not move because the network did."""
    first = _ok(
        "project", "passport", "--root", str(warm.work), "--json", home=warm.home, guard=warm.guard
    )
    second = _ok(
        "project", "passport", "--root", str(warm.work), "--json", home=warm.home, guard=warm.guard
    )
    assert first["stable_id"] == warm.project_id
    assert first["revision_id"] == second["revision_id"]


def test_the_local_registry_reads_and_registers_offline(private: Warm) -> None:
    """Row: local registry — reads, drafts, registration, version pinning."""
    warm = private
    listed = _ok(
        "component",
        "version",
        "list",
        "--id",
        warm.component_id,
        "--json",
        home=warm.home,
        guard=warm.guard,
    )
    assert [item["version"] for item in listed["versions"]] == ["1.0"]
    assert listed["versions"][0]["passport_digest"] == warm.passport_digest

    adopted = _ok(
        "component",
        "adopt",
        "--path",
        str(warm.work / "CLAUDE.md"),
        "--root",
        str(warm.work),
        "--json",
        home=warm.home,
        guard=warm.guard,
    )
    assert adopted["stable_id"]


def test_local_search_answers_offline(warm: Warm) -> None:
    """Row: search — local index."""
    found = _ok("component", "find", "--json", home=warm.home, guard=warm.guard)
    # Own and pinned objects are their own lane (`ADR-0016`): an adopted
    # component is never authoritative, and looking for it there would fail for
    # a reason that has nothing to do with the network.
    assert any(item["stable_id"] == warm.component_id for item in found["local_owner_or_pinned"]), (
        "the adopted component is not findable offline"
    )


def test_composition_and_compilation_run_offline(warm: Warm) -> None:
    """Rows: selection and assembly, bundle and plan — build and inspection."""
    # Recompile the exact already-confirmed SetupVersion. A new proposal would
    # correctly create a different SetupVersion identity and therefore a
    # different bundle even when its component files happen to be equal.
    proposal = warm.proposal_id
    graph = _ok(
        "select", "graph", "--proposal", proposal, "--json", home=warm.home, guard=warm.guard
    )
    assert graph["resolved"] is True

    reports = _ok(
        "select",
        "reports",
        "--harness",
        HARNESS,
        "--proposal",
        proposal,
        "--json",
        home=warm.home,
        guard=warm.guard,
    )
    assert reports["blocked"] is False

    _ok(
        "select",
        "confirm",
        "--proposal",
        proposal,
        "--json",
        home=warm.home,
        guard=warm.guard,
    )
    bundle = _ok(
        "select",
        "bundle",
        "--harness",
        HARNESS,
        "--proposal",
        proposal,
        "--project",
        str(warm.work),
        "--json",
        home=warm.home,
        guard=warm.guard,
    )
    assert bundle["compiled"] is True
    # The whole of "on exact cached bytes": the same bytes, not merely a bundle
    # that also compiles. Both sides, because a digest alone would not say
    # *what* was hashed and a file list alone would not say it was the input.
    assert json.dumps(bundle["files"], sort_keys=True) == warm.bundle_files
    assert bundle["digest"] == warm.bundle_digest
    assert bundle["artifact_digest"] == warm.bundle_artifact_digest


def test_the_checks_run_offline(warm: Warm) -> None:
    """Row: checks — with the installed toolchain."""
    for argv in (
        ("config", "validate"),
        ("doctor",),
        ("capabilities",),
        ("toolchain", "profile"),
        ("toolchain", "harnesses"),
    ):
        assert _ok(*argv, "--json", home=warm.home, guard=warm.guard)

    eligibility = _ok(
        "select",
        "eligibility",
        "--harness",
        HARNESS,
        "--project",
        str(warm.work),
        "--json",
        home=warm.home,
        guard=warm.guard,
    )
    assert eligibility["candidates"], "nothing is selectable offline"


def test_applying_state_and_recovery_run_offline(private: Warm) -> None:
    """Rows: installation and launch — apply, state, recovery."""
    home, work = private.home, private.work
    proposal = _proposal(home, work, private.component_id, guard=private.guard)
    _ok(
        "select",
        "confirm",
        "--proposal",
        proposal,
        "--json",
        home=home,
        guard=private.guard,
    )
    _ok(
        "select",
        "bundle",
        "--harness",
        HARNESS,
        "--proposal",
        proposal,
        "--project",
        str(work),
        "--json",
        home=home,
        guard=private.guard,
    )

    planned = _ok(
        "install",
        "plan",
        "--proposal",
        proposal,
        "--provider",
        str(private.provider),
        "--json",
        home=home,
        guard=private.guard,
    )
    operation = str(planned["operation_id"])
    _ok(
        "install",
        "approve",
        "--operation",
        operation,
        "--plan-digest",
        str(planned["plan_digest"]),
        "--json",
        home=home,
        guard=private.guard,
    )

    applied = _ok(
        "install",
        "apply",
        "--operation",
        operation,
        "--provider",
        str(private.provider),
        "--json",
        home=home,
        guard=private.guard,
    )
    assert applied["state"] == "verified"

    assert _ok("install", "status", "--json", home=home, guard=private.guard)
    recovered = _ok(
        "install", "recover", "--operation", operation, "--json", home=home, guard=private.guard
    )
    assert recovered["state"] == "verified"

    settled = _ok(
        "target",
        "status",
        "--project",
        private.project_id,
        "--harness",
        HARNESS,
        "--provider",
        str(private.provider),
        # The fake provider here answers the frozen v1 conversation, and the
        # read says so: an unqualified observation speaks v3, the protocol
        # released providers actually speak.
        "--protocol-version",
        "1",
        "--json",
        home=home,
        guard=private.guard,
    )
    assert settled["states"] == ["installed"]
    assert settled["installed_version"] == "1.0"


def test_the_provider_is_launched_offline(private: Warm) -> None:
    """Row: installation and launch — launch from cached artifacts.

    There is no `ai-stp launch`: `provider-protocol.md` gives the harness
    lifecycle to the provider, and `launch` is its command. What `ai_stp` owes
    is the ability to reach it with no network, which is what this checks — and
    the provider's own log is the evidence that it really was reached.
    """
    report = _ok(
        "provider",
        "conformance",
        "--harness",
        HARNESS,
        "--executable",
        str(private.provider),
        "--json",
        home=private.home,
        guard=private.guard,
    )
    assert report["reported_version"] == 1
    assert report["conforms"] is True
    asked = private.log.read_text(encoding="utf-8").split()
    assert "launch" not in asked, "conformance must not launch against the selected target"
    assert "provider-info" in asked

    launched = conformance.subprocess_invoker(str(private.provider), str(private.work))(
        "launch", ()
    )
    assert launched == PROVIDER_ANSWERS["launch"]
    assert "launch" in private.log.read_text(encoding="utf-8").split()


# The other side of the contract: what needs the network says so, in a
# registered code, rather than answering with an empty success.
def test_an_uncached_tool_refuses_with_a_registered_reason(warm: Warm) -> None:
    """`offline-capability.md`: the first uncached fetch requires the network."""
    profile = _ok("toolchain", "profile", "--json", home=warm.home, guard=warm.guard)
    pinned = next(
        item["tools"][0]["tool_id"] for item in profile["ecosystems"] if item.get("tools")
    )
    error = _refused(
        "toolchain", "install", "--tool", pinned, "--json", home=warm.home, guard=warm.guard
    )
    assert error["code"] == "AI_STP_DEPENDENCY_UNAVAILABLE", error


def test_an_uncached_cloud_search_refuses_rather_than_answering_empty(warm: Warm) -> None:
    """A missing network may not read as "there is nothing there"."""
    error = _refused(
        "registry",
        "search",
        "--kind",
        "component",
        "--query",
        "rules",
        "--json",
        home=warm.home,
        guard=warm.guard,
    )
    assert error["code"] == "AI_STP_DEPENDENCY_UNAVAILABLE", error


def test_every_offline_row_of_the_contract_has_a_check_here() -> None:
    """The contract owns the list; this pins that the list is the one proved.

    A row added to `offline-capability.md` with nothing proving it is exactly
    the situation `#178` exists to end, and it would otherwise be invisible.
    """
    contract = Path("docs/contracts/offline-capability.md").read_text(encoding="utf-8")
    _heading, _, rest = contract.partition("## Offline operations")
    table, _, _remainder = rest.partition("\n## ")
    rows = [
        line.split("|")[1].strip()
        for line in table.splitlines()
        if line.startswith("|") and "---" not in line
    ][1:]  # drop the header cell
    assert rows == [
        "Developer and project passports",
        "Project index",
        "Local registry",
        "Imported and owned objects",
        "Search",
        "Selection and compilation",
        "Checks",
        "Package and plan",
        "Installation and launch",
    ], "the contract's offline rows moved; the checks above are named after them"
