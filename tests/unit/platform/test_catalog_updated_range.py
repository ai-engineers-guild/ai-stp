"""Inclusive UTC updated-date windows for catalog search."""

from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import cast

import pytest
from pydantic import ValidationError

from ai_stp_api.slices.catalog.service import inclusive_updated_bounds, row_matches_updated_range
from ai_stp_contracts.catalog import ComponentSearchRequest, SetupSearchRequest
from ai_stp_platform.catalog_cursor import filter_signature
from ai_stp_platform.catalog_read import PublicVersionRow

pytestmark = pytest.mark.platform


def test_search_request_rejects_a_reversed_updated_range() -> None:
    with pytest.raises(ValidationError):
        ComponentSearchRequest(updated_from=date(2026, 2, 2), updated_to=date(2026, 2, 1))
    with pytest.raises(ValidationError):
        SetupSearchRequest(updated_from=date(2026, 2, 2), updated_to=date(2026, 2, 1))


def test_search_request_accepts_one_or_both_ordered_bounds() -> None:
    single = ComponentSearchRequest(updated_from=date(2026, 1, 1))
    assert single.updated_from == date(2026, 1, 1)
    assert single.updated_to is None
    both = SetupSearchRequest(updated_from=date(2026, 1, 1), updated_to=date(2026, 1, 31))
    assert both.updated_to == date(2026, 1, 31)


def test_inclusive_updated_bounds_use_utc_start_and_next_day() -> None:
    start, end = inclusive_updated_bounds(date(2026, 8, 13), date(2026, 8, 13))
    assert start == datetime(2026, 8, 13, tzinfo=UTC)
    assert end == datetime(2026, 8, 14, tzinfo=UTC)


def test_row_matches_updated_range_is_start_inclusive_and_end_exclusive() -> None:
    start, end = inclusive_updated_bounds(date(2026, 8, 13), date(2026, 8, 13))
    on_start = SimpleNamespace(
        metadata=SimpleNamespace(updated_at=datetime(2026, 8, 13, tzinfo=UTC)),
        published_at=datetime(2026, 8, 1, tzinfo=UTC),
    )
    at_end = SimpleNamespace(
        metadata=SimpleNamespace(updated_at=datetime(2026, 8, 14, tzinfo=UTC)),
        published_at=datetime(2026, 8, 1, tzinfo=UTC),
    )
    assert row_matches_updated_range(cast(PublicVersionRow, on_start), start, end) is True
    assert row_matches_updated_range(cast(PublicVersionRow, at_end), start, end) is False


def test_filter_signature_omits_empty_updated_bounds() -> None:
    base = filter_signature(
        object_kind="component",
        q=None,
        tags=[],
        harness_id=None,
        component_type=None,
        include_experimental=True,
    )
    unchanged = filter_signature(
        object_kind="component",
        q=None,
        tags=[],
        harness_id=None,
        component_type=None,
        include_experimental=True,
        updated_from=None,
        updated_to=None,
    )
    with_range = filter_signature(
        object_kind="component",
        q=None,
        tags=[],
        harness_id=None,
        component_type=None,
        include_experimental=True,
        updated_from="2026-01-01",
        updated_to="2026-01-31",
    )
    assert base == unchanged
    assert with_range != base
    from_only = filter_signature(
        object_kind="component",
        q=None,
        tags=[],
        harness_id=None,
        component_type=None,
        include_experimental=True,
        updated_from="2026-01-01",
    )
    to_only = filter_signature(
        object_kind="component",
        q=None,
        tags=[],
        harness_id=None,
        component_type=None,
        include_experimental=True,
        updated_to="2026-01-31",
    )
    assert from_only != base
    assert to_only != base
    assert from_only != to_only
    assert from_only != with_range
