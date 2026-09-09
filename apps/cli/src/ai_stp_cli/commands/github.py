"""Use selected GitHub source authority through the server; never accept a GitHub token."""

from collections.abc import Mapping

from ai_stp_cli.answer import Answer
from ai_stp_cli.cloud import client, login
from ai_stp_cli.commands import cloud_auth
from ai_stp_cli.commands.auth import endpoint
from ai_stp_contracts.github_connector import (
    GitHubConnectorStatus,
    GitHubSourcePrepared,
    GitHubSourcePrepareRequest,
)


def status(_parameters: Mapping[str, object]) -> Answer[GitHubConnectorStatus]:
    held, where = cloud_auth.required("GitHub sources"), endpoint()
    with client.open_client(where, access_token=held.access_token) as http:
        result = client.call(
            http, "GET", "/connectors/github", GitHubConnectorStatus, attempts=where.max_attempts
        )
    return Answer(result)


def prepare(parameters: Mapping[str, object]) -> Answer[GitHubSourcePrepared]:
    held, where = cloud_auth.required("GitHub sources"), endpoint()
    body = GitHubSourcePrepareRequest.model_validate(
        {
            "installation_id": parameters.get("installation-id"),
            "repository_id": parameters.get("repository-id"),
            "commit": parameters.get("commit"),
            "subpath": parameters.get("subpath"),
            "idempotency_key": login.new_idempotency_key(),
        }
    )
    with client.open_client(where, access_token=held.access_token) as http:
        result = client.call(
            http,
            "POST",
            "/connectors/github/sources",
            GitHubSourcePrepared,
            body=body,
            attempts=where.max_attempts,
        )
    return Answer(result)
