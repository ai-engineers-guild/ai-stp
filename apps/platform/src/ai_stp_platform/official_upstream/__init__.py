"""Official GitHub upstream component snapshots (SPEC-056, ADR-0138)."""

from ai_stp_contracts.first_party import OWNER_ID as OFFICIAL_ACCOUNT_ID
from ai_stp_platform.official_upstream.errors import OfficialUpstreamError

SOURCE_ID = "official"
SOURCE_SLOT = "official"
OPERATOR_DEVICE_ID = "device_01JZZK7B8N4M6P2R9T5V0X3Y7Z"

__all__ = [
    "OFFICIAL_ACCOUNT_ID",
    "OPERATOR_DEVICE_ID",
    "SOURCE_ID",
    "SOURCE_SLOT",
    "OfficialUpstreamError",
]
