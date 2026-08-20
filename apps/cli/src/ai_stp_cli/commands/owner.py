"""Read server-authorized owner objects without inferring access locally."""

from collections.abc import Mapping

from ai_stp_cli.answer import Answer
from ai_stp_cli.cloud import owner, session
from ai_stp_cli.commands import cloud_auth
from ai_stp_cli.commands.auth import endpoint
from ai_stp_cli.errors import CliFailure
from ai_stp_contracts.owner import (
    CliOwnerObjectDetailView,
    CliOwnerObjectListView,
    CliOwnerVersionDetailView,
    OwnerObjectListQuery,
)


def _required(parameters: Mapping[str, object], name: str) -> str:
    value = str(parameters.get(name) or "")
    if not value:
        raise CliFailure("AI_STP_VALIDATION_ERROR", f"--{name} is required")
    return value


def _page_size(parameters: Mapping[str, object]) -> int:
    value = parameters.get("page-size")
    try:
        return 20 if value is None else int(str(value))
    except ValueError as error:
        raise CliFailure("AI_STP_VALIDATION_ERROR", "--page-size must be an integer") from error


def _session(purpose: str) -> session.Session:
    return cloud_auth.required(purpose)


def list_objects(parameters: Mapping[str, object]) -> Answer[CliOwnerObjectListView]:
    held = _session("owner object listing")
    query = OwnerObjectListQuery(
        cursor=str(parameters["cursor"]) if parameters.get("cursor") else None,
        page_size=_page_size(parameters),
        object_kind=(
            str(parameters["kind"]) if parameters.get("kind") else None  # pyright: ignore[reportArgumentType]
        ),
    )
    result = owner.list_objects(endpoint(), held.access_token, query)
    return Answer(CliOwnerObjectListView.model_validate(result.model_dump(mode="json")))


def show_object(parameters: Mapping[str, object]) -> Answer[CliOwnerObjectDetailView]:
    held = _session("owner object detail")
    result = owner.object_detail(
        endpoint(), held.access_token, _required(parameters, "kind"), _required(parameters, "id")
    )
    return Answer(CliOwnerObjectDetailView.model_validate(result.model_dump(mode="json")))


def show_version(parameters: Mapping[str, object]) -> Answer[CliOwnerVersionDetailView]:
    held = _session("owner version detail")
    result = owner.version_detail(
        endpoint(),
        held.access_token,
        _required(parameters, "kind"),
        _required(parameters, "id"),
        _required(parameters, "version"),
    )
    return Answer(CliOwnerVersionDetailView.model_validate(result.model_dump(mode="json")))
