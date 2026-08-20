"""Catalog path-param validation (stable_id + X.Y version)."""

from __future__ import annotations

import pytest

from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.slices.catalog.router import (
    require_component_id,
    require_setup_id,
    require_version,
)


def test_component_id_accepts_canonical_form() -> None:
    sid = "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z"
    assert require_component_id(sid) == sid


def test_component_id_rejects_wrong_prefix_and_garbage() -> None:
    with pytest.raises(ApiError) as exc:
        require_component_id("setup_01JQZK7B8N4M6P2R9T5V0X3Y7Z")
    assert exc.value.category is ErrorCategory.VALIDATION
    with pytest.raises(ApiError):
        require_component_id("not-an-id")


def test_setup_id_rejects_component_prefix() -> None:
    with pytest.raises(ApiError) as exc:
        require_setup_id("component_01JQZK7B8N4M6P2R9T5V0X3Y7Z")
    assert exc.value.category is ErrorCategory.VALIDATION


def test_version_accepts_xy_rejects_latest_and_leading_zeros() -> None:
    assert require_version("1.0") == "1.0"
    assert require_version("0.0") == "0.0"
    with pytest.raises(ApiError) as exc:
        require_version("latest")
    assert exc.value.category is ErrorCategory.VALIDATION
    with pytest.raises(ApiError):
        require_version("01.0")
    with pytest.raises(ApiError):
        require_version("1")
