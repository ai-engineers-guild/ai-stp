"""Official package-registry adapters (SPEC-057 REQ-5703, REQ-5704, REQ-5718)."""

from __future__ import annotations

import base64
import hashlib
from datetime import UTC, datetime
from typing import cast
from urllib.parse import quote, urlsplit

from ai_stp_foundation.digests import digest_bytes
from ai_stp_sources.archive import MAX_ARCHIVE_BYTES, read_named_members
from ai_stp_sources.coordinates import canonicalize_source
from ai_stp_sources.errors import (
    AMBIGUOUS_DISTRIBUTION,
    INTEGRITY_MISMATCH,
    UNAVAILABLE_SOURCE,
    UNSAFE_ARCHIVE,
    SourceError,
)
from ai_stp_sources.files import ARTIFACT_DIGEST_DOMAIN, files_digest
from ai_stp_sources.git import FetchFn
from ai_stp_sources.http import MAX_GRAPH_ENTRIES, MAX_JSON_BYTES, bounded_get, json_object
from ai_stp_sources.models import (
    CratesEvidence,
    GoEvidence,
    NpmEvidence,
    PackageIntent,
    PubEvidence,
    PypiEvidence,
    SourceSnapshot,
)

_NPM_HOSTS = frozenset({"registry.npmjs.org"})
_PYPI_HOSTS = frozenset({"pypi.org", "files.pythonhosted.org"})
_CRATES_HOSTS = frozenset({"crates.io", "static.crates.io"})
_GO_HOSTS = frozenset({"proxy.golang.org", "sum.golang.org"})
_PUB_HOSTS = frozenset({"pub.dev", "storage.googleapis.com"})
_NPM_SCRIPT_KEYS = frozenset(
    {
        "preinstall",
        "install",
        "postinstall",
        "prepare",
        "prepublish",
        "prepublishOnly",
        "preuninstall",
        "uninstall",
        "postuninstall",
    }
)


def _sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sri_sha512(payload: bytes) -> str:
    digest = base64.b64encode(hashlib.sha512(payload).digest()).decode("ascii")
    return f"sha512-{digest}"


def _go_h1(payload: bytes) -> str:
    digest = base64.b64encode(hashlib.sha256(payload).digest()).decode("ascii")
    return f"h1:{digest}"


def _bounded_graph(values: dict[str, str]) -> dict[str, str]:
    if len(values) > MAX_GRAPH_ENTRIES:
        raise SourceError(UNSAFE_ARCHIVE, "dependency graph exceeds the accepted size")
    return values


def _object_list(raw: object) -> list[object]:
    if not isinstance(raw, list):
        return []
    return cast(list[object], raw)


def _object_dicts(raw: object) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for item in _object_list(raw):
        if isinstance(item, dict):
            items.append(cast(dict[str, object], item))
    return items


def _string_list(raw: object) -> list[str]:
    return [item for item in _object_list(raw) if isinstance(item, str)]


def _string_map(raw: object) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    values: dict[str, str] = {}
    for key, value in cast(dict[str, object], raw).items():
        if isinstance(value, str):
            values[key] = value
    return _bounded_graph(values)


def _snapshot(
    intent: PackageIntent,
    *,
    archive: bytes,
    files: dict[str, bytes],
    evidence: NpmEvidence | PypiEvidence | CratesEvidence | GoEvidence | PubEvidence,
    extra: str = "",
    now: datetime | None,
) -> SourceSnapshot:
    coordinate = f"package:{intent.ecosystem}:{intent.name}@{intent.version}{extra}"
    return SourceSnapshot(
        kind="package",
        canonical_coordinate=coordinate,
        exact_identity=intent.version,
        archive_digest=digest_bytes(ARTIFACT_DIGEST_DOMAIN, archive),
        component_digest=files_digest(files)
        if files
        else digest_bytes(ARTIFACT_DIGEST_DOMAIN, archive),
        files=files,
        package_evidence=evidence,
        fetched_at=now or datetime.now(UTC),
    )


def _require_ok(response_status: int, *, label: str) -> None:
    if response_status != 200:
        raise SourceError(UNAVAILABLE_SOURCE, f"{label} is unavailable")


async def resolve_package(
    intent: PackageIntent,
    *,
    fetch: FetchFn,
    now: datetime | None = None,
) -> SourceSnapshot:
    canonical = canonicalize_source(intent)
    assert isinstance(canonical, PackageIntent)
    if canonical.ecosystem == "npm":
        return await _resolve_npm(canonical, fetch=fetch, now=now)
    if canonical.ecosystem == "pypi":
        return await _resolve_pypi(canonical, fetch=fetch, now=now)
    if canonical.ecosystem == "crates.io":
        return await _resolve_crates(canonical, fetch=fetch, now=now)
    if canonical.ecosystem == "go":
        return await _resolve_go(canonical, fetch=fetch, now=now)
    return await _resolve_pub(canonical, fetch=fetch, now=now)


