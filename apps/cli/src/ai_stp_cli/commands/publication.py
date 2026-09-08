"""Create, inspect and explicitly confirm immutable publication plans."""

from collections.abc import Mapping
from contextlib import closing
from pathlib import Path
from typing import Literal, cast

from ai_stp_assurance import AuthorAttestation as FullAuthorAttestation
from ai_stp_assurance import attestation_digest
from ai_stp_cli import identity
from ai_stp_cli.answer import Answer
from ai_stp_cli.cloud import login, publication, session
from ai_stp_cli.commands import attestations as local_attestations
from ai_stp_cli.commands import cloud_auth
from ai_stp_cli.commands.auth import endpoint
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import (
    cache,
    component_passports,
    content,
    lifecycle,
    publication_snapshot,
    versions,
)
from ai_stp_cli.local.database import configured_path, open_readonly, open_registry, transaction
from ai_stp_contracts.machine_help import PublicationPlanView
from ai_stp_contracts.publication import (
    AuthorAttestation,
    PublicationConfirmRequest,
    PublicationPlanCreateRequest,
)
from ai_stp_foundation.canonical import JsonValue


def _required(parameters: Mapping[str, object], name: str) -> str:
    value = parameters.get(name)
    if value is None or not str(value):
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a required option was not supplied",
            details={"option": f"--{name}"},
        )
    return str(value)


def _session() -> session.Session:
    return cloud_auth.required("publication")


def _files(parameters: Mapping[str, object], name: str) -> tuple[Path, ...]:
    value = parameters.get(name, ())
    if not isinstance(value, tuple | list):
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a required option must be repeatable text",
            details={"option": f"--{name}"},
        )
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
        result.append(
            AuthorAttestation.model_validate(record.model_dump(mode="json", exclude_none=True))
        )
    return result


def plan(parameters: Mapping[str, object]) -> Answer[PublicationPlanView]:
    stable_id = _required(parameters, "id")
    version = _required(parameters, "version")
    selected_root = parameters.get("component-root")
    component_root = Path(str(selected_root)).expanduser() if selected_root else None
    held = _session()
    with (
        closing(open_registry(configured_path(), create=True)) as connection,
        transaction(connection),
    ):
        passport = component_passports.version_passport(connection, stable_id, version)
        recorded = versions.held(connection, stable_id, version)
        overlay = lifecycle.version_is_overlay(connection, stable_id, version)
        _artifact_bytes, artifact_inventory = publication_snapshot.prepared_bytes(
            connection, passport, root=component_root
        )
        artifact = passport.artifact
    if recorded is None:
        raise CliFailure("AI_STP_NOT_FOUND", "the exact released component version is absent")
    if overlay:
        raise CliFailure(
            "AI_STP_CONFLICT",
            "a local overlay cannot be published; materialize an owner version",
            details={"stable_id": stable_id, "version": version},
        )
    visibility = str(parameters.get("visibility") or "private")
    if visibility not in {"public", "private"}:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "visibility must be public or private",
            details={"visibility": visibility},
        )
    publication_passport = publication_snapshot.bind(
        passport,
        visibility=visibility,
        digest=artifact.digest,
        size_bytes=artifact.size_bytes,
    )
    publication_passport_digest = cache.digest_of(
        cast(JsonValue, publication_passport.model_dump(mode="json"))
    )
    request = PublicationPlanCreateRequest(
        object_kind="component",
        visibility=cast(Literal["public", "private"], visibility),
        stable_id=stable_id,
        version=version,
        content_digest=artifact.digest,
        artifact_inventory=list(artifact_inventory),
        passport=cast(dict[str, object], publication_passport.model_dump(mode="json")),
        attestations=validated_attestations(
            parameters,
            stable_id=stable_id,
            version=version,
            content_digest=artifact.digest,
            passport_digest=publication_passport_digest,
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
    if current.plan_id != plan_id or current.plan_hash != plan_hash:
        raise CliFailure("AI_STP_PRECONDITION_FAILED", "the distribution plan changed after review")
    if current.state in {"ready", "draft"}:
        with closing(open_readonly(configured_path())) as connection:
            artifact = content.get(connection, current.content_digest)
            projection_payloads: list[tuple[str, bytes]] = []
            if current.object_kind == "component":
                passport = component_passports.version_passport(
                    connection, current.stable_id, current.version
                )
                projection_digests = sorted(
                    {
                        str(scope.projection_artifact.digest)
                        for adaptation in passport.adaptations
                        for scope in adaptation.scope_adaptations
                        if str(scope.projection_artifact.digest) != current.content_digest
                    }
                )
                projection_payloads = [
                    (digest, content.get(connection, digest)) for digest in projection_digests
                ]
        bound = publication.bind(where, held.access_token, plan_id, artifact)
        publication.require_same_plan(current, bound)
        for digest, payload in projection_payloads:
            projection_bound = publication.bind_projection(
                where, held.access_token, plan_id, digest, payload
            )
            publication.require_same_plan(current, projection_bound)
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
    publication.require_same_plan(current, result)
    return Answer(PublicationPlanView.model_validate(result.model_dump(mode="json")))
