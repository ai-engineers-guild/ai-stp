"""Create and verify full device-signed author attestations."""

import base64
import os
import stat
from collections.abc import Mapping
from contextlib import closing
from pathlib import Path
from typing import cast

from ai_stp_assurance import AuthorAttestation, attestation_digest
from ai_stp_cli import identity
from ai_stp_cli.answer import Answer
from ai_stp_cli.cloud import session
from ai_stp_cli.commands import cloud_auth
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import component_passports, versions
from ai_stp_cli.local.database import configured_path, open_readonly
from ai_stp_cli.local.passports import moment
from ai_stp_cli.paths import redact_home, write_private
from ai_stp_contracts.machine_help import CliSignedAttestation
from ai_stp_foundation.refs import ComponentRef

MAX_ATTESTATION_BYTES = 256 * 1024
_EMPTY_SIGNATURE = base64.b64encode(b"\x00" * 64).decode("ascii")


def _required(parameters: Mapping[str, object], name: str) -> str:
    value = str(parameters.get(name) or "")
    if not value:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a required option was not supplied",
            details={"option": f"--{name}"},
        )
    return value


def _repeated(parameters: Mapping[str, object], name: str) -> list[str]:
    value = parameters.get(name, ())
    if not isinstance(value, tuple | list):
        raise CliFailure("AI_STP_VALIDATION_ERROR", f"--{name} must be repeatable text")
    return [str(item) for item in cast(tuple[object, ...] | list[object], value)]


def _tools(parameters: Mapping[str, object]) -> dict[str, str]:
    result: dict[str, str] = {}
    for entry in _repeated(parameters, "tool-version"):
        name, separator, version = entry.partition("=")
        if not separator or not name or not version or name in result:
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                "each --tool-version must be one unique non-empty name=version pair",
            )
        if any(word in name.lower() for word in ("secret", "token", "password", "key")):
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR", "secret-bearing tool version names are forbidden"
            )
        result[name] = version
    return result


def _session() -> session.Session:
    return cloud_auth.required("attestation signing")


def _identity() -> tuple[identity.Identity | None, str | None]:
    return identity.current()


def sign(parameters: Mapping[str, object]) -> Answer[CliSignedAttestation]:
    stable_id = _required(parameters, "id")
    version = _required(parameters, "version")
    output = Path(_required(parameters, "output")).expanduser()
    if parameters.get("confirm") is not True:
        raise CliFailure(
            "AI_STP_USER_DECISION_REQUIRED",
            "attestation signing requires confirmation of the exact local evidence",
            next_actions=["attestation sign --confirm --json"],
        )
    if output.exists() or output.is_symlink():
        raise CliFailure(
            "AI_STP_CONFLICT",
            "the attestation output already exists and will not be replaced",
            details={"output": redact_home(output)},
        )
    held_session = _session()
    held_identity, warning = _identity()
    if held_identity is None or held_identity.state != "active":
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "an active local device identity is required for attestation signing",
            next_actions=["device init --json"],
        )
    if held_identity.device_id != held_session.device_id:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the cloud session and local signing identity name different devices",
            next_actions=["auth login --provider github --json"],
        )
    with closing(open_readonly(configured_path())) as connection:
        passport = component_passports.version_passport(connection, stable_id, version)
        recorded = versions.held(connection, stable_id, version)
    if recorded is None:
        raise CliFailure("AI_STP_NOT_FOUND", "the exact released component version is absent")
    unsigned = AuthorAttestation(
        object_digest=passport.artifact.digest,
        subject=ComponentRef(
            stable_id=stable_id,
            version=version,
            passport_digest=recorded.passport_digest,
        ),
        check_id=_required(parameters, "check-id"),
        policy_version=_required(parameters, "policy-version"),
        tool_versions=_tools(parameters),
        harness_id=_required(parameters, "harness-id"),  # pyright: ignore[reportArgumentType]
        harness_version=_required(parameters, "harness-version"),
        provider_version=_required(parameters, "provider-version"),
        test_case_ids=_repeated(parameters, "test-case-id"),
        result=_required(parameters, "result"),  # pyright: ignore[reportArgumentType]
        account_id=held_session.account_id,
        device_id=held_identity.device_id,
        attested_at=moment(),
        signature=_EMPTY_SIGNATURE,
    )
    digest = attestation_digest(unsigned)
    signed = unsigned.model_copy(
        update={"signature": base64.b64encode(held_identity.sign(digest.encode("utf-8"))).decode()}
    )
    write_private(output, signed.model_dump_json(indent=2) + "\n")
    return Answer(
        CliSignedAttestation(
            **signed.model_dump(mode="python"),
            output_path=redact_home(output),
            attestation_digest=digest,
        ),
        warnings=() if warning is None else (warning,),
    )


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
