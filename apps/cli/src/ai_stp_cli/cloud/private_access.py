"""Explicit authenticated private reads with account- and endpoint-scoped metadata."""

from pydantic import ValidationError

from ai_stp_cli.cloud import client, session
from ai_stp_cli.cloud.client import Endpoint
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import cache
from ai_stp_cli.secrets import open_store
from ai_stp_contracts.machine_help import CatalogKind, CatalogVersionView
from ai_stp_contracts.private_access import CliPrivateVersionResponse
from ai_stp_passports import ComponentVersionPassport, SetupVersionPassport


def held_session(*, offline: bool = False) -> session.Session:
    store, _warning = open_store()
    held = session.load(store)
    if held is None or (not offline and held.state() == "expired"):
        raise CliFailure(
            "AI_STP_AUTH_REQUIRED",
            "private cloud access requires a signed-in account",
            next_actions=["auth login --provider github --json"],
        )
    if not offline and held.state() == "revoked":
        raise CliFailure("AI_STP_DEVICE_REVOKED", "this device has been revoked")
    return held


def _key(endpoint: Endpoint, account: str, kind: CatalogKind, stable_id: str, number: str) -> str:
    scope = f"{client.check_base_url(endpoint.base_url)}:{account}:{stable_id}@{number}"
    return cache.key_for(f"{kind}-private-version", scope)


def _view(
    response: CliPrivateVersionResponse, *, source: str, checked_at: str
) -> CatalogVersionView:
    if tuple(response.passport.get(name) for name in ("kind", "stable_id", "version")) != (
        response.kind,
        response.stable_id,
        response.version,
    ):
        raise CliFailure(
            "AI_STP_CATALOG_INTEGRITY", "private version identity does not match the request"
        )
    try:
        model = ComponentVersionPassport if response.kind == "component" else SetupVersionPassport
        model.model_validate(response.passport)
    except ValidationError:
        raise CliFailure(
            "AI_STP_CATALOG_INTEGRITY", "the private version passport is invalid"
        ) from None
    cache.verify(response.passport, response.passport_digest)
    return CatalogVersionView.model_validate(
        {
            "kind": response.kind,
            "distribution_visibility": "private",
            "source": source,
            "checked_at": checked_at,
            "passport_digest": response.passport_digest,
            "lifecycle": response.lifecycle,
            "trust": response.trust.model_dump(mode="json"),
            "published_at": response.published_at,
            "passport": response.passport,
        }
    )


def version(
    endpoint: Endpoint, kind: CatalogKind, stable_id: str, number: str
) -> CatalogVersionView:
    from datetime import UTC, datetime

    from ai_stp_foundation.timestamps import format_timestamp

    held = held_session()
    path = (
        f"/access/{'components' if kind == 'component' else 'setups'}/{stable_id}/versions/{number}"
    )
    with client.open_client(endpoint, access_token=held.access_token) as http:
        response = client.call(
            http, "GET", path, CliPrivateVersionResponse, attempts=endpoint.max_attempts
        )
    if (response.kind, response.stable_id, response.version) != (kind, stable_id, number):
        raise CliFailure(
            "AI_STP_CATALOG_INTEGRITY", "private version identity does not match the request"
        )
    checked_at = format_timestamp(datetime.now(UTC))
    result = _view(response, source="online", checked_at=checked_at)
    cache.store(
        _key(endpoint, held.account_id, kind, stable_id, number),
        response.model_dump(mode="json"),
        checked_at=checked_at,
    )
    return result


def cached_version(
    endpoint: Endpoint, kind: CatalogKind, stable_id: str, number: str
) -> CatalogVersionView:
    held = held_session(offline=True)
    entry = cache.load(_key(endpoint, held.account_id, kind, stable_id, number))
    if entry is None:
        raise CliFailure(
            "AI_STP_DEPENDENCY_UNAVAILABLE", "this account has no cached private version"
        )
    response = CliPrivateVersionResponse.model_validate(entry.document)
    if (response.kind, response.stable_id, response.version) != (kind, stable_id, number):
        raise CliFailure(
            "AI_STP_CATALOG_INTEGRITY", "cached private version identity does not match"
        )
    return _view(response, source="cache", checked_at=entry.checked_at)
