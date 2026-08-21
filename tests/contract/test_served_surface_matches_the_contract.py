"""What the server serves against what the contract promises.

The frozen `/v1` boundary in `packages/contracts` exists so both surfaces —
the CLI's generated client and the web's — are built against one description.
Nothing enforced that. The application had grown twenty-three paths the
contract does not name, reached by hand-written clients in
`apps/web/src/lib/api/`, and the generated client could not see them at all.

None of that is wrong by itself: a server may carry surfaces beyond a frozen
MVP boundary. What was wrong is that the difference was invisible. A path drifts
out of the contract silently, and the only symptom is a client that cannot call
something everybody assumes is callable.

So the difference is declared here instead. Adding a route without adding it to
the contract still works — it just has to be written down with a reason, the
same way `release_scripts/public_manifest.toml` makes withholding a decision
rather than an omission.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Final, cast

import pytest

from ai_stp_api.app import create_app
from ai_stp_api.settings import AuthSettings, CatalogSettings, ServiceSettings, Settings
from ai_stp_contracts.openapi import build_document
from ai_stp_platform.settings import DatabaseSettings, StorageSettings

#: Refuses fast rather than hanging. Nothing here connects: the document is
#: generated from the route table, and the lifespan never runs.
_UNREACHABLE: Final[str] = "127.0.0.1:59999"
_TEST_SECRET: Final[str] = "test-secret-key-at-least-32-bytes-long!!"
_TEST_CURSOR_SECRET: Final[str] = "test-catalog-cursor-secret-32b-min!!"

#: Served, deliberately, outside the frozen `/v1` contract. Each is a
#: server-owned surface the web reaches through a hand-written client; the CLI
#: cannot reach any of them, which is the cost of not being in the contract and
#: the reason this list should shrink rather than grow.
BEYOND_THE_CONTRACT: Final[dict[str, str]] = {
    "/v1/account/public-profile": "publisher profile (docs/contracts/public-profile.md)",
    "/v1/account/public-profile/avatar": "publisher profile media",
    "/v1/account/public-profile/avatar/from-identity": "publisher profile media",
    "/v1/account/public-profile/draft": "publisher profile draft lifecycle",
    "/v1/account/public-profile/preview": "publisher profile draft lifecycle",
    "/v1/account/public-profile/publish": "publisher profile draft lifecycle",
    "/v1/auth/device/approve": "browser half of the device flow; the CLI drives the other",
    "/v1/auth/link/{provider}": "step-up identity linking, browser-only",
    "/v1/auth/{provider}/login": "browser redirect entry point; the CLI uses the device flow",
    "/v1/catalog/components/{stable_id}/versions/{version}/checks": "catalog support evidence",
    "/v1/catalog/countries": "external product catalogue metadata (ADR-0088)",
    "/v1/catalog/countries/{code}": "external product catalogue metadata (ADR-0088)",
    "/v1/catalog/services": "external product catalogue metadata (ADR-0088)",
    "/v1/catalog/services/{domain}": "external product catalogue metadata (ADR-0088)",
    "/v1/catalog/setups/{stable_id}/versions/{version}/checks": "catalog support evidence",
    "/v1/documents/{slug}": "web content documents",
    "/v1/media/avatars/{asset_id}": "media read path",
    "/v1/media/component/{media_id}": "media read path",
    "/v1/owner/external-products": "external product ownership (ADR-0088)",
    "/v1/owner/objects/component/{stable_id}/presentation": (
        "component presentation (docs/contracts/component-presentation.md)"
    ),
    "/v1/owner/objects/component/{stable_id}/presentation/media": "presentation media",
    "/v1/owner/objects/{object_kind}/{stable_id}/external-products": (
        "external product ownership (ADR-0088)"
    ),
    "/v1/publishers/{account_id}": "public publisher profile read",
}


def _served_document(tmp_path: Path) -> dict[str, Any]:
    settings = Settings(
        service=ServiceSettings(environment="test", version="9.9.9", log_dir=tmp_path),
        database=DatabaseSettings(url=f"postgresql+asyncpg://u:p@{_UNREACHABLE}/db"),
        storage=StorageSettings(
            endpoint=f"http://{_UNREACHABLE}",
            bucket="test",
            access_key_id="test-access",
            secret_access_key="test-secret",
        ),
        auth=AuthSettings(secret_key=_TEST_SECRET, cookie_secure=False),
        catalog=CatalogSettings(cursor_signing_secret=_TEST_CURSOR_SECRET),
    )
    return create_app(settings).openapi()


def test_every_path_the_contract_promises_is_actually_served(tmp_path: Path) -> None:
    """A promise the server does not keep is the worse direction of drift.

    A client generated from the contract calls it, and the failure arrives at
    runtime as a 404 that reads like an outage.
    """
    served = set(_served_document(tmp_path)["paths"])
    declared = set(cast(dict[str, Any], build_document()["paths"]))

    assert sorted(declared - served) == []


def test_every_path_served_beyond_the_contract_is_named_with_a_reason(tmp_path: Path) -> None:
    """Growing past the frozen boundary is allowed; doing it silently is not."""
    served = set(_served_document(tmp_path)["paths"])
    declared = set(cast(dict[str, Any], build_document()["paths"]))

    undeclared = served - declared
    unnamed = sorted(undeclared - set(BEYOND_THE_CONTRACT))
    assert unnamed == [], (
        "these paths are served but neither in the contract nor named here; "
        "add them to the contract, or record why they stay outside it"
    )

    stale = sorted(set(BEYOND_THE_CONTRACT) - undeclared)
    assert stale == [], "named as outside the contract, but no longer served that way"

    assert all(reason.strip() for reason in BEYOND_THE_CONTRACT.values())


def test_no_two_operations_share_an_identifier(tmp_path: Path) -> None:
    """A client generator names its functions after these.

    FastAPI derives the identifier from the handler's name, its path and the
    *first* method of a set, so one handler registered for two methods produces
    the same identifier twice — which is a document no generator can turn into
    two callable functions.
    """
    document = _served_document(tmp_path)
    seen: dict[str, list[str]] = {}
    for path, operations in cast(dict[str, dict[str, Any]], document["paths"]).items():
        for method, operation in operations.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            identifier = cast(dict[str, Any], operation).get("operationId")
            if isinstance(identifier, str):
                seen.setdefault(identifier, []).append(f"{method.upper()} {path}")

    duplicates = {name: where for name, where in seen.items() if len(where) > 1}
    assert duplicates == {}, duplicates


@pytest.mark.parametrize("path", sorted(BEYOND_THE_CONTRACT))
def test_a_path_outside_the_contract_still_lives_under_the_versioned_prefix(path: str) -> None:
    """Outside the contract is not outside the versioning promise.

    `/v1` is what tells a caller the shape may not change under them. A surface
    that skipped the prefix would be unversioned without anybody deciding it.
    """
    assert path.startswith("/v1/")
    assert re.fullmatch(r"[a-z0-9/{}_.-]+", path), path
