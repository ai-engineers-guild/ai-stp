"""`ai-stp config show` — the effective configuration (issues #72, #73)."""

from collections.abc import Mapping
from typing import cast

from ai_stp_cli import config
from ai_stp_cli.answer import Answer
from ai_stp_cli.config import effective_config, for_display
from ai_stp_cli.errors import CliFailure
from ai_stp_contracts.machine_help import ConfigReport

#: Separates the field path from the value in `--set path=value`.
ASSIGNMENT = "="


def run(parameters: Mapping[str, object]) -> Answer[ConfigReport]:
    """Show every declared field, its effective value and where it came from.

    Read-only. `cli-config.md` makes the third precedence tier an argument that
    "acts on this call only and does not rewrite the file", so `--set` shows
    what the configuration *would* be, and nothing in this issue writes one.
    An existing file is still read: reporting `default` for a value the user set
    would be a confident lie.
    """
    return Answer(for_display(effective_config(_overrides(parameters.get("set")))))


def _overrides(raw: object) -> dict[str, str]:
    """Parse repeated `path=value` arguments.

    A malformed assignment is refused rather than ignored. Silently dropping
    `--set catalog.enabled` without a value would answer with the default and
    look like the override had been applied.
    """
    if raw is None:
        return {}
    supplied: tuple[object, ...] = (
        tuple(cast(tuple[object, ...], raw)) if isinstance(raw, tuple | list) else (raw,)
    )
    overrides: dict[str, str] = {}
    for item in supplied:
        text = str(item)
        path, separator, value = text.partition(ASSIGNMENT)
        if not separator or not path.strip():
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                "an override must be written as path=value",
                details={"given": text},
                next_actions=["config show --json"],
            )
        overrides[path.strip()] = value
    return overrides


def init(_parameters: Mapping[str, object]) -> Answer[ConfigReport]:
    """Create the configuration file if it is absent, then report the result.

    Never overwrites: every field has a default, so nothing needs this file to
    exist, and overwriting would discard settings someone relies on. Running it
    against an existing file validates that file instead, which is what a caller
    wanting to know the file is usable actually asks for.
    """
    config.initialise()
    return Answer(for_display(effective_config()))


def set_(parameters: Mapping[str, object]) -> Answer[ConfigReport]:
    """Write declared values to the configuration file.

    Distinct from `config show --set`, which is an override for one call and
    rewrites nothing. This is the write, and the answer is the effective
    configuration afterwards — so the caller sees both the new value and that its
    source is now the file rather than a default.
    """
    config.set_values(_assignments(parameters.get("set")))
    return Answer(for_display(effective_config()))


def unset(parameters: Mapping[str, object]) -> Answer[ConfigReport]:
    """Remove declared values so their defaults apply again."""
    config.unset_values(_names(parameters.get("field")))
    return Answer(for_display(effective_config()))


def validate(_parameters: Mapping[str, object]) -> Answer[ConfigReport]:
    """Read the configuration file and refuse it if it cannot be honoured.

    Same reading `config show` does, without the effective-value question. It
    exists so a caller can ask "is this file sound" and get an answer that is not
    entangled with what the values happen to be.
    """
    config.stored_values()
    return Answer(for_display(effective_config()))


def _assignments(raw: object) -> dict[str, str]:
    values = _overrides(raw)
    if not values:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "nothing was set",
            next_actions=["config show --json"],
        )
    return values


def _names(raw: object) -> tuple[str, ...]:
    if raw is None:
        return ()
    supplied: tuple[object, ...] = (
        tuple(cast(tuple[object, ...], raw)) if isinstance(raw, tuple | list) else (raw,)
    )
    return tuple(str(item).strip() for item in supplied if str(item).strip())
