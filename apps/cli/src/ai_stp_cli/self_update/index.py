"""PyPI JSON API plus the install-visible Simple Index (`SPEC-072` REQ-7203/7204)."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol, cast
from urllib.parse import urlparse

import httpx
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.paths import ensure_directory, redact_home
from ai_stp_cli.runtime import DISTRIBUTION

PROJECT: Final[str] = DISTRIBUTION
INDEX_ORIGIN: Final[str] = "https://pypi.org"
USER_AGENT: Final[str] = "ai-stp-cli"
WHEEL_SUFFIX: Final[str] = "-py3-none-any.whl"
JSON_LIMIT: Final[int] = 2_000_000
WHEEL_LIMIT: Final[int] = 80_000_000
STARTUP_TIMEOUT: Final[float] = 0.5
CHECK_TIMEOUT: Final[float] = 10.0


@dataclass(frozen=True)
class WheelFile:
    version: str
    filename: str
    url: str
    size: int
    sha256: str
    yanked: bool
    requires_python: str | None


@dataclass(frozen=True)
class Candidate:
    version: str
    wheel: WheelFile
    simple_index_ready: bool
    reason: str


class ReleaseIndex(Protocol):
    def project(self, project: str, *, timeout: float) -> Mapping[str, object]: ...

    def simple_files(self, project: str, *, timeout: float) -> Sequence[WheelFile]: ...

    def download(self, url: str, destination: Path, *, expected_size: int) -> None: ...


class PypiIndex:
    """JSON API for metadata, Simple Index for install-ready files."""

    def __init__(self, origin: str = INDEX_ORIGIN) -> None:
        parsed = urlparse(origin)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                "the package index origin must be HTTPS without credentials",
                details={"origin": origin},
            )
        self.origin = f"{parsed.scheme}://{parsed.netloc}"

    def project(self, project: str, *, timeout: float) -> Mapping[str, object]:
        return _get_json(
            f"{self.origin}/pypi/{project}/json",
            timeout=timeout,
            accept="application/json",
            limit=JSON_LIMIT,
        )

    def simple_files(self, project: str, *, timeout: float) -> Sequence[WheelFile]:
        payload = _get_json(
            f"{self.origin}/simple/{project}/",
            timeout=timeout,
            accept="application/vnd.pypi.simple.v1+json",
            limit=JSON_LIMIT,
        )
        files = payload.get("files")
        if not isinstance(files, list):
            return ()
        found: list[WheelFile] = []
        for raw in cast(list[object], files):
            parsed = _simple_file(raw)
            if parsed is not None:
                found.append(parsed)
        return tuple(found)

    def download(self, url: str, destination: Path, *, expected_size: int) -> None:
        _require_https(url)
        if expected_size <= 0 or expected_size > WHEEL_LIMIT:
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                "the planned wheel size is not acceptable",
                details={"size": str(expected_size)},
            )
        ensure_directory(destination.parent)
        if destination.is_symlink():
            raise CliFailure("AI_STP_PLAN_STALE", "the download destination is a symlink")
        handle_fd, temporary_name = tempfile.mkstemp(prefix=".download-", dir=destination.parent)
        temporary = Path(temporary_name)
        try:
            with (
                os.fdopen(handle_fd, "wb") as handle,
                httpx.Client(
                    timeout=CHECK_TIMEOUT,
                    follow_redirects=False,
                    headers=_headers("application/octet-stream"),
                ) as client,
                client.stream("GET", url) as response,
            ):
                if response.status_code == 429:
                    raise _rate_limited(response)
                response.raise_for_status()
                written = 0
                for chunk in response.iter_bytes():
                    written += len(chunk)
                    if written > expected_size or written > WHEEL_LIMIT:
                        raise CliFailure(
                            "AI_STP_DEPENDENCY_UNAVAILABLE",
                            "the index artifact exceeded its declared size",
                        )
                    handle.write(chunk)
                if written != expected_size:
                    raise CliFailure("AI_STP_PLAN_STALE", "the wheel size does not match the plan")
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(destination)
        except httpx.HTTPError as error:
            raise CliFailure(
                "AI_STP_DEPENDENCY_UNAVAILABLE",
                "the CLI wheel could not be downloaded",
                details={"exception": type(error).__name__},
            ) from error
        finally:
            temporary.unlink(missing_ok=True)


def inspect_channel(
    project: Mapping[str, object],
    simple: Sequence[WheelFile],
    *,
    installed: str,
    channel: str,
    python: tuple[int, int, int],
    requested: str | None = None,
) -> tuple[Candidate | None, str, str]:
    """Classify the index without turning 'already current' into a command failure."""
    try:
        candidate = select_candidate(
            project,
            simple,
            installed=installed,
            channel=channel,
            python=python,
            requested=requested,
        )
    except CliFailure as failure:
        if requested:
            raise
        if failure.code == "AI_STP_PRECONDITION_FAILED" and "local version" in failure.message:
            return None, "source_managed", failure.message
        if failure.code == "AI_STP_PRECONDITION_FAILED" and "not a PEP 440" in failure.message:
            return None, "unsupported", failure.message
        if failure.code in {"AI_STP_PRECONDITION_FAILED", "AI_STP_NOT_FOUND"}:
            return None, "current", failure.message
        raise
    if "already installed" in candidate.reason:
        return candidate, "current", candidate.reason
    if not candidate.simple_index_ready:
        return candidate, "stale", candidate.reason
    return candidate, "available", candidate.reason


def select_candidate(
    project: Mapping[str, object],
    simple: Sequence[WheelFile],
    *,
    installed: str,
    channel: str,
    python: tuple[int, int, int],
    requested: str | None = None,
) -> Candidate:
    """Pick one compatible wheel. Absence is a reason, not a latest guess."""
    try:
        current = Version(installed)
    except InvalidVersion as error:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the installed CLI version is not a PEP 440 version",
            details={"installed": installed},
        ) from error
    if current.local:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "a local version is source-managed and is not compared to the index",
            details={"installed": installed},
        )
    wheels = _json_wheels(project)
    simple_by_name = {item.filename: item for item in simple}
    wanted: Version | None = None
    if requested:
        try:
            wanted = Version(requested)
        except InvalidVersion as error:
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                "the requested CLI version is not a PEP 440 version",
                details={"version": requested},
            ) from error
    eligible: list[WheelFile] = []
    for wheel in wheels:
        try:
            parsed = Version(wheel.version)
        except InvalidVersion:
            continue
        if wheel.yanked or parsed.local or parsed.is_devrelease:
            continue
        if channel == "stable" and parsed.is_prerelease:
            continue
        if wanted is not None and parsed != wanted:
            continue
        if not _python_matches(wheel.requires_python, python):
            continue
        if wanted is None and parsed <= current:
            continue
        eligible.append(wheel)
    if not eligible:
        reason = _empty_reason(wheels, current, channel, wanted, python, requested)
        raise CliFailure(
            "AI_STP_NOT_FOUND" if requested else "AI_STP_PRECONDITION_FAILED",
            reason,
            details={"installed": installed, "channel": channel},
        )
    chosen = max(eligible, key=lambda item: Version(item.version))
    simple_file = simple_by_name.get(chosen.filename)
    simple_ready = (
        simple_file is not None
        and simple_file.sha256 == chosen.sha256
        and simple_file.size == chosen.size
        and not simple_file.yanked
    )
    if wanted is not None and Version(chosen.version) == current:
        return Candidate(
            version=chosen.version,
            wheel=chosen,
            simple_index_ready=simple_ready,
            reason="requested version is already installed",
        )
    if not simple_ready:
        return Candidate(
            version=chosen.version,
            wheel=chosen,
            simple_index_ready=False,
            reason="JSON metadata names a wheel the Simple Index does not yet serve",
        )
    return Candidate(
        version=chosen.version,
        wheel=chosen,
        simple_index_ready=True,
        reason="a newer compatible wheel is on the Simple Index",
    )


def file_digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return f"sha256:{hasher.hexdigest()}"


def verify_wheel(path: Path, *, expected_digest: str, expected_size: int) -> None:
    if path.is_symlink() or not path.is_file():
        raise CliFailure(
            "AI_STP_PLAN_STALE",
            "the staged wheel is not a regular file",
            details={"path": redact_home(path)},
        )
    size = path.stat().st_size
    digest = file_digest(path)
    if size != expected_size or digest != expected_digest:
        raise CliFailure(
            "AI_STP_PLAN_STALE",
            "the staged wheel does not match the planned artifact",
            details={
                "path": redact_home(path),
                "expected_digest": expected_digest,
                "observed_digest": digest,
            },
        )


def _json_wheels(project: Mapping[str, object]) -> list[WheelFile]:
    releases = project.get("releases")
    if not isinstance(releases, dict):
        return []
    requires = None
    info = project.get("info")
    if isinstance(info, dict):
        raw_requires = cast(dict[str, object], info).get("requires_python")
        if isinstance(raw_requires, str):
            requires = raw_requires
    wheels: list[WheelFile] = []
    for version, files in cast(dict[object, object], releases).items():
        if not isinstance(version, str) or not isinstance(files, list):
            continue
        expected = f"{PROJECT.replace('-', '_')}-{version}{WHEEL_SUFFIX}"
        for raw in cast(list[object], files):
            if not isinstance(raw, dict):
                continue
            item = cast(dict[str, object], raw)
            if item.get("packagetype") != "bdist_wheel" or item.get("filename") != expected:
                continue
            url = item.get("url")
            size = item.get("size")
            digests = item.get("digests")
            sha = None
            if isinstance(digests, dict):
                held = cast(dict[str, object], digests).get("sha256")
                if isinstance(held, str) and len(held) == 64:
                    sha = held
            if not isinstance(url, str) or not isinstance(size, int) or sha is None:
                continue
            yanked = item.get("yanked") is True
            file_requires = item.get("requires_python")
            file_python = file_requires if isinstance(file_requires, str) else requires
            wheels.append(
                WheelFile(
                    version=version,
                    filename=expected,
                    url=url,
                    size=size,
                    sha256=sha,
                    yanked=yanked,
                    requires_python=file_python,
                )
            )
    return wheels


def _simple_file(raw: object) -> WheelFile | None:
    if not isinstance(raw, dict):
        return None
    item = cast(dict[str, object], raw)
    filename = item.get("filename")
    url = item.get("url")
    size = item.get("size")
    hashes = item.get("hashes")
    if not isinstance(filename, str) or not filename.endswith(WHEEL_SUFFIX):
        return None
    if not isinstance(url, str) or not isinstance(size, int) or not isinstance(hashes, dict):
        return None
    sha = cast(dict[str, object], hashes).get("sha256")
    if not isinstance(sha, str) or len(sha) != 64:
        return None
    yanked_value = item.get("yanked")
    yanked = yanked_value is True or isinstance(yanked_value, str)
    stem = filename[: -len(WHEEL_SUFFIX)]
    prefix = PROJECT.replace("-", "_") + "-"
    if not stem.startswith(prefix):
        return None
    version = stem[len(prefix) :]
    return WheelFile(
        version=version,
        filename=filename,
        url=url,
        size=size,
        sha256=sha,
        yanked=yanked,
        requires_python=None,
    )


def _python_matches(spec: str | None, python: tuple[int, int, int]) -> bool:
    if spec is None or spec == "":
        return True
    try:
        return SpecifierSet(spec).contains(".".join(str(part) for part in python), prereleases=True)
    except InvalidSpecifier:
        return False


def _empty_reason(
    wheels: Sequence[WheelFile],
    current: Version,
    channel: str,
    wanted: Version | None,
    python: tuple[int, int, int],
    requested: str | None,
) -> str:
    if requested:
        matching = [item for item in wheels if item.version == requested]
        if not matching:
            return "the requested CLI version is not on the index"
        if all(item.yanked for item in matching):
            return "the requested CLI version has been yanked"
        if not any(_python_matches(item.requires_python, python) for item in matching):
            return "the requested CLI version does not support this Python"
        return "the requested CLI version is not installable on this channel"
    newer: list[WheelFile] = []
    for item in wheels:
        try:
            parsed = Version(item.version)
        except InvalidVersion:
            continue
        if parsed > current:
            newer.append(item)
    if not newer:
        return "this installation is already the newest compatible release"
    if all(item.yanked for item in newer):
        return "newer versions exist but every file has been yanked"
    if channel == "stable" and all(Version(item.version).is_prerelease for item in newer):
        return "newer versions are pre-releases; set update.channel=prerelease to consider them"
    if not any(_python_matches(item.requires_python, python) for item in newer):
        return "newer versions exist but none support this Python"
    return "no compatible CLI wheel is installable"


def _get_json(url: str, *, timeout: float, accept: str, limit: int) -> dict[str, object]:
    _require_https(url)
    deadline = time.monotonic() + timeout
    try:
        with (
            httpx.Client(
                timeout=timeout,
                follow_redirects=False,
                headers=_headers(accept),
            ) as client,
            client.stream("GET", url) as response,
        ):
            content = bytearray()
            for chunk in response.iter_bytes():
                if time.monotonic() >= deadline:
                    raise httpx.TimeoutException("index response exceeded the total deadline")
                content.extend(chunk)
                if len(content) > limit:
                    raise CliFailure(
                        "AI_STP_DEPENDENCY_UNAVAILABLE", "the package index response is too large"
                    )
    except httpx.TimeoutException as error:
        raise CliFailure(
            "AI_STP_DEPENDENCY_UNAVAILABLE",
            "the package index timed out",
            details={"origin": urlparse(url).netloc, "exception": type(error).__name__},
            retryable=True,
        ) from error
    except httpx.HTTPError as error:
        raise CliFailure(
            "AI_STP_DEPENDENCY_UNAVAILABLE",
            "the package index could not be reached",
            details={"origin": urlparse(url).netloc, "exception": type(error).__name__},
            retryable=True,
        ) from error
    if response.status_code == 429:
        raise _rate_limited(response)
    if response.status_code >= 500:
        raise CliFailure(
            "AI_STP_DEPENDENCY_UNAVAILABLE",
            "the package index is unavailable",
            details={"status": str(response.status_code)},
            retryable=True,
        )
    if response.status_code != 200:
        raise CliFailure(
            "AI_STP_DEPENDENCY_UNAVAILABLE",
            "the package index refused the request",
            details={"status": str(response.status_code)},
        )
    if len(content) > limit:
        raise CliFailure(
            "AI_STP_DEPENDENCY_UNAVAILABLE",
            "the package index response is too large",
            details={"bytes": str(len(content))},
        )
    try:
        payload: object = json.loads(content)
    except ValueError as error:
        raise CliFailure(
            "AI_STP_DEPENDENCY_UNAVAILABLE",
            "the package index did not return JSON",
            details={"origin": urlparse(url).netloc},
        ) from error
    if not isinstance(payload, dict):
        raise CliFailure(
            "AI_STP_DEPENDENCY_UNAVAILABLE",
            "the package index did not return an object",
            details={"origin": urlparse(url).netloc},
        )
    return cast(dict[str, object], payload)


def _rate_limited(response: httpx.Response) -> CliFailure:
    retry_after = response.headers.get("Retry-After")
    details = {"status": "429"}
    if retry_after:
        details["retry_after"] = retry_after
    return CliFailure(
        "AI_STP_RATE_LIMITED",
        "the package index asked this client to wait",
        details=details,
        retryable=True,
    )


def _headers(accept: str) -> dict[str, str]:
    return {"User-Agent": USER_AGENT, "Accept": accept}


def _require_https(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "package index URLs must be HTTPS without credentials",
            details={"url": url},
        )
    if parsed.hostname == "pypi.org" and parsed.path.startswith("/pypi/ai-stp-cli"):
        return
    if parsed.hostname == "pypi.org" and parsed.path.startswith("/simple/ai-stp-cli"):
        return
    if parsed.hostname in {"files.pythonhosted.org", "pypi.org"}:
        return
    raise CliFailure(
        "AI_STP_VALIDATION_ERROR",
        "refusing a package URL outside PyPI",
        details={"host": parsed.hostname or ""},
    )
