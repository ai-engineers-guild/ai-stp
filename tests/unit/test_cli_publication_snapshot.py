"""Publication bind seals artifact bytes and leaves historical visibility alone."""

import pytest

from ai_stp_cli.local import publication_snapshot
from ai_stp_contracts.first_party import versions as first_party_versions
from ai_stp_passports import ComponentVersionPassport

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


def test_bind_refuses_new_bytes_under_the_same_released_identity() -> None:
    from ai_stp_cli.errors import CliFailure

    passport = _passport()
    with pytest.raises(CliFailure) as refused:
        publication_snapshot.bind(
            passport, visibility="public", digest="sha256:" + "ab" * 32, size_bytes=12
        )
    assert refused.value.code == "AI_STP_PLAN_STALE"
