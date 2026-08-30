"""The executable conformance kit for provider protocol v1 (`#169`).

`SPEC-008` REQ-802 asks for a check that compares `provider-info` against what a
provider can really do, and REQ-804 for a malicious corpus covering every class
of path, link, device and limit. Both are here as something that runs, because a
conformance document nobody can execute is a conformance document nobody obeys.

**The kit talks to a provider through one narrow door.** `Invoker` is the whole
interface: a command name, an argument array, an answer. A real provider gets a
subprocess started under `protocol.BOUNDARY`; a test gets a stub. Neither can
see anything the other cannot, which is what makes a passing test mean the same
thing as a passing provider.

**A case fails loudly or passes; there is no "probably".** Every check names
what it wanted and what it got, because the audience for a failure here is
somebody writing a provider against a protocol they cannot see.

**Rejection cases assert a refusal, not an error.** A provider that crashes on a
malicious bundle has not rejected it — it has failed to parse it, and the next
malicious bundle might not crash it.
"""

import json
import os
import subprocess
import sys
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Final, Protocol, Self, cast

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.paths import is_executable_file
from ai_stp_cli.provider import bundle_corpus, bundle_protocol, protocol
from ai_stp_foundation.canonical import JsonValue


@dataclass(frozen=True)
class MaliciousBundle:
    """One hostile shape and the frozen refusal a provider must return."""

    name: str
    refusal: str


#: Bundles a conforming provider must reject, one per shape `REQ-804` names.
#: A testcase name is separate from the frozen protocol refusal: symbolic and
#: hard links are distinct attacks but both intentionally map to
#: ``link_not_allowed``.
MALICIOUS_BUNDLES: Final[tuple[MaliciousBundle, ...]] = tuple(
    MaliciousBundle(name, refusal) for name, refusal in bundle_corpus.CASE_REASONS
)


class Invoker(Protocol):
    """The one door to a provider: a command, arguments, an answer."""

    def __call__(self, command: str, arguments: Sequence[str]) -> JsonValue: ...


#: Whose obligation a case is about. `provider` is the protocol: failing one
#: means the provider did not do what v3 requires. `consumer` is reach: the
#: provider is correct and *this* compiler cannot get to something it offers, or
#: projects something it does not accept.
#:
#: Separated because one word was answering two questions. Reporting a consumer
#: gap as non-conformance blames a provider that satisfied every obligation it
#: has, and sends whoever reads the report to the wrong repository.
SUBJECT_PROVIDER: Final[str] = "provider"
SUBJECT_CONSUMER: Final[str] = "consumer"


@dataclass(frozen=True)
class Case:
    """One conformance check and what it decided."""

    name: str
    passed: bool
    detail: str
    subject: str = SUBJECT_PROVIDER


@dataclass(frozen=True)
class Report:
    """What a whole conformance run decided."""

    harness_id: str
    protocol_version: int
    cases: tuple[Case, ...]

    @property
    def conforms(self) -> bool:
        """Whether the *provider* met the protocol.

        Consumer-subject cases are reported and do not decide this. A provider
        declaring a component kind this compiler has no route for has satisfied
        every obligation v3 places on it; the gap is ours, and calling it
        non-conformance would name the wrong party in the one field people read.
        """
        return all(case.passed for case in self.cases if case.subject == SUBJECT_PROVIDER)

    @property
    def unreachable(self) -> tuple[Case, ...]:
        """Consumer-subject cases that failed: capability neither side can use."""
        return tuple(
            case for case in self.cases if case.subject == SUBJECT_CONSUMER and not case.passed
        )

    @property
    def failures(self) -> tuple[Case, ...]:
        return tuple(case for case in self.cases if not case.passed)


def resolve_executable(executable: str) -> str:
    """Resolve an existing executable artifact before any provider spawn."""
    place = Path(executable).expanduser()
    if not place.is_file():
        raise FileNotFoundError(executable)
    resolved = place.resolve()
    if not is_executable_file(resolved):
        raise PermissionError(executable)
    return str(resolved)


def subprocess_invoker(executable: str, target: str) -> Invoker:
    """Start a real provider under the frozen boundary (`REQ-803`).

    Every term of `protocol.BOUNDARY` is applied here rather than described:
    an argument array, no shell, an absolute target, a filtered environment, a
    time limit and a bound on how much is read. A provider is somebody else's
    program, and these are the terms `ai_stp` is willing to start one on.
    """

    def invoke(command: str, arguments: Sequence[str]) -> JsonValue:
        argv = [executable, command, "--target", target, *arguments]
        return invoke_argv(argv, command=command)

    return invoke


