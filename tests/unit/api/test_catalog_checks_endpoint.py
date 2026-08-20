# pyright: reportUnknownLambdaType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnusedFunction=false, reportUnusedImport=false, reportUnusedVariable=false
"""Unit tests for catalog version checks service (#270)."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from ai_stp_api.slices.catalog import service
from ai_stp_contracts.safety_checks import SafetyChecksSummary

pytestmark = pytest.mark.platform


@pytest.mark.asyncio
async def test_read_version_checks_returns_summary() -> None:
    meta = SimpleNamespace(
        checks_summary={
            "status": "available",
            "checks_passed_percent": 75,
            "passed": 3,
            "failed": 1,
            "warning": 0,
            "total_countable": 4,
            "checks": [
                {
                    "check_id": "path_denylist",
                    "result": "failed",
                    "mandatory": True,
                    "source": "platform_safety_scan",
                    "family": "path",
                    "reason": "unsafe_path",
                }
            ],
        },
        owner_account_id="a1",
        likes_count=0,
        updated_at=None,
        presentation_bio=None,
    )
    row = SimpleNamespace(
        metadata=meta,
        passport={"visibility": "public", "stable_id": "component_x", "version": "1.0"},
        passport_digest="sha256:" + "0" * 64,
        published_at=datetime.now(UTC),
        trust_lane="experimental",
        author_verified=False,
        component_verified=False,
        lifecycle="active",
        stable_id="component_01ARZ3NDEKTSV4RRFFQ69G5FAV",
        version="1.0",
        object_kind="component",
        support_evidence=[],
    )
    with patch(
        "ai_stp_api.slices.catalog.service.get_public_version",
        new=AsyncMock(return_value=row),
    ):
        # project_checks_summary expects PublicVersionRow-like with metadata
        from ai_stp_platform.catalog_read import PublicVersionRow

        real_row = PublicVersionRow(
            metadata=meta,  # type: ignore[arg-type]
            passport={"name": "x"},
            passport_digest="sha256:" + "0" * 64,
            published_at=datetime.now(UTC),
            trust_lane="experimental",
            author_verified=False,
            component_verified=False,
            lifecycle="active",
            stable_id="component_01ARZ3NDEKTSV4RRFFQ69G5FAV",
            version="1.0",
            object_kind="component",
        )
        with patch(
            "ai_stp_api.slices.catalog.service.get_public_version",
            new=AsyncMock(return_value=real_row),
        ):
            out = await service.read_version_checks(
                AsyncMock(),
                object_kind="component",
                stable_id="component_01ARZ3NDEKTSV4RRFFQ69G5FAV",
                version="1.0",
            )
    assert isinstance(out, SafetyChecksSummary)
    assert out.checks_passed_percent == 75
    assert out.status == "available"
    assert out.checks[0].check_id == "path_denylist"
    assert out.checks[0].reason == "unsafe_path"


@pytest.mark.asyncio
async def test_read_version_checks_empty_when_no_summary() -> None:
    meta = SimpleNamespace(
        checks_summary=None,
        owner_account_id="a1",
        likes_count=0,
        updated_at=None,
        presentation_bio=None,
    )
    from ai_stp_platform.catalog_read import PublicVersionRow

    real_row = PublicVersionRow(
        metadata=meta,  # type: ignore[arg-type]
        passport={},
        passport_digest="sha256:" + "0" * 64,
        published_at=datetime.now(UTC),
        trust_lane="experimental",
        author_verified=False,
        component_verified=False,
        lifecycle="active",
        stable_id="component_01ARZ3NDEKTSV4RRFFQ69G5FAV",
        version="1.0",
        object_kind="component",
    )
    with patch(
        "ai_stp_api.slices.catalog.service.get_public_version",
        new=AsyncMock(return_value=real_row),
    ):
        out = await service.read_version_checks(
            AsyncMock(),
            object_kind="component",
            stable_id="component_01ARZ3NDEKTSV4RRFFQ69G5FAV",
            version="1.0",
        )
    assert out.status == "empty"
    assert out.checks_passed_percent is None


@pytest.mark.asyncio
async def test_read_version_checks_not_found() -> None:
    with (
        patch(
            "ai_stp_api.slices.catalog.service.get_public_version",
            new=AsyncMock(return_value=None),
        ),
        pytest.raises(service.CatalogNotFound),
    ):
        await service.read_version_checks(
            AsyncMock(),
            object_kind="component",
            stable_id="component_01ARZ3NDEKTSV4RRFFQ69G5FAV",
            version="1.0",
        )
