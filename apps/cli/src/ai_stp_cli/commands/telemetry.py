"""`ai-stp telemetry` — the consent screen, and what turning it on would send.

The screen is a command rather than a terminal prompt. This CLI's first consumer
is an agent, and an agent asked a question on stdin does not answer it — it
waits. So the text is printed, the answer arrives as an argument, and nothing
blocks while it has not been given (`ADR-0112`).
"""

from collections.abc import Mapping
from typing import Literal, cast

from ai_stp_cli import config, telemetry
from ai_stp_cli.answer import Answer
from ai_stp_cli.errors import CliFailure
from ai_stp_contracts.machine_help import TelemetryStatus


def show(parameters: Mapping[str, object]) -> Answer[TelemetryStatus]:
    """What the ping would carry, where it would go, and whether it is on.

    The anonymous identifier is named among the fields and never printed as a
    value. Showing it would make an ordinary status read the one place it can
    be copied out of, which is the opposite of what it exists for.
    """
    del parameters
    return Answer(_status())


def consent(parameters: Mapping[str, object]) -> Answer[TelemetryStatus]:
    """Record the answer to the screen `show` prints.

    Both answers need `--confirm` and neither is a default. An accept that
    happened because somebody passed a flag they had not read is not consent,
    and a decline that happened by accident would be recorded as an answer and
    stop anything asking again.
    """
    accepted = bool(parameters.get("accept", False))
    declined = bool(parameters.get("decline", False))
    if accepted == declined:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "answer the telemetry screen with exactly one of accept or decline",
            next_actions=[
                "telemetry consent --accept --confirm --json",
                "telemetry consent --decline --confirm --json",
            ],
        )
    if not bool(parameters.get("confirm", False)):
        raise CliFailure(
            "AI_STP_USER_DECISION_REQUIRED",
            "this records an answer about sending data and needs an explicit confirmation",
            details={"answer": "accept" if accepted else "decline"},
            next_actions=["telemetry show --json"],
        )

    if accepted:
        telemetry.accept()
        # Consent is the event; the switch follows it. Written here rather than
        # left to the operator, because a consent that did not turn the feature
        # on would be an answer nobody acted on.
        _force_enabled(True)
    else:
        telemetry.decline()
        _force_enabled(False)
    return Answer(_status())


def _force_enabled(value: bool) -> None:
    """Write the switch past the refusal that guards it.

    `config set telemetry.enabled=true` is refused on purpose (`REQ-1316`), and
    this is the one caller allowed through — it runs only after an answer has
    been recorded, which is the thing the refusal exists to require.
    """
    held = dict(config.stored_values())
    held["telemetry.enabled"] = value
    config.write_config(held)


def _status() -> TelemetryStatus:
    answer = telemetry.consent()
    values = config.effective_config()
    enabled = False
    url = ""
    source: Literal["default", "config"] = "default"
    for value in values.values:
        if value.path == "telemetry.enabled":
            enabled = value.value is True
        elif value.path == "telemetry.url":
            url = str(value.value)
            source = "config" if value.source != "default" else "default"
    return TelemetryStatus(
        state=cast(Literal["not_asked", "declined", "accepted"], answer.state),
        # Consent alone does not send anything: the switch can be off while the
        # answer stands, and reporting `enabled` from the answer would say the
        # feature is on when no ping would leave.
        enabled=enabled and answer.accepted,
        url=url,
        url_source=source,
        collected=list(telemetry.PING_FIELDS),
    )
