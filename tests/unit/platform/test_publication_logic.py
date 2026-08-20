"""Unit tests for publication plan hashing and validation barrier."""

from __future__ import annotations

import base64

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from ai_stp_assurance import AuthorAttestation, attestation_digest
from ai_stp_foundation.ids import new_id
from ai_stp_platform.publication_logic import (
    AttestationBindingContext,
    bind_author_attestations,
    compute_plan_hash,
    run_platform_checks,
    snapshot_outcome,
    validate_passport_completeness,
    validate_publication_passport,
)

pytestmark = pytest.mark.platform


def _passport(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "name": "demo-skill",
        "version": "1.0",
        "tags": ["review"],
        "license": {"spdx_id": "MIT"},
        "source": {
            "repository": "https://github.com/example/demo",
            "commit": "a" * 40,
            "path": "skills/demo",
        },
        "artifact": {
            "digest": "sha256:" + "b" * 64,
            "size_bytes": 12,
        },
    }
    base.update(overrides)
    return base


def test_plan_hash_stable_and_sensitive_to_digest() -> None:
    a = compute_plan_hash(
        actor_account_id="account_1",
        device_id="device_1",
        object_kind="component",
        stable_id="component_1",
        version="1.0",
        content_digest="sha256:" + "b" * 64,
        policy_version="1",
        passport=_passport(),
        attestations=[],
    )
    b = compute_plan_hash(
        actor_account_id="account_1",
        device_id="device_1",
        object_kind="component",
        stable_id="component_1",
        version="1.0",
        content_digest="sha256:" + "b" * 64,
        policy_version="1",
        passport=_passport(),
        attestations=[],
    )
    c = compute_plan_hash(
        actor_account_id="account_1",
        device_id="device_1",
        object_kind="component",
        stable_id="component_1",
        version="1.0",
        content_digest="sha256:" + "c" * 64,
        policy_version="1",
        passport=_passport(),
        attestations=[],
    )
    assert a == b
    assert a != c
    assert a.startswith("plan_")


def test_passport_completeness_and_platform_checks() -> None:
    good = _passport()
    assert validate_passport_completeness(good) == []
    bindings = run_platform_checks(passport=good, content_digest="sha256:" + "b" * 64)
    assert all(b["result"] == "passed" for b in bindings)
    state, verified = snapshot_outcome(bindings)
    assert state == "passed"
    assert verified is True


def test_missing_mandatory_blocks() -> None:
    bad = _passport()
    del bad["license"]
    bindings = run_platform_checks(passport=bad, content_digest="sha256:" + "b" * 64)
    state, verified = snapshot_outcome(bindings)
    assert state == "failed"
    assert verified is False


def test_author_attestation_rejects_secret_keys() -> None:
    private = Ed25519PrivateKey.generate()
    public_key = base64.b64encode(
        private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    ).decode("ascii")
    account_id = new_id("account")
    device_id = new_id("device")
    component_id = new_id("component")
    digest = "sha256:" + "b" * 64
    unsigned = AuthorAttestation.model_validate(
        {
            "object_digest": digest,
            "subject": {
                "stable_id": component_id,
                "version": "1.0",
                "passport_digest": "sha256:" + "c" * 64,
            },
            "check_id": "credentials",
            "policy_version": "1",
            "tool_versions": {"secret_token": "1"},
            "harness_id": "claude-code",
            "harness_version": "1.0",
            "provider_version": "1.0",
            "test_case_ids": ["cred-basic"],
            "result": "passed",
            "account_id": account_id,
            "device_id": device_id,
            "attested_at": "2026-08-15T00:00:00.000Z",
            "signature": base64.b64encode(b"\x00" * 64).decode("ascii"),
        }
    )
    signed = unsigned.model_copy(
        update={
            "signature": base64.b64encode(
                private.sign(attestation_digest(unsigned).encode("utf-8"))
            ).decode("ascii")
        }
    )
    bound = bind_author_attestations(
        [signed.model_dump(mode="json")],
        context=AttestationBindingContext(
            content_digest=digest,
            policy_version="1",
            account_id=account_id,
            device_id=device_id,
            subject_stable_id=component_id,
            subject_version="1.0",
            passport_digest="sha256:" + "c" * 64,
            public_key=public_key,
            device_revoked=False,
        ),
    )
    assert bound == []


