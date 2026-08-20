"""Assurance-layer schema exports (SPEC-015 REQ-1509).

This module declares which models of this layer are published to ``schemas/v1``
and re-exports the layers below it, so the next package up can aggregate one
set instead of walking the chain itself.

It is **not** a runnable generator. Exactly one repository-wide entrypoint
exists — ``python -m ai_stp_contracts.schemas``, the one the justfile targets
``gen-schemas`` and ``check-schemas`` invoke. A second runnable entrypoint here
would know only part of the corpus, so ``--check`` would report every schema it
does not own as an orphan and the write form would silently regenerate a subset,
leaving real drift in the rest.
"""

from typing import Final

from ai_stp_assurance.attestation import AuthorAttestation
from ai_stp_foundation.schemas import ExportedSchema
from ai_stp_passports.schemas import EXPORTED_MODELS as PASSPORT_STACK_MODELS

ASSURANCE_MODELS: Final[dict[str, ExportedSchema]] = {
    "author-attestation": AuthorAttestation,
}

EXPORTED_MODELS: Final[dict[str, ExportedSchema]] = {
    **PASSPORT_STACK_MODELS,
    **ASSURANCE_MODELS,
}
