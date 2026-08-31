"""Offline coarse IP geolocation; no address is retained."""

from __future__ import annotations

from functools import lru_cache
from ipaddress import ip_address
from pathlib import Path
from typing import cast

import maxminddb
from maxminddb.errors import InvalidDatabaseError


@lru_cache(maxsize=1)
def _open_database(path: str) -> maxminddb.Reader:
    return maxminddb.open_database(path)  # pyright: ignore[reportUnknownMemberType]


def _mapping(value: object) -> dict[str, object]:
    return cast("dict[str, object]", value) if isinstance(value, dict) else {}


def approximate_location(client_ip: str | None, database_path: Path | None) -> str | None:
    """Resolve a public address to ``City, Country`` using a local MMDB file."""
    if not client_ip or database_path is None:
        return None
    try:
        address = ip_address(client_ip)
        if not address.is_global:
            return None
        raw = cast(
            "object",
            _open_database(str(database_path)).get(  # pyright: ignore[reportUnknownMemberType]
                str(address)
            ),
        )
    except (InvalidDatabaseError, OSError, ValueError):
        return None
    record = _mapping(raw)
    city = _mapping(record.get("city"))
    country = _mapping(record.get("country"))
    city_name = _mapping(city.get("names")).get("en")
    country_code = country.get("iso_code")
    parts = [value for value in (city_name, country_code) if isinstance(value, str) and value]
    return ", ".join(parts)[:160] or None
