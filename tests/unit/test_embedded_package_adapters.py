"""Official registry adapters (SPEC-057 REQ-5703, REQ-5704, REQ-5718)."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import tarfile
import zipfile
from datetime import UTC, datetime
from urllib.parse import urlsplit

import pytest

from ai_stp_sources import (
    AMBIGUOUS_DISTRIBUTION,
    FLOATING_FROZEN_SOURCE,
    INTEGRITY_MISMATCH,
    INVALID_SOURCE,
    UNAVAILABLE_SOURCE,
    UNSAFE_ARCHIVE,
    CratesEvidence,
    GithubHttpResponse,
    GoEvidence,
    NpmEvidence,
    PackageIntent,
    PubEvidence,
    PypiEvidence,
    SourceError,
    SourceSnapshot,
    resolve_source,
    validate_frozen_snapshot,
)
from ai_stp_sources.http import MAX_GRAPH_ENTRIES

NOW = datetime(2026, 9, 1, tzinfo=UTC)
DIGEST = "sha256:" + "b" * 64


def _sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sri_sha512(payload: bytes) -> str:
    digest = base64.b64encode(hashlib.sha512(payload).digest()).decode("ascii")
    return f"sha512-{digest}"


def _go_h1(payload: bytes) -> str:
    digest = base64.b64encode(hashlib.sha256(payload).digest()).decode("ascii")
    return f"h1:{digest}"


def _tar(files: dict[str, str], *, prefix: str) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, content in files.items():
            payload = content.encode("utf-8")
            info = tarfile.TarInfo(prefix + name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


def _zip(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content.encode("utf-8"))
    return buffer.getvalue()


class Registry:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str]]] = []
        self.routes: dict[str, GithubHttpResponse] = {}

    def add(
        self,
        url: str,
        body: bytes | str | object,
        *,
        status: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        if isinstance(body, bytes):
            payload = body
        elif isinstance(body, str):
            payload = body.encode("utf-8")
        else:
            payload = json.dumps(body).encode("utf-8")
        self.routes[url] = GithubHttpResponse(status, payload, headers or {}, url)

    async def fetch(self, url: str, *, headers: dict[str, str]) -> GithubHttpResponse:
        self.calls.append((url, dict(headers)))
        assert "Authorization" not in headers
        parsed = urlsplit(url)
        assert parsed.username is None
        assert parsed.password is None
        if url not in self.routes:
            raise AssertionError(url)
        return self.routes[url]

    def hosts(self) -> set[str]:
        return {host for host in (urlsplit(url).hostname for url, _headers in self.calls) if host}


def _assert_observation(snapshot: SourceSnapshot) -> None:
    assert snapshot.author_verified is False
    assert snapshot.component_verified is False
    assert snapshot.target_write is False
    assert snapshot.package_evidence is not None
    validate_frozen_snapshot(snapshot)


@pytest.mark.asyncio
async def test_npm_records_tarball_scripts_lock_and_repository() -> None:
    archive = _tar(
        {
            "package.json": json.dumps(
                {
                    "name": "demo",
                    "version": "1.2.3",
                    "main": "index.js",
                    "scripts": {"postinstall": "node setup.js", "test": "jest"},
                    "repository": {"type": "git", "url": "git+https://github.com/acme/demo.git"},
                    "dependencies": {"left-pad": "1.3.0"},
                }
            ),
            "package-lock.json": '{"lockfileVersion": 3}',
        },
        prefix="package/",
    )
    integrity = _sri_sha512(archive)
    registry = Registry()
    registry.add(
        "https://registry.npmjs.org/demo/1.2.3",
        {
            "dist": {
                "tarball": "https://registry.npmjs.org/demo/-/demo-1.2.3.tgz",
                "integrity": integrity,
            },
            "repository": {"type": "git", "url": "git+https://github.com/acme/demo.git"},
        },
    )
    registry.add("https://registry.npmjs.org/demo/-/demo-1.2.3.tgz", archive)

    snapshot = await resolve_source(
        PackageIntent(ecosystem="npm", name="demo", version="1.2.3"),
        fetch=registry.fetch,
        now=NOW,
    )
    evidence = snapshot.package_evidence
    assert isinstance(evidence, NpmEvidence)
    assert evidence.integrity == integrity
    assert evidence.entry_point == "index.js"
    assert evidence.lifecycle_scripts == {"postinstall": "node setup.js"}
    assert evidence.repository == "https://github.com/acme/demo"
    assert evidence.lockfile_name == "package-lock.json"
    assert snapshot.files["package-lock.json"] == b'{"lockfileVersion": 3}'
    assert snapshot.archive_digest is not None
    assert snapshot.canonical_coordinate == "package:npm:demo@1.2.3"
    assert registry.hosts() == {"registry.npmjs.org"}
    _assert_observation(snapshot)


@pytest.mark.asyncio
async def test_npm_scoped_name_keeps_slash_on_official_endpoint() -> None:
    archive = _tar({"package.json": '{"name":"@scope/pkg","main":"lib.js"}'}, prefix="package/")
    registry = Registry()
    registry.add(
        "https://registry.npmjs.org/@scope/pkg/1.0.0",
        {
            "dist": {
                "tarball": "https://registry.npmjs.org/@scope/pkg/-/pkg-1.0.0.tgz",
                "integrity": _sri_sha512(archive),
            }
        },
    )
    registry.add("https://registry.npmjs.org/@scope/pkg/-/pkg-1.0.0.tgz", archive)
    snapshot = await resolve_source(
        PackageIntent(ecosystem="npm", name="@scope/pkg", version="1.0.0"),
        fetch=registry.fetch,
    )
    evidence = snapshot.package_evidence
    assert isinstance(evidence, NpmEvidence)
    assert evidence.entry_point == "lib.js"
    assert next(url for url, _headers in registry.calls) == (
        "https://registry.npmjs.org/@scope/pkg/1.0.0"
    )


@pytest.mark.asyncio
async def test_npm_integrity_mismatch_fails_closed() -> None:
    archive = _tar({"package.json": "{}"}, prefix="package/")
    registry = Registry()
    registry.add(
        "https://registry.npmjs.org/demo/1.2.3",
        {
            "dist": {
                "tarball": "https://registry.npmjs.org/demo/-/demo-1.2.3.tgz",
                "integrity": "sha512-aaaaaaaa",
            }
        },
    )
    registry.add("https://registry.npmjs.org/demo/-/demo-1.2.3.tgz", archive)
    with pytest.raises(SourceError) as raised:
        await resolve_source(
            PackageIntent(ecosystem="npm", name="demo", version="1.2.3"),
            fetch=registry.fetch,
        )
    assert raised.value.code == INTEGRITY_MISMATCH


@pytest.mark.asyncio
async def test_pypi_requires_filename_and_platform_when_multiple_files() -> None:
    wheel = b"wheel-bytes"
    sdist = b"sdist-bytes"
    registry = Registry()
    meta = {
        "info": {"requires_dist": ["httpx (>=0.27)"]},
        "urls": [
            {
                "filename": "demo-1.0.0-py3-none-any.whl",
                "url": "https://files.pythonhosted.org/packages/demo-1.0.0-py3-none-any.whl",
                "digests": {"sha256": _sha256_hex(wheel)},
            },
            {
                "filename": "demo-1.0.0.tar.gz",
                "url": "https://files.pythonhosted.org/packages/demo-1.0.0.tar.gz",
                "digests": {"sha256": _sha256_hex(sdist)},
            },
        ],
    }
    registry.add("https://pypi.org/pypi/demo/1.0.0/json", meta)
    with pytest.raises(SourceError) as ambiguous:
        await resolve_source(
            PackageIntent(ecosystem="pypi", name="demo", version="1.0.0"),
            fetch=registry.fetch,
        )
    assert ambiguous.value.code == AMBIGUOUS_DISTRIBUTION

    registry.add("https://files.pythonhosted.org/packages/demo-1.0.0-py3-none-any.whl", wheel)
    snapshot = await resolve_source(
        PackageIntent(
            ecosystem="pypi",
            name="demo",
            version="1.0.0",
            filename="demo-1.0.0-py3-none-any.whl",
            platform="py3-none-any",
        ),
        fetch=registry.fetch,
    )
    evidence = snapshot.package_evidence
    assert isinstance(evidence, PypiEvidence)
    assert evidence.filename == "demo-1.0.0-py3-none-any.whl"
    assert evidence.platform == "py3-none-any"
    assert evidence.registry_sha256 == _sha256_hex(wheel)
    assert evidence.requires_dist == ("httpx (>=0.27)",)
    assert snapshot.files == {}
    assert snapshot.canonical_coordinate.endswith(":demo-1.0.0-py3-none-any.whl")
    assert registry.hosts() <= {"pypi.org", "files.pythonhosted.org"}
    _assert_observation(snapshot)


@pytest.mark.asyncio
async def test_pypi_integrity_mismatch_fails_closed() -> None:
    payload = b"wheel"
    registry = Registry()
    registry.add(
        "https://pypi.org/pypi/demo/1.0.0/json",
        {
            "info": {},
            "urls": [
                {
                    "filename": "demo-1.0.0-py3-none-any.whl",
                    "url": "https://files.pythonhosted.org/packages/demo-1.0.0-py3-none-any.whl",
                    "digests": {"sha256": "a" * 64},
                }
            ],
        },
    )
    registry.add("https://files.pythonhosted.org/packages/demo-1.0.0-py3-none-any.whl", payload)
    with pytest.raises(SourceError) as raised:
        await resolve_source(
            PackageIntent(ecosystem="pypi", name="demo", version="1.0.0"),
            fetch=registry.fetch,
        )
    assert raised.value.code == INTEGRITY_MISMATCH


@pytest.mark.asyncio
async def test_crates_records_checksum_and_lock_or_resolved_graph() -> None:
    locked = _tar(
        {"Cargo.lock": "[[package]]\nname = 'demo'\n", "Cargo.toml": "[package]"},
        prefix="demo-1.0.0/",
    )
    registry = Registry()
    registry.add(
        "https://crates.io/api/v1/crates/demo/1.0.0",
        {"version": {"checksum": _sha256_hex(locked)}},
    )
    registry.add("https://static.crates.io/crates/demo/demo-1.0.0.crate", locked)
    snapshot = await resolve_source(
        PackageIntent(ecosystem="crates.io", name="demo", version="1.0.0"),
        fetch=registry.fetch,
    )
    evidence = snapshot.package_evidence
    assert isinstance(evidence, CratesEvidence)
    assert evidence.lockfile_name == "Cargo.lock"
    assert evidence.resolved_graph == {}
    assert snapshot.files["Cargo.lock"].startswith(b"[[package]]")
    assert not any(url.endswith("/dependencies") for url, _headers in registry.calls)
    _assert_observation(snapshot)

    unlocked = _tar({"Cargo.toml": "[package]\nname = 'demo'\n"}, prefix="demo-1.0.1/")
    unlocked_registry = Registry()
    unlocked_registry.add(
        "https://crates.io/api/v1/crates/demo/1.0.1",
        {"version": {"checksum": _sha256_hex(unlocked)}},
    )
    unlocked_registry.add("https://static.crates.io/crates/demo/demo-1.0.1.crate", unlocked)
    unlocked_registry.add(
        "https://crates.io/api/v1/crates/demo/1.0.1/dependencies",
        {"dependencies": [{"crate_id": "serde", "req": "^1"}]},
    )
    graph_snapshot = await resolve_source(
        PackageIntent(ecosystem="crates.io", name="demo", version="1.0.1"),
        fetch=unlocked_registry.fetch,
    )
    graph = graph_snapshot.package_evidence
    assert isinstance(graph, CratesEvidence)
    assert graph.lockfile_name is None
    assert graph.resolved_graph == {"serde": "^1"}
    assert unlocked_registry.hosts() <= {"crates.io", "static.crates.io"}


@pytest.mark.asyncio
async def test_crates_checksum_mismatch_fails_closed() -> None:
    archive = _tar({"Cargo.toml": "[package]"}, prefix="demo-1.0.0/")
    registry = Registry()
    registry.add(
        "https://crates.io/api/v1/crates/demo/1.0.0",
        {"version": {"checksum": "a" * 64}},
    )
    registry.add("https://static.crates.io/crates/demo/demo-1.0.0.crate", archive)
    with pytest.raises(SourceError) as raised:
        await resolve_source(
            PackageIntent(ecosystem="crates.io", name="demo", version="1.0.0"),
            fetch=registry.fetch,
        )
    assert raised.value.code == INTEGRITY_MISMATCH


@pytest.mark.asyncio
async def test_go_records_module_zip_hash_and_sumdb_evidence() -> None:
    archive = _zip({"github.com/Azure/mod@v1.2.3/go.mod": "module github.com/Azure/mod\n"})
    zip_hash = _go_h1(archive)
    registry = Registry()
    registry.add(
        "https://proxy.golang.org/github.com/!azure/mod/@v/v1.2.3.info",
        {"Version": "v1.2.3", "Time": "2026-01-01T00:00:00Z"},
    )
    registry.add("https://proxy.golang.org/github.com/!azure/mod/@v/v1.2.3.zip", archive)
    registry.add(
        "https://sum.golang.org/lookup/github.com/!azure/mod@v1.2.3",
        f"111\ngithub.com/Azure/mod v1.2.3 {zip_hash}\n",
    )
    snapshot = await resolve_source(
        PackageIntent(ecosystem="go", name="github.com/Azure/mod", version="v1.2.3"),
        fetch=registry.fetch,
    )
    evidence = snapshot.package_evidence
    assert isinstance(evidence, GoEvidence)
    assert evidence.module == "github.com/Azure/mod"
    assert evidence.zip_hash == zip_hash
    assert evidence.sumdb_hash == zip_hash
    assert snapshot.files["go.mod"].startswith(b"module ")
    assert registry.hosts() == {"proxy.golang.org", "sum.golang.org"}
    _assert_observation(snapshot)


@pytest.mark.asyncio
async def test_go_version_and_checksum_mismatch_fail_closed() -> None:
    archive = _zip({"mod@v1.0.0/go.mod": "module example.com/mod\n"})
    registry = Registry()
    registry.add(
        "https://proxy.golang.org/example.com/mod/@v/v1.0.0.info",
        {"Version": "v1.0.1"},
    )
    with pytest.raises(SourceError) as version:
        await resolve_source(
            PackageIntent(ecosystem="go", name="example.com/mod", version="v1.0.0"),
            fetch=registry.fetch,
        )
    assert version.value.code == UNAVAILABLE_SOURCE

    mismatch = Registry()
    mismatch.add(
        "https://proxy.golang.org/example.com/mod/@v/v1.0.0.info",
        {"Version": "v1.0.0"},
    )
    mismatch.add("https://proxy.golang.org/example.com/mod/@v/v1.0.0.zip", archive)
    mismatch.add(
        "https://sum.golang.org/lookup/example.com/mod@v1.0.0",
        "example.com/mod v1.0.0 h1:aaaaaaaa\n",
    )
    with pytest.raises(SourceError) as integrity:
        await resolve_source(
            PackageIntent(ecosystem="go", name="example.com/mod", version="v1.0.0"),
            fetch=mismatch.fetch,
        )
    assert integrity.value.code == INTEGRITY_MISMATCH


@pytest.mark.asyncio
async def test_pub_records_archive_checksum_and_lock_or_graph() -> None:
    locked = _tar(
        {"pubspec.yaml": "name: demo\n", "pubspec.lock": "packages: {}\n"}, prefix="demo-1.0.0/"
    )
    registry = Registry()
    archive_url = "https://storage.googleapis.com/pub-packages/packages/demo-1.0.0.tar.gz"
    registry.add(
        "https://pub.dev/api/packages/demo/versions/1.0.0",
        {
            "archive_url": archive_url,
            "archive_sha256": _sha256_hex(locked),
            "pubspec": {"dependencies": {"http": "^1.0.0"}},
        },
    )
    registry.add(archive_url, locked)
    snapshot = await resolve_source(
        PackageIntent(ecosystem="pub.dev", name="demo", version="1.0.0"),
        fetch=registry.fetch,
    )
    evidence = snapshot.package_evidence
    assert isinstance(evidence, PubEvidence)
    assert evidence.lockfile_name == "pubspec.lock"
    assert evidence.resolved_graph == {}
    _assert_observation(snapshot)

    unlocked = _tar({"pubspec.yaml": "name: demo\n"}, prefix="demo-1.0.1/")
    unlocked_url = "https://storage.googleapis.com/pub-packages/packages/demo-1.0.1.tar.gz"
    unlocked_registry = Registry()
    unlocked_registry.add(
        "https://pub.dev/api/packages/demo/versions/1.0.1",
        {
            "archive_url": unlocked_url,
            "archive_sha256": _sha256_hex(unlocked),
            "pubspec": {"dependencies": {"http": "^1.0.0"}},
        },
    )
    unlocked_registry.add(unlocked_url, unlocked)
    graph_snapshot = await resolve_source(
        PackageIntent(ecosystem="pub.dev", name="demo", version="1.0.1"),
        fetch=unlocked_registry.fetch,
    )
    graph = graph_snapshot.package_evidence
    assert isinstance(graph, PubEvidence)
    assert graph.lockfile_name is None
    assert graph.resolved_graph == {"http": "^1.0.0"}
    assert unlocked_registry.hosts() <= {"pub.dev", "storage.googleapis.com"}


@pytest.mark.asyncio
async def test_pub_rejects_non_package_storage_and_digest_mismatch() -> None:
    archive = _tar({"pubspec.yaml": "name: demo\n"}, prefix="demo-1.0.0/")
    registry = Registry()
    registry.add(
        "https://pub.dev/api/packages/demo/versions/1.0.0",
        {
            "archive_url": "https://storage.googleapis.com/other-bucket/demo.tar.gz",
            "archive_sha256": _sha256_hex(archive),
        },
    )
    with pytest.raises(SourceError) as storage:
        await resolve_source(
            PackageIntent(ecosystem="pub.dev", name="demo", version="1.0.0"),
            fetch=registry.fetch,
        )
    assert storage.value.code == UNSAFE_ARCHIVE

    mismatch = Registry()
    url = "https://storage.googleapis.com/pub-packages/packages/demo-1.0.0.tar.gz"
    mismatch.add(
        "https://pub.dev/api/packages/demo/versions/1.0.0",
        {"archive_url": url, "archive_sha256": "a" * 64},
    )
    mismatch.add(url, archive)
    with pytest.raises(SourceError) as integrity:
        await resolve_source(
            PackageIntent(ecosystem="pub.dev", name="demo", version="1.0.0"),
            fetch=mismatch.fetch,
        )
    assert integrity.value.code == INTEGRITY_MISMATCH


@pytest.mark.asyncio
async def test_registry_credentials_query_and_foreign_hosts_fail_closed() -> None:
    cases = [
        (
            "https://registry.npmjs.org/demo/1.0.0",
            {
                "dist": {
                    "tarball": "https://user:token@registry.npmjs.org/demo/-/demo-1.0.0.tgz",
                    "integrity": "sha512-x",
                }
            },
        ),
        (
            "https://registry.npmjs.org/demo/1.0.0",
            {
                "dist": {
                    "tarball": "https://registry.npmjs.org/demo/-/demo-1.0.0.tgz?token=secret",
                    "integrity": "sha512-x",
                }
            },
        ),
        (
            "https://registry.npmjs.org/demo/1.0.0",
            {
                "dist": {
                    "tarball": "https://evil.test/demo-1.0.0.tgz",
                    "integrity": "sha512-x",
                }
            },
        ),
    ]
    for meta_url, body in cases:
        registry = Registry()
        registry.add(meta_url, body)
        with pytest.raises(SourceError) as raised:
            await resolve_source(
                PackageIntent(ecosystem="npm", name="demo", version="1.0.0"),
                fetch=registry.fetch,
            )
        assert raised.value.code == UNSAFE_ARCHIVE


@pytest.mark.asyncio
async def test_registry_redirect_and_size_bounds_fail_closed() -> None:
    off_host = Registry()
    off_host.add(
        "https://registry.npmjs.org/demo/1.0.0",
        b"",
        status=302,
        headers={"location": "https://evil.test/meta"},
    )
    with pytest.raises(SourceError) as redirect:
        await resolve_source(
            PackageIntent(ecosystem="npm", name="demo", version="1.0.0"),
            fetch=off_host.fetch,
        )
    assert redirect.value.code == UNSAFE_ARCHIVE

    looping = Registry()
    looping.add(
        "https://registry.npmjs.org/demo/1.0.0",
        b"",
        status=302,
        headers={"location": "https://registry.npmjs.org/demo/a"},
    )
    looping.add(
        "https://registry.npmjs.org/demo/a",
        b"",
        status=302,
        headers={"location": "https://registry.npmjs.org/demo/b"},
    )
    looping.add(
        "https://registry.npmjs.org/demo/b",
        b"",
        status=302,
        headers={"location": "https://registry.npmjs.org/demo/c"},
    )
    with pytest.raises(SourceError) as hops:
        await resolve_source(
            PackageIntent(ecosystem="npm", name="demo", version="1.0.0"),
            fetch=looping.fetch,
        )
    assert hops.value.code == UNSAFE_ARCHIVE

    huge = Registry()
    huge.add(
        "https://registry.npmjs.org/demo/1.0.0",
        b"{}",
        headers={"content-length": str(2 * 1024 * 1024)},
    )
    with pytest.raises(SourceError) as size:
        await resolve_source(
            PackageIntent(ecosystem="npm", name="demo", version="1.0.0"),
            fetch=huge.fetch,
        )
    assert size.value.code == UNSAFE_ARCHIVE


@pytest.mark.asyncio
async def test_dependency_graph_bound_and_unavailable_metadata_fail_closed() -> None:
    deps = {f"pkg-{index}": "1.0.0" for index in range(MAX_GRAPH_ENTRIES + 1)}
    archive = _tar({"package.json": json.dumps({"dependencies": deps})}, prefix="package/")
    registry = Registry()
    registry.add(
        "https://registry.npmjs.org/demo/1.0.0",
        {
            "dist": {
                "tarball": "https://registry.npmjs.org/demo/-/demo-1.0.0.tgz",
                "integrity": _sri_sha512(archive),
            }
        },
    )
    registry.add("https://registry.npmjs.org/demo/-/demo-1.0.0.tgz", archive)
    with pytest.raises(SourceError) as graph:
        await resolve_source(
            PackageIntent(ecosystem="npm", name="demo", version="1.0.0"),
            fetch=registry.fetch,
        )
    assert graph.value.code == UNSAFE_ARCHIVE

    missing = Registry()
    missing.add("https://registry.npmjs.org/demo/1.0.0", b"{}", status=404)
    with pytest.raises(SourceError) as unavailable:
        await resolve_source(
            PackageIntent(ecosystem="npm", name="demo", version="1.0.0"),
            fetch=missing.fetch,
        )
    assert unavailable.value.code == UNAVAILABLE_SOURCE


def test_frozen_package_without_evidence_is_rejected() -> None:
    snapshot = SourceSnapshot(
        kind="package",
        canonical_coordinate="package:npm:demo@1.0.0",
        exact_identity="1.0.0",
        archive_digest=DIGEST,
        component_digest=DIGEST,
    )
    with pytest.raises(SourceError) as raised:
        validate_frozen_snapshot(snapshot)
    assert raised.value.code == FLOATING_FROZEN_SOURCE


@pytest.mark.asyncio
async def test_package_resolution_without_fetch_is_invalid_source() -> None:
    with pytest.raises(SourceError) as raised:
        await resolve_source(PackageIntent(ecosystem="npm", name="demo", version="1.0.0"))
    assert raised.value.code == INVALID_SOURCE
