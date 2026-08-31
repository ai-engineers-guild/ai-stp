"""Serve provider-protocol schemas at the URLs their `$id` values name.

The `$id` is a JSON Schema identifier. Following it used to 404. These bytes
are the generated kit file, kept in lockstep by `release_scripts/provider_kit.py`.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Response

router = APIRouter(tags=["schemas"])

_SCHEMA_DIRECTORY = Path(__file__).parent
_PROVIDER_INFO_PATH = "/schemas/provider-protocol/v3/provider-info.json"
_STATUS_RESPONSE_PATH = "/schemas/provider-protocol/v3/status-response.json"


def _response(name: str) -> Response:
    return Response(
        content=(_SCHEMA_DIRECTORY / name).read_bytes(),
        media_type="application/schema+json",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get(_PROVIDER_INFO_PATH)
def provider_info_schema() -> Response:
    """Return the exact v3 provider-info JSON Schema bytes."""
    return _response("provider-info.schema.json")


@router.get(_STATUS_RESPONSE_PATH)
def status_response_schema() -> Response:
    """Return the exact v3 status-response JSON Schema bytes."""
    return _response("status-response.schema.json")
