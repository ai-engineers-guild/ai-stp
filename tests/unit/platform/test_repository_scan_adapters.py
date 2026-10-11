"""Provider adapters for the shared repository-scan pipeline.

Adapters own only provider specifics: identity integrity rules, the live
head/archive fetch, the rebound-identity check under lock, and the digest
namespace. Transient provider errors must propagate untouched so the queue
retries; permanent states must arrive as ``PermanentJobFailure``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_contracts.github_connector import GitHubRepository
from ai_stp_platform.github_client import GitHubClient, GitHubError
from ai_stp_platform.github_research import GitHubScanAdapter
from ai_stp_platform.github_settings import GitHubConnectorSettings
from ai_stp_platform.gitlab_client import GitLabClient, GitLabError
from ai_stp_platform.gitlab_research import GitLabScanAdapter, gitlab_scan_adapter
from ai_stp_platform.gitlab_settings import GitLabConnection, GitLabSettings
from ai_stp_platform.organization_models import ProjectIdentity
from ai_stp_platform.queue.states import PermanentJobFailure
from ai_stp_sources.errors import SourceError
from ai_stp_worker.handlers.repository_scan import parse_scan_job, user_principal

_HEAD = "a" * 40
_ARCHIVE = b"archive-bytes"


def _gitlab_identity(**overrides: object) -> ProjectIdentity:
    identity = ProjectIdentity(
        id="provider_project_1",
        organization_id="org",
        namespace="provider",
        external_key="gitlab:provider_project_1",
        display_name="group/service",
        provider_kind="gitlab",
        provider_installation_id="https://gitlab.example",
        immutable_repository_id="42",
        provider_default_branch="main",
        provider_observed_revision=_HEAD,
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
        state="active",
    )
    for name, value in overrides.items():
        setattr(identity, name, value)
    return identity


def _github_identity(**overrides: object) -> ProjectIdentity:
    identity = ProjectIdentity(
        id="provider_project_2",
        organization_id="org",
        namespace="provider",
        external_key="github:provider_project_2",
        display_name="owner/repo",
        provider_kind="github",
        provider_installation_id="777",
        immutable_repository_id="github:9001",
        state="active",
    )
    for name, value in overrides.items():
        setattr(identity, name, value)
    return identity


class _GitLabClientStub:
    def __init__(
        self,
        *,
        head: str = _HEAD,
        archive: bytes = _ARCHIVE,
        error: GitLabError | None = None,
    ) -> None:
        self.base_url = "https://gitlab.example"
        self.head = head
        self.archive_bytes = archive
        self.error = error
        self.calls: list[str] = []

    async def head_revision(self, project_id: int, branch: str, *, token: str | None = None) -> str:
        self.calls.append("head")
        if self.error is not None:
            raise self.error
        return self.head

    async def archive(self, project_id: int, *, sha: str, token: str | None = None) -> bytes:
        self.calls.append("archive")
        if self.error is not None:
            raise self.error
        return self.archive_bytes


def _gitlab_adapter(
    client: _GitLabClientStub | None = None,
) -> tuple[GitLabScanAdapter, _GitLabClientStub]:
    stub = client or _GitLabClientStub()
    return GitLabScanAdapter(client=cast(GitLabClient, stub), token="token"), stub


# ---------------------------------------------------------------------------
# Adapter factory
# ---------------------------------------------------------------------------


def test_gitlab_adapter_factory_requires_a_configured_connection() -> None:
    with pytest.raises(PermanentJobFailure, match="connection is not configured"):
        gitlab_scan_adapter(organization_id="org", settings=GitLabSettings())


def test_gitlab_adapter_factory_builds_from_connection() -> None:
    settings = GitLabSettings(
        connections={
            "*": GitLabConnection.model_validate(
                {
                    "base_url": "https://gitlab.example",
                    "token": "secret",
                    "allowed_hosts": ["gitlab.example"],
                }
            )
        }
    )
    adapter = gitlab_scan_adapter(organization_id="org", settings=settings)
    assert isinstance(adapter, GitLabScanAdapter)
    assert adapter.provider == "gitlab"


# ---------------------------------------------------------------------------
# GitLab validate_identity
# ---------------------------------------------------------------------------


def test_gitlab_validate_identity_accepts_a_complete_observation() -> None:
    adapter, _ = _gitlab_adapter()
    adapter.validate_identity(_gitlab_identity())


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"provider_installation_id": "https://other.example"}, "unavailable"),
        ({"provider_default_branch": None}, "no observed revision"),
        ({"provider_observed_revision": None}, "no observed revision"),
        ({"observed_at": None}, "incomplete"),
        ({"immutable_repository_id": "not-an-int"}, "incomplete"),
    ],
)
def test_gitlab_validate_identity_rejects_incomplete_rows(
    overrides: dict[str, object], reason: str
) -> None:
    adapter, _ = _gitlab_adapter()
    with pytest.raises(PermanentJobFailure, match=reason):
        adapter.validate_identity(_gitlab_identity(**overrides))


# ---------------------------------------------------------------------------
# GitLab fetch_snapshot + still_bound
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gitlab_fetch_snapshot_reads_head_and_archive() -> None:
    adapter, stub = _gitlab_adapter()
    snapshot = await adapter.fetch_snapshot(cast(AsyncSession, None), _gitlab_identity())
    assert stub.calls == ["head", "archive"]
    assert snapshot.repository == "group/service"
    assert snapshot.branch == "main"
    assert snapshot.head == _HEAD
    assert snapshot.archive == _ARCHIVE
    assert snapshot.observed_at == datetime(2026, 1, 1, tzinfo=UTC)


@pytest.mark.parametrize("reason", ["gitlab_rate_limited", "gitlab_unavailable"])
@pytest.mark.asyncio
async def test_gitlab_transient_errors_bubble_for_retry(reason: str) -> None:
    adapter, _ = _gitlab_adapter(_GitLabClientStub(error=GitLabError(reason)))
    with pytest.raises(GitLabError, match=reason):
        await adapter.fetch_snapshot(cast(AsyncSession, None), _gitlab_identity())


@pytest.mark.asyncio
async def test_gitlab_permanent_errors_dead_letter() -> None:
    adapter, _ = _gitlab_adapter(
        _GitLabClientStub(error=GitLabError("gitlab_repository_inaccessible"))
    )
    with pytest.raises(PermanentJobFailure, match="gitlab_repository_inaccessible"):
        await adapter.fetch_snapshot(cast(AsyncSession, None), _gitlab_identity())


@pytest.mark.asyncio
async def test_gitlab_still_bound_catches_identity_rebind() -> None:
    adapter, _ = _gitlab_adapter()
    identity = _gitlab_identity()
    snapshot = await adapter.fetch_snapshot(cast(AsyncSession, None), identity)
    assert adapter.still_bound(identity, snapshot)
    assert not adapter.still_bound(
        _gitlab_identity(provider_installation_id="https://other.example"), snapshot
    )
    assert not adapter.still_bound(_gitlab_identity(immutable_repository_id="43"), snapshot)
    # Before any fetch the adapter has no bound repository to prove.
    assert not GitLabScanAdapter(
        client=cast(GitLabClient, _GitLabClientStub()), token="t"
    ).still_bound(identity, snapshot)


# ---------------------------------------------------------------------------
# GitHub validate_identity
# ---------------------------------------------------------------------------


def _github_adapter(client: object | None = None) -> GitHubScanAdapter:
    return GitHubScanAdapter(
        principal_id="account_1",
        settings=GitHubConnectorSettings(),
        client=cast(GitHubClient, client) if client is not None else None,
    )


def test_github_validate_identity_accepts_immutable_coordinates() -> None:
    _github_adapter().validate_identity(_github_identity())


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"provider_installation_id": None}, "unavailable"),
        ({"immutable_repository_id": None}, "unavailable"),
        ({"immutable_repository_id": "not-an-int"}, "incomplete"),
        ({"provider_installation_id": "abc"}, "incomplete"),
    ],
)
def test_github_validate_identity_rejects_incomplete_rows(
    overrides: dict[str, object], reason: str
) -> None:
    adapter = _github_adapter()
    with pytest.raises(PermanentJobFailure, match=reason):
        adapter.validate_identity(_github_identity(**overrides))


# ---------------------------------------------------------------------------
# GitHub fetch_snapshot + still_bound
# ---------------------------------------------------------------------------


class _GitHubClientStub:
    def __init__(self, *, error: GitHubError | None = None) -> None:
        self.error = error
        self.calls: list[str] = []

    async def api(self, method: str, path: str, *, token: str | None, **kwargs: object) -> object:
        self.calls.append(path)
        if self.error is not None:
            raise self.error

        class _Reply:
            def __init__(self, data: object) -> None:
                self.data = data

        if path.startswith("/repositories/"):
            return _Reply({"default_branch": "main"})
        if path.endswith("/commits"):
            return _Reply([{"sha": _HEAD}])
        raise AssertionError(f"unexpected api path {path}")

    async def fetch(self, url: str, *, headers: object) -> object:
        raise AssertionError("tarball download is stubbed at module level")


def _stub_github_fetch(
    monkeypatch: pytest.MonkeyPatch, *, client: _GitHubClientStub
) -> GitHubScanAdapter:
    import ai_stp_platform.github_research as research

    repository = GitHubRepository.model_validate(
        {
            "installation_id": 777,
            "repository_id": 9001,
            "owner_id": 5,
            "full_name": "owner/repo",
            "html_url": "https://github.com/owner/repo",
            "owner_type": "Organization",
            "private": True,
            "can_administer": False,
            "permission": "read",
        }
    )

    async def _load_connector(*args: object, **kwargs: object) -> tuple[object, str]:
        return object(), "token"

    async def _require_repository(*args: object, **kwargs: object) -> GitHubRepository:
        return repository

    async def _tarball(full_name: str, commit: str, *, fetch: object, token: str | None) -> bytes:
        assert full_name == "owner/repo" and commit == _HEAD
        return _ARCHIVE

    monkeypatch.setattr(research, "load_connector", _load_connector)
    monkeypatch.setattr(research, "require_repository", _require_repository)
    monkeypatch.setattr(research, "download_repository_tarball", _tarball)
    return _github_adapter(client)


@pytest.mark.asyncio
async def test_github_fetch_snapshot_resolves_branch_head_and_archive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _stub_github_fetch(monkeypatch, client=_GitHubClientStub())
    identity = _github_identity()
    snapshot = await adapter.fetch_snapshot(cast(AsyncSession, None), identity)
    assert snapshot.repository == "owner/repo"
    assert snapshot.branch == "main"
    assert snapshot.head == _HEAD
    assert snapshot.archive == _ARCHIVE
    assert adapter.still_bound(identity, snapshot)


@pytest.mark.parametrize("reason", ["github_rate_limited", "github_unavailable"])
@pytest.mark.asyncio
async def test_github_transient_errors_bubble_for_retry(
    monkeypatch: pytest.MonkeyPatch, reason: str
) -> None:
    adapter = _stub_github_fetch(monkeypatch, client=_GitHubClientStub(error=GitHubError(reason)))
    with pytest.raises(GitHubError, match=reason):
        await adapter.fetch_snapshot(cast(AsyncSession, None), _github_identity())


@pytest.mark.asyncio
async def test_github_permanent_errors_dead_letter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _stub_github_fetch(
        monkeypatch, client=_GitHubClientStub(error=GitHubError("repository_access_denied"))
    )
    with pytest.raises(PermanentJobFailure, match="repository_access_denied"):
        await adapter.fetch_snapshot(cast(AsyncSession, None), _github_identity())


@pytest.mark.asyncio
async def test_github_connector_errors_dead_letter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ai_stp_platform.github_research as research

    async def _denied(*args: object, **kwargs: object) -> tuple[object, str]:
        raise GitHubError("connect_github_required", status=401)

    monkeypatch.setattr(research, "load_connector", _denied)
    with pytest.raises(PermanentJobFailure, match="connect_github_required"):
        await _github_adapter().fetch_snapshot(cast(AsyncSession, None), _github_identity())


@pytest.mark.asyncio
async def test_github_tarball_source_error_dead_letter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ai_stp_platform.github_research as research

    _ = _stub_github_fetch(monkeypatch, client=_GitHubClientStub())

    async def _broken(full_name: str, commit: str, *, fetch: object, token: str | None) -> bytes:
        raise SourceError("unsafe_archive", "boom")

    monkeypatch.setattr(research, "download_repository_tarball", _broken)
    adapter = _github_adapter(_GitHubClientStub())
    with pytest.raises(PermanentJobFailure, match="archive is unusable"):
        await adapter.fetch_snapshot(cast(AsyncSession, None), _github_identity())


@pytest.mark.asyncio
async def test_github_still_bound_catches_identity_rebind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _stub_github_fetch(monkeypatch, client=_GitHubClientStub())
    identity = _github_identity()
    snapshot = await adapter.fetch_snapshot(cast(AsyncSession, None), identity)
    assert adapter.still_bound(identity, snapshot)
    assert not adapter.still_bound(_github_identity(provider_installation_id="778"), snapshot)
    assert not adapter.still_bound(
        _github_identity(immutable_repository_id="github:9002"), snapshot
    )
    # The "github:" prefix is storage detail, not part of the binding value.
    assert adapter.still_bound(_github_identity(immutable_repository_id="9001"), snapshot)


# ---------------------------------------------------------------------------
# Digest namespaces stay provider-scoped
# ---------------------------------------------------------------------------


def test_adapter_digests_stay_provider_namespaced() -> None:
    gitlab_adapter, _ = _gitlab_adapter()
    github_adapter = _github_adapter()
    value = {"scan_id": "scan_1"}
    assert gitlab_adapter.request_digest(value) != github_adapter.request_digest(value)


# ---------------------------------------------------------------------------
# Handler payload parsing
# ---------------------------------------------------------------------------


_ENVELOPE = {
    "_tenant": {
        "organization_id": "org",
        "authorization_revision": 1,
        "principal_type": "user",
        "principal_id": "account_1",
        "required_permission": "technology.scan.publish",
        "scope_kind": "project",
        "scope_id": "project_1",
    }
}
_FIELDS = {
    "provider_project_id": "provider_1",
    "project_id": "project_1",
    "scan_id": "scan_1",
    "mapping_version": "v1",
}


def test_parse_scan_job_returns_fields_and_envelope() -> None:
    job = parse_scan_job({**_ENVELOPE, **_FIELDS}, job_label="gitlab_technology_scan")
    assert job.organization_id == "org"
    assert job.provider_project_id == "provider_1"
    assert job.project_id == "project_1"
    assert job.scan_id == "scan_1"
    assert job.mapping_version == "v1"
    assert user_principal(job, job_label="github_technology_scan") == "account_1"


def test_parse_scan_job_requires_envelope() -> None:
    with pytest.raises(PermanentJobFailure, match="tenant envelope"):
        parse_scan_job(dict(_FIELDS), job_label="gitlab_technology_scan")


def test_parse_scan_job_requires_organization_id() -> None:
    envelope = {"_tenant": {"principal_type": "user", "principal_id": "a"}}
    with pytest.raises(PermanentJobFailure, match="organization_id"):
        parse_scan_job({**envelope, **_FIELDS}, job_label="gitlab_technology_scan")


@pytest.mark.parametrize(
    "missing", ["provider_project_id", "project_id", "scan_id", "mapping_version"]
)
def test_parse_scan_job_requires_each_field(missing: str) -> None:
    payload = {**_ENVELOPE, **_FIELDS}
    del payload[missing]
    with pytest.raises(PermanentJobFailure, match=missing):
        parse_scan_job(payload, job_label="gitlab_technology_scan")


def test_user_principal_requires_a_user() -> None:
    envelope = {"_tenant": {**_ENVELOPE["_tenant"], "principal_type": "service_principal"}}
    job = parse_scan_job({**envelope, **_FIELDS}, job_label="github_technology_scan")
    with pytest.raises(PermanentJobFailure, match="user principal"):
        user_principal(job, job_label="github_technology_scan")
