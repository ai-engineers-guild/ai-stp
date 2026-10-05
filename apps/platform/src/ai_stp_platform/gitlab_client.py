"""Bounded, read-only GitLab repository metadata requests."""

from __future__ import annotations

import ipaddress
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, cast
from urllib.parse import quote, unquote, urlsplit

import httpx

from ai_stp_foundation.timestamps import format_timestamp

MAX_GITLAB_API_BYTES = 262_144
# The repository archive is the one large payload the connector accepts;
# packages/sources applies the same ceiling to every upstream archive.
MAX_GITLAB_ARCHIVE_BYTES = 100 * 1024 * 1024


class GitLabError(RuntimeError):
    def __init__(self, reason: str, status: int = 0) -> None:
        super().__init__(reason)
        self.reason = reason
        self.status = status


@dataclass(frozen=True)
class GitLabIdentity:
    user_id: int
    username: str


@dataclass(frozen=True)
class GitLabRepository:
    repository_id: int
    namespace_id: int
    path_with_namespace: str
    repository_url: str
    default_branch: str | None
    last_activity_at: str | None
    visibility: str | None = None


_HOST = re.compile(r"^[a-z0-9]+(?:[a-z0-9.-]*[a-z0-9])?$")
_PATH = re.compile(r"^[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+$")
_LANGUAGE = re.compile(r"^[A-Za-z0-9+#._ -]{1,64}$")
_REVISION = re.compile(r"^[0-9a-f]{40}$")
_PROJECT_PATH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,254}$")
_BRANCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")
_VISIBILITY = {"private", "internal", "public"}
# Read-side API paths only: project metadata, language shares, commit lookup,
# the source archive, and exact-username member resolution. Mutation endpoints
# live behind _MUTATION_PATH on administration grants only.
_API_PATH = re.compile(
    r"projects(?:/[1-9][0-9]{0,15}(?:/languages|/repository/commits/"
    r"(?:[A-Za-z0-9._-]|%2F){1,384}|/repository/archive(?:\.tar\.gz|\.tar|"
    r"\.tar\.bz2|\.zip))?)?|user(?:s)?"
)
# Administration-side mutations: repository visibility edits, member grants and
# revocations, and top-level project creation. Anything else is refused before
# the request is even assembled.
_MUTATION_PATH = re.compile(r"projects(?:/[1-9][0-9]{0,15}(?:/members(?:/[1-9][0-9]{0,15})?)?)?")


def gitlab_base_url(value: str, *, allowed_hosts: Iterable[str]) -> str:
    """Accept only an exact, operator-allowlisted HTTPS authority."""
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        raise GitLabError("gitlab_base_url_denied") from None
    if (
        parsed.scheme != "https"
        or host is None
        or not _HOST.fullmatch(host)
        or host.startswith(".")
        or ".." in host
        or len(host) > 120
        or port not in {None, 443}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or host not in {"gitlab.com", *(item.lower() for item in allowed_hosts)}
    ):
        raise GitLabError("gitlab_base_url_denied")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise GitLabError("gitlab_base_url_denied")
    return f"https://{host}"


def _positive_id(value: object) -> int:
    if type(value) is not int or not 0 < value <= 9_007_199_254_740_991:
        raise GitLabError("invalid_gitlab_response")
    return value


def _valid_branch(value: object) -> bool:
    return isinstance(value, str) and bool(_BRANCH.fullmatch(value)) and ".." not in value


