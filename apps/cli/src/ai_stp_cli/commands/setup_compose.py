"""User-facing mixed setup composition from one bounded JSON manifest."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from contextlib import closing
from pathlib import Path
from typing import cast

import httpx

from ai_stp_cli import identity
from ai_stp_cli.answer import Answer
from ai_stp_cli.commands import registry as registry_commands
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import passports, setup_compose
from ai_stp_cli.local.database import configured_path, open_registry
from ai_stp_contracts.machine_help import SetupComposePlan, SetupComposeResult
from ai_stp_foundation.harnesses import HarnessId
from ai_stp_foundation.ids import new_id
from ai_stp_foundation.refs import ComponentRef
from ai_stp_passports import ComponentVersionPassport, adaptation_for
from ai_stp_sources.archive import MAX_ARCHIVE_BYTES
from ai_stp_sources.errors import SourceError
from ai_stp_sources.git import GithubHttpResponse
from ai_stp_sources.models import CatalogIntent, SourceSnapshot
from ai_stp_sources.resolve import resolve_source

MAX_MANIFEST_BYTES = 1_048_576
HTTP_TIMEOUT = httpx.Timeout(30.0, connect=5.0)


def plan(parameters: Mapping[str, object]) -> Answer[SetupComposePlan]:
    """Resolve every member and return the exact immutable composition."""
    setup_id = str(parameters.get("id") or new_id("setup"))
    created_at = passports.moment()
    resolved = _resolve(parameters, setup_id=setup_id, created_at=created_at)
    return Answer(setup_compose.plan_view(resolved))


def apply(parameters: Mapping[str, object]) -> Answer[SetupComposeResult]:
    """Re-resolve and record only the exact composition the caller reviewed."""
    if parameters.get("confirm") is not True:
        raise CliFailure(
            "AI_STP_USER_DECISION_REQUIRED",
            "setup compose apply requires explicit confirmation",
            next_actions=["setup compose plan --manifest <path> --json"],
        )
    setup_id = str(parameters.get("id") or "")
    created_at = str(parameters.get("created-at") or "")
    expected = str(parameters.get("expected-plan-digest") or "")
    if not setup_id or not created_at or not expected:
        raise CliFailure("AI_STP_VALIDATION_ERROR", "the exact setup plan identity is required")
    resolved = _resolve(parameters, setup_id=setup_id, created_at=created_at)
    current, _warning = identity.load_or_create()
    with closing(open_registry(configured_path(), create=True)) as connection:
        return Answer(
            setup_compose.apply(
                connection,
                resolved,
                expected_plan_digest=expected,
                device_id=current.device_id,
                publisher_id=passports.owner().account_id,
                at=created_at,
            )
        )


def _resolve(
    parameters: Mapping[str, object], *, setup_id: str, created_at: str
) -> setup_compose.ResolvedComposition:
    manifest_path = Path(str(parameters.get("manifest") or "")).expanduser()
    manifest = setup_compose.parse_manifest(_read_manifest(manifest_path))
    root = Path(str(parameters.get("root") or manifest_path.parent)).expanduser().resolve()
    snapshots: list[tuple[setup_compose.ComposeComponent, SourceSnapshot]] = []
    catalog: list[setup_compose.CatalogMaterial] = []
    for component in manifest.components:
        intent = setup_compose.source_intent(component)
        if isinstance(intent, CatalogIntent):
            acquired = registry_commands.acquire_version(
                "component", intent.stable_id, intent.version, offline=False
            )
            if acquired.view.passport_digest != intent.passport_digest:
                raise CliFailure(
                    "AI_STP_CATALOG_INTEGRITY",
                    "the catalog component passport differs from the manifest",
                    details={"stable_id": intent.stable_id},
                )
            if not isinstance(acquired.passport, ComponentVersionPassport):
                raise CliFailure(
                    "AI_STP_CATALOG_INTEGRITY", "a component source is not a component"
                )
            try:
                adaptation_for(acquired.passport, cast(HarnessId, manifest.harness_id))
            except ValueError as error:
                raise CliFailure(
                    "AI_STP_CONFLICT",
                    "the component has no adaptation for the requested harness",
                    details={"stable_id": intent.stable_id, "code": "adaptation_unavailable"},
                ) from error
            catalog.append(
                setup_compose.CatalogMaterial(
                    ComponentRef(
                        stable_id=intent.stable_id,
                        version=intent.version,
                        passport_digest=intent.passport_digest,
                        variant_id=intent.variant_id,
                    ),
                    acquired.view.passport,
                    acquired.artifact,
                )
            )
            continue
        try:
            snapshot = asyncio.run(resolve_source(intent, fetch=_fetch, local_root=root))
        except SourceError as exc:
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                exc.message,
                details={"source_code": exc.code},
            ) from exc
        snapshots.append((component, snapshot))
    try:
        return setup_compose.compose(
            manifest=manifest,
            setup_id=setup_id,
            publisher_id=passports.owner().account_id,
            created_at=created_at,
            snapshots=snapshots,
            catalog=catalog,
        )
    except SourceError as exc:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR", exc.message, details={"source_code": exc.code}
        ) from exc


def _read_manifest(path: Path) -> object:
    try:
        if not path.is_file() or path.stat().st_size > MAX_MANIFEST_BYTES:
            raise ValueError
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR", "the setup composition manifest cannot be read"
        ) from exc


async def _fetch(url: str, *, headers: Mapping[str, str]) -> GithubHttpResponse:
    """Bound transport shared by GitHub and allowlisted package adapters."""
    try:
        async with (
            httpx.AsyncClient(follow_redirects=False, timeout=HTTP_TIMEOUT) as client,
            client.stream("GET", url, headers=dict(headers)) as response,
        ):
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > MAX_ARCHIVE_BYTES:
                    raise CliFailure("AI_STP_VALIDATION_ERROR", "the remote component is too large")
            return GithubHttpResponse(
                response.status_code,
                bytes(body),
                {key.lower(): value for key, value in response.headers.items()},
                str(response.url),
            )
    except httpx.HTTPError as exc:
        raise CliFailure(
            "AI_STP_DEPENDENCY_UNAVAILABLE", "the remote component source is unavailable"
        ) from exc
