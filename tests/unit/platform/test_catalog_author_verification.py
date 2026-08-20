from dataclasses import replace
from datetime import UTC, datetime

from ai_stp_platform.catalog_read import PublicVersionRow, with_current_author_verification
from ai_stp_platform.models import CatalogMetadata


def test_current_author_verification_overrides_publication_snapshot() -> None:
    metadata = CatalogMetadata(owner_account_id="account_current")
    row = PublicVersionRow(
        metadata=metadata,
        passport={},
        passport_digest="sha256:" + "0" * 64,
        published_at=datetime(2026, 1, 1, tzinfo=UTC),
        trust_lane="experimental",
        author_verified=False,
        component_verified=False,
        lifecycle="active",
        stable_id="component_test",
        version="1.0",
        object_kind="component",
    )

    verified = with_current_author_verification([row], {metadata.owner_account_id: True})

    assert verified == [replace(row, author_verified=True)]