async def _resolve_npm(
    intent: PackageIntent, *, fetch: FetchFn, now: datetime | None
) -> SourceSnapshot:
    encoded = quote(intent.name, safe="@/")
    meta = await bounded_get(
        f"https://registry.npmjs.org/{encoded}/{quote(intent.version, safe='')}",
        fetch=fetch,
        allowed_hosts=_NPM_HOSTS,
        max_bytes=MAX_JSON_BYTES,
    )
    _require_ok(meta.status_code, label="npm metadata")
    body = json_object(meta.body)
    dist_raw = body.get("dist")
    if not isinstance(dist_raw, dict):
        raise SourceError(UNAVAILABLE_SOURCE, "npm dist metadata is missing")
    dist = cast(dict[str, object], dist_raw)
    tarball = dist.get("tarball")
    if not isinstance(tarball, str):
        raise SourceError(UNAVAILABLE_SOURCE, "npm tarball URL is missing")
    archive_response = await bounded_get(
        tarball, fetch=fetch, allowed_hosts=_NPM_HOSTS, max_bytes=MAX_ARCHIVE_BYTES
    )
    _require_ok(archive_response.status_code, label="npm tarball")
    archive = archive_response.body
    integrity = dist.get("integrity")
    if (
        isinstance(integrity, str)
        and integrity.startswith("sha512-")
        and _sri_sha512(archive) != integrity
    ):
        raise SourceError(INTEGRITY_MISMATCH, "npm tarball digest does not match integrity")
    files = read_named_members(
        archive, frozenset({"package.json", "package-lock.json", "npm-shrinkwrap.json"})
    )
    manifest = json_object(files.get("package.json", b"{}"))
    scripts_raw = manifest.get("scripts")
    scripts = {
        key: value for key, value in _string_map(scripts_raw).items() if key in _NPM_SCRIPT_KEYS
    }
    lock_name = next(
        (name for name in ("package-lock.json", "npm-shrinkwrap.json") if name in files), None
    )
    repository = _https_repository(body.get("repository") or manifest.get("repository"))
    entry = manifest.get("main")
    evidence = NpmEvidence(
        integrity=integrity if isinstance(integrity, str) else None,
        entry_point=entry if isinstance(entry, str) else None,
        lifecycle_scripts=scripts,
        repository=repository,
        lockfile_name=lock_name,
        declared_dependencies=_string_map(manifest.get("dependencies")),
    )
    return _snapshot(intent, archive=archive, files=files, evidence=evidence, now=now)


def _https_repository(raw: object) -> str | None:
    if isinstance(raw, dict):
        raw = cast(dict[str, object], raw).get("url")
    if not isinstance(raw, str):
        return None
    cleaned = raw.removeprefix("git+").removesuffix(".git")
    parsed = urlsplit(cleaned)
    if parsed.scheme != "https" or parsed.username or parsed.password or not parsed.hostname:
        return None
    path = parsed.path.rstrip("/")
    return f"https://{parsed.hostname}{path}"


