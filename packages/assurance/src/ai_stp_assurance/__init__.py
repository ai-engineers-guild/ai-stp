"""Evidence records of the assurance layer.

Currently owns the author attestation record (ADR-0026): the signed,
secret-free evidence that a credential-dependent mandatory check ran on the
author's device against exact coordinates.
"""

from ai_stp_assurance.attestation import (
    AuthorAttestation,
    attestation_digest,
    attestation_payload,
)

__all__ = [
    "AuthorAttestation",
    "attestation_digest",
    "attestation_payload",
]
