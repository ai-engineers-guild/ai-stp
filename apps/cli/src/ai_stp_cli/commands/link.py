"""Pure CLI/web deep-link projection (SPEC-030, issue #241)."""

from collections.abc import Mapping

from pydantic import ValidationError

from ai_stp_cli import config
from ai_stp_cli.answer import Answer
from ai_stp_cli.cloud.client import check_base_url
from ai_stp_cli.errors import CliFailure
from ai_stp_contracts.deep_links import (
    DEFAULT_LOCALE,
    DeepLinkTarget,
    DeepLinkView,
    build_deep_link,
)


def web(parameters: Mapping[str, object]) -> Answer[DeepLinkView]:
    """Print one canonical web URL without lookup or browser side effects."""
    kind = parameters.get("kind")
    stable_id = parameters.get("id")
    if kind is None or stable_id is None:
        raise _refused("a deep-link kind and stable identifier are both required")

    report = config.effective_config()
    base = next(value.value for value in report.values if value.path == "catalog.url")
    try:
        target = DeepLinkTarget(
            kind=str(kind),  # pyright: ignore[reportArgumentType]
            stable_id=str(stable_id),
            version=_optional(parameters.get("version")),
            locale=_optional(parameters.get("locale")) or DEFAULT_LOCALE,  # pyright: ignore[reportArgumentType]
            intent="report" if parameters.get("report") else "view",
        )
        return Answer(build_deep_link(check_base_url(str(base)), target))
    except (ValidationError, ValueError) as error:
        raise _refused("the deep-link target is not canonical") from error


def _optional(value: object | None) -> str | None:
    return None if value is None else str(value)


def _refused(message: str) -> CliFailure:
    return CliFailure(
        "AI_STP_VALIDATION_ERROR",
        message,
        details={"contract": "deep_link_v1"},
        next_actions=["help --agent --json"],
    )
