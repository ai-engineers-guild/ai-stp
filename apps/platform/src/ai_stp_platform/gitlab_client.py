"""Bounded, read-only GitLab repository metadata requests."""

from __future__ import annotations

import ipaddress
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from urllib.parse import quote, urlsplit

import httpx

from ai_stp_foundation.timestamps import format_timestamp


class GitLabError(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class GitLabRepository:
    repository_id: int
    namespace_id: int
    path_with_namespace: str
    repository_url: str
    default_branch: str | None
    last_activity_at: str | None


_HOST = re.compile(r"^[a-z0-9]+(?:[a-z0-9.-]*[a-z0-9])?$")
_PATH = re.compile(r"^[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+$")
_LANGUAGE = re.compile(r"^[A-Za-z0-9+#._ -]{1,64}$")
_REVISION = re.compile(r"^[0-9a-f]{40}$")
_BRANCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")


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
    if (
        not isinstance(path, str)
        or not _PATH.fullmatch(path)
        or any(part in {".", ".."} for part in path.split("/"))
        or not isinstance(url, str)
        or url != f"{base_url}/{path}"
        or not isinstance(namespace, dict)
        or (branch is not None and not _valid_branch(branch))
    ):
        raise GitLabError("invalid_gitlab_response")
    return GitLabRepository(
        repository_id=_positive_id(fields.get("id")),
        namespace_id=_positive_id(namespace.get("id")),
        path_with_namespace=path,
        repository_url=url,
        default_branch=cast(str | None, branch),
        last_activity_at=_activity(activity),
    )


class GitLabClient:
    def __init__(
        self,
        base_url: str,
        *,
        allowed_hosts: Iterable[str] = (),
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = gitlab_base_url(base_url, allowed_hosts=allowed_hosts)
        self.transport = transport

    async def _get(
        self, path: str, *, token: str, params: Mapping[str, str | int] | None = None
    ) -> object:
        if not token or any(ord(character) < 33 or ord(character) > 126 for character in token):
            raise GitLabError("gitlab_credential_unavailable")
        url = f"{self.base_url}/api/v4/{path}"
        try:
            async with (
                httpx.AsyncClient(
                    timeout=httpx.Timeout(20.0, connect=5.0),
                    follow_redirects=False,
                    trust_env=False,
                    transport=self.transport,
                ) as client,
                client.stream(
                    "GET", url, headers={"PRIVATE-TOKEN": token}, params=params
                ) as response,
            ):
                if response.status_code in {401, 403, 404}:
                    raise GitLabError("gitlab_repository_inaccessible")
                if response.status_code == 429:
                    raise GitLabError("gitlab_rate_limited")
                if response.status_code != 200:
                    raise GitLabError("gitlab_unavailable")
                declared = response.headers.get("content-length")
                if declared is not None and (not declared.isdigit() or int(declared) > 262_144):
                    raise GitLabError("gitlab_response_too_large")
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(body) + len(chunk) > 262_144:
                        raise GitLabError("gitlab_response_too_large")
                    body.extend(chunk)
        except (httpx.HTTPError, OSError):
            raise GitLabError("gitlab_unavailable") from None
        try:
            return cast(object, json.loads(body))
        except (ValueError, UnicodeDecodeError):
            raise GitLabError("invalid_gitlab_response") from None

    async def list_repositories(self, *, token: str, limit: int = 100) -> list[GitLabRepository]:
        if not 1 <= limit <= 500:
            raise GitLabError("gitlab_limit_invalid")
        repositories: list[GitLabRepository] = []
        for page in range(1, (limit - 1) // 100 + 2):
            count = min(100, limit - len(repositories))
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
        return repositories

    async def repository(self, repository_id: int, *, token: str) -> GitLabRepository:
        repository_id = _positive_id(repository_id)
        data = await self._get(f"projects/{repository_id}", token=token)
        repository = _repository(data, base_url=self.base_url)
        if repository.repository_id != repository_id:
            raise GitLabError("invalid_gitlab_response")
        return repository

    async def languages(self, repository_id: int, *, token: str) -> dict[str, float]:
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

    async def head_revision(self, repository_id: int, branch: str, *, token: str) -> str:
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
