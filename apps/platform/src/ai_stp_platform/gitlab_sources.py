"""Server-only GitLab source bindings; passports carry no private coordinates."""

from __future__ import annotations

from typing import cast
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_foundation.canonical import JsonValue, canonize
from ai_stp_foundation.digests import digest_bytes
from ai_stp_platform.gitlab_authority import load_connector, require_project
from ai_stp_platform.gitlab_client import GitLabClient, GitLabError
from ai_stp_platform.gitlab_models import GitLabSourceBinding
from ai_stp_platform.gitlab_settings import GitLabSettings
from ai_stp_platform.models import OAuthIdentity, PublicationPlan
from ai_stp_sources.archive import MAX_GIT_ARCHIVE_BYTES, extract_component_files
from ai_stp_sources.definition import pack_component_tree
from ai_stp_sources.errors import SourceError


def request_digest(value: object) -> str:
    return digest_bytes("ai-stp:gitlab-request:v1", canonize(cast(JsonValue, value)))


async def bound_source(db: AsyncSession, plan: PublicationPlan) -> GitLabSourceBinding | None:
    binding_id = getattr(plan, "gitlab_source_binding_id", None)
    if not binding_id:
        return None
    binding = await db.scalar(
        select(GitLabSourceBinding).where(
            GitLabSourceBinding.id == binding_id,
            GitLabSourceBinding.organization_id == plan.organization_id,
        )
    )
    if binding is None:
        raise GitLabError("source_binding_mismatch", status=412)
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
        raise GitLabError("source_binding_mismatch", status=412)
    return binding


async def authorize_binding(
    db: AsyncSession,
    binding: GitLabSourceBinding,
    *,
    client: GitLabClient,
    settings: GitLabSettings,
    public: bool = False,
) -> str:
    if client.base_url != binding.gitlab_base_url:
        raise GitLabError("source_binding_mismatch", status=412)
    connector, token = await load_connector(
        db,
        account_id=binding.account_id,
        gitlab_base_url=binding.gitlab_base_url,
        client=client,
        settings=settings,
        lock=True,
    )
    if connector.id != binding.connector_id:
        raise GitLabError("source_binding_mismatch", status=412)
    subject = await db.scalar(
        select(OAuthIdentity.provider_subject).where(
            OAuthIdentity.account_id == binding.account_id,
            OAuthIdentity.provider == "gitlab",
            OAuthIdentity.state == "linked",
        )
    )
    if subject != connector.gitlab_subject:
        raise GitLabError("gitlab_identity_mismatch", status=403)
    repository = await require_project(client, token=token, project_id=binding.project_id)
    if (
        repository.namespace_id != binding.namespace_id
        or repository.path_with_namespace != binding.path_with_namespace
    ):
        raise GitLabError("repository_identity_changed", status=412)
    if public and repository.visibility != "public":
        raise GitLabError("public_source_required", status=400)
    return token


def anonymous_client(binding: GitLabSourceBinding, *, verify: str | bool = True) -> GitLabClient:
    host = urlsplit(binding.gitlab_base_url).hostname or ""
    return GitLabClient(
        binding.gitlab_base_url, allowed_hosts=(host,), auth="anonymous", verify=verify
    )


async def public_bound_source_bytes(
    binding: GitLabSourceBinding, *, verify: str | bool = True
) -> bytes:
    """Promotion proves public provenance anonymously; no source credentials."""
    client = anonymous_client(binding, verify=verify)
    try:
        repository = await client.repository(binding.project_id)
        archive = await client.archive(binding.project_id, sha=binding.commit)
        files = extract_component_files(
            archive, subpath=binding.subpath, max_archive_bytes=MAX_GIT_ARCHIVE_BYTES
        )
        payload = pack_component_tree(files)
    except (GitLabError, SourceError):
        raise GitLabError("public_source_unavailable", status=400) from None
    if (
        repository.visibility != "public"
        or repository.namespace_id != binding.namespace_id
        or repository.path_with_namespace != binding.path_with_namespace
        or digest_bytes("ai-stp:artifact:v1", payload) != binding.content_digest
        or len(payload) != binding.size_bytes
        or sorted(files) != binding.inventory
    ):
        raise GitLabError("source_binding_mismatch", status=412)
    return payload
