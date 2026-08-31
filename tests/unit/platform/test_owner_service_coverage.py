# pyright: reportUnknownLambdaType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnusedFunction=false, reportUnusedImport=false, reportUnusedVariable=false, reportPrivateUsage=false
"""Unit coverage for owner workspace service helpers and list/read paths."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from ai_stp_api.errors import ApiError
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.owner import service as owner_service
from ai_stp_contracts.owner import (
    COMPONENT_MEDIA_PUBLIC_PREFIX,
    OwnerPresentationMedia,
    OwnerPresentationUpdateRequest,
)

pytestmark = pytest.mark.platform


def _ctx(account_id: str = "account_test") -> AuthContext:
    return AuthContext(
        account_id=account_id,
        account_status="active",
        device_id="device_test",
        session_id="sess",
        is_admin=False,
        via_cookie=False,
    )


def test_ts_and_install_eligible_helpers() -> None:
    assert owner_service._ts(None) is None
    naive = datetime(2026, 1, 2, 3, 4, 5, 123456)
    stamped = owner_service._ts(naive)
    assert stamped is not None and stamped.endswith("Z")
    aware = datetime(2026, 1, 2, 3, 4, 5, 123456, tzinfo=UTC)
    assert owner_service._ts(aware) is not None
    assert owner_service._install_eligible(component_verified=True, lifecycle="active") is True
    assert owner_service._install_eligible(component_verified=True, lifecycle="blocked") is False
    assert owner_service._install_eligible(component_verified=False, lifecycle="active") is False
    assert owner_service.can_start_publication(lifecycle="ready", published_at=None) is True
    assert (
        owner_service.can_start_publication(lifecycle="active", published_at=datetime.now(tz=UTC))
        is False
    )


@pytest.mark.asyncio
async def test_require_owned_component_missing() -> None:
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=None)
    with pytest.raises(ApiError):
        await owner_service._require_owned_component(db, ctx=_ctx(), stable_id="component_missing")


@pytest.mark.asyncio
async def test_read_component_media_bytes_paths() -> None:
    db = AsyncMock()
    store = AsyncMock()
    db.get = AsyncMock(return_value=None)
    assert await owner_service.read_component_media_bytes(db, store, media_id="m1") is None

    row = SimpleNamespace(state="ready", object_key="k", content_type="image/png")
    db.get = AsyncMock(return_value=row)
    store.read_bytes = AsyncMock(return_value=None)
    assert await owner_service.read_component_media_bytes(db, store, media_id="m1") is None

    store.read_bytes = AsyncMock(return_value=b"img")
    got = await owner_service.read_component_media_bytes(db, store, media_id="m1")
    assert got == (b"img", "image/png")

    row2 = SimpleNamespace(state="pending", object_key="k", content_type=None)
    db.get = AsyncMock(return_value=row2)
    assert await owner_service.read_component_media_bytes(db, store, media_id="m2") is None


def _result_scalars(items: list[object]) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = items
    return result


@pytest.mark.asyncio
async def test_list_owner_objects_collapses_versions() -> None:
    older = SimpleNamespace(
        object_kind="component",
        stable_id="component_aaaa",
        version="1.0",
        name="A",
        visibility="public",
        lifecycle_state="active",
        trust_lane="authoritative",
        author_verified=True,
        component_verified=True,
        published_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
        id="1",
    )
    newer = SimpleNamespace(
        object_kind="component",
        stable_id="component_aaaa",
        version="1.1",
        name="A2",
        visibility="private",
        lifecycle_state="ready",
        trust_lane="experimental",
        author_verified=False,
        component_verified=False,
        published_at=datetime(2026, 2, 1, tzinfo=UTC),
        updated_at=datetime(2026, 2, 1, tzinfo=UTC),
        id="2",
    )
    other = SimpleNamespace(
        object_kind="setup",
        stable_id="setup_bbbbbbbb",
        version="2.0",
        name=None,
        visibility="public",
        lifecycle_state="active",
        trust_lane="authoritative",
        author_verified=True,
        component_verified=True,
        published_at=None,
        updated_at=datetime(2026, 3, 1, tzinfo=UTC),
        id="3",
    )
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_result_scalars([newer, older, other]))
    out = await owner_service.list_owner_objects(db, ctx=_ctx(), page_size=10)
    assert len(out.items) == 2
    assert out.items[0].stable_id == "component_aaaa"
    assert out.items[0].latest_version == "1.1"
    assert out.items[1].name == "setup_bbbbbbbb"

    db.execute = AsyncMock(return_value=_result_scalars([newer, older, other]))
    limited = await owner_service.list_owner_objects(
        db, ctx=_ctx(), object_kind="component", page_size=1
    )
    assert len(limited.items) == 1


@pytest.mark.asyncio
async def test_read_owner_presentation_with_media() -> None:
    version = SimpleNamespace(
        presentation_bio=None,
        passport_document={"description": "from passport"},
    )
    media = SimpleNamespace(
        kind="youtube",
        youtube_video_id="dQw4w9WgXcQ",
        public_url=None,
        alt="video alt",
        caption="c",
    )
    media2 = SimpleNamespace(
        kind="image",
        youtube_video_id=None,
        public_url="/v1/media/component/m1",
        alt="image alt",
        caption="",
    )
    db = AsyncMock()
    # first execute: versions; second: media
    db.execute = AsyncMock(
        side_effect=[_result_scalars([version]), _result_scalars([media, media2])]
    )
    out = await owner_service.read_owner_presentation(db, ctx=_ctx(), stable_id="component_x")
    assert out.bio == "from passport"
    assert len(out.media) == 2
    assert out.media[0].url == "dQw4w9WgXcQ"

    db.execute = AsyncMock(return_value=_result_scalars([]))
    with pytest.raises(ApiError):
        await owner_service.read_owner_presentation(db, ctx=_ctx(), stable_id="missing")


@pytest.mark.asyncio
async def test_upload_owner_component_media_validation() -> None:
    db = AsyncMock()
    store = AsyncMock()
    db.scalar = AsyncMock(return_value="owned")
    db.execute = AsyncMock(return_value=_result_scalars([0, 1, 2, 3, 4]))
    with pytest.raises(ApiError):
        await owner_service.upload_owner_component_media(
            db,
            store,
            ctx=_ctx(),
            stable_id="component_x",
            content_type="image/png",
            payload=b"x",
        )

    db.execute = AsyncMock(return_value=_result_scalars([]))
    with pytest.raises(ApiError):
        await owner_service.upload_owner_component_media(
            db,
            store,
            ctx=_ctx(),
            stable_id="component_x",
            content_type="image/png",
            payload=b"",
        )

    with pytest.raises(ApiError):
        await owner_service.upload_owner_component_media(
            db,
            store,
            ctx=_ctx(),
            stable_id="component_x",
            content_type="application/x-evil",
            payload=b"x" * 10,
        )

    store.put_avatar = AsyncMock(return_value=SimpleNamespace(size_bytes=3, object_key="obj/k"))
    db.add = MagicMock()
    db.flush = AsyncMock()
    # Need free position 0
    out = await owner_service.upload_owner_component_media(
        db,
        store,
        ctx=_ctx(),
        stable_id="component_x",
        content_type="image/png",
        payload=b"png",
    )
    assert out["state"] == "ready"
    assert out["kind"] in {"image", "png", "photo"} or "public_url" in out

    store.put_avatar = AsyncMock(side_effect=RuntimeError("s3 down"))
    with pytest.raises(ApiError):
        await owner_service.upload_owner_component_media(
            db,
            store,
            ctx=_ctx(),
            stable_id="component_x",
            content_type="image/png",
            payload=b"png",
        )


@pytest.mark.asyncio
async def test_update_owner_presentation_media_kinds() -> None:
    db = AsyncMock()
    db.scalar = AsyncMock(return_value="owned")
    existing = SimpleNamespace(
        id="media_upload1",
        owner_account_id="account_test",
        stable_id="component_x",
        source_type="upload",
        object_key="obj/1",
        kind="image",
        public_url=f"{COMPONENT_MEDIA_PUBLIC_PREFIX}media_upload1",
        content_type="image/png",
        size_bytes=10,
    )
    db.execute = AsyncMock(
        side_effect=[
            MagicMock(),  # update bio
            _result_scalars([existing]),  # existing media
            MagicMock(),  # delete
        ]
    )
    db.flush = AsyncMock()
    db.add = MagicMock()
    body = OwnerPresentationUpdateRequest(
        schema_version=1,
        bio="hello",
        media=[
            OwnerPresentationMedia(kind="youtube", url="dQw4w9WgXcQ", alt="a", caption="c"),
            OwnerPresentationMedia(
                kind="image",
                url=f"{COMPONENT_MEDIA_PUBLIC_PREFIX}media_upload1",
                alt="img",
                caption="",
            ),
            OwnerPresentationMedia(
                kind="image",
                url="https://raw.githubusercontent.com/x/y/main/a.png",
                alt="gh",
                caption="",
            ),
        ],
    )
    out = await owner_service.update_owner_presentation(
        db, ctx=_ctx(), stable_id="component_x", body=body
    )
    assert out.bio == "hello"
    assert len(out.media) == 3

    # unknown upload ref
    db.execute = AsyncMock(
        side_effect=[
            MagicMock(),
            _result_scalars([]),
        ]
    )
    bad = OwnerPresentationUpdateRequest(
        schema_version=1,
        bio="x",
        media=[
            OwnerPresentationMedia(
                kind="image",
                url=f"{COMPONENT_MEDIA_PUBLIC_PREFIX}missing",
                alt="missing",
                caption="",
            )
        ],
    )
    with pytest.raises(ApiError):
        await owner_service.update_owner_presentation(
            db, ctx=_ctx(), stable_id="component_x", body=bad
        )


@pytest.mark.asyncio
async def test_read_owner_object_and_version_and_start() -> None:

    row = SimpleNamespace(
        name="N",
        version="1.0",
        passport_digest="sha256:" + "a" * 64,
        lifecycle_state="ready",
        visibility="public",
        trust_lane="authoritative",
        author_verified=True,
        component_verified=True,
        published_at=None,
        passport_document={
            "description": "desc " * 10,
            "artifact": {"digest": "sha256:" + "b" * 64},
        },
    )
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_result_scalars([row, SimpleNamespace(version=None)]))
    detail = await owner_service.read_owner_object(
        db, ctx=_ctx(), object_kind="component", stable_id="component_zzzz"
    )
    assert detail.versions
    assert detail.versions[0].can_start_publication is True

    db.execute = AsyncMock(return_value=_result_scalars([]))
    with pytest.raises(ApiError):
        await owner_service.read_owner_object(
            db, ctx=_ctx(), object_kind="component", stable_id="component_zzzz"
        )

    plan = SimpleNamespace(
        id="plan_1",
        state="validating",
        created_at=datetime.now(tz=UTC),
    )
    snapshot = SimpleNamespace(id="snap_1")
    binding = SimpleNamespace(
        check_id="path_denylist",
        result="passed",
        source="platform_safety_scan",
        expires_at=datetime.now(tz=UTC),
    )
    db.scalar = AsyncMock(side_effect=[row, plan, snapshot])
    db.execute = AsyncMock(return_value=_result_scalars([binding]))
    ver = await owner_service.read_owner_version(
        db,
        ctx=_ctx(),
        object_kind="component",
        stable_id="component_zzzz",
        version="1.0",
    )
    assert ver.open_publication_plan_id == "plan_1"
    assert ver.evidence
    assert ver.description.startswith("desc")

    db.scalar = AsyncMock(return_value=None)
    with pytest.raises(ApiError):
        await owner_service.read_owner_version(
            db,
            ctx=_ctx(),
            object_kind="component",
            stable_id="component_zzzz",
            version="9.9",
        )

    db.scalar = AsyncMock(return_value=row)
    monkey_create = AsyncMock(return_value=SimpleNamespace(plan_id="plan_new"))
    import ai_stp_api.slices.publish.service as publish_service

    original = publish_service.create_plan
    publish_service.create_plan = monkey_create  # type: ignore[method-assign]
    body2 = MagicMock()
    body2.policy_version = "safety-1"
    body2.idempotency_key = "idem_01" + "0" * 20
    body2.device_id = "device_01" + "0" * 24
    try:
        await owner_service.start_publication(
            db,
            ctx=_ctx(),
            object_kind="component",
            stable_id="component_zzzz",
            version="1.0",
            body=body2,
        )
        monkey_create.assert_awaited()

        bare = SimpleNamespace(passport_digest=None, passport_document={})
        db.scalar = AsyncMock(return_value=bare)
        with pytest.raises(ApiError):
            await owner_service.start_publication(
                db,
                ctx=_ctx(),
                object_kind="component",
                stable_id="component_zzzz",
                version="1.0",
                body=body2,
            )

        art = SimpleNamespace(
            passport_digest=None,
            passport_document={"artifact": {"digest": "sha256:" + "c" * 64}},
        )
        db.scalar = AsyncMock(return_value=art)
        await owner_service.start_publication(
            db,
            ctx=_ctx(),
            object_kind="component",
            stable_id="component_zzzz",
            version="1.0",
            body=body2,
        )

        db.scalar = AsyncMock(return_value=None)
        with pytest.raises(ApiError):
            await owner_service.start_publication(
                db,
                ctx=_ctx(),
                object_kind="component",
                stable_id="component_zzzz",
                version="1.0",
                body=body2,
            )
    finally:
        publish_service.create_plan = original  # type: ignore[method-assign]
