"""GitHub adapter for the shared repository-scan pipeline.

The only GitHub-specific surface: the bearer token comes from the queueing
principal's ``source`` connector — the same authorization the synchronous
enrich performs — the repository's installation binding is re-proved live
through ``require_repository``, and default branch plus head are resolved
through the GitHub API. Everything after ``fetch_snapshot`` is the shared
``scan_linked_repository`` invariant sequence.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_platform.github_authority import load_connector, require_repository
from ai_stp_platform.github_client import GitHubClient, GitHubError, object_data
from ai_stp_platform.github_settings import GitHubConnectorSettings
from ai_stp_platform.github_sources import request_digest
from ai_stp_platform.organization_models import ProjectIdentity
from ai_stp_platform.queue.states import PermanentJobFailure
from ai_stp_platform.repository_scan import RepositorySnapshot
from ai_stp_sources.errors import SourceError
from ai_stp_sources.git import download_repository_tarball

_PROVIDER = "github"
# Upstream failures a retry can repair; every other provider error is a
# permanent precondition the queue dead-letters instead of burning attempts.
_TRANSIENT_REASONS = frozenset({"github_rate_limited", "github_unavailable"})


def _translate(error: GitHubError) -> GitHubError | PermanentJobFailure:
    if error.reason in _TRANSIENT_REASONS:
        return error
    return PermanentJobFailure(f"github scan fetch failed: {error.reason}")


class GitHubScanAdapter:
    """GitHub half of ``scan_linked_repository``.

    ``validate_identity`` requires the immutable installation/repository
    coordinates the link flow recorded. ``fetch_snapshot`` re-authorizes the
    queueing principal against the live installation before reading the
    repository — a principal whose grant no longer covers it fails the job.
    ``still_bound`` re-proves under lock that the identity still names the
    installation and repository the snapshot came from.
    """

    provider = _PROVIDER

    def __init__(
        self,
        *,
        principal_id: str,
        settings: GitHubConnectorSettings,
        client: GitHubClient | None = None,
    ) -> None:
        self._principal_id = principal_id
        self._settings = settings
        self._client = client or GitHubClient()
        self._installation_id = 0
        self._repository_id = 0

    def validate_identity(self, identity: ProjectIdentity) -> None:
        if identity.provider_installation_id is None or identity.immutable_repository_id is None:
            raise PermanentJobFailure("linked GitHub project is unavailable")
        try:
            int(identity.immutable_repository_id.removeprefix("github:"))
            int(identity.provider_installation_id)
        except ValueError:
            raise PermanentJobFailure("github repository identity is incomplete") from None

    async def fetch_snapshot(
        self, db: AsyncSession, identity: ProjectIdentity
    ) -> RepositorySnapshot:
        repository_id = int((identity.immutable_repository_id or "").removeprefix("github:"))
        installation_id = int(identity.provider_installation_id or 0)
        try:
            _connector, token = await load_connector(
                db,
                account_id=self._principal_id,
                purpose="source",
                settings=self._settings,
            )
            repository = await require_repository(
                self._client,
                token=token,
                purpose="source",
                settings=self._settings,
                installation_id=installation_id,
                repository_id=repository_id,
            )
            metadata = object_data(
                (await self._client.api("GET", f"/repositories/{repository_id}", token=token)).data
            )
            branch = metadata.get("default_branch")
            if not isinstance(branch, str) or not 1 <= len(branch) <= 128:
                raise GitHubError("invalid_upstream_response")
            commits_data = (
                await self._client.api(
                    "GET",
                    f"/repos/{repository.full_name}/commits",
                    token=token,
                    params={"sha": branch, "per_page": 1},
                )
            ).data
            if not isinstance(commits_data, list):
                raise GitHubError("invalid_upstream_response")
            commits = cast(list[object], commits_data)
            if len(commits) != 1:
                raise GitHubError("invalid_upstream_response")
            head = object_data(commits[0]).get("sha")
            if (
                not isinstance(head, str)
                or len(head) != 40
                or any(character not in "0123456789abcdef" for character in head)
            ):
                raise GitHubError("invalid_upstream_response")
            archive = await download_repository_tarball(
                repository.full_name, head, fetch=self._client.fetch, token=token
            )
        except GitHubError as error:
            raise _translate(error) from error
        except SourceError as error:
            raise PermanentJobFailure(f"github archive is unusable: {error.code}") from error
        self._installation_id = installation_id
        self._repository_id = repository_id
        return RepositorySnapshot(
            repository=repository.full_name,
            branch=branch,
            head=head,
            archive=archive,
            observed_at=datetime.now(UTC),
        )

    def still_bound(self, identity: ProjectIdentity, snapshot: RepositorySnapshot) -> bool:
        del snapshot
        return identity.provider_installation_id == str(self._installation_id) and (
            identity.immutable_repository_id or ""
        ).removeprefix("github:") == str(self._repository_id)

    def request_digest(self, value: object) -> str:
        return request_digest(value)


__all__ = [
    "GitHubScanAdapter",
]
