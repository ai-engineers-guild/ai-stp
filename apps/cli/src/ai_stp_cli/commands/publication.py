"""Create, inspect and explicitly confirm immutable publication plans."""

from collections.abc import Mapping
from contextlib import closing
from pathlib import Path
from typing import cast

from ai_stp_assurance import AuthorAttestation as FullAuthorAttestation
from ai_stp_assurance import attestation_digest
from ai_stp_cli import identity
from ai_stp_cli.answer import Answer
from ai_stp_cli.cloud import login, publication, session
from ai_stp_cli.commands import attestations as local_attestations
from ai_stp_cli.commands import cloud_auth
from ai_stp_cli.commands.auth import endpoint
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import component_passports, content, versions
from ai_stp_cli.local.database import configured_path, open_readonly
from ai_stp_contracts.machine_help import PublicationPlanView
from ai_stp_contracts.publication import (
    AuthorAttestation,
    PublicationConfirmRequest,
    PublicationPlanCreateRequest,
)


def _required(parameters: Mapping[str, object], name: str) -> str:
    value = parameters.get(name)
    if value is None or not str(value):
        raise CliFailure("AI_STP_VALIDATION_ERROR", f"--{name} is required")
    return str(value)


def _session() -> session.Session:
    return cloud_auth.required("publication")


def _files(parameters: Mapping[str, object], name: str) -> tuple[Path, ...]:
    value = parameters.get(name, ())
    if not isinstance(value, tuple | list):
        raise CliFailure("AI_STP_VALIDATION_ERROR", f"--{name} must be repeatable text")
    return tuple(
        Path(str(item)).expanduser() for item in cast(tuple[object, ...] | list[object], value)
    )


def validated_attestations(
    parameters: Mapping[str, object],
    *,
    stable_id: str,
    version: str,
    content_digest: str,
    passport_digest: str,
    held_session: session.Session,
) -> list[AuthorAttestation]:
    paths = _files(parameters, "attestation-file")
    if not paths:
        return []
    signer, _warning = identity.current()
    if signer is None or signer.state != "active" or signer.device_id != held_session.device_id:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "publication attestations require the active session's local signing identity",
            next_actions=["device show --json", "auth status --json"],
        )
    result: list[AuthorAttestation] = []
    seen: set[str] = set()
    for path in paths:
        record: FullAuthorAttestation = local_attestations.load(path)
        if (
            record.object_digest != content_digest
            or record.subject.stable_id != stable_id
            or record.subject.version != version
            or record.subject.passport_digest != passport_digest
            or record.account_id != held_session.account_id
            or record.device_id != held_session.device_id
        ):
            raise CliFailure(
                "AI_STP_PRECONDITION_FAILED",
                "an attestation is not bound to the exact released publication coordinates",
            )
        digest = attestation_digest(record)
        if digest in seen:
            raise CliFailure("AI_STP_CONFLICT", "the same attestation was supplied more than once")
        if not local_attestations.verify(record, signer):
            raise CliFailure("AI_STP_VALIDATION_ERROR", "an attestation signature is invalid")
        seen.add(digest)
        result.append(AuthorAttestation.model_validate(record.model_dump(mode="json")))
    return result


def plan(parameters: Mapping[str, object]) -> Answer[PublicationPlanView]:
    stable_id = _required(parameters, "id")
    version = _required(parameters, "version")
    held = _session()
    with closing(open_readonly(configured_path())) as connection:
        passport = component_passports.version_passport(connection, stable_id, version)
        recorded = versions.held(connection, stable_id, version)
    if recorded is None:
        raise CliFailure("AI_STP_NOT_FOUND", "the exact released component version is absent")
    request = PublicationPlanCreateRequest(
        object_kind="component",
        stable_id=stable_id,
        version=version,
        content_digest=passport.artifact.digest,
        passport=cast(dict[str, object], passport.model_dump(mode="json")),
        attestations=validated_attestations(
            parameters,
            stable_id=stable_id,
            version=version,
            content_digest=passport.artifact.digest,
            passport_digest=recorded.passport_digest,
            held_session=held,
        ),
        idempotency_key=login.new_idempotency_key(),
        device_id=held.device_id,
    )
    return Answer(
        PublicationPlanView.model_validate(
            publication.create(endpoint(), held.access_token, request).model_dump(mode="json")
        )
    )


def show(parameters: Mapping[str, object]) -> Answer[PublicationPlanView]:
    plan_id = _required(parameters, "plan-id")
    held = _session()
    return Answer(
        PublicationPlanView.model_validate(
            publication.status(endpoint(), held.access_token, plan_id).model_dump(mode="json")
        )
    )


def confirm(parameters: Mapping[str, object]) -> Answer[PublicationPlanView]:
    plan_id = _required(parameters, "plan-id")
    plan_hash = _required(parameters, "plan-hash")
    if not bool(parameters.get("confirm")):
        raise CliFailure(
            "AI_STP_USER_DECISION_REQUIRED",
            "publication requires explicit confirmation of the exact plan hash",
            details={"plan_id": plan_id},
            next_actions=[
                f"publication confirm --plan-id {plan_id} --plan-hash {plan_hash} --confirm --json"
            ],
        )
    held = _session()
    where = endpoint()
    current = publication.status(where, held.access_token, plan_id)
    if current.state in {"ready", "draft"}:
        with closing(open_readonly(configured_path())) as connection:
            artifact = content.get(connection, current.content_digest)
        publication.bind(where, held.access_token, plan_id, artifact)
    request = PublicationConfirmRequest(
        plan_hash=plan_hash,
        confirmed=True,
        idempotency_key=login.new_idempotency_key(),
    )
    try:
        result = publication.confirm(where, held.access_token, plan_id, request)
    except CliFailure as failure:
        if failure.retryable:
            raise CliFailure(
                failure.code,
                failure.message,
                retryable=True,
                details=failure.details,
                next_actions=[f"publication status --plan-id {plan_id} --json"],
            ) from failure
        raise
    return Answer(PublicationPlanView.model_validate(result.model_dump(mode="json")))
