"""Typed failure for the CLI (docs/contracts/cli-json.md, issue #72).

Every way this process can fail arrives here and leaves as one registered
`AI_STP_*` code with the exit class the contract assigns it. Nothing invents an
exit code at the call site, and nothing lets a library's own exit status become
the public one — `SPEC-011` REQ-1102 makes the classes stable, so they cannot be
whatever Click happened to raise.
"""

from typing import Final

from pydantic import ValidationError

from ai_stp_foundation.errors import exit_class_for

#: A message shown for an unexpected internal failure. The real exception text
#: may carry a path, an argument or an environment value, and `SPEC-011`
#: REQ-1108 forbids any of that reaching output or a log. The exception type is
#: named because it is safe and it is the one thing that helps a bug report.
INTERNAL_MESSAGE: Final[str] = "unexpected internal failure"


class CliFailure(Exception):
    """A failure the CLI knows how to describe.

    `retryable` is a property of the occurrence, not of the code: the same
    `AI_STP_DEPENDENCY_UNAVAILABLE` is worth retrying after a timeout and not
    worth retrying when the dependency is switched off.
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        details: dict[str, str] | None = None,
        next_actions: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details or {}
        self.next_actions = next_actions or []

    @property
    def exit_code(self) -> int:
        """The contract's exit class for this code."""
        return exit_class_for(self.code)


def internal_failure(error: BaseException) -> CliFailure:
    """Wrap an unexpected exception without leaking what it said."""
    return CliFailure(
        "AI_STP_INTERNAL",
        INTERNAL_MESSAGE,
        details={"exception": type(error).__name__},
    )


def invalid_parameters(error: ValidationError) -> CliFailure:
    """A value the caller supplied does not satisfy the contract it is sent under.

    Request models are built from parameters, so a `ValidationError` raised
    while building one is bad input, not a fault in this program. Letting it
    reach the generic handler answered `AI_STP_INTERNAL: unexpected internal
    failure` with an empty `next_actions` — `registry search --query ""` said
    the CLI had broken rather than that `q` may not be empty.

    Only the field path travels. `ValidationError.errors()` also carries the
    rejected `input`, and `SPEC-011` REQ-1108 keeps caller values out of output
    and logs: the offending value may be exactly the credential someone
    mistyped into a flag.
    """
    fields = sorted({".".join(str(part) for part in item["loc"]) for item in error.errors()} - {""})
    named = ", ".join(fields)
    return CliFailure(
        "AI_STP_VALIDATION_ERROR",
        f"a supplied value is not valid for this command: {named}"
        if named
        else "a supplied value is not valid for this command",
        details={"fields": named},
        next_actions=["help --agent --json"],
    )


def unknown_command(detail: str) -> CliFailure:
    """An unknown command or option.

    Click would print its own usage text and exit with its own status. Both are
    library behaviour, and `#72` requires that none of it reach the public
    machine contract, so the failure is re-expressed here instead.
    """
    return CliFailure(
        "AI_STP_VALIDATION_ERROR",
        detail,
        next_actions=["help --agent --json"],
    )
