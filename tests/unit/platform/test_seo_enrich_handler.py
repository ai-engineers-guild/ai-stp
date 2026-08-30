"""Optional seo_enrich handler (SPEC-053 REQ-5320 to REQ-5325)."""

from __future__ import annotations

from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_platform.seo.settings import SeoSettings
from ai_stp_worker.handlers.seo_enrich import handle_seo_enrich

pytestmark = pytest.mark.platform


class _ForbiddenSession:
    async def get(self, *_args: object, **_kwargs: object) -> None:
        raise AssertionError("disabled enrichment must not load snapshots")

    async def execute(self, *_args: object, **_kwargs: object) -> None:
        raise AssertionError("disabled enrichment must not query")


@pytest.mark.asyncio
async def test_disabled_enrichment_is_a_noop() -> None:
    async def fetch(**_kwargs: object) -> dict[str, object]:
        raise AssertionError("disabled enrichment must not call LiteLLM")

    await handle_seo_enrich(
        cast(AsyncSession, _ForbiddenSession()),
        {
            "subject_kind": "article",
            "subject_id": "article:safe-setup",
            "locale": "en",
            "snapshot_id": "sha256:" + "b" * 64,
            "source_digest": "sha256:" + "b" * 64,
        },
        settings=SeoSettings(
            enrichment_enabled=False, enrichment_url="http://litellm:4000/v1/chat/completions"
        ),
        fetch=fetch,
    )


def test_request_targets_configured_alias_not_upstream_routing() -> None:
    from ai_stp_platform.seo.enrich import request_body

    body = request_body(snapshot={"name": "Demo"}, model_alias="seo-writer")
    assert body["model"] == "seo-writer"
    assert "cliproxy" not in str(body).lower()
    assert "openai.com" not in str(body).lower()
