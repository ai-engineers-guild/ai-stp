"""Canonical source coordinates (SPEC-057 REQ-5701, REQ-5702)."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from ai_stp_foundation.refs import ComponentRef
from ai_stp_sources.errors import INVALID_SOURCE, SourceError
from ai_stp_sources.models import (
    CatalogIntent,
    GitIntent,
    PackageIntent,
    PathIntent,
    SourceIntent,
)

_TRAVERSAL = re.compile(r"(^|/|\\)\.\.(/|\\|$)")
_FLOATING_PACKAGE = re.compile(r"^(latest|\*|x|X)$|[~^<>]|^\s|\s$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


def canonical_github_source(repository: str) -> str | None:
    """Return the closed public GitHub source URL, or None when unsupported."""
    parsed = urlsplit(repository)
    parts = [part for part in parsed.path.split("/") if part]
    if (
        parsed.scheme != "https"
        or parsed.hostname != "github.com"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or len(parts) != 2
        or not all(parts)
    ):
        return None
    name = parts[1].removesuffix(".git")
    if not name:
        return None
    return f"https://github.com/{parts[0]}/{name}"


def canonical_subpath(subpath: str) -> str:
    """Return a relative POSIX subpath or raise."""
    cleaned = subpath.strip().replace("\\", "/")
    if cleaned == ".":
        return cleaned
    if (
        not cleaned
        or cleaned.startswith("/")
        or _TRAVERSAL.search(cleaned)
        or any(part in {"", ".", ".."} for part in cleaned.split("/"))
    ):
        raise SourceError(INVALID_SOURCE, "component subpath is empty or unsafe")
    return cleaned


def canonical_relative_path(relative_path: str) -> str:
    """Return a root-relative POSIX path; reject absolute and traversal names."""
    raw = relative_path.strip()
    if not raw:
        raise SourceError(INVALID_SOURCE, "local path is empty")
    if raw.startswith("/") or raw.startswith("\\") or (len(raw) >= 2 and raw[1] == ":"):
        raise SourceError(INVALID_SOURCE, "local absolute paths are not accepted")
    cleaned = raw.replace("\\", "/")
    if cleaned.startswith("/") or _TRAVERSAL.search(cleaned):
        raise SourceError(INVALID_SOURCE, "local path escapes the confirmed root")
    parts = [part for part in cleaned.split("/") if part not in {""}]
    if not parts or any(part == ".." or part == "." for part in parts):
        raise SourceError(INVALID_SOURCE, "local path escapes the confirmed root")
    return "/".join(parts)


def _canonical_filename(filename: str) -> str:
    cleaned = filename.strip().replace("\\", "/")
    if (
        not cleaned
        or "/" in cleaned
        or cleaned in {".", ".."}
        or cleaned.startswith("/")
        or "://" in cleaned
    ):
        raise SourceError(INVALID_SOURCE, "package filename is empty or unsafe")
    return cleaned


def canonicalize_source(intent: SourceIntent) -> SourceIntent:
    """Return a coordinate-canonical intent; never grants trust."""
    if isinstance(intent, CatalogIntent):
        ComponentRef(
            stable_id=intent.stable_id,
            variant_id=intent.variant_id,
            version=intent.version,
            passport_digest=intent.passport_digest,
        )
        return intent
    if isinstance(intent, GitIntent):
        repository = canonical_github_source(intent.repository_url)
        if repository is None:
            raise SourceError(INVALID_SOURCE, "repository must be a public https://github.com URL")
        ref = intent.tracked_ref.strip()
        if not ref:
            raise SourceError(INVALID_SOURCE, "tracked ref is required")
        return GitIntent(
            repository_url=repository,
            tracked_ref=ref,
            subpath=canonical_subpath(intent.subpath),
        )
    if isinstance(intent, PackageIntent):
        name = intent.name.strip()
        version = intent.version.strip()
        if not name or "://" in name or ("@" in name and not name.startswith("@")):
            raise SourceError(INVALID_SOURCE, "package name is empty or credential-bearing")
        if not version or _FLOATING_PACKAGE.search(version) is not None:
            raise SourceError(INVALID_SOURCE, "package version must be exact")
        filename = None if intent.filename is None else _canonical_filename(intent.filename)
        platform = None if intent.platform is None else intent.platform.strip()
        if intent.platform is not None and not platform:
            raise SourceError(INVALID_SOURCE, "package platform is empty")
        return PackageIntent(
            ecosystem=intent.ecosystem,
            name=name,
            version=version,
            filename=filename,
            platform=platform,
        )
    return PathIntent(relative_path=canonical_relative_path(intent.relative_path))
