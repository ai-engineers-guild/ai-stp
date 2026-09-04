"""Bind a closed provider-release manifest from a PEP 740 wheel (`REQ-849`/`REQ-850`).

This is the second delivery channel. Default acquire stays on GitHub
(`ADR-0146`). `provider fetch --source index` is the explicit path. The
executable is not spawned until provenance and wheel inspection succeed.
"""

from __future__ import annotations

import json
import os
import stat
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Literal, Protocol, cast
from urllib.parse import urlparse

import httpx

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.paths import data_dir, ensure_directory, redact_home, write_private
from ai_stp_cli.provider import (
    attested_bind,
    index_attestation,
    index_wheel,
    protocol_v3,
    release,
)
from ai_stp_foundation.harnesses import HARNESS_IDS

_INDEX_ORIGIN = "https://pypi.org"
_USER_AGENT = "ai-stp-cli"

#: Platform tag inside a provider wheel filename. Must match what OpenNetwork
#: actually publishes, not a rustc target triple.
_WHEEL_TAGS: Mapping[str, str] = MappingProxyType(
    {
        "linux/x86_64": "manylinux_2_34_x86_64",
        "linux/arm64": "manylinux_2_34_aarch64",
        "macos/x86_64": "macosx_10_12_x86_64",
        "macos/arm64": "macosx_11_0_arm64",
        "windows/x86_64": "win_amd64",
        "windows/arm64": "win_arm64",
    }
)


@dataclass(frozen=True)
class IndexFile:
    filename: str
    url: str
    size: int


class IndexClient(Protocol):
    def resolve_version(self, project: str, version: str | None) -> str: ...

    def wheel(self, project: str, version: str, platform_name: str) -> IndexFile: ...

    def download(self, url: str, destination: Path) -> None: ...

    def provenance(self, project: str, version: str, filename: str) -> dict[str, object] | None: ...


def wheel_tag(platform_name: str) -> str:
    """Wheel platform tag OpenNetwork actually publishes for this machine."""
    tag = _WHEEL_TAGS.get(platform_name)
    if tag is None:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "no attested provider asset exists for this platform",
            details={"platform": platform_name},
        )
    return tag


def project_for_harness(harness: str) -> str:
    """PyPI project name for a supported harness. Derived from the GitHub repo."""
    repository = attested_bind.repository_for_harness(harness)
    return repository.rsplit("/", 1)[-1]