def _executable_argv(executable: str) -> list[str]:
    """Return an exact argv prefix for a provider on the current platform.

    POSIX executes a shebang file directly. Windows does not implement that
    kernel convention and reports ``WinError 193`` for the same file, so a
    Python provider script must be handed to the running interpreter there.
    Native executables keep the exact path the caller supplied.
    """
    if os.name != "nt":
        return [executable]
    try:
        # Builtin open, not Path.open: the probe reads a raw path string and must
        # not depend on pathlib's OS-flavoured parsing. A test exercising the
        # Windows branch on POSIX (os.name patched to "nt") would otherwise turn
        # the path into a WindowsPath and fail to open it. Identical to Path.open
        # in production.
        with open(executable, "rb") as stream:  # noqa: PTH123
            first_line = stream.readline(256).lower()
    except OSError:
        return [executable]
    if first_line.startswith(b"#!") and b"python" in first_line:
        return [sys.executable, executable]
    return [executable]


class ProcessLike(Protocol):
    """The four members of `subprocess.Popen` this boundary actually uses."""

    stdout: IO[bytes] | None

    def kill(self) -> None: ...

    def wait(self) -> int: ...

    def __enter__(self) -> Self: ...

    def __exit__(self, *args: object) -> None: ...


#: How a process gets created. Named so a launcher can supply its own without
#: the boundary knowing what an AppContainer is.
type SpawnProcess = Callable[[list[str], dict[str, str]], ProcessLike]


def _popen(command: list[str], environment: dict[str, str]) -> ProcessLike:
    """The ordinary factory, and the one every platform but Windows uses."""
    return cast(
        ProcessLike,
        subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=environment,
        ),
    )


def invoke_argv(
    argv: Sequence[str], *, command: str, spawn: SpawnProcess | None = None
) -> JsonValue:
    """Run one already-decided provider argv under the common process boundary.

    Network policy is intentionally absent here. Frozen v1 calls this function
    directly; protocol v2 first makes an auditable phase decision and, for a
    local-only phase, hands the argv to its proved OS launcher. Every version
    shares the same environment, timeout and output-volume boundary.

    `spawn` is how a launcher that cannot be expressed as a wrapper still gets
    to run under that boundary. Bubblewrap is an executable, so it rewrites the
    argv and leaves this alone. An AppContainer is a token: `subprocess` cannot
    create one, and its `STARTUPINFO` accepts only a handle list. Passing the
    process factory instead of the argv is what lets the read limit, the
    watchdog and the environment allowlist stay written once — the alternative
    was a second copy of them behind the Windows branch, which is where the
    output-volume bug would have been reintroduced without anyone porting it.
    """
    boundary = protocol.BOUNDARY
    raw, over_limit = _bounded_output(
        argv,
        spawn=spawn,
        limit=boundary.output_limit_bytes,
        timeout_seconds=boundary.timeout_seconds,
        # An allowlist, not the caller's environment: these names pass through
        # with their real values and everything else is dropped. Passing them
        # empty would be a different thing entirely: a provider with no PATH
        # cannot start, and that would look like a provider failure.
        environment={
            name: os.environ[name] for name in boundary.environment_allowlist if name in os.environ
        },
    )
    if over_limit:
        # Named rather than parsed. A truncated answer that happened to be
        # valid JSON would be acted on, and the one thing known about a
        # provider that wrote past its limit is that it is not conforming.
        return {"error": "the provider wrote past the output limit", "command": command}
    try:
        return cast(JsonValue, json.loads(raw.decode("utf-8", errors="replace")))
    except ValueError:
        return {"error": "the provider did not answer with JSON", "command": command}


