"""Verify a provider wheel against pinned PEP 740 provenance (`SPEC-008` REQ-850).

GitHub attestation shells out to `gh`. The index path uses `pypi-attestations`
the same way: an external Sigstore verifier, never a second trust level. This
module owns publisher pinning, subject-digest comparison, and the order that
keeps provider code from running first. Cryptographic verification is injected
so unit tests can fail the fixture when that order is reversed.
"""

from __future__ import annotations

import base64
import hashlib
import importlib
import json
import shutil
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.paths import redact_home
from ai_stp_cli.provider.release import IndexPublisherRule
from ai_stp_foundation.canonical import JsonValue, canonize


@dataclass(frozen=True)
class PublisherIdentity:
    repository: str
    workflow: str
    environment: str
    subject_name: str
    subject_digest: str
    source_commit: str = ""


@dataclass(frozen=True)
class Evidence:
    trust_level: str
    digest: str
    document: str
    identity: PublisherIdentity


class BundleVerifier(Protocol):
    def verify(
        self, artifact: Path, provenance: Mapping[str, object], rule: IndexPublisherRule
    ) -> PublisherIdentity: ...


def verify(
    artifact: Path,
    provenance: Mapping[str, object] | None,
    rule: IndexPublisherRule,
    *,
    verifier: BundleVerifier | None = None,
) -> Evidence:
    """Refuse a wheel whose provenance does not bind these exact bytes to `rule`."""
    if provenance is None:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the index serves no provenance for this file",
            details={"project": rule.pypi_project},
        )
    identity = parse_identity(provenance)
    _match_publisher(identity, rule)
    digest = _file_digest(artifact)
    if identity.subject_digest != digest:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the downloaded wheel is not the subject of its provenance",
            details={"expected": identity.subject_digest, "observed": digest},
        )
    if identity.subject_name and identity.subject_name != artifact.name:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the downloaded wheel is not the subject of its provenance",
            details={"expected": identity.subject_name, "observed": artifact.name},
        )
    confirmed = (verifier or production_verifier()).verify(artifact, provenance, rule)
    _match_publisher(confirmed, rule)
    if confirmed.subject_digest and confirmed.subject_digest != digest:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the downloaded wheel is not the subject of its provenance",
            details={"expected": confirmed.subject_digest, "observed": digest},
        )
    trust = "verified_publisher" if rule.verified_publisher else "build_attested"
    return Evidence(
        trust_level=trust,
        digest=digest,
        document=canonize(cast(JsonValue, provenance)).decode("utf-8"),
        identity=confirmed if confirmed.source_commit else identity,
    )


def parse_identity(provenance: Mapping[str, object]) -> PublisherIdentity:
    """Read the publisher triple and subject digest. Does not verify a signature."""
    bundles = _object_list(provenance.get("attestation_bundles"), "attestation_bundles")
    first = _object_map(bundles[0], "attestation_bundles")
    publisher = _object_map(first.get("publisher"), "publisher")
    repository = _nonempty(publisher, "repository")
    workflow = _nonempty(publisher, "workflow")
    environment = _nonempty(publisher, "environment")
    attestations = _object_list(first.get("attestations"), "attestations")
    attestation = _object_map(attestations[0], "attestations")
    envelope = _object_map(attestation.get("envelope"), "envelope")
    statement = envelope.get("statement")
    if not isinstance(statement, str) or not statement:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the index provenance is not a PEP 740 integrity document",
            details={"field": "statement"},
        )
    subject_name, subject_digest = _subject(statement)
    return PublisherIdentity(
        repository=repository,
        workflow=workflow,
        environment=environment,
        subject_name=subject_name,
        subject_digest=subject_digest,
    )


def production_verifier() -> BundleVerifier:
    """Library first, then the `pypi-attestations` executable, then unavailable."""
    return _ProductionVerifier()


class _ProductionVerifier:
    def verify(
        self, artifact: Path, provenance: Mapping[str, object], rule: IndexPublisherRule
    ) -> PublisherIdentity:
        try:
            return _verify_with_library(artifact, provenance, rule)
        except ImportError:
            pass
        return _verify_with_cli(artifact, provenance, rule)


def _verify_with_library(
    artifact: Path, provenance: Mapping[str, object], rule: IndexPublisherRule
) -> PublisherIdentity:
    module: object = importlib.import_module("pypi_attestations")
    distribution_cls = getattr(module, "Distribution", None)
    provenance_cls = getattr(module, "Provenance", None)
    publisher_cls = getattr(module, "GitHubPublisher", None)
    error_cls = getattr(module, "VerificationError", None)
    from_file = getattr(distribution_cls, "from_file", None)
    model_validate = getattr(provenance_cls, "model_validate", None)
    if (
        not callable(from_file)
        or not callable(model_validate)
        or not callable(publisher_cls)
        or not isinstance(error_cls, type)
        or not issubclass(error_cls, BaseException)
    ):
        raise ImportError("pypi_attestations")
    dist: object = from_file(artifact)
    document: object = model_validate(dict(provenance))
    publisher: object = publisher_cls(
        repository=rule.repository,
        workflow=rule.workflow,
        environment=rule.environment,
    )
    last_error = "the provider wheel has no acceptable PEP 740 provenance"
    bundles = getattr(document, "attestation_bundles", ())
    if not isinstance(bundles, list):
        bundles = []
    for bundle in cast(list[object], bundles):
        held = getattr(bundle, "attestations", ())
        if not isinstance(held, list):
            continue
        for attestation in cast(list[object], held):
            verify = getattr(attestation, "verify", None)
            if not callable(verify):
                continue
            try:
                verify(identity=publisher, dist=dist)
            except error_cls as error:
                last_error = str(error) or last_error
                continue
            identity = parse_identity(provenance)
            commit = _commit_from_claims(attestation)
            return PublisherIdentity(
                repository=rule.repository,
                workflow=rule.workflow,
                environment=rule.environment,
                subject_name=identity.subject_name,
                subject_digest=identity.subject_digest,
                source_commit=commit,
            )
    raise CliFailure(
        "AI_STP_PRECONDITION_FAILED",
        "the provider wheel has no acceptable PEP 740 provenance",
        details={"project": rule.pypi_project, "detail": last_error},
    )


