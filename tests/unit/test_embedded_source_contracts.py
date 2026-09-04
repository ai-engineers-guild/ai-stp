"""Shared source contracts and Git/local resolvers (SPEC-057 REQ-5701, REQ-5702, REQ-5718)."""

from __future__ import annotations

import io
import json
import tarfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from ai_stp_sources import (
    FLOATING_FROZEN_SOURCE,
    INVALID_SOURCE,
    UNAVAILABLE_SOURCE,
    UNSAFE_ARCHIVE,
    CatalogIntent,
    GithubHttpResponse,
    GitIntent,
    PackageIntent,
    PathIntent,
    SourceError,
    SourceSnapshot,
    canonicalize_source,
    resolve_source,
    validate_frozen_snapshot,
)

COMMIT = "a" * 40
STABLE_ID = "component_01ARZ3NDEKTSV4RRFFQ69G5FAV"
PASSPORT_DIGEST = "sha256:" + "b" * 64


def _tar(files: dict[str, bytes | str], *, prefix: str = "tool-aaaaaaaa/") -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, content in files.items():
            payload = content.encode("utf-8") if isinstance(content, str) else content
            info = tarfile.TarInfo(prefix + name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


def _git_intent() -> GitIntent:
    return GitIntent(
        repository_url="https://github.com/acme/tool.git",
        tracked_ref="main",
        subpath="skills/demo",
    )


def test_catalog_intent_canonicalizes_and_keeps_trust_false() -> None:
    intent = CatalogIntent(
        stable_id=STABLE_ID,
        version="1.0",
        passport_digest=PASSPORT_DIGEST,
    )
    canonical = canonicalize_source(intent)
    assert canonical == intent


@pytest.mark.asyncio
async def test_catalog_snapshot_never_sets_verification_axes() -> None:
    snapshot = await resolve_source(
        CatalogIntent(
            stable_id=STABLE_ID,
            version="1.0",
            passport_digest=PASSPORT_DIGEST,
        )
    )
    assert snapshot.kind == "catalog"
    assert snapshot.canonical_coordinate.startswith("catalog:")
    assert snapshot.author_verified is False
    assert snapshot.component_verified is False
    assert snapshot.target_write is False


def test_git_url_ref_and_subpath_are_canonical() -> None:
    canonical = canonicalize_source(_git_intent())
    assert isinstance(canonical, GitIntent)
    assert canonical.repository_url == "https://github.com/acme/tool"
    assert canonical.tracked_ref == "main"
    assert canonical.subpath == "skills/demo"


def test_git_repository_root_is_a_valid_component_subpath() -> None:
    canonical = canonicalize_source(
        GitIntent(
            repository_url="https://github.com/acme/tool",
            tracked_ref=COMMIT,
            subpath=".",
        )
    )
    assert isinstance(canonical, GitIntent)
    assert canonical.subpath == "."


def test_credentials_and_traversal_are_rejected() -> None:
    cases: list[GitIntent | PathIntent | PackageIntent] = [
        GitIntent(
            repository_url="https://user:pass@github.com/acme/tool",
            tracked_ref="main",
            subpath="skills/demo",
        ),
        GitIntent(
            repository_url="https://github.com/acme/tool",
            tracked_ref="main",
            subpath="../escape",
        ),
        PathIntent(relative_path="../escape"),
        PathIntent(relative_path="/abs"),
        PathIntent(relative_path="C:/windows"),
        PackageIntent(ecosystem="npm", name="user:pass@host/pkg", version="1.0.0"),
        PackageIntent(ecosystem="npm", name="left-pad", version="latest"),
        PackageIntent(ecosystem="npm", name="left-pad", version="^1.0.0"),
    ]
    for intent in cases:
        with pytest.raises(SourceError) as raised:
            canonicalize_source(intent)
        assert raised.value.code == INVALID_SOURCE


@pytest.mark.asyncio
async def test_git_resolves_branch_to_full_commit_and_records_provenance() -> None:
    archive = _tar({"skills/demo/SKILL.md": "# Demo\n"})

    async def fetch(url: str, *, headers: dict[str, str]) -> GithubHttpResponse:
        path = urlsplit(url).path
        if path.endswith("/repos/acme/tool"):
            assert headers.get("Authorization") == "Bearer secret-token"
            return GithubHttpResponse(
                200,
                json.dumps({"id": 42, "private": False, "license": {"spdx_id": "MIT"}}).encode(),
                {},
                url,
            )
        if "/commits/" in path:
            assert path.endswith("/commits/main")
            return GithubHttpResponse(200, json.dumps({"sha": COMMIT}).encode(), {}, url)
        if "/tarball/" in path:
            assert headers.get("Authorization") == "Bearer secret-token"
            return GithubHttpResponse(
                302,
                b"",
                {"location": f"https://codeload.github.com/acme/tool/legacy.tar.gz/{COMMIT}"},
                url,
            )
        if "codeload.github.com" in url:
            assert "Authorization" not in headers
            return GithubHttpResponse(200, archive, {}, url)
        raise AssertionError(url)

    snapshot = await resolve_source(_git_intent(), fetch=fetch, token="secret-token")
    assert snapshot.exact_identity == COMMIT
    assert snapshot.repository_url == "https://github.com/acme/tool"
    assert snapshot.github_repo_id == 42
    assert snapshot.subpath == "skills/demo"
    assert snapshot.archive_digest is not None
    assert snapshot.component_digest is not None
    assert snapshot.files["SKILL.md"] == b"# Demo\n"
    assert "secret-token" not in snapshot.model_dump_json()
    assert snapshot.author_verified is False
    assert snapshot.component_verified is False
    validate_frozen_snapshot(snapshot)


def test_floating_frozen_git_identity_is_rejected() -> None:
    snapshot = SourceSnapshot(
        kind="git",
        canonical_coordinate="git:https://github.com/acme/tool@main:skills/demo",
        exact_identity="main",
        repository_url="https://github.com/acme/tool",
        subpath="skills/demo",
    )
    with pytest.raises(SourceError) as raised:
        validate_frozen_snapshot(snapshot)
    assert raised.value.code == FLOATING_FROZEN_SOURCE


@pytest.mark.asyncio
async def test_git_rejects_unsafe_redirect() -> None:
    async def evil(url: str, *, headers: dict[str, str]) -> GithubHttpResponse:
        del headers
        path = urlsplit(url).path
        if path.endswith("/repos/acme/tool"):
            return GithubHttpResponse(
                200, json.dumps({"id": 1, "private": False, "license": None}).encode(), {}, url
            )
        if "/commits/" in path:
            return GithubHttpResponse(200, json.dumps({"sha": COMMIT}).encode(), {}, url)
        return GithubHttpResponse(302, b"", {"location": "https://evil.test/archive"}, url)

    with pytest.raises(SourceError) as raised:
        await resolve_source(_git_intent(), fetch=evil)
    assert raised.value.code == UNSAFE_ARCHIVE


@pytest.mark.asyncio
async def test_git_rejects_secret_and_oversize_archive() -> None:
    secret = _tar({"skills/demo/.env": "TOKEN=1\n"})

    async def fetch_secret(url: str, *, headers: dict[str, str]) -> GithubHttpResponse:
        del headers
        path = urlsplit(url).path
        if path.endswith("/repos/acme/tool"):
            return GithubHttpResponse(
                200, json.dumps({"id": 1, "private": False, "license": None}).encode(), {}, url
            )
        if "/commits/" in path:
            return GithubHttpResponse(200, json.dumps({"sha": COMMIT}).encode(), {}, url)
        return GithubHttpResponse(200, secret, {}, url)

    with pytest.raises(SourceError) as raised:
        await resolve_source(_git_intent(), fetch=fetch_secret)
    assert raised.value.code == UNSAFE_ARCHIVE

    template = _tar({"skills/demo/.env.example": "TOKEN=\n", "skills/demo/SKILL.md": "# Demo\n"})

    async def fetch_template(url: str, *, headers: dict[str, str]) -> GithubHttpResponse:
        del headers
        path = urlsplit(url).path
        if path.endswith("/repos/acme/tool"):
            return GithubHttpResponse(
                200, json.dumps({"id": 1, "private": False, "license": None}).encode(), {}, url
            )
        if "/commits/" in path:
            return GithubHttpResponse(200, json.dumps({"sha": COMMIT}).encode(), {}, url)
        return GithubHttpResponse(200, template, {}, url)

    snapshot = await resolve_source(_git_intent(), fetch=fetch_template)
    assert snapshot.files[".env.example"] == b"TOKEN=\n"

    traversal = _tar({"../skills/demo/SKILL.md": "# Demo\n"}, prefix="")

    async def fetch_traversal(url: str, *, headers: dict[str, str]) -> GithubHttpResponse:
        del headers
        path = urlsplit(url).path
        if path.endswith("/repos/acme/tool"):
            return GithubHttpResponse(
                200, json.dumps({"id": 1, "private": False, "license": None}).encode(), {}, url
            )
        if "/commits/" in path:
            return GithubHttpResponse(200, json.dumps({"sha": COMMIT}).encode(), {}, url)
        return GithubHttpResponse(200, traversal, {}, url)

    with pytest.raises(SourceError) as escaped:
        await resolve_source(_git_intent(), fetch=fetch_traversal)
    assert escaped.value.code == UNSAFE_ARCHIVE

    async def huge(url: str, *, headers: dict[str, str]) -> GithubHttpResponse:
        del headers
        return GithubHttpResponse(200, b"x" * 100, {"content-length": str(30 * 1024 * 1024)}, url)

    with pytest.raises(SourceError) as bounds:
        await resolve_source(_git_intent(), fetch=huge)
    assert bounds.value.code == UNSAFE_ARCHIVE


@pytest.mark.asyncio
async def test_git_unavailable_repository_fails_closed() -> None:
    async def missing(url: str, *, headers: dict[str, str]) -> GithubHttpResponse:
        del headers
        return GithubHttpResponse(404, b"{}", {}, url)

    with pytest.raises(SourceError) as raised:
        await resolve_source(_git_intent(), fetch=missing)
    assert raised.value.code == UNAVAILABLE_SOURCE
    assert raised.value.message == "GitHub repository is unavailable"


@pytest.mark.asyncio
async def test_git_rate_limit_is_not_reported_as_a_missing_repository() -> None:
    async def limited(url: str, *, headers: dict[str, str]) -> GithubHttpResponse:
        del headers
        return GithubHttpResponse(
            403,
            b'{"message":"API rate limit exceeded"}',
            {"x-ratelimit-remaining": "0"},
            url,
        )

    with pytest.raises(SourceError) as raised:
        await resolve_source(_git_intent(), fetch=limited)
    assert raised.value.code == UNAVAILABLE_SOURCE
    assert raised.value.message == "GitHub rate limit exceeded"


@pytest.mark.asyncio
async def test_local_path_is_confined_to_confirmed_root(tmp_path: Path) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "skills").mkdir()
    demo = root / "skills" / "demo"
    demo.mkdir()
    (demo / "SKILL.md").write_text("# Demo\n", encoding="utf-8")
    (outside / "secret.md").write_text("nope\n", encoding="utf-8")

    snapshot = await resolve_source(
        PathIntent(relative_path="skills/demo"),
        local_root=root,
        now=datetime(2026, 9, 1, tzinfo=UTC),
    )
    assert snapshot.canonical_coordinate == "path:skills/demo"
    assert "SKILL.md" in snapshot.files
    assert snapshot.author_verified is False
    assert "\\" not in snapshot.canonical_coordinate
    assert str(root) not in snapshot.canonical_coordinate

    with pytest.raises(SourceError) as escaped:
        await resolve_source(PathIntent(relative_path="../outside"), local_root=root)
    assert escaped.value.code == INVALID_SOURCE


@pytest.mark.asyncio
async def test_local_secret_file_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / ".env").write_text("TOKEN=1\n", encoding="utf-8")
    with pytest.raises(SourceError) as raised:
        await resolve_source(PathIntent(relative_path=".env"), local_root=root)
    assert raised.value.code == UNSAFE_ARCHIVE


@pytest.mark.asyncio
async def test_package_intent_canonicalizes_and_requires_fetch() -> None:
    canonical = canonicalize_source(
        PackageIntent(ecosystem="npm", name="@scope/pkg", version="1.2.3")
    )
    assert isinstance(canonical, PackageIntent)
    assert canonical.name == "@scope/pkg"
    with pytest.raises(SourceError) as raised:
        await resolve_source(canonical)
    assert raised.value.code == INVALID_SOURCE
