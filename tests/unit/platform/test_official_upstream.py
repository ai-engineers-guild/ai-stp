"""Official upstream snapshots (SPEC-056 REQ-5601, REQ-5603, REQ-5605, REQ-5607)."""

from __future__ import annotations

import io
import json
import tarfile
from datetime import UTC, datetime
from urllib.parse import urlsplit

import pytest
from tests.support.component_passports import adaptation_fields

from ai_stp_foundation.digests import digest_bytes
from ai_stp_passports.envelope import derive_revision_id
from ai_stp_passports.versions import ComponentVersionPassport
from ai_stp_platform.catalog_projection import component_summary
from ai_stp_platform.catalog_read import PublicVersionRow
from ai_stp_platform.models import CatalogMetadata
from ai_stp_platform.official_upstream import OFFICIAL_ACCOUNT_ID
from ai_stp_platform.official_upstream.archive import MAX_ARCHIVE_BYTES, extract_component_files
from ai_stp_platform.official_upstream.attribution import OWNERSHIP_NOTICE, build_description
from ai_stp_platform.official_upstream.errors import (
    INVALID_SOURCE,
    UNAVAILABLE_UPSTREAM,
    UNSAFE_ARCHIVE,
    OfficialUpstreamError,
)
from ai_stp_platform.official_upstream.github import GithubHttpResponse
from ai_stp_platform.official_upstream.resolve import resolve_intent
from ai_stp_platform.official_upstream.source import SourceUpsert, validate_source
from ai_stp_platform.official_upstream.sync import next_unused_minor
from ai_stp_platform.publication_logic import passport_digest
from ai_stp_platform.storage.object_store import ARTIFACT_DIGEST_DOMAIN
from ai_stp_sources.models import GitIntent

pytestmark = pytest.mark.platform

COMMIT = "a" * 40
STABLE_ID = "component_01ARZ3NDEKTSV4RRFFQ69G5FAV"


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
        "target_scope": "global",
        "projection_root": "skills/demo",
        "projection_shape": "tree",
        "tags": ("code-review",),
    }
    payload.update(overrides)
    return SourceUpsert(**payload)  # type: ignore[arg-type]


def _tar(files: dict[str, bytes | str], *, prefix: str = "tool-aaaaaaaa/") -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, content in files.items():
            payload = content.encode("utf-8") if isinstance(content, str) else content
            info = tarfile.TarInfo(prefix + name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


def test_source_rejects_unsafe_coordinates_and_non_official_owner() -> None:
    validate_source(_command())
    validate_source(
        _command(
            kind="package",
            ecosystem="npm",
            package_name="demo",
            package_version="1.2.3",
            repository_url="",
            tracked_ref="",
            component_subpath="",
        )
    )
    cases = (
        {"repository_url": "http://github.com/acme/tool"},
        {"repository_url": "https://user:pass@github.com/acme/tool"},
        {"repository_url": "https://gitlab.com/acme/tool"},
        {"component_subpath": ""},
        {"component_subpath": "../escape"},
        {"component_type": "marketplace"},
        {"owner_account_id": "account_01ARZ3NDEKTSV4RRFFQ69G5FAV"},
        {"upstream_project_name": " "},
        {"reviewed_description": ""},
        {"kind": "svn"},
        {
            "kind": "package",
            "ecosystem": "maven",
            "package_name": "demo",
            "package_version": "1.0.0",
        },
        {"kind": "package", "ecosystem": "npm", "package_name": "", "package_version": "1.0.0"},
        {"source_id": "Official"},
    )
    for overrides in cases:
        with pytest.raises(OfficialUpstreamError) as raised:
            validate_source(_command(**overrides))
        assert raised.value.code == INVALID_SOURCE


def test_extract_resolves_component_root_and_records_exact_files() -> None:
    archive = _tar({"skills/demo/SKILL.md": "# Demo\n", "README.md": "docs\n"})
    files = extract_component_files(archive, subpath="skills/demo")
    assert files == {"SKILL.md": b"# Demo\n"}


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        ("redirect", "escapes"),
        ("link", "link"),
        ("secret", "secret-like"),
        ("binary", "binary"),
        ("missing", "missing"),
    ],
)
def test_extract_rejects_unsafe_archives(mutate: str, message: str) -> None:
    if mutate == "redirect":
        archive = _tar({"../escape": "x"})
    elif mutate == "link":
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as tarball:
            info = tarfile.TarInfo("tool-aaaaaaaa/skills/demo/link")
            info.type = tarfile.SYMTYPE
            info.linkname = "../README.md"
            tarball.addfile(info)
        archive = buffer.getvalue()
    elif mutate == "secret":
        archive = _tar({"skills/demo/.env": "TOKEN=1\n"})
    elif mutate == "binary":
        archive = _tar({"skills/demo/SKILL.md": b"# x\x00\n"})
    else:
        archive = _tar({"README.md": "no root\n"})
    with pytest.raises(OfficialUpstreamError) as raised:
        extract_component_files(archive, subpath="skills/demo")
    assert raised.value.code == UNSAFE_ARCHIVE
    assert message in raised.value.message


