"""Projection bytes are an exact, deterministic closure of one scope atom."""

import io
import zipfile

import pytest

import ai_stp_passports.projections as projections
from ai_stp_foundation.digests import digest_bytes
from ai_stp_passports.projections import (
    ProjectionArtifactError,
    build_projection,
    verify_projection,
)
from ai_stp_passports.versions import ScopeAdaptation

_DIGEST = "sha256:" + "1" * 64
_CONTENT = b"review\n"
_CONTENT_DIGEST = digest_bytes("ai-stp:artifact:v1", _CONTENT)


def _scope(*, digest: str = _DIGEST, size: int = 1) -> ScopeAdaptation:
    return ScopeAdaptation.model_validate(
        {
            "scope": "project",
            "projection_format": "ai-stp-adaptation-projection/1",
            "projection_artifact": {"digest": digest, "size_bytes": size},
            "provider_component_kind": "agent",
            "projection_kind": "native_files",
            "required_surface": {
                "profile_id": "cursor/native-files/project/1",
                "profile_digest": _DIGEST,
                "bundle_format": "ai-stp-bundle/1",
            },
            "members": [
                {
                    "path": ".cursor/agents",
                    "object_type": "directory",
                    "mode": 493,
                    "native_ids": [],
                    "content_format": "directory",
                    "ownership": "whole",
                    "write_semantics": "replace",
                    "withdrawal_semantics": "remove_path",
                },
                {
                    "path": ".cursor/agents/reviewer.md",
                    "object_type": "file",
                    "mode": 420,
                    "content_artifact": {
                        "digest": _CONTENT_DIGEST,
                        "size_bytes": len(_CONTENT),
                    },
                    "native_ids": ["reviewer"],
                    "content_format": "text/markdown",
                    "ownership": "whole",
                    "write_semantics": "replace",
                    "withdrawal_semantics": "remove_path",
                },
            ],
            "technical_support": "supported",
        }
    )


def _sealed(payload: bytes) -> ScopeAdaptation:
    return _scope(digest=digest_bytes("ai-stp:artifact:v1", payload), size=len(payload))


def test_projection_archive_is_deterministic_and_verifies_exact_bytes() -> None:
    provisional = _scope()
    first = build_projection(provisional, {".cursor/agents/reviewer.md": _CONTENT})
    second = build_projection(provisional, {".cursor/agents/reviewer.md": _CONTENT})

    assert first == second
    verify_projection(_sealed(first), first)


def test_projection_builder_requires_exact_file_closure() -> None:
    with pytest.raises(ProjectionArtifactError, match="differ"):
        build_projection(_scope(), {})
    with pytest.raises(ProjectionArtifactError, match="differ"):
        build_projection(
            _scope(),
            {".cursor/agents/reviewer.md": b"ok", "undeclared": b"no"},
        )


@pytest.mark.parametrize("mutation", ["bytes", "mode", "extra", "compression"])
def test_projection_verifier_rejects_every_archive_boundary_mutation(mutation: str) -> None:
    original = build_projection(_scope(), {".cursor/agents/reviewer.md": _CONTENT})
    source = zipfile.ZipFile(io.BytesIO(original))
    output = io.BytesIO()
    compression = zipfile.ZIP_DEFLATED if mutation == "compression" else zipfile.ZIP_STORED
    with source, zipfile.ZipFile(output, "w", compression=compression) as target:
        for held in source.infolist():
            info = zipfile.ZipInfo(held.filename, date_time=held.date_time)
            info.create_system = held.create_system
            info.compress_type = compression
            info.external_attr = held.external_attr
            if mutation == "mode" and held.filename.endswith("reviewer.md"):
                info.external_attr = (0o100755) << 16
            content = source.read(held)
            if mutation == "bytes" and held.filename.endswith("reviewer.md"):
                content = b"changed\n"
            target.writestr(info, content)
        if mutation == "extra":
            target.writestr("extra", b"no")
    mutated = output.getvalue()

    with pytest.raises(ProjectionArtifactError):
        verify_projection(_sealed(mutated), mutated)


def test_projection_verifier_checks_passport_size_and_digest_before_opening() -> None:
    payload = build_projection(_scope(), {".cursor/agents/reviewer.md": _CONTENT})
    with pytest.raises(ProjectionArtifactError, match="size"):
        verify_projection(
            _scope(digest=digest_bytes("ai-stp:artifact:v1", payload), size=1), payload
        )
    with pytest.raises(ProjectionArtifactError, match="digest"):
        verify_projection(_scope(size=len(payload)), payload)


def test_projection_verifier_refuses_bytes_before_opening_an_oversized_archive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = build_projection(_scope(), {".cursor/agents/reviewer.md": _CONTENT})
    monkeypatch.setattr(projections, "MAX_PROJECTION_BYTES", len(payload) - 1)

    with pytest.raises(ProjectionArtifactError, match="consumer byte limit"):
        verify_projection(_sealed(payload), payload)
