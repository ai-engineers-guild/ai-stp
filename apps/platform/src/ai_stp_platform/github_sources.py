"""Server-only source bindings; passports carry no private GitHub coordinates."""

from __future__ import annotations

from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_foundation.canonical import JsonValue, canonize
from ai_stp_foundation.digests import digest_bytes
from ai_stp_platform.github_authority import load_connector, require_repository
from ai_stp_platform.github_client import GitHubClient, GitHubError, object_data, positive_id
from ai_stp_platform.github_models import GitHubSourceBinding
from ai_stp_platform.github_settings import GitHubConnectorSettings
from ai_stp_platform.models import OAuthIdentity, PublicationPlan
from ai_stp_sources.definition import pack_component_tree
from ai_stp_sources.errors import SourceError
from ai_stp_sources.git import resolve_git
from ai_stp_sources.models import GitIntent


def request_digest(value: object) -> str:
    return digest_bytes("ai-stp:github-request:v1", canonize(cast(JsonValue, value)))


async def bound_source(db: AsyncSession, plan: PublicationPlan) -> GitHubSourceBinding | None:
    if not getattr(plan, "source_binding_id", None):
        return None
    binding = await db.scalar(
        select(GitHubSourceBinding).where(
            GitHubSourceBinding.id == plan.source_binding_id,
            GitHubSourceBinding.organization_id == plan.organization_id,
        )
    )
    if binding is None:
        raise GitHubError("source_binding_mismatch", status=412)
    passport_hash = digest_bytes("ai-stp:passport:v1", canonize(cast(JsonValue, plan.passport)))
    artifact = plan.passport.get("artifact")
    if (
        binding.account_id != plan.actor_account_id
        or binding.content_digest != plan.content_digest
        or binding.passport_digest != passport_hash
        or plan.passport.get("source") is not None
        or not isinstance(artifact, dict)
        or cast(dict[str, object], artifact).get("size_bytes") != binding.size_bytes
        or list(plan.artifact_inventory) != binding.inventory
    ):
        raise GitHubError("source_binding_mismatch", status=412)
    return binding


async def authorize_binding(
    db: AsyncSession,
    binding: GitHubSourceBinding,
    *,
    client: GitHubClient,
    settings: GitHubConnectorSettings,
    public: bool = False,
) -> str:
    connector, token = await load_connector(
        db,
        account_id=binding.account_id,
        purpose="source",
        settings=settings,
        organization_id=binding.organization_id,
    )
    if connector.id != binding.connector_id:
        raise GitHubError("source_binding_mismatch", status=412)
    subject = await db.scalar(
        select(OAuthIdentity.provider_subject).where(
            OAuthIdentity.account_id == binding.account_id,
            OAuthIdentity.provider == "github",
            OAuthIdentity.state == "linked",
        )
    )
    if subject != connector.github_subject:
        raise GitHubError("github_identity_mismatch", status=403)
    repository = await require_repository(
        client,
        token=token,
        purpose="source",
        settings=settings,
        installation_id=binding.installation_id,
        repository_id=binding.repository_id,
    )
    if (
        repository.owner_id != binding.repository_owner_id
        or repository.full_name != binding.repository_full_name
    ):
        raise GitHubError("repository_identity_changed", status=412)
    if public and repository.private:
        raise GitHubError("public_source_required", status=400)
    return token


async def public_bound_source_bytes(binding: GitHubSourceBinding, *, client: GitHubClient) -> bytes:
    """Promotion proves public provenance anonymously; no source credentials."""
    reply = await client.api("GET", f"/repositories/{binding.repository_id}", token=None)
    repository = object_data(reply.data)
    owner = object_data(repository.get("owner"))
    if (
        repository.get("private") is not False
        or positive_id(repository.get("id")) != binding.repository_id
        or positive_id(owner.get("id")) != binding.repository_owner_id
        or repository.get("full_name") != binding.repository_full_name
    ):
        raise GitHubError("public_source_required", status=400)
    try:
        snapshot = await resolve_git(
            GitIntent(
                repository_url=f"https://github.com/{binding.repository_full_name}",
                tracked_ref=binding.commit,
                subpath=binding.subpath,
            ),
            fetch=client.fetch,
        )
        payload = pack_component_tree(snapshot.files)
    except SourceError:
        raise GitHubError("public_source_unavailable", status=400) from None
    if (
        snapshot.github_repo_id != binding.repository_id
        or digest_bytes("ai-stp:artifact:v1", payload) != binding.content_digest
        or len(payload) != binding.size_bytes
        or sorted(snapshot.files) != binding.inventory
    ):
        raise GitHubError("source_binding_mismatch", status=412)
    return payload