def _bounded_output(
    argv: Sequence[str],
    *,
    limit: int,
    timeout_seconds: float,
    environment: dict[str, str],
    spawn: SpawnProcess | None = None,
) -> tuple[bytes, bool]:
    """Run a provider and read at most ``limit`` bytes of what it says.

    `capture_output` reads to end of file first and truncates afterwards, which
    makes the declared limit a bound on what is *kept* rather than on what is
    *read*: a provider emitting 64 MiB grew this process by 183 MiB and ran to
    completion, with the boundary saying 1 MiB the whole time. That is the
    output-volume class failing open into the caller's memory.

    So the read is bounded and the child is stopped the moment it goes past.
    One byte over the limit is read on purpose — it is the only way to tell
    "exactly at the limit" from "more than we will look at".

    The time limit is a watchdog rather than `run(timeout=...)`, because the
    read has to be the bounded one. It kills the child, which closes the pipe,
    which ends the read; `TimeoutExpired` is then raised by hand so that callers
    see the same exception they always did — `install apply` maps it to
    `partial`, and a call that did not come back does not prove nothing
    happened.

    Standard error is discarded rather than captured. Nothing read it, and a
    second unbounded buffer is a second way to run this process out of memory.
    """
    command = [*_executable_argv(str(argv[0])), *argv[1:]]
    expired = threading.Event()
    # An argument array, no shell and the exact executable the caller named —
    # `protocol.BOUNDARY` in three of its terms, applied rather than described.
    started = _popen if spawn is None else spawn
    with started(command, environment) as child:
        stream = child.stdout
        if stream is None:  # pragma: no cover - Popen always gives a pipe here
            raise RuntimeError("the provider was started without a readable pipe")

        def _stop() -> None:
            expired.set()
            child.kill()

        watchdog = threading.Timer(timeout_seconds, _stop)
        watchdog.start()
        try:
            raw = stream.read(limit + 1)
        finally:
            watchdog.cancel()

        over_limit = len(raw) > limit
        if over_limit:
            # Immediately, rather than waiting out the time limit: a provider
            # blocked writing into a pipe nobody is draining would otherwise
            # hold the caller for the whole two minutes it is allowed.
            child.kill()
        child.wait()

    if expired.is_set():
        raise subprocess.TimeoutExpired(cmd=command, timeout=timeout_seconds)
    return raw[:limit], over_limit


def run(invoke: Invoker, *, harness_id: str) -> Report:
    """Run the whole kit against one provider.

    Every case runs even after one fails: somebody writing a provider should see
    the whole list, not the first thing that broke.
    """
    with bundle_corpus.materialized(
        protocol_version=protocol.VERSION, harness_id=harness_id
    ) as corpus:
        info = _object(invoke("provider-info", ()))
        cases: list[Case] = [
            _fields_present(info),
            _version_spoken(info),
            _harness_matches(info, harness_id),
            _actions_declared(info),
            _safe_actions_answerable(invoke, info),
            _valid_bundle_accepted(invoke, corpus.valid),
            _valid_bundle_planned(invoke, corpus.valid),
        ]
        cases.extend(_rejections(invoke, corpus))
        cases.append(_states_mapped(invoke))
        cases.append(_reads_create_nothing(invoke, corpus.valid))

    version = info.get("protocol_version")
    return Report(
        harness_id=str(info.get("harness_id", "")),
        protocol_version=version if isinstance(version, int) else 0,
        cases=tuple(cases),
    )


def _fields_present(info: dict[str, JsonValue]) -> Case:
    missing = [name for name in protocol.INFO_FIELDS if name not in info]
    return Case(
        "provider_info_complete",
        not missing,
        "every declared field is answered" if not missing else f"missing: {', '.join(missing)}",
    )


def _version_spoken(info: dict[str, JsonValue]) -> Case:
    version = info.get("protocol_version")
    spoken = isinstance(version, int) and protocol.speaks(version)
    return Case(
        "protocol_version_spoken",
        spoken,
        f"speaks v{protocol.VERSION}"
        if spoken
        else f"announces {version!r}, which this build does not speak",
    )


def _harness_matches(info: dict[str, JsonValue], harness_id: str) -> Case:
    reported = str(info.get("harness_id", ""))
    return Case(
        "harness_matches",
        reported == harness_id,
        f"reports {reported!r}" + ("" if reported == harness_id else f", expected {harness_id!r}"),
    )


def _actions_declared(info: dict[str, JsonValue]) -> Case:
    """`provider-info` may not claim an action the protocol does not have."""
    declared = {str(item) for item in _list(info.get("supported_actions"))}
    invented = sorted(declared - set(protocol.COMMANDS))
    return Case(
        "actions_within_protocol",
        not invented,
        "declares only protocol commands"
        if not invented
        else f"declares commands the protocol has no name for: {', '.join(invented)}",
    )