def fetch(
    *,
    harness: str,
    tag: str | None = None,
    directory: Path | None = None,
    artifact: Path | None = None,
    provenance: Path | None = None,
    index: IndexClient | None = None,
    inspect: Callable[[Path], protocol_v3.ProviderCapabilities] | None = None,
    verifier: index_attestation.BundleVerifier | None = None,
) -> attested_bind.BoundRelease:
    """Download or bind one index wheel and write its manifest after provenance."""
    if harness not in HARNESS_IDS:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a supported harness identifier is required",
            details={"supported": ", ".join(sorted(HARNESS_IDS))},
            next_actions=["toolchain harnesses --json"],
        )
    policy = release.pinned_policy()
    project = project_for_harness(harness)
    rule = policy.index_publishers.get(project)
    if rule is None:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the named harness has no pinned index publisher",
            details={"harness": harness, "project": project},
            next_actions=["provider trust --json"],
        )
    client = index if index is not None else PypiIndex()
    version = client.resolve_version(project, tag)
    sequence = attested_bind.sequence_from_tag(version)
    platform_name = release.current_platform()
    held = client.wheel(project, version, platform_name)
    destination = _destination(harness, version, held.filename, directory, artifact)
    if artifact is None:
        client.download(held.url, destination)
    elif artifact.resolve() != destination.resolve():
        destination.write_bytes(artifact.read_bytes())
    payload = index_wheel.inspect(
        destination, project=project, version=version, platform_name=platform_name
    )
    document = _load_provenance(client, project, version, held.filename, provenance)
    evidence = index_attestation.verify(destination, document, rule, verifier=verifier)
    if not evidence.identity.source_commit:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the index provenance identity does not name a source commit",
            details={"project": project},
        )
    executable = destination.parent / payload.executable_name
    executable.write_bytes(payload.executable)
    if os.name != "nt":
        mode = stat.S_IMODE(executable.stat().st_mode)
        executable.chmod(mode | stat.S_IXUSR)
    digest, size = release.artifact_identity(executable)
    capabilities = (inspect or attested_bind.inspect_provider)(executable)
    if capabilities.harness_id != harness:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the provider-info harness does not match the requested harness",
            details={"reported": capabilities.harness_id, "requested": harness},
        )
    github_repository = attested_bind.HARNESS_REPOSITORIES[harness]
    manifest = release.ReleaseManifest(
        provider_id=capabilities.provider_id,
        provider_version=capabilities.provider_version,
        protocol_version=protocol_v3.VERSION,
        repository=github_repository,
        commit=evidence.identity.source_commit,
        license=payload.license_id,
        artifact_url=held.url,
        artifact_size=size,
        artifact_digest=digest,
        entry_point=payload.executable_name,
        supported_os=frozenset(capabilities.supported_os),
        supported_arch=frozenset(capabilities.supported_arch),
        sequence=sequence,
        policy_id=policy.policy_id,
        publisher="NDDev-OpenNetwork",
        signing_key=attested_bind.ATTESTED_SIGNING_KEY,
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
    trust_level = evidence.trust_level
    if trust_level not in {"verified_publisher", "build_attested"}:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the provider wheel has no acceptable PEP 740 provenance",
            details={"project": project},
        )
    manifest_path = executable.parent / attested_bind.MANIFEST_NAME
    write_private(manifest_path, release.serialize_manifest(manifest))
    return attested_bind.BoundRelease(
        harness_id=harness,
        repository=github_repository,
        tag=version,
        commit=evidence.identity.source_commit,
        provider_id=capabilities.provider_id,
        provider_version=capabilities.provider_version,
        protocol_version=protocol_v3.VERSION,
        sequence=sequence,
        artifact=executable,
        manifest_path=manifest_path,
        artifact_digest=digest,
        artifact_url=held.url,
        trust_level=cast(Literal["verified_publisher", "build_attested"], trust_level),
        manifest=manifest,
    )


