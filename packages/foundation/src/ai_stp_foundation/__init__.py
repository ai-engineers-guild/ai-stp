"""Cross-cutting primitives of ai_stp.

Owns nothing domain-specific: typed stable identifiers, canonical JSON bytes,
domain-separated digests, two-integer versions, exact references and the
machine output envelope. Normative sources: SPEC-015, docs/contracts/
canonical-data.md and docs/contracts/cli-json.md.
"""

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
    "DIGEST_DOMAINS",
    "ERROR_CODES",
    "ID_PREFIXES",
    "CanonicalizationError",
    "CliError",
    "CliErrorReader",
    "ComponentRef",
    "DigestError",
    "ErrorEnvelope",
    "ErrorEnvelopeReader",
    "SetupRef",
    "StableIdError",
    "SuccessEnvelope",
    "SuccessEnvelopeReader",
    "TimestampError",
    "VersionError",
    "canonize",
    "compare_versions",
    "digest_bytes",
    "digest_canonical",
    "error_code_schema",
    "exit_class_for",
    "format_timestamp",
    "format_version",
    "from_json_bytes",
    "is_digest",
    "is_registered_code",
    "is_valid_id",
    "is_valid_revision_id",
    "is_valid_timestamp",
    "new_id",
    "parse_id",
    "parse_timestamp",
    "parse_version",
    "revision_id",
]
