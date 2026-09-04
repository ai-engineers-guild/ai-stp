"""Acquire a managed attested provider when none is already selected.

`ADR-0146` / `REQ-853`: the public install is `ai-stp-cli` alone. The first
plan or install operation for a harness, with no explicit, configured,
remembered or discovered provider, binds the pinned OpenNetwork release
through the same `attested_bind` path `provider fetch` uses. Trust failures
stay refusals. This never becomes `--unverified-provider`.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ai_stp_cli.config import effective_config
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import provider_installations as installations
from ai_stp_cli.local.passports import moment
from ai_stp_cli.provider import attested_bind, conformance


@dataclass(frozen=True)
class ProviderContext:
    """The executable and trust inputs established by one resolution."""

    executable: str
    parameters: Mapping[str, object]


def configured_path(harness_id: str) -> str:
    """The configured executable for this harness, if the user named one."""
    values = {item.path: item.value for item in effective_config().values}
    return str(values.get(f"provider.paths.{harness_id}") or "")


def ensure_provider(
    connection: sqlite3.Connection,
    harness_id: str,
    parameters: Mapping[str, object],
) -> str:
    """Return the provider executable this operation will run."""
    return provider_context(connection, harness_id, parameters).executable


def provider_context(
    connection: sqlite3.Connection,
    harness_id: str,
    parameters: Mapping[str, object],
) -> ProviderContext:
    """Resolve a provider and carry its verified managed manifest forward.

    Precedence is `installations.resolve`: argument, configuration, remembered
    choice, discovery. A missing managed provider is acquired only after those
    four have nothing to say. A manifest beside consumer-managed bytes is not
    trusted by location: the caller still verifies it against pinned policy and
    the exact executable before the first provider spawn.
    """
    argument = str(parameters.get("provider") or "")
    found = installations.resolve(
        connection,
        harness_id,
        argument=argument,
        configured=configured_path(harness_id),
    )
    if found.state == installations.STATE_AMBIGUOUS:
        raise CliFailure(
            "AI_STP_USER_DECISION_REQUIRED",
            "more than one provider serves this harness here",
            details={"harness": harness_id, "candidates": ", ".join(found.candidates)},
            next_actions=[
                "provider check --json",
                f"install plan --harness {harness_id} --provider <path> --json",
            ],
        )
    if found.path:
        executable = conformance.resolve_executable(found.path)
        manifest = _managed_manifest(executable, harness_id)
        return ProviderContext(
            executable=executable,
            parameters=_with_manifest(parameters, manifest),
        )
    if bool(parameters.get("unverified-provider", False)):
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "an unverified provider must be named; automatic acquisition only "
            "binds attested OpenNetwork bytes",
            details={"harness": harness_id},
            next_actions=[
                f"install plan --harness {harness_id} --provider <path> "
                "--unverified-provider --json",
                f"provider fetch --harness {harness_id} --json",
            ],
        )
    bound = attested_bind.fetch(harness=harness_id)
    at = moment()
    installations.remember(
        connection,
        installations.Installation(
            harness_id=bound.harness_id,
            path=str(bound.artifact),
            source=installations.SOURCE_CHOSEN,
            state=installations.STATE_INSTALLED,
            provider_id=bound.provider_id,
            provider_version=bound.provider_version,
            tag=bound.tag,
            commit=bound.commit,
            artifact_digest=bound.artifact_digest,
            checked_at=at,
            source_checked_at=at,
        ),
    )
    return ProviderContext(
        executable=conformance.resolve_executable(str(bound.artifact)),
        parameters=_with_manifest(parameters, bound.manifest_path),
    )


def _managed_manifest(executable: str, harness_id: str) -> Path | None:
    """Return a regular sibling manifest only for the managed harness root."""
    place = Path(executable).resolve()
    root = (installations.managed_root() / harness_id).resolve()
    try:
        place.relative_to(root)
    except ValueError:
        return None
    manifest = place.parent / attested_bind.MANIFEST_NAME
    if manifest.is_symlink() or not manifest.is_file():
        return None
    return manifest


def _with_manifest(parameters: Mapping[str, object], manifest: Path | None) -> Mapping[str, object]:
    """Preserve an explicit manifest; otherwise add the acquired exact path."""
    if parameters.get("provider-manifest") or manifest is None:
        return parameters
    return {**parameters, "provider-manifest": str(manifest)}