class PypiIndex:
    """Exact files from pypi.org. Artifact URLs contain the content hash, never `latest`."""

    def resolve_version(self, project: str, version: str | None) -> str:
        if version:
            attested_bind.sequence_from_tag(version)
            return version
        payload = _get_json(f"{_INDEX_ORIGIN}/pypi/{project}/json")
        found = payload.get("info")
        if not isinstance(found, dict):
            raise CliFailure(
                "AI_STP_DEPENDENCY_UNAVAILABLE",
                "the index package version is not a closed sequence",
                details={"project": project},
            )
        resolved = cast(dict[str, object], found).get("version")
        if not isinstance(resolved, str) or not resolved:
            raise CliFailure(
                "AI_STP_DEPENDENCY_UNAVAILABLE",
                "the index package version is not a closed sequence",
                details={"project": project},
            )
        attested_bind.sequence_from_tag(resolved)
        return resolved

    def wheel(self, project: str, version: str, platform_name: str) -> IndexFile:
        tag = wheel_tag(platform_name)
        payload = _get_json(f"{_INDEX_ORIGIN}/pypi/{project}/{version}/json")
        files = payload.get("urls")
        if not isinstance(files, list):
            raise CliFailure(
                "AI_STP_NOT_FOUND",
                "the index lists no wheel for this platform",
                details={"project": project, "version": version, "platform": platform_name},
            )
        wanted = f"{project.replace('-', '_')}-{version}-py3-none-{tag}.whl"
        for raw in cast(list[object], files):
            if not isinstance(raw, dict):
                continue
            item = cast(dict[str, object], raw)
            filename = item.get("filename")
            url = item.get("url")
            size = item.get("size")
            if filename == wanted and isinstance(url, str) and isinstance(size, int):
                _require_hashed_url(url)
                return IndexFile(filename=wanted, url=url, size=size)
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "the index lists no wheel for this platform",
            details={"project": project, "version": version, "platform": platform_name},
        )

    def download(self, url: str, destination: Path) -> None:
        _require_hashed_url(url)
        ensure_directory(destination.parent)
        try:
            with httpx.Client(timeout=60.0, follow_redirects=True, headers=_headers()) as client:
                response = client.get(url)
                response.raise_for_status()
                destination.write_bytes(response.content)
        except httpx.HTTPError as error:
            raise CliFailure(
                "AI_STP_DEPENDENCY_UNAVAILABLE",
                "the index artifact could not be downloaded",
                details={"url": url, "exception": type(error).__name__},
            ) from error
        if destination.is_symlink() or not destination.is_file():
            raise CliFailure(
                "AI_STP_NOT_FOUND",
                "the provider distribution is not a regular wheel",
                details={"artifact": redact_home(destination)},
            )

    def provenance(self, project: str, version: str, filename: str) -> dict[str, object] | None:
        url = f"{_INDEX_ORIGIN}/integrity/{project}/{version}/{filename}/provenance"
        try:
            with httpx.Client(timeout=30.0, follow_redirects=True, headers=_headers()) as client:
                response = client.get(url)
        except httpx.HTTPError as error:
            raise CliFailure(
                "AI_STP_DEPENDENCY_UNAVAILABLE",
                "index provenance verification is unavailable",
                details={"dependency": "pypi", "exception": type(error).__name__},
            ) from error
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise CliFailure(
                "AI_STP_DEPENDENCY_UNAVAILABLE",
                "index provenance verification is unavailable",
                details={"dependency": "pypi", "status": str(response.status_code)},
            )
        payload: object = response.json()
        if not isinstance(payload, dict):
            return None
        return cast(dict[str, object], payload)


def _destination(
    harness: str,
    version: str,
    filename: str,
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
        return (place / filename).resolve()
    if artifact is not None:
        return artifact.expanduser().resolve()
    return (data_dir() / "providers" / harness / version / filename).resolve()


def _load_provenance(
    client: IndexClient,
    project: str,
    version: str,
    filename: str,
    provenance: Path | None,
) -> dict[str, object] | None:
    if provenance is None:
        return client.provenance(project, version, filename)
    place = provenance.expanduser()
    if place.is_symlink() or not place.is_file():
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "the index serves no provenance for this file",
            details={"provenance": redact_home(place)},
        )
    try:
        payload: object = json.loads(place.read_text("utf-8"))
    except ValueError as error:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the index provenance is not a PEP 740 integrity document",
            details={"field": "<root>"},
        ) from error
    if not isinstance(payload, dict):
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the index provenance is not a PEP 740 integrity document",
            details={"field": "<root>"},
        )
    return cast(dict[str, object], payload)


def _get_json(url: str) -> dict[str, object]:
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True, headers=_headers()) as client:
            response = client.get(url)
            response.raise_for_status()
            payload: object = response.json()
    except httpx.HTTPError as error:
        raise CliFailure(
            "AI_STP_DEPENDENCY_UNAVAILABLE",
            "index provenance verification is unavailable",
            details={"dependency": "pypi", "exception": type(error).__name__},
        ) from error
    if not isinstance(payload, dict):
        raise CliFailure(
            "AI_STP_DEPENDENCY_UNAVAILABLE",
            "index provenance verification is unavailable",
            details={"dependency": "pypi"},
        )
    return cast(dict[str, object], payload)


def _headers() -> dict[str, str]:
    return {"User-Agent": _USER_AGENT, "Accept": "application/json"}


def _require_hashed_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or "latest" in url.casefold():
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the artifact address does not identify exact bytes",
            details={"url": url},
        )
    if "/packages/" not in parsed.path:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the artifact address does not identify exact bytes",
            details={"url": url},
        )
