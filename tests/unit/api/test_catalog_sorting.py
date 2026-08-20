from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast

from ai_stp_api.slices.catalog.service import sort_catalog_rows, sort_relevant_catalog_rows
from ai_stp_platform.catalog_read import PublicVersionRow


def _row(
    stable_id: str,
    *,
    likes: int,
    updated_offset: int,
    tags: list[str] | None = None,
    author: str = "author",
) -> PublicVersionRow:
    published = datetime(2026, 8, 1, tzinfo=UTC)
    metadata = SimpleNamespace(
        likes_count=likes,
        updated_at=published + timedelta(days=updated_offset),
        owner_account_id=author,
    )
    return cast(
        PublicVersionRow,
        SimpleNamespace(
            metadata=metadata,
            passport={"name": stable_id, "description": "", "tags": tags or []},
            published_at=published,
            stable_id=stable_id,
        ),
    )


def test_likes_sort_uses_count_then_update_time_then_stable_id() -> None:
    rows = [
        _row("component_a", likes=2, updated_offset=3),
        _row("component_b", likes=5, updated_offset=1),
        _row("component_c", likes=5, updated_offset=2),
    ]

    ordered = sort_catalog_rows(rows, sort="likes")

    assert [row.stable_id for row in ordered] == ["component_c", "component_b", "component_a"]


def test_updated_sort_uses_update_time() -> None:
    rows = [
        _row("component_a", likes=99, updated_offset=1),
        _row("component_b", likes=0, updated_offset=2),
    ]

    ordered = sort_catalog_rows(rows, sort="updated_at")

    assert [row.stable_id for row in ordered] == ["component_b", "component_a"]


def test_updated_sort_ascending_orders_the_complete_input_before_paging() -> None:
    rows = [
        _row("component_a", likes=0, updated_offset=3),
        _row("component_b", likes=0, updated_offset=1),
        _row("component_c", likes=0, updated_offset=2),
    ]

    ordered = sort_catalog_rows(rows, sort="updated_at", direction="asc")

    assert [row.stable_id for row in ordered] == ["component_b", "component_c", "component_a"]


def test_relevance_prioritizes_exact_name_over_description_match() -> None:
    exact = _row("search term", likes=0, updated_offset=0)
    description = _row("other", likes=0, updated_offset=1)
    description.passport["description"] = "Contains search term in prose"

    ordered = sort_relevant_catalog_rows([description, exact], q="search term")

    assert [row.stable_id for row in ordered] == ["search term", "other"]


def test_relevance_scores_name_prefix_name_fragment_tag_author_and_description() -> None:
    rows = [
        _row("prefix match", likes=0, updated_offset=0),
        _row("a prefix inside", likes=0, updated_offset=0),
        _row("tag", likes=0, updated_offset=0, tags=["prefix"]),
        _row("author", likes=0, updated_offset=0, author="prefix-publisher"),
        _row("description", likes=0, updated_offset=0),
    ]
    rows[-1].passport["description"] = "prefix in prose"

    ordered = sort_relevant_catalog_rows(rows, q="prefix")

    assert [row.stable_id for row in ordered] == [
        "prefix match",
        "a prefix inside",
        "tag",
        "author",
        "description",
    ]


def test_relevance_without_query_uses_recency_and_stable_id() -> None:
    older = _row("component_z", likes=0, updated_offset=0)
    newer = _row("component_a", likes=0, updated_offset=1)

    assert sort_relevant_catalog_rows([older, newer], q=None) == [newer, older]
