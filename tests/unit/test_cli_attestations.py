"""Device attestations bind exact released coordinates and remain verifiable."""

import base64
import json
import os
import sqlite3
from pathlib import Path
from sqlite3 import Connection
from typing import cast

import pytest

from ai_stp_assurance import AuthorAttestation, attestation_digest
from ai_stp_cli import identity
from ai_stp_cli.cloud import session
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import component_passports, versions
from ai_stp_cli.local.cache import digest_of
from ai_stp_contracts.first_party import versions as first_party_versions
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.refs import ComponentRef
from ai_stp_passports import ComponentVersionPassport

ACCOUNT = "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z"


def _passport() -> ComponentVersionPassport:
    return next(
        item.passport
        for item in first_party_versions()
        if isinstance(item.passport, ComponentVersionPassport)
    )


def test_sign_writes_one_owner_only_full_record_and_load_verifies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ai_stp_cli.commands import attestations

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("AI_STP_FORCE_FILE_CREDENTIAL_STORE", "1")
    signer, _warning = identity.load_or_create()
    passport = _passport()
    passport_document = cast(dict[str, JsonValue], passport.model_dump(mode="json"))
    recorded = versions.Recorded(
        stable_id=passport.stable_id,
        version=passport.version,
        major=1,
        minor=0,
        passport_digest=digest_of(passport_document),
        revision_id="revision_" + "a" * 64,
        created_at="2026-08-13T00:00:00.000Z",
    )
    monkeypatch.setattr(
        attestations,
        "_session",
        lambda: session.Session(
            account_id=ACCOUNT,
            device_id=signer.device_id,
            access_token="bearer",
            refresh_token="refresh",
            expires_at="2099-01-01T00:00:00.000Z",
        ),
    )
    monkeypatch.setattr(attestations, "_identity", lambda: (signer, None))

    def open_memory(_path: Path) -> Connection:
        return sqlite3.connect(":memory:")

    def passport_for_version(
        _connection: Connection, _stable_id: str, _version: str
    ) -> ComponentVersionPassport:
        return passport

    def held_version(_connection: Connection, _stable_id: str, _version: str) -> versions.Recorded:
        return recorded

    monkeypatch.setattr(attestations, "open_readonly", open_memory)
    monkeypatch.setattr(
        component_passports,
        "version_passport",
        passport_for_version,
    )
    monkeypatch.setattr(
        versions,
        "held",
        held_version,
    )
    output = tmp_path / "evidence" / "attestation.json"

    result = attestations.sign(
        {
            "id": passport.stable_id,
            "version": passport.version,
            "check-id": "credentials",
            "policy-version": "1",
            "tool-version": ("runner=2.0",),
            "harness-id": passport.adaptations[0].harness_id,
            "harness-version": "1.2.3",
            "provider-version": "1.0.0",
            "test-case-id": ("credential-smoke",),
            "result": "passed",
            "output": str(output),
            "confirm": True,
        }
    ).payload

    loaded = attestations.load(output)
    assert loaded.object_digest == passport.artifact.digest
    assert loaded.subject.passport_digest == recorded.passport_digest
    assert result.attestation_digest == attestation_digest(loaded)
    assert attestations.verify(loaded, signer)
    if os.name != "nt":
        assert output.stat().st_mode & 0o077 == 0


def test_mutating_an_attestation_breaks_its_device_signature(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ai_stp_cli.commands import attestations

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("AI_STP_FORCE_FILE_CREDENTIAL_STORE", "1")
    signer, _warning = identity.load_or_create()
    vector = cast(
        dict[str, JsonValue],
        json.loads(Path("tests/golden/passports/author-attestation.json").read_text("utf-8")),
    )
    unsigned = AuthorAttestation.model_validate(vector["value"])
    signed = unsigned.model_copy(
        update={
            "device_id": signer.device_id,
            "signature": base64.b64encode(
                signer.sign(
                    attestation_digest(
                        unsigned.model_copy(update={"device_id": signer.device_id})
                    ).encode("utf-8")
                )
            ).decode(),
        }
    )

    assert attestations.verify(signed, signer)
    assert not attestations.verify(signed.model_copy(update={"result": "failed"}), signer)


def test_publication_accepts_only_a_valid_exact_attestation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ai_stp_cli.commands import publication

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("AI_STP_FORCE_FILE_CREDENTIAL_STORE", "1")
    signer, _warning = identity.load_or_create()
    held = session.Session(
        account_id=ACCOUNT,
        device_id=signer.device_id,
        access_token="bearer",
        refresh_token="refresh",
        expires_at="2099-01-01T00:00:00.000Z",
    )
    stable_id = "component_01ARZ3NDEKTSV4RRFFQ69G5FAV"
    object_digest = "sha256:" + "b" * 64
    passport_digest = "sha256:" + "c" * 64
    unsigned = AuthorAttestation(
        object_digest=object_digest,
        subject=ComponentRef(stable_id=stable_id, version="1.0", passport_digest=passport_digest),
        check_id="credentials",
        policy_version="1",
        tool_versions={"runner": "2"},
        harness_id="codex",
        harness_version="1.2.3",
        provider_version="1.0.0",
        test_case_ids=["credential-smoke"],
        result="passed",
        account_id=ACCOUNT,
        device_id=signer.device_id,
        attested_at="2026-08-13T00:00:00.000Z",
        signature="A" * 86 + "==",
    )
    signed = unsigned.model_copy(
        update={
            "signature": base64.b64encode(
                signer.sign(attestation_digest(unsigned).encode("utf-8"))
            ).decode()
        }
    )
    path = tmp_path / "attestation.json"
    path.write_text(signed.model_dump_json(), encoding="utf-8")
    monkeypatch.setattr(identity, "current", lambda: (signer, None))

    result = publication.validated_attestations(
        {"attestation-file": (str(path),)},
        stable_id=stable_id,
        version="1.0",
        content_digest=object_digest,
        passport_digest=passport_digest,
        held_session=held,
    )
    assert result[0].signature == signed.signature

    with pytest.raises(CliFailure) as changed:
        publication.validated_attestations(
            {"attestation-file": (str(path),)},
            stable_id=stable_id,
            version="1.0",
            content_digest="sha256:" + "d" * 64,
            passport_digest=passport_digest,
            held_session=held,
        )
    assert changed.value.code == "AI_STP_PRECONDITION_FAILED"

    with pytest.raises(CliFailure) as duplicate:
        publication.validated_attestations(
            {"attestation-file": (str(path), str(path))},
            stable_id=stable_id,
            version="1.0",
            content_digest=object_digest,
            passport_digest=passport_digest,
            held_session=held,
        )
    assert duplicate.value.code == "AI_STP_CONFLICT"


def test_load_rejects_symlinks_and_unknown_fields(tmp_path: Path) -> None:
    from ai_stp_cli.commands import attestations

    vector = json.loads(Path("tests/golden/passports/author-attestation.json").read_text("utf-8"))
    source = tmp_path / "record.json"
    source.write_text(json.dumps(vector["value"]), encoding="utf-8")
    link = tmp_path / "link.json"
    link.symlink_to(source)

    with pytest.raises(CliFailure) as symlink:
        attestations.load(link)
    assert symlink.value.code == "AI_STP_VALIDATION_ERROR"

    changed = dict(vector["value"])
    changed["credential"] = "must-not-be-representable"
    source.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(CliFailure) as unknown:
        attestations.load(source)
    assert unknown.value.code == "AI_STP_VALIDATION_ERROR"
