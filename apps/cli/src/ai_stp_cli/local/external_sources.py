"""Parse external source names without turning an intent into provenance."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

from ai_stp_cli.errors import CliFailure

_SEGMENT = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,98}[A-Za-z0-9])?$")
_SHA = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class Intent:
    kind: str
    canonical: str
    owner: str | None = None
    repository: str | None = None
    ref: str | None = None
    subpath: str | None = None
    selector: str | None = None
    local_path: str | None = None
    collection_owner: str | None = None
    collection_handle: str | None = None


def parse(value: str, *, cwd: Path) -> Intent:
    """Return bounded syntax only; no returned field is a trust claim."""
    source = value.strip()
    if not source or len(source) > 2048 or any(ord(char) < 32 for char in source):
        raise _refused("the source identity is empty, too long, or contains controls")

    collection = _collection(source)
    if collection is not None:
        return collection
    slug = re.fullmatch(
        r"@([a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?)/([a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?)(?:@([^/\s]+))?",
        source,
    )
    if slug:
        return Intent("published", source, owner=slug[1], selector=slug[3], repository=slug[2])
    if _local(source):
        path = Path(source).expanduser()
        resolved = (
            path.resolve(strict=False) if path.is_absolute() else (cwd / path).resolve(strict=False)
        )
        return Intent("local", str(resolved), local_path=str(resolved))

    candidate = source[3:] if source.startswith("gh:") else source
    if candidate.startswith(("https://", "http://")):
        return _github_url(candidate)
    match = re.fullmatch(r"([^/]+)/([^/@]+)(?:@([^/]+)|/(.+))?", candidate)
    if match and _segment(match[1]) and _segment(match[2]):
        subpath = _subpath(match[4]) if match[4] else None
        repository = f"https://github.com/{match[1]}/{match[2]}"
        return Intent(
            "github",
            repository,
            owner=match[1],
            repository=repository,
            selector=match[3],
            subpath=subpath,
        )
    raise _refused("the source identity uses an unsupported or ambiguous form")


def resolve_exact(intent: Intent, *, commit: str | None = None) -> Intent:
    """Promote GitHub syntax only when a complete exact commit is present."""
    if intent.kind != "github":
        raise _refused("only a GitHub source intent can resolve to github/exact")
    revision = commit or intent.ref or ""
    if not _SHA.fullmatch(revision):
        raise _refused("GitHub provenance requires one full lowercase 40-character commit SHA")
    return Intent(**{**intent.__dict__, "kind": "github/exact", "ref": revision})


def _github_url(value: str) -> Intent:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.hostname != "github.com" or parsed.username:
        raise _refused("GitHub source URLs require credential-free HTTPS on github.com")
    parts = [unquote(part) for part in parsed.path.strip("/").split("/")]
    if len(parts) < 2 or not _segment(parts[0]) or not _segment(parts[1].removesuffix(".git")):
        raise _refused("the GitHub URL does not name an owner and repository")
    owner, repo = parts[0], parts[1].removesuffix(".git")
    ref = None
    subpath = None
    if len(parts) > 2:
        if len(parts) < 4 or parts[2] not in {"tree", "blob"}:
            raise _refused("the GitHub URL path must use tree or blob with an explicit ref")
        ref = parts[3]
        subpath = _subpath("/".join(parts[4:])) if len(parts) > 4 else None
    repository = f"https://github.com/{owner}/{repo}"
    return Intent("github", repository, owner, repository, ref, subpath)


def _collection(value: str) -> Intent | None:
    match = re.fullmatch(r"col:([^/\s]+)/([^/\s?#]+)", value, re.IGNORECASE)
    if match is None:
        parsed = urlsplit(value)
        parts = parsed.path.strip("/").split("/")
        if (
            parsed.scheme == "https"
            and parsed.hostname == "askill.sh"
            and len(parts) == 3
            and parts[0] == "c"
        ):
            match = re.fullmatch(r"([^/\s]+)/([^/\s?#]+)", "/".join(parts[1:]))
    if match is None:
        return None
    if not _segment(match[1]) or not _segment(match[2]):
        raise _refused("the collection owner or handle is invalid")
    canonical = f"https://askill.sh/c/{match[1]}/{match[2]}"
    return Intent("collection", canonical, collection_owner=match[1], collection_handle=match[2])


def _local(value: str) -> bool:
    return (
        value in {".", ".."}
        or value.startswith(("./", "../", "/", "~/"))
        or bool(re.match(r"^[A-Za-z]:[\\/]", value))
    )


def _segment(value: str) -> bool:
    return bool(_SEGMENT.fullmatch(value)) and value not in {".", ".."}


def _subpath(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or value.startswith("/")
        or "\\" in value
        or len(value) > 512
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise _refused("the source subpath is not a bounded relative POSIX path")
    return path.as_posix()


def _refused(message: str) -> CliFailure:
    return CliFailure("AI_STP_VALIDATION_ERROR", message)