@pytest.mark.parametrize(
    "member_name",
    (
        "../evil",
        "./../evil",
        "/evil",
        "../skills/demo/SKILL.md",
        "./../skills/demo/SKILL.md",
        "/skills/demo/SKILL.md",
    ),
)
def test_extract_rejects_absolute_and_traversal_member_names_before_normalization(
    member_name: str,
) -> None:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        payload = b"# Demo\n"
        info = tarfile.TarInfo(member_name)
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))
    with pytest.raises(OfficialUpstreamError) as raised:
        extract_component_files(buffer.getvalue(), subpath="skills/demo")
    assert raised.value.code == UNSAFE_ARCHIVE
    assert "escapes" in raised.value.message


def test_extract_rejects_oversize_archive() -> None:
    with pytest.raises(OfficialUpstreamError) as raised:
        extract_component_files(b"x" * (MAX_ARCHIVE_BYTES + 1), subpath="skills/demo")
    assert raised.value.code == UNSAFE_ARCHIVE


@pytest.mark.asyncio
async def test_acquire_resolves_commit_and_follows_only_github_redirects() -> None:
    sha = COMMIT
    archive = _tar({"skills/demo/SKILL.md": "# Demo\n"})
    calls: list[str] = []

    async def fetch(url: str, *, headers: dict[str, str]) -> GithubHttpResponse:
        del headers
        calls.append(url)
        path = urlsplit(url).path
        if path.endswith("/repos/acme/tool"):
            return GithubHttpResponse(
                200,
                json.dumps({"id": 42, "private": False, "license": {"spdx_id": "MIT"}}).encode(),
                {},
                url,
            )
        if "/commits/" in path:
            return GithubHttpResponse(200, json.dumps({"sha": sha}).encode(), {}, url)
        if "/tarball/" in path:
            return GithubHttpResponse(
                302,
                b"",
                {"location": f"https://codeload.github.com/acme/tool/legacy.tar.gz/{sha}"},
                url,
            )
        if "codeload.github.com" in url:
            return GithubHttpResponse(200, archive, {}, url)
        raise AssertionError(url)

    snapshot = await resolve_intent(
        GitIntent(
            repository_url="https://github.com/acme/tool",
            tracked_ref="main",
            subpath="skills/demo",
        ),
        fetch=fetch,
    )
    assert snapshot.exact_identity == sha
    assert snapshot.github_repo_id == 42
    assert snapshot.observed_license == "MIT"
    assert snapshot.files["SKILL.md"] == b"# Demo\n"
    assert snapshot.archive_digest == digest_bytes(ARTIFACT_DIGEST_DOMAIN, archive)
    assert any("codeload.github.com" in item for item in calls)


