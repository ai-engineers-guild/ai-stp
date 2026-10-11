"""Exact provider projection profiles selected by the first alpha contract."""

import json
from importlib.resources import files
from typing import Any, Final, Literal, NamedTuple, cast

from ai_stp_foundation.harnesses import HarnessId

type TargetScope = Literal["global", "user_root", "project"]
type ProviderSurfaceKey = tuple[HarnessId, TargetScope]


class ProviderSurfaceIdentity(NamedTuple):
    profile_id: str
    profile_digest: str
    bundle_format: str = "ai-stp-bundle/2"


_CATALOG: Final[dict[str, Any]] = json.loads(
    files("ai_stp_foundation").joinpath("provider_catalog.json").read_text(encoding="utf-8")
)
if _CATALOG["schema_version"] != 1:
    raise ValueError("unsupported provider catalog schema")

PROVIDER_SURFACES: Final[dict[ProviderSurfaceKey, ProviderSurfaceIdentity]] = {
    (
        cast("HarnessId", row["harness_id"]),
        cast("TargetScope", row["target_scope"]),
    ): ProviderSurfaceIdentity(row["profile_id"], row["profile_digest"], row["bundle_format"])
    for row in _CATALOG["profiles"]
}


def provider_route_rows() -> tuple[dict[str, Any], ...]:
    """Return the passive projection rows shared by the native and Python engines."""
    return tuple(dict(row) for row in _CATALOG["routes"])


def provider_surface(harness_id: HarnessId, target_scope: TargetScope) -> ProviderSurfaceIdentity:
    """Return the exact profile for one supported harness scope."""
    return PROVIDER_SURFACES[(harness_id, target_scope)]
