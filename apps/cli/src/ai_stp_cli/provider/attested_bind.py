"""Bind a closed provider-release manifest from attested OpenNetwork bytes.

OpenNetwork ships binaries, SHA256SUMS and GitHub attestations. It does not
ship `ai-stp:provider-release-manifest:v1`. The consumer still needs that JSON
to plan a v3 install. This module materialises it from facts the pinned policy
and the attested artifact already name: repository, signer workflow, source
commit, exact bytes, and `provider-info` from those bytes after attestation.

That is not a second trust anchor. Ed25519 `releases` stay empty. Sequence is a
consumer encoding of the exact semver tag so two machines bind the same tag to
the same floor.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Final, Literal, Protocol, cast

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.paths import data_dir, ensure_directory, redact_home, write_private
from ai_stp_cli.provider import build_attestation, conformance, protocol_v3, release
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.harnesses import HARNESS_IDS

ATTESTED_SIGNING_KEY: Final[str] = "attested"
MANIFEST_NAME: Final[str] = "release.json"
_GITHUB_PREFIX: Final[str] = "github.com/"
_SEMVER_TAG: Final[re.Pattern[str]] = re.compile(
    r"^v?(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)$"
)
_COMMIT: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{40}$")

#: One public OpenNetwork setup-system per supported harness. Values must match
#: `build_attestations` in the shipped policy; a drift is a test failure, not a
#: silent second map.
HARNESS_REPOSITORIES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "claude-code": "github.com/NDDev-OpenNetwork/claude-setup-system",
        "codex": "github.com/NDDev-OpenNetwork/codex-setup-system",
        "pi": "github.com/NDDev-OpenNetwork/pi-setup-system",
        "opencode": "github.com/NDDev-OpenNetwork/opencode-setup-system",
        "grok-build": "github.com/NDDev-OpenNetwork/grok-setup-system",
        "cursor": "github.com/NDDev-OpenNetwork/cursor-setup-system",
        "antigravity": "github.com/NDDev-OpenNetwork/antigravity-setup-system",
    }
)

_ASSET_TRIPLES: Final[dict[str, tuple[str, str]]] = {
    "linux/x86_64": ("x86_64-unknown-linux-gnu", ""),
    "linux/arm64": ("aarch64-unknown-linux-gnu", ""),
    "macos/x86_64": ("x86_64-apple-darwin", ""),
    "macos/arm64": ("aarch64-apple-darwin", ""),
    "windows/x86_64": ("x86_64-pc-windows-msvc", ".exe"),
    "windows/arm64": ("aarch64-pc-windows-msvc", ".exe"),
}


@dataclass(frozen=True)
class ReleaseFacts:
    tag: str
    commit: str
    license_id: str
    assets: frozenset[str]


@dataclass(frozen=True)
class BoundRelease:
    harness_id: str
    repository: str
    tag: str
    commit: str
    provider_id: str
    provider_version: str
    protocol_version: int
    sequence: int
    artifact: Path
    manifest_path: Path
    artifact_digest: str
    artifact_url: str
    trust_level: Literal["verified_publisher", "build_attested"]
    manifest: release.ReleaseManifest


class ReleaseClient(Protocol):
    def resolve_tag(self, repository: str, tag: str | None) -> str: ...

    def facts(self, repository: str, tag: str) -> ReleaseFacts: ...

    def download(self, repository: str, tag: str, asset: str, destination: Path) -> None: ...


def repository_for_harness(harness: str) -> str:
    """Return the pinned OpenNetwork repository for a supported harness."""
    if harness not in HARNESS_IDS:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a supported harness identifier is required",
            details={"supported": ", ".join(sorted(HARNESS_IDS))},
            next_actions=["toolchain harnesses --json"],
        )
    repository = HARNESS_REPOSITORIES[harness]
    policy = release.pinned_policy()
    if repository not in policy.build_attestations:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the named harness has no attested OpenNetwork repository",
            details={"harness": harness, "repository": repository},
            next_actions=["provider trust --json"],
        )
    return repository


def sequence_from_tag(tag: str) -> int:
    """Encode exact `X.Y.Z` as a monotonic sequence. `latest` is not a tag."""
    lowered = tag.casefold()
    floating = any(
        mark == lowered or mark in lowered.split("/") for mark in release.FLOATING_MARKERS
    )
    if not tag or floating:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the release tag does not encode a closed sequence",
            details={"tag": tag},
        )
    matched = _SEMVER_TAG.fullmatch(tag)
    if matched is None:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the release tag does not encode a closed sequence",
            details={"tag": tag},
        )
    return (
        int(matched.group("major")) * 1_000_000
        + int(matched.group("minor")) * 1_000
        + int(matched.group("patch"))
    )


def asset_name(repository: str, platform_name: str) -> str:
    """GitHub asset basename for this OS/arch. Not a rustc target on Windows."""
    triple = _ASSET_TRIPLES.get(platform_name)
    if triple is None:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "no attested provider asset exists for this platform",
            details={"platform": platform_name},
        )
    target, suffix = triple
    return f"{repository.rsplit('/', 1)[-1]}-{target}{suffix}"


def artifact_url(repository: str, tag: str, asset: str) -> str:
    """Exact GitHub download address. The path contains the tag, never `latest`."""
    return f"https://github.com/{_owner_repo(repository)}/releases/download/{tag}/{asset}"


def inspect_provider(executable: Path) -> protocol_v3.ProviderCapabilities:
    """Read `provider-info` from already-attested bytes. Observing, not installing."""
    raw = conformance.invoke_argv((str(executable), "provider-info"), command="provider-info")
    if not isinstance(raw, dict) or "error" in raw:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the provider-info payload is not a v3 capability declaration",
            details={"artifact": redact_home(executable)},
        )
    try:
        return protocol_v3.parse_capabilities(cast(dict[str, object], raw))
    except (ValueError, TypeError, KeyError) as error:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the provider-info payload is not a v3 capability declaration",
            details={"detail": str(error)},
        ) from error


def fetch(
    *,
    harness: str,
    tag: str | None = None,
    directory: Path | None = None,
    artifact: Path | None = None,
    attestation_bundle: Path | None = None,
    github: ReleaseClient | None = None,
    inspect: Callable[[Path], protocol_v3.ProviderCapabilities] | None = None,
) -> BoundRelease:
    """Download or bind one attested OpenNetwork artifact and write its manifest."""
    repository = repository_for_harness(harness)
    policy = release.pinned_policy()
    if attestation_bundle is not None:
        bundle = attestation_bundle.expanduser()
        if bundle.is_symlink() or not bundle.is_file():
            raise CliFailure(
                "AI_STP_NOT_FOUND",
                "no regular provider attestation bundle sits at that path",
                details={"bundle": redact_home(bundle)},
            )
        attestation_bundle = bundle
    client = github if github is not None else GithubReleases()
    resolved_tag = client.resolve_tag(repository, tag)
    sequence = sequence_from_tag(resolved_tag)
    facts = client.facts(repository, resolved_tag)
    _require_commit(facts.commit)
    _require_license(facts.license_id)
    platform_name = release.current_platform()
    asset = asset_name(repository, platform_name)
    if asset not in facts.assets:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "the GitHub release does not contain this platform artifact",
            details={"tag": resolved_tag, "asset": asset, "platform": platform_name},
        )
    destination = _artifact_destination(harness, resolved_tag, asset, directory, artifact)
    if artifact is None:
        client.download(repository, resolved_tag, asset, destination)
    elif artifact.resolve() != destination.resolve():
        _copy_artifact(artifact, destination)
    _make_executable(destination)
    digest, size = release.artifact_identity(destination)
    rule = policy.build_attestations[repository]
    evidence = build_attestation.verify(
        destination,
        build_attestation.Policy(
            repository=_owner_repo(repository),
            source_commit=facts.commit,
            signer_workflow=rule.signer_workflow,
            verified_publisher=rule.verified_publisher,
        ),
        bundle=attestation_bundle,
    )
    capabilities = (inspect or inspect_provider)(destination)
    if capabilities.harness_id != harness:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the provider-info harness does not match the requested harness",
            details={"reported": capabilities.harness_id, "requested": harness},
        )
    url = artifact_url(repository, resolved_tag, asset)
    manifest = release.ReleaseManifest(
        provider_id=capabilities.provider_id,
        provider_version=capabilities.provider_version,
        protocol_version=protocol_v3.VERSION,
        repository=repository,
        commit=facts.commit,
        license=facts.license_id,
        artifact_url=url,
        artifact_size=size,
        artifact_digest=digest,
        entry_point=destination.name,
        supported_os=frozenset(capabilities.supported_os),
        supported_arch=frozenset(capabilities.supported_arch),
        sequence=sequence,
        policy_id=policy.policy_id,
        publisher=_publisher(repository),
        signing_key=ATTESTED_SIGNING_KEY,
        signature_subject=policy.signature_subject,
        signature="",
    )
    verdict = release.verify_attested(
        manifest,
        policy,
        known_sequence=0,
        observed_digest=digest,
        observed_size=size,
        platform=platform_name,
    )
    if not verdict.accepted:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the bound provider release does not satisfy the pinned trust policy",
            details={"refusals": ", ".join(item.code for item in verdict.refusals)},
            next_actions=["provider trust --json"],
        )
    if evidence.trust_level not in {"verified_publisher", "build_attested"}:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the provider artifact has no acceptable GitHub build attestation",
            details={"repository": repository},
        )
    manifest_path = destination.parent / MANIFEST_NAME
    write_private(manifest_path, release.serialize_manifest(manifest))
    trust_level = cast(Literal["verified_publisher", "build_attested"], evidence.trust_level)
    return BoundRelease(
        harness_id=harness,
        repository=repository,
        tag=resolved_tag,
        commit=facts.commit,
        provider_id=capabilities.provider_id,
        provider_version=capabilities.provider_version,
        protocol_version=protocol_v3.VERSION,
        sequence=sequence,
        artifact=destination,
        manifest_path=manifest_path,
        artifact_digest=digest,
        artifact_url=url,
        trust_level=trust_level,
        manifest=manifest,
    )


class GithubReleases:
    """Exact GitHub release facts through `gh`. No `latest` in artifact URLs."""

    def resolve_tag(self, repository: str, tag: str | None) -> str:
        if tag:
            sequence_from_tag(tag)
            return tag
        payload = _gh_json(
            ("release", "view", "--repo", _owner_repo(repository), "--json", "tagName"),
            timeout=60,
        )
        if not isinstance(payload, dict):
            raise CliFailure(
                "AI_STP_DEPENDENCY_UNAVAILABLE",
                "GitHub release metadata is not valid JSON",
                details={"dependency": "gh"},
            )
        resolved = payload.get("tagName")
        if not isinstance(resolved, str) or not resolved:
            raise CliFailure(
                "AI_STP_PRECONDITION_FAILED",
                "GitHub release metadata is unavailable",
                details={"repository": repository},
            )
        sequence_from_tag(resolved)
        return resolved

    def facts(self, repository: str, tag: str) -> ReleaseFacts:
        owner_repo = _owner_repo(repository)
        release_payload = _gh_json(
            ("release", "view", tag, "--repo", owner_repo, "--json", "tagName,assets"),
            timeout=60,
        )
        commit_payload = _gh_json(("api", f"repos/{owner_repo}/commits/{tag}"), timeout=60)
        repo_payload = _gh_json(("api", f"repos/{owner_repo}"), timeout=60)
        assets = _asset_names(release_payload)
        commit = _commit_sha(commit_payload)
        license_id = _spdx_license(repo_payload)
        return ReleaseFacts(tag=tag, commit=commit, license_id=license_id, assets=assets)

    def download(self, repository: str, tag: str, asset: str, destination: Path) -> None:
        ensure_directory(destination.parent)
        _gh(
            (
                "release",
                "download",
                tag,
                "--repo",
                _owner_repo(repository),
                "--pattern",
                asset,
                "--dir",
                str(destination.parent),
                "--clobber",
            ),
            timeout=180,
            unavailable="the GitHub release artifact could not be downloaded",
        )
        if destination.is_symlink() or not destination.is_file():
            raise CliFailure(
                "AI_STP_NOT_FOUND",
                "the GitHub release does not contain this platform artifact",
                details={"asset": asset, "tag": tag},
            )


def _owner_repo(repository: str) -> str:
    if not repository.startswith(_GITHUB_PREFIX):
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the named harness has no attested OpenNetwork repository",
            details={"repository": repository},
        )
    return repository.removeprefix(_GITHUB_PREFIX)


def _publisher(repository: str) -> str:
    return _owner_repo(repository).split("/", 1)[0]


def _require_commit(commit: str) -> None:
    if _COMMIT.fullmatch(commit) is None:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the GitHub release names no exact commit",
            details={"commit": commit},
        )


def _require_license(license_id: str) -> None:
    if not license_id or license_id in {"NOASSERTION", "NONE"}:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the GitHub repository declares no SPDX license",
            details={"license": license_id},
        )


def _artifact_destination(
    harness: str,
    tag: str,
    asset: str,
    directory: Path | None,
    artifact: Path | None,
) -> Path:
    if directory is not None:
        place = directory.expanduser()
        if place.exists() and (place.is_symlink() or not place.is_dir()):
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                "the provider fetch destination must be a real directory, not a symlink",
                details={"directory": redact_home(place)},
            )
        ensure_directory(place)
        return (place / asset).resolve()
    if artifact is not None:
        return artifact.expanduser().resolve()
    return (data_dir() / "providers" / harness / tag / asset).resolve()


def _copy_artifact(source: Path, destination: Path) -> None:
    digest_source, _ = release.artifact_identity(source.expanduser())
    ensure_directory(destination.parent)
    if source.expanduser().resolve() == destination.resolve():
        return
    if destination.exists() and destination.is_symlink():
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the provider artifact must be one existing regular file, not a symlink",
            details={"artifact": redact_home(destination)},
        )
    shutil.copy2(source.expanduser(), destination)
    copied, _ = release.artifact_identity(destination)
    if copied != digest_source:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the copied provider artifact is not the source file",
            details={"source": redact_home(source), "destination": redact_home(destination)},
        )


def _make_executable(path: Path) -> None:
    if os.name == "nt":
        return
    mode = stat.S_IMODE(path.stat().st_mode)
    path.chmod(mode | stat.S_IXUSR)


def _asset_names(payload: JsonValue) -> frozenset[str]:
    if not isinstance(payload, dict):
        raise CliFailure(
            "AI_STP_DEPENDENCY_UNAVAILABLE",
            "GitHub release metadata is not valid JSON",
            details={"dependency": "gh"},
        )
    assets = payload.get("assets")
    if not isinstance(assets, list):
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "GitHub release metadata is unavailable",
            details={"field": "assets"},
        )
    names: list[str] = []
    for item in assets:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if isinstance(name, str) and name:
            names.append(name)
    return frozenset(names)


def _commit_sha(payload: JsonValue) -> str:
    if not isinstance(payload, dict):
        raise CliFailure(
            "AI_STP_DEPENDENCY_UNAVAILABLE",
            "GitHub release metadata is not valid JSON",
            details={"dependency": "gh"},
        )
    sha = payload.get("sha")
    if not isinstance(sha, str):
        return ""
    return sha.casefold()


def _spdx_license(payload: JsonValue) -> str:
    if not isinstance(payload, dict):
        raise CliFailure(
            "AI_STP_DEPENDENCY_UNAVAILABLE",
            "GitHub release metadata is not valid JSON",
            details={"dependency": "gh"},
        )
    license_block = payload.get("license")
    if not isinstance(license_block, dict):
        return ""
    spdx = license_block.get("spdx_id")
    return spdx if isinstance(spdx, str) else ""


def _gh_json(arguments: Sequence[str], *, timeout: int) -> JsonValue:
    raw = _gh(arguments, timeout=timeout, unavailable="GitHub release metadata is unavailable")
    try:
        parsed: object = json.loads(raw)
    except ValueError as error:
        raise CliFailure(
            "AI_STP_DEPENDENCY_UNAVAILABLE",
            "GitHub release metadata is not valid JSON",
            details={"dependency": "gh"},
        ) from error
    return cast(JsonValue, parsed)


def _gh(arguments: Sequence[str], *, timeout: int, unavailable: str) -> str:
    command = ["gh", *arguments]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            shell=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as error:
        raise CliFailure(
            "AI_STP_DEPENDENCY_UNAVAILABLE",
            unavailable,
            details={"dependency": "gh", "exception": type(error).__name__},
        ) from error
    if completed.returncode != 0:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            unavailable,
            details={"dependency": "gh"},
        )
    return completed.stdout
