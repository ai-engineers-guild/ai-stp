"""Cross-cutting primitives of ai_stp.

Owns nothing domain-specific: typed stable identifiers, canonical JSON bytes,
domain-separated digests, two-integer versions, exact references and the
machine output envelope. Normative sources: SPEC-015, docs/contracts/
canonical-data.md and docs/contracts/cli-json.md.
"""

from ai_stp_foundation.adaptations import (
    ADAPTATION_ID_PATTERN,
    adaptation_id,
    is_valid_adaptation_id,
)
from ai_stp_foundation.canonical import CanonicalizationError, canonize, from_json_bytes
from ai_stp_foundation.digests import (
    DIGEST_DOMAINS,
    DigestError,
    digest_bytes,
    digest_canonical,
    is_digest,
)
from ai_stp_foundation.envelope import (
    CliError,
    CliErrorReader,
    ErrorEnvelope,
    ErrorEnvelopeReader,
    SuccessEnvelope,
    SuccessEnvelopeReader,
)
from ai_stp_foundation.errors import (
    ERROR_CODES,
    error_code_schema,
    exit_class_for,
    is_registered_code,
)
from ai_stp_foundation.identity import (
    DISPLAY_NAME_MAX_LENGTH,
    HANDLE_PATTERN,
    IDENTITY_NORMALIZATION_VERSION,
    OFFICIAL_DISPLAY_NAME,
    OFFICIAL_HANDLE,
    IdentityNormalizationError,
    canonical_slug,
    handle_from_account_id,
    is_protected_official_display,
    is_protected_official_handle,
    normalize_display_key,
    normalize_handle,
    submitted_display_name,
)
from ai_stp_foundation.ids import ID_PREFIXES, StableIdError, is_valid_id, new_id, parse_id
from ai_stp_foundation.refs import ComponentRef, SetupRef
from ai_stp_foundation.revisions import is_valid_revision_id, revision_id
from ai_stp_foundation.timestamps import (
    TimestampError,
    format_timestamp,
    is_valid_timestamp,
    parse_timestamp,
)
from ai_stp_foundation.versioning import (
    VersionError,
    compare_versions,
    format_version,
    parse_version,
)

__all__ = [
    "ADAPTATION_ID_PATTERN",
    "DIGEST_DOMAINS",
    "DISPLAY_NAME_MAX_LENGTH",
    "ERROR_CODES",
    "HANDLE_PATTERN",
    "IDENTITY_NORMALIZATION_VERSION",
    "ID_PREFIXES",
    "OFFICIAL_DISPLAY_NAME",
    "OFFICIAL_HANDLE",
    "CanonicalizationError",
    "CliError",
    "CliErrorReader",
    "ComponentRef",
    "DigestError",
    "ErrorEnvelope",
    "ErrorEnvelopeReader",
    "IdentityNormalizationError",
    "SetupRef",
    "StableIdError",
    "SuccessEnvelope",
    "SuccessEnvelopeReader",
    "TimestampError",
    "VersionError",
    "adaptation_id",
    "canonical_slug",
    "canonize",
    "compare_versions",
    "digest_bytes",
    "digest_canonical",
    "error_code_schema",
    "exit_class_for",
    "format_timestamp",
    "format_version",
    "from_json_bytes",
    "handle_from_account_id",
    "is_digest",
    "is_protected_official_display",
    "is_protected_official_handle",
    "is_registered_code",
    "is_valid_adaptation_id",
    "is_valid_id",
    "is_valid_revision_id",
    "is_valid_timestamp",
    "new_id",
    "normalize_display_key",
    "normalize_handle",
    "parse_id",
    "parse_timestamp",
    "parse_version",
    "revision_id",
    "submitted_display_name",
]
