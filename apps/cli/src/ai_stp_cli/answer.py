"""What a command handler returns.

Its own module so the registry can import handlers and handlers can import this
without a cycle: the registry knows every command, a command knows only how to
answer.
"""

from dataclasses import dataclass

from pydantic import BaseModel

from ai_stp_foundation.envelope import Continuation


@dataclass(frozen=True)
class Answer[T: BaseModel]:
    """A payload, and anything the caller must be told alongside it.

    A warning does not make the call unsuccessful, so it cannot be an exception,
    and machine mode forbids writing it to stderr — stdout carries exactly one
    JSON object and stderr stays empty. It belongs in the envelope, which is
    where this type carries it. `ADR-0058` uses it to say that a secret went to
    a file rather than to the operating system store, a fact a caller on a
    shared machine has to be able to see.

    Compensation, recovery-required and other unmet goals are `CliFailure`, not
    this type: `ok` on the envelope means the requested effect completed.
    """

    payload: T
    warnings: tuple[str, ...] = ()
    operation_id: str | None = None
    continuations: tuple[Continuation, ...] = ()


def with_warning[T: BaseModel](payload: T, warning: str | None) -> Answer[T]:
    """An answer carrying at most one warning, which is the common case."""
    return Answer(payload, () if warning is None else (warning,))
