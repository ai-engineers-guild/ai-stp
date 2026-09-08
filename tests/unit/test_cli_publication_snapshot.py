"""Publication bind seals artifact bytes and leaves historical visibility alone."""

from typing import cast

import pytest

from ai_stp_cli.local import components, publication_snapshot
from ai_stp_contracts.first_party import versions as first_party_versions
from ai_stp_foundation.canonical import JsonValue
from ai_stp_passports import ComponentVersionPassport
from ai_stp_passports.envelope import derive_revision_id

pytestmark = pytest.mark.cli


def _passport() -> ComponentVersionPassport:
    return next(
        item.passport
        for item in first_party_versions()
        if isinstance(item.passport, ComponentVersionPassport)
    )


def test_bind_does_not_rewrite_visibility_or_revision_when_bytes_match() -> None:
    passport = _passport()
    bound = publication_snapshot.bind(
        passport,
        visibility="public" if passport.visibility == "private" else "private",
        digest=passport.artifact.digest,
        size_bytes=passport.artifact.size_bytes,
    )
    assert bound is passport


def test_bind_seals_new_artifact_bytes_without_changing_visibility() -> None:
    passport = _passport()
    digest = "sha256:" + "ab" * 32
    bound = publication_snapshot.bind(
        passport,
        visibility="public",
        digest=digest,
        size_bytes=12,
    )
    document = bound.model_dump(mode="json")
    assert bound.visibility == passport.visibility
    assert bound.artifact.digest == digest
    assert bound.artifact.size_bytes == 12
    assert document.get("artifact_format") == components.COMPONENT_TREE_FORMAT
    assert bound.revision_id == derive_revision_id(cast(dict[str, JsonValue], document))
