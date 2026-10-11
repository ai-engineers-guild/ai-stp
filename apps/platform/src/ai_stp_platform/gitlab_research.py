"""GitLab adapter for the shared repository-scan pipeline.

The only GitLab-specific surface: the organization connection resolves the
client and token, the stored identity must record the observation the link
flow took (default branch, head revision, timestamp), and the live head is
read through the GitLab API. Everything after ``fetch_snapshot`` is the
shared ``scan_linked_repository`` invariant sequence.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_platform.gitlab_client import GitLabClient, GitLabError
from ai_stp_platform.gitlab_settings import GitLabSettings
from ai_stp_platform.gitlab_sources import request_digest
from ai_stp_platform.organization_models import ProjectIdentity
from ai_stp_platform.queue.states import PermanentJobFailure
from ai_stp_platform.repository_scan import RepositorySnapshot

_PROVIDER = "gitlab"
# Upstream failures a retry can repair; every other provider error is a
# permanent precondition the queue dead-letters instead of burning attempts.
_TRANSIENT_REASONS = frozenset({"gitlab_rate_limited", "gitlab_unavailable"})


def _translate(error: GitLabError) -> GitLabError | PermanentJobFailure:
    if error.reason in _TRANSIENT_REASONS:
        return error
    return PermanentJobFailure(f"gitlab scan fetch failed: {error.reason}")


class GitLabScanAdapter:
    """GitLab half of ``scan_linked_repository``.

    ``validate_identity`` requires the observation recorded at link time —
    the scan is pinned to the recorded head, so a repository that moved
    forces a fresh observation instead of scanning unrecorded state.
    ``still_bound`` re-proves under lock that the identity still names the
    instance and repository the snapshot came from.
    """

    provider = _PROVIDER

    def __init__(self, *, client: GitLabClient, token: str) -> None:
        self._client = client
        self._token = token
        self._repository_id: str | None = None

    def validate_identity(self, identity: ProjectIdentity) -> None:
        if identity.provider_installation_id != self._client.base_url:
            raise PermanentJobFailure("linked GitLab project is unavailable")
        if identity.provider_default_branch is None or identity.provider_observed_revision is None:
            raise PermanentJobFailure("gitlab default branch has no observed revision")
        if identity.observed_at is None:
            raise PermanentJobFailure("gitlab observation is incomplete")
        try:
            int(identity.immutable_repository_id or "")
        except ValueError:
            raise PermanentJobFailure("gitlab repository identity is incomplete") from None

    async def fetch_snapshot(
        self, db: AsyncSession, identity: ProjectIdentity
    ) -> RepositorySnapshot:
        del db
        repository_id = int(identity.immutable_repository_id or "")
        branch = identity.provider_default_branch or ""
        try:
            head = await self._client.head_revision(repository_id, branch, token=self._token)
            archive = await self._client.archive(repository_id, sha=head, token=self._token)
        except GitLabError as error:
            raise _translate(error) from error
        self._repository_id = str(repository_id)
        return RepositorySnapshot(
            repository=identity.display_name,
            branch=branch,
            head=head,
            archive=archive,
            observed_at=identity.observed_at or datetime.now(UTC),
        )

    def still_bound(self, identity: ProjectIdentity, snapshot: RepositorySnapshot) -> bool:
        del snapshot
        return (
            identity.provider_installation_id == self._client.base_url
            and self._repository_id is not None
            and identity.immutable_repository_id == self._repository_id
        )

    def request_digest(self, value: object) -> str:
        return request_digest(value)


def gitlab_scan_adapter(*, organization_id: str, settings: GitLabSettings) -> GitLabScanAdapter:
    """Build the adapter for one organization's configured GitLab connection."""
    connection = settings.connection_for(organization_id)
    if connection is None:
        raise PermanentJobFailure("gitlab connection is not configured")
    try:
        client = GitLabClient(
            connection.base_url,
            allowed_hosts=connection.allowed_hosts,
            verify=settings.tls_verify(),
        )
    except GitLabError:
        raise PermanentJobFailure("gitlab connection is not configured") from None
    return GitLabScanAdapter(client=client, token=connection.token.get_secret_value())


__all__ = [
    "GitLabScanAdapter",
    "gitlab_scan_adapter",
]