@pytest.mark.asyncio
async def test_acquire_rejects_non_github_redirect_and_oversize() -> None:
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

    with pytest.raises(OfficialUpstreamError) as raised:
        await resolve_intent(
            GitIntent(
                repository_url="https://github.com/acme/tool",
                tracked_ref="main",
                subpath="skills/demo",
            ),
            fetch=evil,
        )
    assert raised.value.code == UNSAFE_ARCHIVE

    async def missing(url: str, *, headers: dict[str, str]) -> GithubHttpResponse:
        del headers
        return GithubHttpResponse(404, b"{}", {}, url)

    with pytest.raises(OfficialUpstreamError) as unavailable:
        await resolve_intent(
            GitIntent(
                repository_url="https://github.com/acme/tool",
                tracked_ref="main",
                subpath="skills/demo",
            ),
            fetch=missing,
        )
    assert unavailable.value.code == UNAVAILABLE_UPSTREAM


def test_attribution_leads_and_ends_with_required_notice() -> None:
    text = build_description(
        project_name="Demo",
        maintainer="Acme Maintainers",
        repository="https://github.com/acme/tool",
        license_spdx="MIT",
        reviewed_body="Reviewed component body.",
    )
    assert text.startswith(
        "Demo is maintained by Acme Maintainers at https://github.com/acme/tool under MIT."
    )
    assert text.endswith(OWNERSHIP_NOTICE + "\n")
    assert "Reviewed component body." in text
    assert "authored" not in text.lower() or "does not claim upstream authorship" in text


def test_next_unused_minor_advances_the_stable_line() -> None:
    assert next_unused_minor([]) == "1.0"
    assert next_unused_minor(["1.0", "1.1"]) == "1.2"


def test_catalog_projection_separates_publisher_from_upstream_attribution() -> None:
    description = build_description(
        project_name="Demo",
        maintainer="Acme Maintainers",
        repository="https://github.com/acme/tool",
        license_spdx="MIT",
        reviewed_body="Reviewed component body.",
    )
    passport: dict[str, object] = {
        "schema_version": 1,
        "kind": "component",
        "stable_id": STABLE_ID,
        "revision_id": "revision_" + "0" * 64,
        "parent_revision_ids": [],
        "owner_id": OFFICIAL_ACCOUNT_ID,
        "created_at": "2026-09-01T00:00:00.000Z",
        "visibility": "public",
        "facts": {},
        "name": "Demo Skill",
        "description": description,
        "version": "1.0",
        "license": {"spdx_id": "MIT", "redistribution_allowed": True},
        "tags": ["code-review"],
        "source": {
            "repository": "https://github.com/acme/tool",
            "commit": COMMIT,
            "path": "skills/demo",
        },
        "artifact": {"digest": "sha256:" + "b" * 64, "size_bytes": 12},
        **adaptation_fields(digest="sha256:" + "b" * 64, size=12),
        "required_env": [],
        "requires_credentials": False,
        "requires_authorization": "none",
        "permissions": {"filesystem": [], "network": [], "process": []},
        "external_endpoints": [],
        "compatibility_evidence_refs": [],
        "component_type": "skill",
        "provides_capabilities": [],
        "requires_components": [],
        "requires_capabilities": [],
        "conflicts": {
            "paths": [],
            "commands": [],
            "hooks": [],
            "mcp": [],
            "agents": [],
            "plugins": [],
        },
    }
    passport["revision_id"] = derive_revision_id(passport)  # type: ignore[arg-type]
    published_at = datetime(2026, 9, 1, tzinfo=UTC)
    metadata = CatalogMetadata(
        owner_account_id=OFFICIAL_ACCOUNT_ID,
        object_kind="component",
        stable_id=STABLE_ID,
        version="1.0",
        current_revision_id=str(passport["revision_id"]),
        visibility="public",
        lifecycle_state="active",
        name="Demo Skill",
        published_at=published_at,
        trust_lane="experimental",
        author_verified=True,
        component_verified=True,
        passport_digest=passport_digest(ComponentVersionPassport.model_validate(passport)),
        passport_document=passport,
        likes_count=0,
        updated_at=published_at,
    )
    row = PublicVersionRow(
        metadata=metadata,
        passport=passport,
        passport_digest=str(metadata.passport_digest),
        published_at=published_at,
        trust_lane="experimental",
        author_verified=True,
        component_verified=True,
        lifecycle="active",
        stable_id=STABLE_ID,
        version="1.0",
        object_kind="component",
    )
    summary = component_summary(row, now=published_at)
    assert summary.publisher_id == OFFICIAL_ACCOUNT_ID
    assert summary.latest_description.startswith("Demo is maintained by Acme Maintainers")
    assert "Acme Maintainers" in summary.latest_description
    assert "AI STP authored" not in description
    assert "does not claim upstream authorship" in description
    assert summary.latest_trust.author_verified is True
    assert summary.latest_trust.component_verified is True


