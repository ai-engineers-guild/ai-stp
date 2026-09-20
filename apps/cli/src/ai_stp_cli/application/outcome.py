"""Turn a handler Answer into envelope identity. One owner for `ok` vs effect."""

from pydantic import BaseModel

from ai_stp_cli.answer import Answer
from ai_stp_cli.application.continuations import bind_continuation
from ai_stp_foundation.envelope import Continuation, continuation_command
from ai_stp_foundation.ids import ID_PREFIXES


def intent_start_continuation(intent: str) -> Continuation:
    """Executable `task start` for a shipped intent. Shared by parser redirects."""
    key = f"{intent}-session-01"
    return Continuation(
        kind="advance",
        path=["task", "start"],
        arguments={"intent": intent, "idempotency-key": key},
        argv=[
            "task",
            "start",
            "--intent",
            intent,
            "--idempotency-key",
            key,
            "--json",
        ],
        actor="cli",
    )


def operation_id_of(answer: Answer[BaseModel]) -> str | None:
    """The durable operation this result is about, if the payload named one."""
    if answer.operation_id:
        return answer.operation_id
    held = getattr(answer.payload, "operation_id", None)
    if isinstance(held, str) and held.startswith("operation_"):
        prefix, _, _ = held.partition("_")
        if prefix in ID_PREFIXES:
            return held
    return None


def envelope_actions(answer: Answer[BaseModel]) -> tuple[list[Continuation], list[str]]:
    """Continuations the handler bound. Static registry hints are not argv."""
    continuations = [bind_continuation(item) for item in answer.continuations]
    return continuations, [continuation_command(item) for item in continuations]
