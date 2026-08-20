from datetime import UTC, datetime

import pytest

from ai_stp_api.slices.owner.service import can_start_publication


@pytest.mark.platform
def test_can_start_publication_unpublished_ready_version_is_allowed() -> None:
    assert can_start_publication(lifecycle="ready", published_at=None) is True


@pytest.mark.platform
def test_can_start_publication_published_active_version_is_denied() -> None:
    published_at = datetime.min.replace(tzinfo=UTC)

    assert can_start_publication(lifecycle="active", published_at=published_at) is False
