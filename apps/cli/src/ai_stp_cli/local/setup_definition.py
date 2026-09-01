"""CLI re-export of setup-definition freeze (SPEC-057 REQ-5705, REQ-5706, REQ-5707)."""

from ai_stp_sources.definition import (
    DEFINITION_V1,
    DEFINITION_V2,
    MAX_DEFINITION_BYTES,
    MAX_EMBEDDED_RECORDS,
    EmbeddedDraft,
    FrozenDefinition,
    encode_component_ref,
    freeze_setup_definition,
    identity_key,
    local_component_identity,
    pack_component_tree,
    validate_setup_definition,
)

author_mixed_setup = freeze_setup_definition

__all__ = [
    "DEFINITION_V1",
    "DEFINITION_V2",
    "MAX_DEFINITION_BYTES",
    "MAX_EMBEDDED_RECORDS",
    "EmbeddedDraft",
    "FrozenDefinition",
    "author_mixed_setup",
    "encode_component_ref",
    "freeze_setup_definition",
    "identity_key",
    "local_component_identity",
    "pack_component_tree",
    "validate_setup_definition",
]