def _activity(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 40:
        raise GitLabError("invalid_gitlab_response")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise GitLabError("invalid_gitlab_response") from None
    if parsed.tzinfo is None:
        raise GitLabError("invalid_gitlab_response")
    return format_timestamp(parsed.astimezone(UTC))


def _repository(value: object, *, base_url: str) -> GitLabRepository:
    if not isinstance(value, dict):
        raise GitLabError("invalid_gitlab_response")
    fields = cast(dict[str, object], value)
    path = fields.get("path_with_namespace")
    url = fields.get("web_url")
    namespace_value = fields.get("namespace")
    namespace = (
        cast(dict[str, object], namespace_value) if isinstance(namespace_value, dict) else None
    )
    branch = fields.get("default_branch")
    activity = fields.get("last_activity_at")
    visibility = fields.get("visibility")
    if (
        not isinstance(path, str)
        or not _PATH.fullmatch(path)
        or any(part in {".", ".."} for part in path.split("/"))
        or not isinstance(url, str)
        or url != f"{base_url}/{path}"
        or not isinstance(namespace, dict)
        or (branch is not None and not _valid_branch(branch))
        or (visibility is not None and visibility not in _VISIBILITY)
    ):
        raise GitLabError("invalid_gitlab_response")
    return GitLabRepository(
        repository_id=_positive_id(fields.get("id")),
        namespace_id=_positive_id(namespace.get("id")),
        path_with_namespace=path,
        repository_url=url,
        default_branch=cast(str | None, branch),
        last_activity_at=_activity(activity),
        visibility=cast(str | None, visibility),
    )


class GitLabClient:
    def __init__(
        self,
        base_url: str,
        *,
        allowed_hosts: Iterable[str] = (),
        transport: httpx.AsyncBaseTransport | None = None,
        auth: Literal["private_token", "bearer", "anonymous"] = "private_token",
    ) -> None:
        self.base_url = gitlab_base_url(base_url, allowed_hosts=allowed_hosts)
        self.transport = transport
        self.auth = auth

    def _headers(self, token: str | None) -> dict[str, str]:
        if self.auth == "anonymous":
            return {}
        if not token or any(ord(character) < 33 or ord(character) > 126 for character in token):
            raise GitLabError("gitlab_credential_unavailable")
        if self.auth == "bearer":
            return {"Authorization": f"Bearer {token}"}
        return {"PRIVATE-TOKEN": token}

    async def _get_bytes(
        self,
        path: str,
        *,
        token: str | None,
        params: Mapping[str, str | int] | None = None,
        limit: int = MAX_GITLAB_API_BYTES,
    ) -> bytes:
        headers = self._headers(token)
        if not _API_PATH.fullmatch(path) or (
            "/repository/commits/" in path
            and not _valid_branch(unquote(path.split("/repository/commits/", 1)[1]))
        ):
            raise GitLabError("gitlab_path_invalid")
        url = f"{self.base_url}/api/v4/{path}"
        try:
            async with (
                httpx.AsyncClient(
                    timeout=httpx.Timeout(20.0, connect=5.0),
                    follow_redirects=False,
                    trust_env=False,
                    transport=self.transport,
                ) as client,
                client.stream("GET", url, headers=headers, params=params) as response,
            ):
                if response.status_code in {401, 403, 404}:
                    raise GitLabError("gitlab_repository_inaccessible")
                if response.status_code == 429:
                    raise GitLabError("gitlab_rate_limited")
                if response.status_code != 200:
                    raise GitLabError("gitlab_unavailable")
                declared = response.headers.get("content-length")
                if declared is not None and (not declared.isdigit() or int(declared) > limit):
                    raise GitLabError("gitlab_response_too_large")
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(body) + len(chunk) > limit:
                        raise GitLabError("gitlab_response_too_large")
                    body.extend(chunk)
        except (httpx.HTTPError, OSError):
            raise GitLabError("gitlab_unavailable") from None
        return bytes(body)

    async def _get(
        self, path: str, *, token: str | None, params: Mapping[str, str | int] | None = None
    ) -> object:
        body = await self._get_bytes(path, token=token, params=params)
        try:
            return cast(object, json.loads(body))
        except (ValueError, UnicodeDecodeError):
            raise GitLabError("invalid_gitlab_response") from None

    async def _mutate(
        self,
        method: Literal["POST", "PUT", "DELETE"],
        path: str,
        *,
        token: str,
        body: Mapping[str, str | int] | None = None,
        accepted: frozenset[int] = frozenset({200, 201, 204}),
    ) -> object:
        """One allowlisted administration call on an ``api``-scoped grant."""
        if not _MUTATION_PATH.fullmatch(path):
            raise GitLabError("gitlab_path_invalid")
        url = f"{self.base_url}/api/v4/{path}"
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(20.0, connect=5.0),
                follow_redirects=False,
                trust_env=False,
                transport=self.transport,
            ) as client:
                response = await client.request(
                    method,
                    url,
                    headers={**self._headers(token), "Accept": "application/json"},
                    json=dict(body) if body is not None else None,
                )
                declared = response.headers.get("content-length")
                if declared is not None and (
                    not declared.isdigit() or int(declared) > MAX_GITLAB_API_BYTES
                ):
                    raise GitLabError("invalid_gitlab_response")
                payload = await response.aread()
                if len(payload) > MAX_GITLAB_API_BYTES:
                    raise GitLabError("invalid_gitlab_response")
                status = response.status_code
        except (httpx.HTTPError, OSError):
            raise GitLabError("gitlab_unavailable") from None
        if status == 429:
            raise GitLabError("gitlab_rate_limited", status=429)
        if status in {401, 403}:
            raise GitLabError("gitlab_action_denied", status=403)
        if status == 404:
            raise GitLabError("gitlab_repository_inaccessible", status=404)
        if status == 409:
            raise GitLabError("gitlab_action_conflict", status=409)
        if status not in accepted:
            if status >= 500:
                raise GitLabError("gitlab_unavailable", status=status)
            raise GitLabError("gitlab_action_refused", status=422)
        if status == 204 or not payload:
            return None
        try:
            return cast(object, json.loads(payload))
        except (ValueError, UnicodeDecodeError):
            raise GitLabError("invalid_gitlab_response") from None

    async def oauth_token(self, payload: Mapping[str, str]) -> dict[str, object]:
        """Exchange or refresh an OAuth grant; the only write the connector ever
        sends — to the identity endpoint, never to a repository."""
        url = f"{self.base_url}/oauth/token"
        body = bytearray()
        try:
            async with (
                httpx.AsyncClient(
                    timeout=httpx.Timeout(20.0, connect=5.0),
                    follow_redirects=False,
                    trust_env=False,
                    transport=self.transport,
                ) as client,
                client.stream(
                    "POST", url, data=dict(payload), headers={"Accept": "application/json"}
                ) as response,
            ):
                declared = response.headers.get("content-length")
                if declared is not None and (
                    not declared.isdigit() or int(declared) > MAX_GITLAB_API_BYTES
                ):
                    raise GitLabError("invalid_gitlab_response")
                async for chunk in response.aiter_bytes():
                    if len(body) + len(chunk) > MAX_GITLAB_API_BYTES:
                        raise GitLabError("invalid_gitlab_response")
                    body.extend(chunk)
                status = response.status_code
        except (httpx.HTTPError, OSError):
            raise GitLabError("gitlab_unavailable") from None
        if status in {400, 401}:
            raise GitLabError("gitlab_grant_revoked")
        if status != 200:
            raise GitLabError("gitlab_unavailable")
        try:
            data = cast(object, json.loads(body))
        except (ValueError, UnicodeDecodeError):
            raise GitLabError("invalid_gitlab_response") from None
        if not isinstance(data, dict):
            raise GitLabError("invalid_gitlab_response")
        return cast(dict[str, object], data)

    async def user(self, *, token: str | None = None) -> GitLabIdentity:
        data = await self._get("user", token=token)
        if not isinstance(data, dict):
            raise GitLabError("invalid_gitlab_response")
        fields = cast(dict[str, object], data)
        username = fields.get("username")
        if not isinstance(username, str) or not username or len(username) > 255:
            raise GitLabError("invalid_gitlab_response")
        return GitLabIdentity(user_id=_positive_id(fields.get("id")), username=username)

    async def archive(self, project_id: int, *, sha: str, token: str | None = None) -> bytes:
        project_id = _positive_id(project_id)
        if not _REVISION.fullmatch(sha):
            raise GitLabError("gitlab_branch_invalid")
        return await self._get_bytes(
            f"projects/{project_id}/repository/archive.tar.gz",
            token=token,
            params={"sha": sha},
            limit=MAX_GITLAB_ARCHIVE_BYTES,
        )

    async def list_repositories(
        self, *, token: str | None = None, limit: int = 100
    ) -> list[GitLabRepository]:
        if not 1 <= limit <= 500:
            raise GitLabError("gitlab_limit_invalid")
        repositories: list[GitLabRepository] = []
        count = min(100, limit)
        for page in range(1, (limit - 1) // 100 + 2):
            data = await self._get(
                "projects",
                token=token,
                params={"membership": "true", "simple": "true", "per_page": count, "page": page},
            )
            if not isinstance(data, list):
                raise GitLabError("invalid_gitlab_response")
            rows = cast(list[object], data)
            if len(rows) > count:
                raise GitLabError("invalid_gitlab_response")
            repositories.extend(_repository(item, base_url=self.base_url) for item in rows)
            if len(rows) < count:
                break
        return repositories[:limit]

    async def repository(self, repository_id: int, *, token: str | None = None) -> GitLabRepository:
        repository_id = _positive_id(repository_id)
        data = await self._get(f"projects/{repository_id}", token=token)
        repository = _repository(data, base_url=self.base_url)
        if repository.repository_id != repository_id:
            raise GitLabError("invalid_gitlab_response")
        return repository

    async def languages(self, repository_id: int, *, token: str | None = None) -> dict[str, float]:
        repository_id = _positive_id(repository_id)
        data = await self._get(f"projects/{repository_id}/languages", token=token)
        if not isinstance(data, dict):
            raise GitLabError("invalid_gitlab_response")
        languages = cast(dict[object, object], data)
        if len(languages) > 64 or any(
            not isinstance(name, str)
            or not _LANGUAGE.fullmatch(name)
            or not isinstance(share, (int, float))
            or isinstance(share, bool)
            or not 0 <= share <= 100
            for name, share in languages.items()
        ):
            raise GitLabError("invalid_gitlab_response")
        return {cast(str, name): float(cast(float, share)) for name, share in languages.items()}

    async def head_revision(
        self, repository_id: int, branch: str, *, token: str | None = None
    ) -> str:
        repository_id = _positive_id(repository_id)
        if not _valid_branch(branch):
            raise GitLabError("gitlab_branch_invalid")
        data = await self._get(
            f"projects/{repository_id}/repository/commits/{quote(branch, safe='')}",
            token=token,
        )
        if not isinstance(data, dict):
            raise GitLabError("invalid_gitlab_response")
        revision = cast(dict[str, object], data).get("id")
        if not isinstance(revision, str) or not _REVISION.fullmatch(revision):
            raise GitLabError("invalid_gitlab_response")
        return revision

    async def find_user(self, username: str, *, token: str) -> GitLabIdentity | None:
        """Resolve an exact username for access grants; anything loose is refused."""
        if len(username) > 255:
            raise GitLabError("invalid_gitlab_response")
        data = await self._get("users", token=token, params={"username": username, "per_page": 2})
        if not isinstance(data, list) or len(cast(list[object], data)) > 2:
            raise GitLabError("invalid_gitlab_response")
        matches: list[dict[str, object]] = [
            cast(dict[str, object], item)
            for item in cast(list[object], data)
            if isinstance(item, dict) and cast(dict[str, object], item).get("username") == username
        ]
        if not matches:
            return None
        fields = matches[0]
        return GitLabIdentity(
            user_id=_positive_id(fields.get("id")), username=cast(str, fields["username"])
        )

    async def set_visibility(
        self, project_id: int, visibility: str, *, token: str
    ) -> GitLabRepository:
        project_id = _positive_id(project_id)
        if visibility not in _VISIBILITY:
            raise GitLabError("gitlab_visibility_invalid")
        data = await self._mutate(
            "PUT",
            f"projects/{project_id}",
            token=token,
            body={"visibility": visibility},
        )
        repository = _repository(data, base_url=self.base_url)
        if repository.repository_id != project_id or repository.visibility != visibility:
            raise GitLabError("gitlab_action_outcome_unknown")
        return repository

    async def add_member(
        self, project_id: int, user_id: int, access_level: int, *, token: str
    ) -> None:
        project_id = _positive_id(project_id)
        user_id = _positive_id(user_id)
        if access_level not in {10, 20, 30, 40}:
            raise GitLabError("gitlab_access_level_invalid")
        await self._mutate(
            "POST",
            f"projects/{project_id}/members",
            token=token,
            body={"user_id": user_id, "access_level": access_level},
            accepted=frozenset({200, 201}),
        )

    async def remove_member(self, project_id: int, user_id: int, *, token: str) -> None:
        project_id = _positive_id(project_id)
        user_id = _positive_id(user_id)
        await self._mutate(
            "DELETE",
            f"projects/{project_id}/members/{user_id}",
            token=token,
            accepted=frozenset({204, 404}),
        )

    async def create_project(
        self, name: str, path: str, visibility: str, *, token: str
    ) -> GitLabRepository:
        if (
            not 1 <= len(name) <= 255
            or not _PROJECT_PATH.fullmatch(path)
            or visibility not in _VISIBILITY
        ):
            raise GitLabError("gitlab_visibility_invalid")
        data = await self._mutate(
            "POST",
            "projects",
            token=token,
            body={"name": name, "path": path, "visibility": visibility},
            accepted=frozenset({200, 201}),
        )
        repository = _repository(data, base_url=self.base_url)
        if repository.path_with_namespace.split("/")[-1] != path:
            raise GitLabError("gitlab_action_outcome_unknown")
        return repository
