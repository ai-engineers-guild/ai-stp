"""GitLab discovery reads only bounded metadata from the configured authority."""

import httpx
import pytest
from pydantic import ValidationError

from ai_stp_contracts.gitlab import GitLabMutationRequest
from ai_stp_platform.gitlab_client import GitLabClient, GitLabError, gitlab_base_url

REPOSITORY = {
    "id": 42,
    "namespace": {"id": 7},
    "path_with_namespace": "group/subgroup/service",
    "web_url": "https://gitlab.com/group/subgroup/service",
    "default_branch": "main",
    "last_activity_at": "2026-09-01T00:00:00Z",
}


@pytest.mark.parametrize(
    "url",
    [
        "http://gitlab.com",
        "https://gitlab.com.evil.invalid",
        "https://user@gitlab.com",
        "https://gitlab.com:8443",
        "https://gitlab.com/other",
        "https://127.0.0.1",
        "https://gitlab.com?redirect=evil",
        "https://gitlab.com:bad",
    ],
)
def test_base_url_rejects_unapproved_authorities(url: str) -> None:
    with pytest.raises(GitLabError, match="gitlab_base_url_denied"):
        gitlab_base_url(url, allowed_hosts=())


def test_self_hosted_requires_exact_operator_allowlist() -> None:
    assert (
        gitlab_base_url("https://gitlab.example.com/", allowed_hosts=("gitlab.example.com",))
        == "https://gitlab.example.com"
    )
    with pytest.raises(GitLabError, match="gitlab_base_url_denied"):
        gitlab_base_url("https://other.example.com", allowed_hosts=("gitlab.example.com",))


@pytest.mark.asyncio
async def test_read_only_metadata_languages_and_revision() -> None:
    paths: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        assert request.method == "GET"
        assert request.url.host == "gitlab.com"
        assert request.headers["PRIVATE-TOKEN"] == "x"
        if request.url.path == "/api/v4/projects":
            assert request.url.params["membership"] == "true"
            return httpx.Response(200, json=[REPOSITORY])
        if request.url.path == "/api/v4/projects/42":
            return httpx.Response(200, json=REPOSITORY)
        if request.url.path == "/api/v4/projects/42/languages":
            return httpx.Response(200, json={"Python": 70.5, "HTML": 29.5})
        if request.url.path == "/api/v4/projects/42/repository/commits/main":
            return httpx.Response(200, json={"id": "a" * 40, "message": "not retained"})
        raise AssertionError(request.url)

    client = GitLabClient("https://gitlab.com", transport=httpx.MockTransport(respond))
    assert [row.repository_id for row in await client.list_repositories(token="x")] == [42]
    repository = await client.repository(42, token="x")
    assert repository.namespace_id == 7
    assert repository.last_activity_at == "2026-09-01T00:00:00.000Z"
    assert await client.languages(42, token="x") == {"Python": 70.5, "HTML": 29.5}
    assert await client.head_revision(42, "main", token="x") == "a" * 40
    assert len(paths) == 4


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (
            httpx.Response(302, headers={"location": "http://127.0.0.1/private"}),
            "gitlab_unavailable",
        ),
        (httpx.Response(404), "gitlab_repository_inaccessible"),
        (httpx.Response(200, headers={"content-length": "262145"}), "gitlab_response_too_large"),
    ],
)
async def test_redirects_oversize_and_inaccessible_repositories_are_closed_errors(
    response: httpx.Response, reason: str
) -> None:
    client = GitLabClient("https://gitlab.com", transport=httpx.MockTransport(lambda _: response))
    with pytest.raises(GitLabError, match=reason):
        await client.repository(42, token="x")


@pytest.mark.asyncio
async def test_untrusted_metadata_and_path_traversal_do_not_escape() -> None:
    bad = {**REPOSITORY, "web_url": "https://evil.invalid/group/subgroup/service"}
    client = GitLabClient(
        "https://gitlab.com",
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=bad)),
    )
    with pytest.raises(GitLabError, match="invalid_gitlab_response"):
        await client.repository(42, token="x")
    with pytest.raises(GitLabError, match="gitlab_branch_invalid"):
        await client.head_revision(42, "../private", token="x")


def test_discovery_mutations_have_no_credential_or_source_field() -> None:
    safe = {
        "authorization_revision": "corporate:organization_test:1:1",
        "expected_revision": 0,
        "idempotency_key": "register-test-12345678",
    }
    assert GitLabMutationRequest.model_validate(safe).expected_revision == 0
    with pytest.raises(ValidationError):
        GitLabMutationRequest.model_validate(
            {**safe, "repository_contents": "untrusted source bytes"}
        )
