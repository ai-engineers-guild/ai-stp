"""Reachable-but-corrupt catalog rows are reported, not hidden (REQ-2108)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.slices.catalog import service
from ai_stp_platform.catalog_read import CatalogIntegrityError

pytestmark = pytest.mark.platform

READERS = [
    (
        "read_component",
        "get_public_object_versions",
        "component_detail",
        ("component_example",),
    ),
    ("read_setup", "get_public_object_versions", "setup_detail", ("setup_example",)),
    (
        "read_component_version",
        "get_public_version",
        "component_version_response",
        ("component_example", "1.0"),
    ),
    (
        "read_setup_version",
        "get_public_version",
        "setup_version_response",
        ("setup_example", "1.0"),
    ),
]


def _arrange(monkeypatch: pytest.MonkeyPatch, loader_name: str, projector_name: str) -> None:
    loaded = [object()] if loader_name == "get_public_object_versions" else object()
    monkeypatch.setattr(service, loader_name, AsyncMock(return_value=loaded))

    def fail_projection(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise CatalogIntegrityError("invalid public projection")

    monkeypatch.setattr(service, projector_name, fail_projection)


@pytest.mark.asyncio
@pytest.mark.parametrize(("reader_name", "loader_name", "projector_name", "arguments"), READERS)
async def test_readers_report_integrity_failure_instead_of_not_found(
    monkeypatch: pytest.MonkeyPatch,
    reader_name: str,
    loader_name: str,
    projector_name: str,
    arguments: tuple[str, ...],
) -> None:
    """The row is present and public; a miss would send the caller elsewhere.

    This replaces the earlier acceptance that readers hide integrity failures as
    not-found. That behaviour is what let a poisoned immutable version sit behind
    an ordinary 404 until someone went looking in the database by hand.
    """
    _arrange(monkeypatch, loader_name, projector_name)

    with pytest.raises(service.CatalogCorrupt):
        await getattr(service, reader_name)(object(), *arguments)


@pytest.mark.asyncio
@pytest.mark.parametrize(("reader_name", "loader_name", "projector_name", "arguments"), READERS)
async def test_integrity_failure_is_never_a_not_found(
    monkeypatch: pytest.MonkeyPatch,
    reader_name: str,
    loader_name: str,
    projector_name: str,
    arguments: tuple[str, ...],
) -> None:
    """CatalogCorrupt must not be catchable as CatalogNotFound.

    Asserted separately because the two would be indistinguishable to every
    caller if one were ever made a subclass of the other for convenience.
    """
    _arrange(monkeypatch, loader_name, projector_name)

    with pytest.raises(service.CatalogCorrupt) as caught:
        await getattr(service, reader_name)(object(), *arguments)
    assert not isinstance(caught.value, service.CatalogNotFound)


@pytest.mark.asyncio
async def test_integrity_failure_records_an_operator_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The answer carries no detail, so the log is the only place the reason lives."""
    _arrange(monkeypatch, "get_public_version", "component_version_response")
    log = Mock()
    monkeypatch.setattr(service, "_log", log)
    session = cast(AsyncSession, object())

    with pytest.raises(service.CatalogCorrupt):
        await service.read_component_version(session, "component_example", "1.0")

    log.error.assert_called_once_with(
        "catalog_integrity_failed",
        reason="invalid public projection",
        object_kind="component",
        stable_id="component_example",
        version="1.0",
    )


@pytest.mark.asyncio
async def test_search_components_reports_integrity_failure_instead_of_internal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Search is the same reachable-but-corrupt condition as detail (REQ-2108)."""
    from datetime import UTC, datetime

    from ai_stp_contracts.catalog import ComponentSearchRequest
    from ai_stp_platform.catalog_read import PublicVersionRow

    row = SimpleNamespace(stable_id="component_example", version="1.0")

    async def fake_search(*args: object, **kwargs: object) -> service.SearchPage:
        del args, kwargs
        return service.SearchPage(
            authoritative=[cast(PublicVersionRow, row)],
            experimental=[],
            next_cursor=None,
            page_size=20,
            now=datetime(2026, 8, 24, tzinfo=UTC),
        )

    monkeypatch.setattr(service, "_search", fake_search)

    def fail_projection(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise CatalogIntegrityError("invalid public projection")

    monkeypatch.setattr(service, "component_summary", fail_projection)
    log = Mock()
    monkeypatch.setattr(service, "_log", log)

    with pytest.raises(service.CatalogCorrupt):
        await service.search_components(
            cast(AsyncSession, object()),
            ComponentSearchRequest(),
            cursor_secret="secret",
        )

    log.error.assert_called_once_with(
        "catalog_integrity_failed",
        reason="invalid public projection",
        object_kind="component",
        stable_id="component_example",
        version="1.0",
    )