async def _resolve_pypi(
    intent: PackageIntent, *, fetch: FetchFn, now: datetime | None
) -> SourceSnapshot:
    name = quote(intent.name, safe="")
    version = quote(intent.version, safe="")
    meta = await bounded_get(
        f"https://pypi.org/pypi/{name}/{version}/json",
        fetch=fetch,
        allowed_hosts=_PYPI_HOSTS,
        max_bytes=MAX_JSON_BYTES,
    )
    _require_ok(meta.status_code, label="PyPI metadata")
    body = json_object(meta.body)
    urls_raw = body.get("urls")
    files_meta = _object_dicts(urls_raw)
    if not files_meta:
        raise SourceError(UNAVAILABLE_SOURCE, "PyPI files are missing")
    if len(files_meta) > 1 and (intent.filename is None or intent.platform is None):
        raise SourceError(
            AMBIGUOUS_DISTRIBUTION,
            "PyPI release has more than one file; filename and platform are required",
        )
    matches: list[dict[str, object]] = files_meta
    if intent.filename is not None:
        matches = [item for item in matches if item.get("filename") == intent.filename]
    elif intent.platform is not None:
        matches = [
            item
            for item in matches
            if isinstance(item.get("filename"), str)
            and intent.platform in str(item.get("filename"))
        ]
    if len(matches) != 1:
        raise SourceError(
            AMBIGUOUS_DISTRIBUTION, "PyPI file and platform do not select one distribution"
        )
    chosen = matches[0]
    filename = chosen.get("filename")
    url = chosen.get("url")
    digests_raw = chosen.get("digests")
    if (
        not isinstance(filename, str)
        or not isinstance(url, str)
        or not isinstance(digests_raw, dict)
    ):
        raise SourceError(UNAVAILABLE_SOURCE, "PyPI file metadata is incomplete")
    expected = cast(dict[str, object], digests_raw).get("sha256")
    if not isinstance(expected, str) or len(expected) != 64:
        raise SourceError(UNAVAILABLE_SOURCE, "PyPI sha256 is missing")
    archive_response = await bounded_get(
        url, fetch=fetch, allowed_hosts=_PYPI_HOSTS, max_bytes=MAX_ARCHIVE_BYTES
    )
    _require_ok(archive_response.status_code, label="PyPI file")
    archive = archive_response.body
    if _sha256_hex(archive) != expected:
        raise SourceError(INTEGRITY_MISMATCH, "PyPI file digest does not match registry sha256")
    info_raw = body.get("info")
    requires: list[str] = []
    if isinstance(info_raw, dict):
        dist = cast(dict[str, object], info_raw).get("requires_dist")
        requires = _string_list(dist)[:MAX_GRAPH_ENTRIES]
    platform = intent.platform or "any"
    extra = f":{filename}"
    evidence = PypiEvidence(
        filename=filename,
        platform=platform,
        registry_sha256=expected,
        requires_dist=tuple(requires),
    )
    return _snapshot(intent, archive=archive, files={}, evidence=evidence, extra=extra, now=now)


async def _resolve_crates(
    intent: PackageIntent, *, fetch: FetchFn, now: datetime | None
) -> SourceSnapshot:
    crate_name = quote(intent.name, safe="")
    crate_version = quote(intent.version, safe="")
    meta = await bounded_get(
        f"https://crates.io/api/v1/crates/{crate_name}/{crate_version}",
        fetch=fetch,
        allowed_hosts=_CRATES_HOSTS,
        max_bytes=MAX_JSON_BYTES,
    )
    _require_ok(meta.status_code, label="crates.io metadata")
    version_raw = json_object(meta.body).get("version")
    if not isinstance(version_raw, dict):
        raise SourceError(UNAVAILABLE_SOURCE, "crates.io version metadata is missing")
    version = cast(dict[str, object], version_raw)
    checksum = version.get("checksum")
    if not isinstance(checksum, str) or len(checksum) != 64:
        raise SourceError(UNAVAILABLE_SOURCE, "crates.io checksum is missing")
    crate_url = f"https://static.crates.io/crates/{crate_name}/{crate_name}-{crate_version}.crate"
    archive_response = await bounded_get(
        crate_url, fetch=fetch, allowed_hosts=_CRATES_HOSTS, max_bytes=MAX_ARCHIVE_BYTES
    )
    _require_ok(archive_response.status_code, label="crates.io crate")
    archive = archive_response.body
    if _sha256_hex(archive) != checksum:
        raise SourceError(INTEGRITY_MISMATCH, "crate digest does not match crates.io checksum")
    files = read_named_members(archive, frozenset({"Cargo.lock", "Cargo.toml"}))
    lock_name = "Cargo.lock" if "Cargo.lock" in files else None
    graph: dict[str, str] = {}
    if lock_name is None:
        deps = await bounded_get(
            f"https://crates.io/api/v1/crates/{crate_name}/{crate_version}/dependencies",
            fetch=fetch,
            allowed_hosts=_CRATES_HOSTS,
            max_bytes=MAX_JSON_BYTES,
        )
        _require_ok(deps.status_code, label="crates.io dependencies")
        deps_raw = json_object(deps.body).get("dependencies")
        for dep in _object_dicts(deps_raw):
            dep_name = dep.get("crate_id")
            req = dep.get("req")
            if isinstance(dep_name, str) and isinstance(req, str):
                graph[dep_name] = req
        graph = _bounded_graph(graph)
    evidence = CratesEvidence(
        registry_checksum=checksum, lockfile_name=lock_name, resolved_graph=graph
    )
    return _snapshot(intent, archive=archive, files=files, evidence=evidence, now=now)


def _go_module_path(module: str) -> str:
    encoded = "".join(f"!{char.lower()}" if char.isupper() else char for char in module)
    return quote(encoded, safe="/@!")


