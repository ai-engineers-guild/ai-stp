"""Observe GitHub archived state without turning it into lifecycle (SPEC-044)."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal, cast
from urllib.parse import quote, urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.github_token import github_api_token
from ai_stp_cli.local import cache, component_passports, revisions, versions
from ai_stp_contracts.github_evidence import GitHubArchiveEvidence, GitHubArchiveHistory
from ai_stp_foundation.canonical import JsonValue

API_ROOT = "https://api.github.com"
API_VERSION = "2022-11-28"
TTL = timedelta(hours=24)
MAX_RESPONSE_BYTES = 1_048_576


class _RepositoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    id: Annotated[int, Field(gt=0)]
    full_name: Annotated[str, Field(pattern=r"^[^/\s]+/[^/\s]+$")]
    archived: bool
    private: bool


@dataclass(frozen=True)
class _Coordinate:
    stable_id: str
    version: str
    passport_digest: str
    source_repository: str
    owner: str
    repository: str


def refresh(
    connection: sqlite3.Connection,
    stable_id: str,
    version: str,
    *,
    at: str,
    transport: httpx.BaseTransport | None = None,
) -> GitHubArchiveEvidence:
    """Fetch one official public repository observation and append it."""
    coordinate = _coordinate(connection, stable_id, version)
    previous = _latest_row(connection, stable_id, version)
    path = (
        f"/repositories/{int(previous['repository_id'])}"
        if previous is not None
        else f"/repos/{quote(coordinate.owner, safe='')}/{quote(coordinate.repository, safe='')}"
    )
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": API_VERSION,
        "User-Agent": "ai-stp-cli",
    }
    token = github_api_token()
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if previous is not None and previous["etag"] is not None:
        headers["If-None-Match"] = str(previous["etag"])

    try:
        with (
            httpx.Client(
                base_url=API_ROOT,
                timeout=httpx.Timeout(30.0, connect=5.0),
                follow_redirects=False,
                transport=transport,
                headers=headers,
            ) as client,
            client.stream("GET", path) as response,
        ):
            if response.status_code == 304 and previous is not None:
                return _append(
                    connection,
                    coordinate,
                    repository_id=int(previous["repository_id"]),
                    full_name=str(previous["repository_full_name"]),
                    archived=bool(previous["archived"]),
                    etag=(str(previous["etag"]) if previous["etag"] is not None else None),
                    at=at,
                    response_kind="not_modified",
                )
            if response.status_code != 200:
                raise _unavailable(
                    "GitHub repository metadata is unavailable",
                    status=str(response.status_code),
                )
            declared_length = response.headers.get("content-length")
            if declared_length is not None and (
                not declared_length.isdigit() or int(declared_length) > MAX_RESPONSE_BYTES
            ):
                raise _unavailable("GitHub repository metadata exceeds the bounded response size")
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > MAX_RESPONSE_BYTES:
                    raise _unavailable(
                        "GitHub repository metadata exceeds the bounded response size"
                    )
            etag = response.headers.get("etag")
    except httpx.HTTPError as error:
        raise _unavailable("GitHub repository metadata is unavailable") from error
    try:
        raw = cast(dict[str, object], json.loads(body))
        parsed = _RepositoryResponse.model_validate(
            {name: raw.get(name) for name in ("id", "full_name", "archived", "private")}
        )
    except (json.JSONDecodeError, UnicodeDecodeError, ValidationError, TypeError) as error:
        raise _unavailable("GitHub repository metadata is malformed") from error
    if parsed.private:
        raise _unavailable("GitHub repository metadata is unavailable")
    if previous is not None and int(previous["repository_id"]) != parsed.id:
        raise CliFailure(
            "AI_STP_CONFLICT",
            "the GitHub coordinate now resolves to another repository identity",
            details={"stable_id": stable_id, "version": version},
        )
    return _append(
        connection,
        coordinate,
        repository_id=parsed.id,
        full_name=parsed.full_name,
        archived=parsed.archived,
        etag=etag,
        at=at,
        response_kind="modified",
    )


def show(
    connection: sqlite3.Connection, stable_id: str, version: str, *, at: str
) -> GitHubArchiveEvidence:
    coordinate = _coordinate(connection, stable_id, version)
    row = _latest_row(connection, stable_id, version)
    if row is None:
        return GitHubArchiveEvidence(
            observation_id=None,
            stable_id=stable_id,
            version=version,
            passport_digest=coordinate.passport_digest,
            source_repository=coordinate.source_repository,
            repository_id=None,
            repository_full_name=None,
            repository_state="unavailable",
            archived=None,
            fetched_at=None,
            expires_at=None,
            freshness="unavailable",
        )
    return _view(row, at=at)


def history(
    connection: sqlite3.Connection,
    stable_id: str,
    version: str,
    *,
    at: str,
    limit: int = 100,
) -> GitHubArchiveHistory:
    _coordinate(connection, stable_id, version)
    if limit < 1 or limit > 100:
        raise CliFailure("AI_STP_VALIDATION_ERROR", "history limit must be between 1 and 100")
    rows = connection.execute(
        "SELECT * FROM github_repository_observation "
        "WHERE stable_id = ? AND version = ? ORDER BY observation_id DESC LIMIT ?",
        (stable_id, version, limit),
    ).fetchall()
    return GitHubArchiveHistory(
        stable_id=stable_id,
        version=version,
        observations=[_view(row, at=at) for row in reversed(rows)],
    )


def _coordinate(connection: sqlite3.Connection, stable_id: str, version: str) -> _Coordinate:
    recorded = versions.held(connection, stable_id, version)
    if recorded is None:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "that object has no such recorded version",
            details={"id": stable_id, "version": version},
        )
    stored = revisions.get(connection, recorded.revision_id)
    if stored is None:
        raise CliFailure("AI_STP_CONFLICT", "the recorded version revision is missing")
    document = cast(dict[str, JsonValue], stored.envelope.model_dump(mode="json"))
    if cache.digest_of(cast(JsonValue, document)) != recorded.passport_digest:
        raise CliFailure("AI_STP_CONFLICT", "the recorded version passport digest does not match")
    source = document.get("source")
    if not isinstance(source, dict):
        # An adopted draft declares its source as a fact rather than as a
        # top-level field, the way every other declared value travels; the
        # public passport of a corpus version carries it at the top. Reading
        # only the top level made evidence unreachable for any component this
        # machine adopted and enriched, however exact its declared source.
        source = component_passports.declared_values(document).get("source")
    repository = source.get("repository") if isinstance(source, dict) else None
    if not isinstance(repository, str):
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the exact version has no public GitHub source",
            details={"id": stable_id, "version": version},
            next_actions=[f"component passport suggest --id {stable_id} --json"],
        )
    parsed = urlsplit(repository)
    parts = parsed.path.strip("/").split("/")
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
        raise CliFailure("AI_STP_VALIDATION_ERROR", "the exact version source is not public GitHub")
    repo = parts[1].removesuffix(".git")
    if not repo:
        raise CliFailure("AI_STP_VALIDATION_ERROR", "the exact version source is not public GitHub")
    return _Coordinate(stable_id, version, recorded.passport_digest, repository, parts[0], repo)


def _append(
    connection: sqlite3.Connection,
    coordinate: _Coordinate,
    *,
    repository_id: int,
    full_name: str,
    archived: bool,
    etag: str | None,
    at: str,
    response_kind: Literal["modified", "not_modified"],
) -> GitHubArchiveEvidence:
    expires_at = _format(_parse(at) + TTL)
    cursor = connection.execute(
        """
        INSERT INTO github_repository_observation
            (stable_id, version, passport_digest, source_repository, repository_id,
             repository_full_name, archived, etag, fetched_at, expires_at, response_kind)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            coordinate.stable_id,
            coordinate.version,
            coordinate.passport_digest,
            coordinate.source_repository,
            repository_id,
            full_name,
            int(archived),
            etag,
            at,
            expires_at,
            response_kind,
        ),
    )
    row = connection.execute(
        "SELECT * FROM github_repository_observation WHERE observation_id = ?",
        (cursor.lastrowid,),
    ).fetchone()
    return _view(row, at=at)


def _latest_row(connection: sqlite3.Connection, stable_id: str, version: str) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT * FROM github_repository_observation "
        "WHERE stable_id = ? AND version = ? ORDER BY observation_id DESC LIMIT 1",
        (stable_id, version),
    ).fetchone()


def _view(row: sqlite3.Row, *, at: str) -> GitHubArchiveEvidence:
    archived = bool(row["archived"])
    return GitHubArchiveEvidence(
        observation_id=int(row["observation_id"]),
        stable_id=str(row["stable_id"]),
        version=str(row["version"]),
        passport_digest=str(row["passport_digest"]),
        source_repository=str(row["source_repository"]),
        repository_id=int(row["repository_id"]),
        repository_full_name=str(row["repository_full_name"]),
        repository_state="archived" if archived else "active",
        archived=archived,
        fetched_at=str(row["fetched_at"]),
        expires_at=str(row["expires_at"]),
        freshness="fresh" if _parse(at) <= _parse(str(row["expires_at"])) else "stale",
        proposal="deprecated" if archived else "none",
    )


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _format(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _unavailable(message: str, **details: str) -> CliFailure:
    return CliFailure("AI_STP_DEPENDENCY_UNAVAILABLE", message, details=details)