def _verify_with_cli(
    artifact: Path, provenance: Mapping[str, object], rule: IndexPublisherRule
) -> PublisherIdentity:
    found = shutil.which("pypi-attestations")
    if found is None:
        raise CliFailure(
            "AI_STP_DEPENDENCY_UNAVAILABLE",
            "index provenance verification is unavailable",
            details={"dependency": "pypi-attestations"},
        )
    provenance_file = artifact.parent / f"{artifact.name}.provenance"
    provenance_file.write_text(json.dumps(provenance), encoding="utf-8")
    command = [
        found,
        "verify",
        "pypi",
        "--repository",
        f"https://github.com/{rule.repository}",
        "--provenance-file",
        str(provenance_file),
        str(artifact),
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            shell=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as error:
        raise CliFailure(
            "AI_STP_DEPENDENCY_UNAVAILABLE",
            "index provenance verification is unavailable",
            details={"dependency": "pypi-attestations", "exception": type(error).__name__},
        ) from error
    if completed.returncode != 0:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the provider wheel has no acceptable PEP 740 provenance",
            details={"project": rule.pypi_project},
        )
    return parse_identity(provenance)


def _match_publisher(identity: PublisherIdentity, rule: IndexPublisherRule) -> None:
    if (
        identity.repository != rule.repository
        or identity.workflow != rule.workflow
        or identity.environment != rule.environment
    ):
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the index provenance publisher is not pinned by local policy",
            details={
                "repository": identity.repository,
                "workflow": identity.workflow,
                "environment": identity.environment,
                "project": rule.pypi_project,
            },
        )


def _subject(statement: str) -> tuple[str, str]:
    try:
        padding = "=" * ((4 - len(statement) % 4) % 4)
        payload: object = json.loads(base64.urlsafe_b64decode(statement + padding))
    except (ValueError, json.JSONDecodeError) as error:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the index provenance is not a PEP 740 integrity document",
            details={"field": "statement"},
        ) from error
    body = _object_map(payload, "statement")
    subjects_raw = body.get("subject")
    if not isinstance(subjects_raw, list):
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the index provenance is not a PEP 740 integrity document",
            details={"field": "subject"},
        )
    subjects = cast(list[object], subjects_raw)
    if len(subjects) != 1:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the index provenance is not a PEP 740 integrity document",
            details={"field": "subject"},
        )
    item = _object_map(subjects[0], "subject")
    name = item.get("name")
    digest = _object_map(item.get("digest"), "digest")
    if not isinstance(name, str) or not name:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the index provenance is not a PEP 740 integrity document",
            details={"field": "subject"},
        )
    sha = digest.get("sha256")
    if not isinstance(sha, str) or len(sha) != 64 or sha != sha.lower():
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the index provenance is not a PEP 740 integrity document",
            details={"field": "digest"},
        )
    return name, f"sha256:{sha}"


def _file_digest(artifact: Path) -> str:
    if artifact.is_symlink() or not artifact.is_file():
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "the provider distribution is not a regular wheel",
            details={"artifact": redact_home(artifact)},
        )
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    return f"sha256:{digest}"


def _nonempty(held: Mapping[str, object], field: str) -> str:
    value = held.get(field)
    if not isinstance(value, str) or not value:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the index provenance is not a PEP 740 integrity document",
            details={"field": field},
        )
    return value


def _object_map(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the index provenance is not a PEP 740 integrity document",
            details={"field": field},
        )
    return cast(dict[str, object], value)


def _object_list(value: object, field: str) -> list[object]:
    if not isinstance(value, list) or not value:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the index provenance is not a PEP 740 integrity document",
            details={"field": field},
        )
    return cast(list[object], value)


def _commit_from_claims(attestation: object) -> str:
    claims = getattr(attestation, "certificate_claims", None)
    if not callable(claims):
        return ""
    held: object = claims()
    if not isinstance(held, dict):
        return ""
    mapping = cast(dict[str, object], held)
    for key in ("sha", "source_sha", "1.3.6.1.4.1.57264.1.3"):
        value = mapping.get(key)
        if isinstance(value, str) and len(value) == 40 and value == value.lower():
            return value
    return ""
