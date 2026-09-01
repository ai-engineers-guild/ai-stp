"""Official upstream source, enqueue, and publication (SPEC-056)."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import tarfile
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import cast
from urllib.parse import urlsplit

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_platform.models import (
    Account,
    AccountAuthorVerification,
    AuditEvent,
    CatalogMetadata,
    OfficialUpstreamSource,
    OfficialUpstreamSync,
    PublicationPlan,
    PublicProfile,
)
from ai_stp_platform.official_upstream import OFFICIAL_ACCOUNT_ID, SOURCE_ID
from ai_stp_platform.official_upstream.artifact import COMPONENT_TREE_FORMAT
from ai_stp_platform.official_upstream.enqueue import enqueue_daily
from ai_stp_platform.official_upstream.errors import (
    CHANGED_REPOSITORY_IDENTITY,
    OfficialUpstreamError,
)
from ai_stp_platform.official_upstream.github import GithubHttpResponse
from ai_stp_platform.official_upstream.source import (
    SourceUpsert,
    delete_source,
    disable_source,
    upsert_source,
)
from ai_stp_platform.official_upstream.sync import run_sync
from ai_stp_platform.publication_logic import execute_publish, execute_validate
from ai_stp_platform.queue.models import Job
from ai_stp_platform.queue.states import JobType
from ai_stp_platform.seed_cli import ensure_official_publisher
from ai_stp_platform.settings import StorageSettings
from ai_stp_platform.storage import ImmutableObjectStore, MemoryObjectClient
from ai_stp_sources.catalog_match import CatalogMatchInput, suggest_catalog_replacement
from ai_stp_worker.handlers.official_upstream import handle_official_upstream_sync

pytestmark = pytest.mark.platform

COMMIT = "a" * 40


@pytest.mark.asyncio
async def test_serving_seed_bootstraps_verified_official_profile(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with db_sessionmaker() as session, session.begin():
        assert await ensure_official_publisher(session) is True
        assert await ensure_official_publisher(session) is False
        account = await session.get(Account, OFFICIAL_ACCOUNT_ID)
        profile = await session.get(PublicProfile, OFFICIAL_ACCOUNT_ID)
        verification = await session.get(AccountAuthorVerification, OFFICIAL_ACCOUNT_ID)
        assert account is not None and account.show_profile_publicly
        assert account.allow_publisher_listing
        assert profile is not None and profile.published_revision_id
        assert verification is not None and verification.verified


def _command(**overrides: object) -> SourceUpsert:
    payload: dict[str, object] = {
        "repository_url": "https://github.com/acme/tool",
        "tracked_ref": "main",
        "component_subpath": "skills/demo",
        "component_type": "skill",
        "owner_account_id": OFFICIAL_ACCOUNT_ID,
        "name": "Demo Skill",
        "upstream_project_name": "Demo",
        "upstream_maintainer": "Acme Maintainers",
        "reviewed_description": "Reviewed component body.",
        "reviewed_license": "MIT",
        "harness_id": "claude-code",
        "tags": ("code-review",),
    }
    payload.update(overrides)
    return SourceUpsert(**payload)  # type: ignore[arg-type]


def _tar(body: str, *, name: str = "skills/demo/SKILL.md") -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        payload = body.encode("utf-8")
        info = tarfile.TarInfo("tool-aaaaaaaa/" + name)
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


def _fetch(archive: bytes, *, repo_id: int = 42, sha: str = COMMIT):
    async def fetch(url: str, *, headers: dict[str, str]) -> GithubHttpResponse:
        del headers
        path = urlsplit(url).path
        if (
            path.endswith("/repos/acme/tool")
            and "/commits/" not in path
            and "/tarball/" not in path
        ):
            return GithubHttpResponse(
                200,
                json.dumps(
                    {"id": repo_id, "private": False, "license": {"spdx_id": "MIT"}}
                ).encode(),
                {},
                url,
            )
        if "/commits/" in path:
            return GithubHttpResponse(200, json.dumps({"sha": sha}).encode(), {}, url)
        return GithubHttpResponse(200, archive, {}, url)

    return fetch


def _store() -> ImmutableObjectStore:
    return ImmutableObjectStore(
        settings=StorageSettings(
            endpoint="http://memory.test",
            bucket="test",
            access_key_id="test",
            secret_access_key="test",
        ),
        client=MemoryObjectClient(),
    )


async def _owner(session: AsyncSession) -> None:
    if await session.get(Account, OFFICIAL_ACCOUNT_ID) is None:
        session.add(Account(id=OFFICIAL_ACCOUNT_ID))
        await session.flush()


@pytest.mark.asyncio
async def test_upsert_is_idempotent_and_audited(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with db_sessionmaker() as session, session.begin():
        await _owner(session)
        first = await upsert_source(session, _command())
        second = await upsert_source(session, _command(tracked_ref="main"))
        assert first.id == SOURCE_ID
        assert second.id == SOURCE_ID
        assert first.stable_id == second.stable_id
        count = (
            await session.execute(select(func.count()).select_from(OfficialUpstreamSource))
        ).scalar_one()
        assert count == 1
        audits = list((await session.scalars(select(AuditEvent))).all())
        assert {item.action for item in audits} >= {"official_upstream.source_upserted"}


@pytest.mark.asyncio
async def test_scheduler_enqueues_one_job_per_utc_day(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
    async with db_sessionmaker() as session, session.begin():
        await _owner(session)
        await upsert_source(session, _command())
        first = await enqueue_daily(session, now=now)
        second = await enqueue_daily(session, now=now + timedelta(hours=3))
        next_day = await enqueue_daily(session, now=now + timedelta(days=1))
        assert first and second and next_day
        assert first[0].id == second[0].id
        assert next_day[0].id != first[0].id
        assert first[0].payload == {"source_id": SOURCE_ID}
        assert next_day[0].payload == {"source_id": SOURCE_ID}
        assert first[0].job_type == JobType.OFFICIAL_UPSTREAM_SYNC
        jobs = list((await session.scalars(select(Job))).all())
        assert len(jobs) == 2


@pytest.mark.asyncio
async def test_sync_noop_then_publish_once_and_redelivery_is_idempotent(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    store = _store()
    archive = _tar("# Demo\n")
    fetch = _fetch(archive)
    now = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)
    async with db_sessionmaker() as session, session.begin():
        await _owner(session)
        await upsert_source(session, _command())
        result = await run_sync(session, SOURCE_ID, fetch=fetch, store=store, now=now)
        assert result == "publication_started"
        plan = (await session.scalars(select(PublicationPlan))).first()
        assert plan is not None
        validate = (
            await session.scalars(select(Job).where(Job.job_type == JobType.VALIDATE))
        ).first()
        assert validate is not None
        assert validate.payload == {"plan_id": plan.id}
        await execute_validate(session, plan_id=plan.id, object_store=store, skip_safety=True)
        published = await execute_publish(session, plan_id=plan.id, store=store)
        assert published.version == "1.0"
        assert published.owner_account_id == OFFICIAL_ACCOUNT_ID
        passport = dict(published.passport_document or {})
        assert passport.get("artifact_format") == COMPONENT_TREE_FORMAT
        assert str(passport.get("description", "")).startswith(
            "Demo is maintained by Acme Maintainers at https://github.com/acme/tool under MIT."
        )
        assert "does not claim upstream authorship" in str(passport.get("description"))
        source_raw = passport.get("source")
        assert isinstance(source_raw, dict)
        source_map = cast(dict[str, object], source_raw)
        assert source_map.get("commit") == COMMIT
        await handle_official_upstream_sync(
            session, {"source_id": SOURCE_ID}, fetch=fetch, store=store, now=now
        )
        versions = list((await session.scalars(select(CatalogMetadata))).all())
        assert len(versions) == 1
        plans = list((await session.scalars(select(PublicationPlan))).all())
        assert len(plans) == 1
        legacy_passport = dict(published.passport_document or {})
        legacy_passport.pop("artifact_format", None)
        published.passport_document = legacy_passport
        await session.flush()
        repaired = await run_sync(
            session, SOURCE_ID, fetch=fetch, store=store, now=now + timedelta(days=1)
        )
        assert repaired == "publication_started"
        repair_plan = (
            await session.scalars(select(PublicationPlan).where(PublicationPlan.version == "1.1"))
        ).one()
        await execute_validate(
            session, plan_id=repair_plan.id, object_store=store, skip_safety=True
        )
        repaired_metadata = await execute_publish(session, plan_id=repair_plan.id, store=store)
        assert repaired_metadata.version == "1.1"
        assert (
            dict(repaired_metadata.passport_document or {}).get("artifact_format")
            == COMPONENT_TREE_FORMAT
        )
        changed = _fetch(_tar("# Demo changed\n"))
        started = await run_sync(
            session, SOURCE_ID, fetch=changed, store=store, now=now + timedelta(days=2)
        )
        assert started == "publication_started"
        second_plan = (
            await session.scalars(select(PublicationPlan).where(PublicationPlan.version == "1.2"))
        ).first()
        assert second_plan is not None
        await execute_validate(
            session, plan_id=second_plan.id, object_store=store, skip_safety=True
        )
        second = await execute_publish(session, plan_id=second_plan.id, store=store)
        assert second.version == "1.2"
        first_read = await session.get(CatalogMetadata, published.id)
        assert first_read is not None
        assert first_read.version == "1.0"


@pytest.mark.asyncio
async def test_failure_and_disable_preserve_history(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    store = _store()
    now = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)
    async with db_sessionmaker() as session, session.begin():
        await _owner(session)
        await upsert_source(session, _command())
        await run_sync(session, SOURCE_ID, fetch=_fetch(_tar("# Demo\n")), store=store, now=now)
        plan = (await session.scalars(select(PublicationPlan))).one()
        await execute_validate(session, plan_id=plan.id, object_store=store, skip_safety=True)
        published = await execute_publish(session, plan_id=plan.id, store=store)
        with pytest.raises(OfficialUpstreamError) as raised:
            await run_sync(
                session,
                SOURCE_ID,
                fetch=_fetch(_tar("# Demo\n"), repo_id=99),
                store=store,
                now=now + timedelta(days=1),
            )
        assert raised.value.code == CHANGED_REPOSITORY_IDENTITY
        still = await session.get(CatalogMetadata, published.id)
        assert still is not None
        assert still.version == "1.0"
        failed = (
            await session.scalars(
                select(OfficialUpstreamSync).where(OfficialUpstreamSync.result == "failed")
            )
        ).first()
        assert failed is not None
        await disable_source(session)
        skipped = await enqueue_daily(session, now=now + timedelta(days=2))
        assert skipped == []
        await delete_source(session)
        assert await session.get(OfficialUpstreamSource, SOURCE_ID) is None
        remaining = await session.get(CatalogMetadata, published.id)
        assert remaining is not None
        session.expire_all()
        history = list((await session.scalars(select(OfficialUpstreamSync))).all())
        assert history
        assert all(row.source_id == SOURCE_ID for row in history)
        assert {row.result for row in history} >= {"publication_started", "failed"}
        audits = list((await session.scalars(select(AuditEvent))).all())
        assert "official_upstream.source_deleted" in {item.action for item in audits}
        later = await enqueue_daily(session, now=now + timedelta(days=3))
        assert later == []


def _sri_sha512(payload: bytes) -> str:
    digest = base64.b64encode(hashlib.sha512(payload).digest()).decode("ascii")
    return f"sha512-{digest}"


def _git_fetch(
    archive: bytes, *, owner: str = "acme", name: str = "tool", repo_id: int = 42, sha: str = COMMIT
):
    async def fetch(url: str, *, headers: dict[str, str]) -> GithubHttpResponse:
        del headers
        path = urlsplit(url).path
        repo = f"/repos/{owner}/{name}"
        if path.endswith(repo) and "/commits/" not in path and "/tarball/" not in path:
            return GithubHttpResponse(
                200,
                json.dumps(
                    {"id": repo_id, "private": False, "license": {"spdx_id": "MIT"}}
                ).encode(),
                {},
                url,
            )
        if f"{repo}/commits/" in path:
            return GithubHttpResponse(200, json.dumps({"sha": sha}).encode(), {}, url)
        if f"{repo}/tarball/" in path or f"/{name}/legacy.tar.gz/" in path:
            return GithubHttpResponse(200, archive, {}, url)
        raise LookupError(url)

    return fetch


def _npm_fetch(archive: bytes, *, name: str = "demo", version: str = "1.2.3"):
    integrity = _sri_sha512(archive)

    async def fetch(url: str, *, headers: dict[str, str]) -> GithubHttpResponse:
        del headers
        meta = f"https://registry.npmjs.org/{name}/{version}"
        tarball = f"https://registry.npmjs.org/{name}/-/{name}-{version}.tgz"
        if url == meta:
            return GithubHttpResponse(
                200,
                json.dumps({"dist": {"tarball": tarball, "integrity": integrity}}).encode(),
                {},
                url,
            )
        if url == tarball:
            return GithubHttpResponse(200, archive, {}, url)
        raise LookupError(url)

    return fetch


def _join_fetch(
    *fns: Callable[..., Awaitable[GithubHttpResponse]],
) -> Callable[..., Awaitable[GithubHttpResponse]]:
    async def fetch(url: str, *, headers: dict[str, str]) -> GithubHttpResponse:
        for item in fns:
            try:
                return await item(url, headers=headers)
            except LookupError:
                continue
        raise AssertionError(url)

    return fetch


def _npm_tar() -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        payload = json.dumps({"name": "demo", "version": "1.2.3"}).encode()
        info = tarfile.TarInfo("package/package.json")
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


@pytest.mark.asyncio
async def test_two_git_sources_enqueue_sync_fail_and_history_independently(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    store = _store()
    now = datetime(2026, 9, 1, 10, 0, tzinfo=UTC)
    tool = _tar("# Demo\n")
    other = _tar("# Other\n", name="skills/other/SKILL.md")
    fetch = _join_fetch(_git_fetch(tool), _git_fetch(other, name="other", repo_id=7))
    async with db_sessionmaker() as session, session.begin():
        await _owner(session)
        first = await upsert_source(session, _command())
        second = await upsert_source(
            session,
            _command(
                source_id="other",
                repository_url="https://github.com/acme/other",
                component_subpath="skills/other",
                name="Other Skill",
            ),
        )
        assert first.id == SOURCE_ID
        assert second.id == "other"
        assert first.stable_id != second.stable_id
        jobs = await enqueue_daily(session, now=now)
        assert {job.payload["source_id"] for job in jobs} == {SOURCE_ID, "other"}
        assert jobs[0].id != jobs[1].id
        assert await run_sync(session, SOURCE_ID, fetch=fetch, store=store, now=now) == (
            "publication_started"
        )
        assert await run_sync(session, "other", fetch=fetch, store=store, now=now) == (
            "publication_started"
        )
        with pytest.raises(OfficialUpstreamError) as raised:
            await run_sync(
                session,
                SOURCE_ID,
                fetch=_join_fetch(
                    _git_fetch(tool, repo_id=99), _git_fetch(other, name="other", repo_id=7)
                ),
                store=store,
                now=now + timedelta(days=1),
            )
        assert raised.value.code == CHANGED_REPOSITORY_IDENTITY
        other_retry = await run_sync(
            session,
            "other",
            fetch=_join_fetch(
                _git_fetch(tool, repo_id=99), _git_fetch(other, name="other", repo_id=7)
            ),
            store=store,
            now=now + timedelta(days=1),
        )
        assert other_retry == "publication_started"
        official_rows = list(
            (
                await session.scalars(
                    select(OfficialUpstreamSync).where(OfficialUpstreamSync.source_id == SOURCE_ID)
                )
            ).all()
        )
        other_rows = list(
            (
                await session.scalars(
                    select(OfficialUpstreamSync).where(OfficialUpstreamSync.source_id == "other")
                )
            ).all()
        )
        assert {row.result for row in official_rows} >= {"publication_started", "failed"}
        assert {row.result for row in other_rows} == {"publication_started"}
        await disable_source(session, "other")
        later = await enqueue_daily(session, now=now + timedelta(days=2))
        assert [job.payload["source_id"] for job in later] == [SOURCE_ID]


@pytest.mark.asyncio
async def test_git_and_package_sources_sync_independently(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    store = _store()
    now = datetime(2026, 9, 1, 11, 0, tzinfo=UTC)
    git_archive = _tar("# Demo\n")
    npm_archive = _npm_tar()
    fetch = _join_fetch(_git_fetch(git_archive), _npm_fetch(npm_archive))
    async with db_sessionmaker() as session, session.begin():
        await _owner(session)
        git_source = await upsert_source(session, _command())
        package_source = await upsert_source(
            session,
            _command(
                source_id="npm-demo",
                kind="package",
                repository_url="",
                tracked_ref="",
                component_subpath="",
                ecosystem="npm",
                package_name="demo",
                package_version="1.2.3",
                name="Demo Package",
            ),
        )
        jobs = await enqueue_daily(session, now=now)
        assert {job.payload["source_id"] for job in jobs} == {SOURCE_ID, "npm-demo"}
        git_result = await run_sync(session, git_source.id, fetch=fetch, store=store, now=now)
        package_result = await run_sync(
            session, package_source.id, fetch=fetch, store=store, now=now
        )
        assert git_result == "publication_started"
        assert package_result == "publication_started"
        git_plan = (
            await session.scalars(
                select(PublicationPlan).where(PublicationPlan.stable_id == git_source.stable_id)
            )
        ).one()
        package_plan = (
            await session.scalars(
                select(PublicationPlan).where(PublicationPlan.stable_id == package_source.stable_id)
            )
        ).one()
        await execute_validate(session, plan_id=git_plan.id, object_store=store, skip_safety=True)
        await execute_validate(
            session, plan_id=package_plan.id, object_store=store, skip_safety=True
        )
        git_published = await execute_publish(session, plan_id=git_plan.id, store=store)
        package_published = await execute_publish(session, plan_id=package_plan.id, store=store)
        assert git_published.stable_id == git_source.stable_id
        assert package_published.stable_id == package_source.stable_id
        assert git_published.stable_id != package_published.stable_id
        git_passport = dict(git_published.passport_document or {})
        package_passport = dict(package_published.passport_document or {})
        git_facts = cast(dict[str, object], git_passport.get("facts") or {})
        package_facts = cast(dict[str, object], package_passport.get("facts") or {})
        git_upstream = cast(dict[str, object], git_facts.get("upstream_source") or {})
        package_upstream = cast(dict[str, object], package_facts.get("upstream_source") or {})
        assert str(git_upstream.get("value", "")).startswith("git:https://github.com/acme/tool@")
        assert package_upstream.get("value") == "package:npm:demo@1.2.3"
        await disable_source(session, "npm-demo")
        later = await enqueue_daily(session, now=now + timedelta(days=1))
        assert [job.payload["source_id"] for job in later] == [SOURCE_ID]
        npm_history = list(
            (
                await session.scalars(
                    select(OfficialUpstreamSync).where(OfficialUpstreamSync.source_id == "npm-demo")
                )
            ).all()
        )
        assert npm_history
        assert all(row.source_id == "npm-demo" for row in npm_history)


@pytest.mark.asyncio
async def test_coordinate_and_digest_match_suggests_without_substituting_identity(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    store = _store()
    now = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
    archive = _tar("# Demo\n")
    fetch = _join_fetch(
        _git_fetch(archive),
        _git_fetch(archive, name="copy", repo_id=8),
    )
    async with db_sessionmaker() as session, session.begin():
        await _owner(session)
        first = await upsert_source(session, _command())
        second = await upsert_source(
            session,
            _command(
                source_id="copy",
                repository_url="https://github.com/acme/copy",
                name="Copy Skill",
            ),
        )
        await run_sync(session, first.id, fetch=fetch, store=store, now=now)
        await run_sync(session, second.id, fetch=fetch, store=store, now=now)
        first_plan = (
            await session.scalars(
                select(PublicationPlan).where(PublicationPlan.stable_id == first.stable_id)
            )
        ).one()
        second_plan = (
            await session.scalars(
                select(PublicationPlan).where(PublicationPlan.stable_id == second.stable_id)
            )
        ).one()
        await execute_validate(session, plan_id=first_plan.id, object_store=store, skip_safety=True)
        await execute_validate(
            session, plan_id=second_plan.id, object_store=store, skip_safety=True
        )
        published_first = await execute_publish(session, plan_id=first_plan.id, store=store)
        published_second = await execute_publish(session, plan_id=second_plan.id, store=store)
        assert published_first.stable_id == first.stable_id
        assert published_second.stable_id == second.stable_id
        assert published_first.stable_id != published_second.stable_id
        first_passport = dict(published_first.passport_document or {})
        artifact = cast(dict[str, object], first_passport.get("artifact") or {})
        facts = cast(dict[str, object], first_passport.get("facts") or {})
        upstream = cast(dict[str, object], facts.get("upstream_source") or {})
        suggestion = suggest_catalog_replacement(
            canonical_coordinate=str(upstream.get("value") or ""),
            artifact_digest=str(artifact.get("digest") or ""),
            catalog=(
                CatalogMatchInput(
                    stable_id=published_first.stable_id,
                    version=str(published_first.version),
                    canonical_coordinate=str(upstream.get("value") or ""),
                    artifact_digest=str(artifact.get("digest") or ""),
                ),
            ),
        )
        assert suggestion is not None
        assert suggestion.dismissible is True
        assert suggestion.catalog_stable_id == published_first.stable_id
        assert published_second.stable_id != suggestion.catalog_stable_id
        none_coordinate = suggest_catalog_replacement(
            canonical_coordinate=f"git:https://github.com/acme/other@{COMMIT}:skills/demo",
            artifact_digest=str(artifact.get("digest") or ""),
            catalog=(
                CatalogMatchInput(
                    stable_id=published_first.stable_id,
                    version=str(published_first.version),
                    canonical_coordinate=str(upstream.get("value") or ""),
                    artifact_digest=str(artifact.get("digest") or ""),
                ),
            ),
        )
        none_digest = suggest_catalog_replacement(
            canonical_coordinate=str(upstream.get("value") or ""),
            artifact_digest="sha256:" + "c" * 64,
            catalog=(
                CatalogMatchInput(
                    stable_id=published_first.stable_id,
                    version=str(published_first.version),
                    canonical_coordinate=str(upstream.get("value") or ""),
                    artifact_digest=str(artifact.get("digest") or ""),
                ),
            ),
        )
        assert none_coordinate is None
        assert none_digest is None
