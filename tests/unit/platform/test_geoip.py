"""Offline GeoIP projection tests."""

from __future__ import annotations

from pathlib import Path
from typing import cast
from unittest.mock import Mock, patch

from ai_stp_api.geoip import approximate_location


def test_approximate_location_public_address_returns_coarse_label() -> None:
    reader = Mock()
    reader.get.return_value = {
        "city": {"names": {"en": "São Paulo"}},
        "country": {"iso_code": "BR"},
    }
    with patch("ai_stp_api.geoip._open_database", return_value=reader):
        result = approximate_location("8.8.8.8", Path("city.mmdb"))

    assert result == "São Paulo, BR"


def test_approximate_location_private_address_skips_database() -> None:
    with patch("ai_stp_api.geoip._open_database") as open_database:
        result = approximate_location("127.0.0.1", Path("city.mmdb"))

    assert result is None
    cast("Mock", open_database).assert_not_called()
