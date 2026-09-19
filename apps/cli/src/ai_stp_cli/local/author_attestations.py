"""Load and verify a device-signed author attestation file.

Bounded regular files only. Publication and the sign command share this so
application code does not import the Click handler module.
"""

from __future__ import annotations

import base64
import os
import stat
from pathlib import Path
from typing import Final

from ai_stp_assurance import AuthorAttestation, attestation_digest
from ai_stp_cli import identity
from ai_stp_cli.errors import CliFailure

MAX_ATTESTATION_BYTES: Final[int] = 256 * 1024


def load(path: Path) -> AuthorAttestation:
    """Load one bounded regular signed record without following a symlink."""
    try:
        before = path.lstat()
    except OSError as error:
        raise CliFailure("AI_STP_NOT_FOUND", "the attestation file cannot be opened") from error
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_size > MAX_ATTESTATION_BYTES
    ):
        raise CliFailure("AI_STP_VALIDATION_ERROR", "attestation must be a bounded regular file")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(path, flags)
        try:
            after = os.fstat(descriptor)
            if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
                raise CliFailure("AI_STP_CONFLICT", "the attestation file changed")
            with os.fdopen(descriptor, "rb", closefd=False) as stream:
                payload = stream.read(MAX_ATTESTATION_BYTES + 1)
        finally:
            os.close(descriptor)
    except CliFailure:
        raise
    except OSError as error:
        raise CliFailure("AI_STP_VALIDATION_ERROR", "attestation is not safely readable") from error
    if len(payload) > MAX_ATTESTATION_BYTES:
        raise CliFailure("AI_STP_VALIDATION_ERROR", "attestation exceeds its byte limit")
    try:
        return AuthorAttestation.model_validate_json(payload)
    except ValueError as error:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR", "attestation is not a valid closed record"
        ) from error


def verify(record: AuthorAttestation, signer: identity.Identity) -> bool:
    try:
        signature = base64.b64decode(record.signature, validate=True)
    except ValueError:
        return False
    return identity.verify(signer.public_key, attestation_digest(record).encode("utf-8"), signature)