async def _resolve_go(
    intent: PackageIntent, *, fetch: FetchFn, now: datetime | None
) -> SourceSnapshot:
    module = _go_module_path(intent.name)
    version = quote(intent.version, safe="")
    info = await bounded_get(
        f"https://proxy.golang.org/{module}/@v/{version}.info",
        fetch=fetch,
        allowed_hosts=_GO_HOSTS,
        max_bytes=MAX_JSON_BYTES,
    )
    _require_ok(info.status_code, label="Go module info")
    info_body = json_object(info.body)
    resolved_version = info_body.get("Version")
    if not isinstance(resolved_version, str) or resolved_version != intent.version:
        raise SourceError(UNAVAILABLE_SOURCE, "Go module version did not match the exact pin")
    zip_response = await bounded_get(
        f"https://proxy.golang.org/{module}/@v/{version}.zip",
        fetch=fetch,
        allowed_hosts=_GO_HOSTS,
        max_bytes=MAX_ARCHIVE_BYTES,
    )
    _require_ok(zip_response.status_code, label="Go module zip")
    archive = zip_response.body
    zip_hash = _go_h1(archive)
    lookup = await bounded_get(
        f"https://sum.golang.org/lookup/{module}@{version}",
        fetch=fetch,
        allowed_hosts=_GO_HOSTS,
        max_bytes=MAX_JSON_BYTES,
    )
    _require_ok(lookup.status_code, label="Go checksum database")
    sumdb_hash = _parse_sumdb(lookup.body.decode("utf-8"), intent.name, intent.version)
    if zip_hash != sumdb_hash:
        raise SourceError(INTEGRITY_MISMATCH, "Go zip hash does not match the checksum database")
    files = read_named_members(archive, frozenset({"go.mod", "go.sum"}))
    evidence = GoEvidence(module=intent.name, zip_hash=zip_hash, sumdb_hash=sumdb_hash)
    return _snapshot(intent, archive=archive, files=files, evidence=evidence, now=now)


def _parse_sumdb(text: str, module: str, version: str) -> str:
    for line in text.splitlines():
        parts = line.split()
        if (
            len(parts) >= 3
            and parts[0] == module
            and parts[1] == version
            and parts[2].startswith("h1:")
        ):
            return parts[2]
    raise SourceError(UNAVAILABLE_SOURCE, "Go checksum database did not include the module")


async def _resolve_pub(
    intent: PackageIntent, *, fetch: FetchFn, now: datetime | None
) -> SourceSnapshot:
    name = quote(intent.name, safe="")
    version = quote(intent.version, safe="")
    meta = await bounded_get(
        f"https://pub.dev/api/packages/{name}/versions/{version}",
        fetch=fetch,
        allowed_hosts=_PUB_HOSTS,
        max_bytes=MAX_JSON_BYTES,
    )
    _require_ok(meta.status_code, label="pub.dev metadata")
    body = json_object(meta.body)
    archive_url = body.get("archive_url")
    expected = body.get("archive_sha256")
    if not isinstance(archive_url, str) or not isinstance(expected, str) or len(expected) != 64:
        raise SourceError(UNAVAILABLE_SOURCE, "pub.dev archive metadata is missing")
    parsed = urlsplit(archive_url)
    if parsed.hostname == "storage.googleapis.com" and not parsed.path.startswith("/pub-packages/"):
        raise SourceError(UNSAFE_ARCHIVE, "pub.dev archive left the official registry hosts")
    archive_response = await bounded_get(
        archive_url, fetch=fetch, allowed_hosts=_PUB_HOSTS, max_bytes=MAX_ARCHIVE_BYTES
    )
    _require_ok(archive_response.status_code, label="pub.dev archive")
    archive = archive_response.body
    if _sha256_hex(archive) != expected:
        raise SourceError(
            INTEGRITY_MISMATCH, "pub.dev archive digest does not match registry sha256"
        )
    files = read_named_members(archive, frozenset({"pubspec.yaml", "pubspec.lock"}))
    lock_name = "pubspec.lock" if "pubspec.lock" in files else None
    graph: dict[str, str] = {}
    pubspec = body.get("pubspec")
    if lock_name is None and isinstance(pubspec, dict):
        graph = _string_map(cast(dict[str, object], pubspec).get("dependencies"))
    evidence = PubEvidence(registry_sha256=expected, lockfile_name=lock_name, resolved_graph=graph)
    return _snapshot(intent, archive=archive, files=files, evidence=evidence, now=now)
