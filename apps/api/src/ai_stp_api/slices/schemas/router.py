"""Serve the provider-info schema at the URL its `$id` names.

The `$id` is a JSON Schema identifier. Following it used to 404. These bytes
are the generated kit file, kept in lockstep by `release_scripts/provider_kit.py`.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Response

router = APIRouter(tags=["schemas"])

_SCHEMA = Path(__file__).with_name("provider-info.schema.json")
_PROVIDER_INFO_PATH = "/schemas/provider-protocol/v3/provider-info.json"


@router.get(_PROVIDER_INFO_PATH)
def provider_info_schema() -> Response:
    """Return the exact v3 provider-info JSON Schema bytes."""
    return Response(
        content=_SCHEMA.read_bytes(),
        media_type="application/schema+json",
        headers={"Cache-Control": "public, max-age=3600"},
    )