def test_inspect_publication_artifact_rejects_traversal_and_symlink() -> None:
    import io
    import zipfile

    from ai_stp_platform.artifact_bind import ArtifactBindError, inspect_publication_artifact

    inspect_publication_artifact(b"plain-bytes")

    traversal = io.BytesIO()
    with zipfile.ZipFile(traversal, "w") as archive:
        archive.writestr("../escape.txt", "no")
    with pytest.raises(ArtifactBindError, match="escapes"):
        inspect_publication_artifact(traversal.getvalue())

    linked = io.BytesIO()
    with zipfile.ZipFile(linked, "w") as archive:
        info = zipfile.ZipInfo("link")
        info.external_attr = 0xA000 << 16
        archive.writestr(info, "target")
    with pytest.raises(ArtifactBindError, match="special"):
        inspect_publication_artifact(linked.getvalue())


@pytest.mark.asyncio
async def test_bind_plan_artifact_rejects_digest_mismatch() -> None:
    from ai_stp_foundation.digests import digest_bytes
    from ai_stp_platform.artifact_bind import bind_plan_artifact
    from ai_stp_platform.settings import StorageSettings
    from ai_stp_platform.storage.memory import MemoryObjectClient
    from ai_stp_platform.storage.object_store import (
        ARTIFACT_DIGEST_DOMAIN,
        ImmutableObjectStore,
        ObjectIntegrityError,
    )

    payload = b"artifact-bytes"
    digest = digest_bytes(ARTIFACT_DIGEST_DOMAIN, payload)
    store = ImmutableObjectStore(
        settings=StorageSettings(
            endpoint="http://memory.test",
            bucket="test",
            access_key_id="test",
            secret_access_key="test",
        ),
        client=MemoryObjectClient(),
    )
    stored = await bind_plan_artifact(
        store=store,
        payload=payload,
        expected_digest=digest,
        expected_size=len(payload),
    )
    assert stored.digest == digest
    with pytest.raises(ObjectIntegrityError):
        await bind_plan_artifact(
            store=store,
            payload=payload,
            expected_digest="sha256:" + "0" * 64,
            expected_size=len(payload),
        )


@pytest.mark.asyncio
async def test_confirm_refuses_until_bytes_are_durable() -> None:
    from ai_stp_platform.artifact_bind import plan_artifact_is_durable
    from ai_stp_platform.settings import StorageSettings
    from ai_stp_platform.storage.memory import MemoryObjectClient
    from ai_stp_platform.storage.object_store import ImmutableObjectStore

    store = ImmutableObjectStore(
        settings=StorageSettings(
            endpoint="http://memory.test",
            bucket="test",
            access_key_id="test",
            secret_access_key="test",
        ),
        client=MemoryObjectClient(),
    )
    assert not await plan_artifact_is_durable(
        store=store,
        content_digest="sha256:" + "0" * 64,
        expected_size=1,
    )


def test_passport_completeness_flags_non_object_source_and_license() -> None:
    # Breakage: non-object source/license accepted as complete for publication.
    incomplete = _passport(source="not-a-map", license="MIT", tags=[])
    missing = validate_passport_completeness(incomplete)
    assert "source" in missing
    assert "license" in missing
    assert "tags" in missing


def test_validate_publication_passport_rejects_field_mismatches() -> None:
    # Breakage: catalog accepts a passport whose identity axes diverge from the plan.
    from ai_stp_passports.envelope import derive_revision_id

    digest = "sha256:" + "b" * 64
    account = "account_01ARZ3NDEKTSV4RRFFQ69G5FAV"
    component = "component_01ARZ3NDEKTSV4RRFFQ69G5FAV"
    passport: dict[str, object] = {
        "schema_version": 1,
        "kind": "component",
        "stable_id": component,
        "revision_id": "revision_" + "0" * 64,
        "parent_revision_ids": [],
        "owner_id": account,
        "created_at": "2026-08-10T00:00:00.000Z",
        "visibility": "public",
        "facts": {},
        "name": "demo",
        "description": "Demo component.",
        "version": "1.0",
        "license": {"spdx_id": "MIT", "redistribution_allowed": True},
        "tags": ["test"],
        "source": {
            "repository": "https://example.test/repo",
            "commit": "a" * 40,
            "path": ".",
        },
        "artifact": {"digest": digest, "size_bytes": 1},
        "harness_id": "claude-code",
        "component_type": "skill",
        "projection_kind": "native_files",
        "conflicts": {
            "paths": [],
            "commands": [],
            "hooks": [],
            "mcp": [],
            "agents": [],
            "plugins": [],
        },
    }
    passport["revision_id"] = derive_revision_id(passport)  # type: ignore[arg-type]

    model, invalid = validate_publication_passport(
        passport,
        object_kind="component",
        stable_id=component,
        version="9.9",
        content_digest="sha256:" + "c" * 64,
        owner_account_id="account_other",
    )
    assert model is None
    assert "version" in invalid
    assert "artifact.digest" in invalid
    assert "owner_id" in invalid