def test_catalog_projection_keeps_verification_axes_independent() -> None:
    description = build_description(
        project_name="Demo",
        maintainer="Acme Maintainers",
        repository="https://github.com/acme/tool",
        license_spdx="MIT",
        reviewed_body="Reviewed component body.",
    )
    passport: dict[str, object] = {
        "schema_version": 1,
        "kind": "component",
        "stable_id": STABLE_ID,
        "revision_id": "revision_" + "0" * 64,
        "parent_revision_ids": [],
        "owner_id": OFFICIAL_ACCOUNT_ID,
        "created_at": "2026-09-01T00:00:00.000Z",
        "visibility": "public",
        "facts": {},
        "name": "Demo Skill",
        "description": description,
        "version": "1.0",
        "license": {"spdx_id": "MIT", "redistribution_allowed": True},
        "tags": ["code-review"],
        "source": {
            "repository": "https://github.com/acme/tool",
            "commit": COMMIT,
            "path": "skills/demo",
        },
        "artifact": {"digest": "sha256:" + "b" * 64, "size_bytes": 12},
        **adaptation_fields(digest="sha256:" + "b" * 64, size=12),
        "required_env": [],
        "requires_credentials": False,
        "requires_authorization": "none",
        "permissions": {"filesystem": [], "network": [], "process": []},
        "external_endpoints": [],
        "compatibility_evidence_refs": [],
        "component_type": "skill",
        "provides_capabilities": [],
        "requires_components": [],
        "requires_capabilities": [],
        "conflicts": {
            "paths": [],
            "commands": [],
            "hooks": [],
            "mcp": [],
            "agents": [],
            "plugins": [],
        },
    }
    passport["revision_id"] = derive_revision_id(passport)  # type: ignore[arg-type]
    published_at = datetime(2026, 9, 1, tzinfo=UTC)
    metadata = CatalogMetadata(
        owner_account_id=OFFICIAL_ACCOUNT_ID,
        object_kind="component",
        stable_id=STABLE_ID,
        version="1.0",
        current_revision_id=str(passport["revision_id"]),
        visibility="public",
        lifecycle_state="active",
        name="Demo Skill",
        published_at=published_at,
        trust_lane="experimental",
        author_verified=True,
        component_verified=False,
        passport_digest=passport_digest(ComponentVersionPassport.model_validate(passport)),
        passport_document=passport,
        likes_count=0,
        updated_at=published_at,
    )
    row = PublicVersionRow(
        metadata=metadata,
        passport=passport,
        passport_digest=str(metadata.passport_digest),
        published_at=published_at,
        trust_lane="experimental",
        author_verified=True,
        component_verified=False,
        lifecycle="active",
        stable_id=STABLE_ID,
        version="1.0",
        object_kind="component",
    )
    summary = component_summary(row, now=published_at)
    assert summary.publisher_id == OFFICIAL_ACCOUNT_ID
    assert summary.latest_trust.author_verified is True
    assert summary.latest_trust.component_verified is False
    assert summary.latest_trust.author_verified != summary.latest_trust.component_verified
