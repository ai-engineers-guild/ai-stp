"""`ai-stp skill` — deliver the canonical Agent Skill to a harness (issue #77)."""

from collections.abc import Mapping
from pathlib import Path

from ai_stp_cli import skill
from ai_stp_cli.answer import Answer
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.paths import redact_home
from ai_stp_contracts.machine_help import SkillDelivery


def status(parameters: Mapping[str, object]) -> Answer[SkillDelivery]:
    """Report what is at a destination and whether this installation owns it.

    Creates nothing, including the destination directory.
    """
    target = _target(parameters)
    return Answer(_view(target, skill.inspect(target)))


def install(parameters: Mapping[str, object]) -> Answer[SkillDelivery]:
    """Install the Skill package at a destination, refusing to overwrite what is not ours.

    The destination is named rather than discovered. Where each harness looks
    for a native Skill is a fact about that harness and differs across them;
    inventing those paths would be a guess presented as support. Discovery
    arrives with the harness detectors of `SPEC-014`.
    """
    target = _target(parameters)
    harness = _harness(parameters)
    locale = _locale(parameters)
    return Answer(_view(target, skill.install(target, harness, locale)))


def remove(parameters: Mapping[str, object]) -> Answer[SkillDelivery]:
    """Remove only what this installation put there.

    The local registry and anything the user set up are a different thing and
    are never touched: this is the control plane, not their data.
    """
    target = _target(parameters)
    return Answer(_view(target, skill.remove(target)))


def _view(target: Path, held: skill.Installed) -> SkillDelivery:
    return SkillDelivery(
        state=held.state,  # pyright: ignore[reportArgumentType]
        target=redact_home(target),
        digest=held.digest,
        harness=held.harness,
        locale=held.locale,
        files=list(held.files),
        available_harnesses=list(skill.HARNESSES),
    )


def _target(parameters: Mapping[str, object]) -> Path:
    given = parameters.get("target")
    if given is None:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a destination directory is required",
            details={"supported_harnesses": ", ".join(skill.HARNESSES)},
            next_actions=["skill status --target <path> --json"],
        )
    return Path(str(given)).expanduser()


def _harness(parameters: Mapping[str, object]) -> str | None:
    given = parameters.get("harness")
    return None if given is None else str(given)


def _locale(parameters: Mapping[str, object]) -> str:
    given = parameters.get("locale")
    return "en" if given is None else str(given)
