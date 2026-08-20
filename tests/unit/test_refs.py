"""Exact references: typed IDs, canonical versions, digests, no setup variant."""

import pytest
from pydantic import ValidationError

from ai_stp_foundation import ComponentRef, SetupRef, digest_canonical, new_id

DIGEST = digest_canonical("ai-stp:passport:v1", {"fixture": True})


def test_component_ref_accepts_optional_variant() -> None:
    ref = ComponentRef(
        stable_id=new_id("component"),
        variant_id=new_id("variant"),
        version="1.2",
        passport_digest=DIGEST,
    )
    assert ref.variant_id is not None


def test_setup_ref_has_no_variant_axis() -> None:
    with pytest.raises(ValidationError):
        SetupRef.model_validate(
            {
                "stable_id": new_id("setup"),
                "variant_id": new_id("variant"),
                "version": "1.0",
                "passport_digest": DIGEST,
            }
        )


def test_wrong_id_kind_is_rejected() -> None:
    with pytest.raises(ValidationError):
        SetupRef(stable_id=new_id("component"), version="1.0", passport_digest=DIGEST)


@pytest.mark.parametrize("bad_version", ["1", "01.2", "latest", "1.2.3"])
def test_floating_versions_are_not_representable(bad_version: str) -> None:
    with pytest.raises(ValidationError):
        ComponentRef(stable_id=new_id("component"), version=bad_version, passport_digest=DIGEST)


def test_malformed_digest_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ComponentRef(stable_id=new_id("component"), version="1.0", passport_digest="sha256:xyz")


def test_refs_are_frozen() -> None:
    ref = SetupRef(stable_id=new_id("setup"), version="1.0", passport_digest=DIGEST)
    with pytest.raises(ValidationError):
        ref.version = "1.1"  # type: ignore[misc]