def _safe_actions_answerable(
    invoke: Invoker,
    info: dict[str, JsonValue],
) -> Case:
    """REQ-802: every safely probeable declared action really answers.

    Conformance never invokes an effect, restore or launch against the user's
    target. Those commands need a disposable provider E2E with an approved
    plan; invoking them with empty arguments is neither safe nor evidence.
    """
    declared = {str(item) for item in _list(info.get("supported_actions"))}
    silent: list[str] = []
    arguments: dict[str, tuple[str, ...]] = {
        "provider-info": (),
        "software-status": (),
        "software-plan": (),
        "status": (),
    }
    for command in sorted(declared & arguments.keys()):
        answer = _object(invoke(command, arguments[command]))
        if answer.get("unsupported") is True or not answer:
            silent.append(command)
    return Case(
        "declared_safe_actions_answer",
        not silent,
        "every declared action answers"
        if not silent
        else f"declared but does not answer: {', '.join(silent)}",
    )


def _valid_bundle_accepted(invoke: Invoker, artifact: bundle_protocol.Binding) -> Case:
    answer = _object(invoke("validate-bundle", artifact.common_arguments()))
    try:
        bundle_protocol.require_validated(answer, artifact)
    except CliFailure as error:
        return Case("valid_literal_bundle_accepted", False, error.message)
    return Case("valid_literal_bundle_accepted", True, "accepts and echoes the exact ZIP binding")


def _valid_bundle_planned(invoke: Invoker, artifact: bundle_protocol.Binding) -> Case:
    answer = _object(invoke("plan-bundle", artifact.plan_arguments(_CONFORMANCE_TARGET_DIGEST)))
    try:
        bundle_protocol.require_plan(answer, artifact, _CONFORMANCE_TARGET_DIGEST)
    except CliFailure as error:
        return Case("valid_literal_bundle_planned", False, error.message)
    return Case("valid_literal_bundle_planned", True, "plans and echoes the exact ZIP binding")


def _rejections(invoke: Invoker, corpus: bundle_corpus.Corpus) -> list[Case]:
    """Every malicious class is rejected, and rejected rather than survived."""
    cases: list[Case] = []
    for malicious in corpus.malicious:
        answer = _object(invoke("validate-bundle", malicious.binding.common_arguments()))
        reason = str(answer.get("reason", ""))
        try:
            bundle_protocol.require_rejected(answer, malicious.binding, malicious.refusal)
        except CliFailure:
            passed = False
        else:
            passed = True
        cases.append(
            Case(
                f"rejects_{malicious.name}",
                passed,
                f"rejected exact artifact as {reason!r}"
                if passed
                else "did not return the exact artifact binding and required refusal",
            )
        )
    return cases


def _states_mapped(invoke: Invoker) -> Case:
    """Whatever `status` reports must map onto a durable operation state."""
    answer = _object(invoke("status", ()))
    reported = str(answer.get("state", ""))
    try:
        protocol.operation_state(reported)
    except KeyError:
        return Case("state_is_mapped", False, f"reports {reported!r}, which maps to nothing")
    return Case("state_is_mapped", True, f"reports {reported!r}")


def _reads_create_nothing(invoke: Invoker, artifact: bundle_protocol.Binding) -> Case:
    """A read run twice answers twice the same (`provider-protocol.md`).

    Not a proof that nothing was written — only the provider can prove that —
    but a read whose second answer differs has certainly done something, and
    that is worth catching before an install depends on it.
    """
    changed: list[str] = []
    for command in sorted(protocol.READ_COMMANDS):
        arguments = artifact.common_arguments() if command == "validate-bundle" else ()
        if command == "plan-bundle":
            arguments = artifact.plan_arguments(_CONFORMANCE_TARGET_DIGEST)
        first = invoke(command, arguments)
        second = invoke(command, arguments)
        if first != second:
            changed.append(command)
    return Case(
        "reads_are_repeatable",
        not changed,
        "every read answers the same twice"
        if not changed
        else f"answered differently on a second read: {', '.join(changed)}",
    )


def _object(value: JsonValue) -> dict[str, JsonValue]:
    return cast(dict[str, JsonValue], value) if isinstance(value, dict) else {}


def _list(value: JsonValue | None) -> list[JsonValue]:
    return cast(list[JsonValue], value) if isinstance(value, list) else []


_CONFORMANCE_TARGET_DIGEST: Final[str] = "sha256:" + "0" * 64
