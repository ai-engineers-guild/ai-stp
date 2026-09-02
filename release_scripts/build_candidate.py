"""Build and verify the unpublished Python release candidate (`#185`).

The builder intentionally has no upload operation. It produces the exact files
that a later protected OIDC publication job may consume: reproducible wheels and
sdists, a deterministic CycloneDX SBOM, a release manifest and SHA-256 sums.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import unicodedata
import uuid
import zipfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from email.parser import Parser
from pathlib import Path
from typing import Any, Final, cast

ROOT: Final[Path] = Path(__file__).resolve().parents[1]
REPOSITORY: Final[str] = "https://github.com/ai-engineers-guild/ai-stp"
PUBLISHABLE: Final[dict[str, Path]] = {
    "ai-stp-foundation": ROOT / "packages" / "foundation" / "pyproject.toml",
    "ai-stp-passports": ROOT / "packages" / "passports" / "pyproject.toml",
    "ai-stp-assurance": ROOT / "packages" / "assurance" / "pyproject.toml",
    "ai-stp-contracts": ROOT / "packages" / "contracts" / "pyproject.toml",
    "ai-stp-sources": ROOT / "packages" / "sources" / "pyproject.toml",
    "ai-stp-cli": ROOT / "apps" / "cli" / "pyproject.toml",
}
INTERNAL_DEPENDENCIES: Final[dict[str, frozenset[str]]] = {
    "ai-stp-foundation": frozenset(),
    "ai-stp-passports": frozenset({"ai-stp-foundation"}),
    "ai-stp-assurance": frozenset({"ai-stp-foundation", "ai-stp-passports"}),
    "ai-stp-contracts": frozenset({"ai-stp-assurance", "ai-stp-foundation", "ai-stp-passports"}),
    "ai-stp-sources": frozenset({"ai-stp-foundation", "ai-stp-passports"}),
    # `ai-stp-assurance` and `ai-stp-sources` were both absent here while the
    # manifest required them, so neither pin was ever checked. A dependency the
    # map does not name is a dependency the release does not verify.
    "ai-stp-cli": frozenset(
        {
            "ai-stp-assurance",
            "ai-stp-contracts",
            "ai-stp-foundation",
            "ai-stp-passports",
            "ai-stp-sources",
        }
    ),
}


class CandidateError(RuntimeError):
    """The candidate cannot be proven reproducible or publishable."""


@dataclass(frozen=True)
class CandidateEvidence:
    """A complete, checksum-verified candidate directory at one instant."""

    identity: tuple[int, int]
    manifest: dict[str, object]
    digests: dict[str, str]


def _run(arguments: Sequence[str], *, environment: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        arguments,
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip().splitlines()
        suffix = detail[-1] if detail else "command failed without stderr"
        raise CandidateError(f"{arguments[0]} failed: {suffix}")
    return result.stdout


def _git(*arguments: str) -> str:
    return _run(("git", *arguments)).strip()


def _project(path: Path) -> dict[str, object]:
    document = tomllib.loads(path.read_text(encoding="utf-8"))
    held = document.get("project")
    if not isinstance(held, dict):
        raise CandidateError(f"{path.relative_to(ROOT)} has no [project] table")
    return cast(dict[str, object], held)


def _versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for expected_name, path in PUBLISHABLE.items():
        project = _project(path)
        name = project.get("name")
        version = project.get("version")
        if name != expected_name or not isinstance(version, str) or not version:
            raise CandidateError(f"invalid name/version in {path.relative_to(ROOT)}")
        for field in ("description", "readme", "requires-python", "license", "authors"):
            if not project.get(field):
                raise CandidateError(f"{expected_name} is missing release metadata: {field}")
        versions[expected_name] = version
    if len(set(versions.values())) != 1:
        raise CandidateError(f"publishable package versions diverge: {versions}")
    return versions


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _build_once(output: Path, *, source_date_epoch: int) -> None:
    environment = {**os.environ, "SOURCE_DATE_EPOCH": str(source_date_epoch)}
    for package in PUBLISHABLE:
        _run(
            (
                "uv",
                "build",
                "--package",
                package,
                "--out-dir",
                str(output),
                "--no-build-logs",
                "--no-create-gitignore",
            ),
            environment=environment,
        )


def _digests(directory: Path) -> dict[str, str]:
    return {path.name: _sha256(path) for path in sorted(directory.iterdir()) if path.is_file()}


def _safe_member(name: str) -> str:
    """Return one portable archive path or fail before any extraction/install."""
    normalized = unicodedata.normalize("NFC", name.replace("\\", "/"))
    candidate = normalized.rstrip("/")
    parts = candidate.split("/")
    if (
        not candidate
        or normalized.startswith("/")
        or "\x00" in normalized
        or any(part in {"", ".", ".."} for part in parts)
        or parts[0].endswith(":")
    ):
        raise CandidateError(f"archive member escapes its root: {name}")
    return candidate


def _validate_member_names(names: Iterable[str]) -> None:
    """Reject exact, Unicode and case-folded collisions across target filesystems."""
    seen: set[str] = set()
    folded: dict[str, str] = {}
    for name in names:
        canonical = _safe_member(name)
        lowered = canonical.casefold()
        if canonical in seen:
            raise CandidateError(f"archive repeats one member path: {canonical}")
        if lowered in folded:
            raise CandidateError(
                f"archive member paths collide by case: {folded[lowered]} and {canonical}"
            )
        seen.add(canonical)
        folded[lowered] = canonical


def _metadata_fields(text: str, *, expected_name: str, expected_version: str) -> None:
    metadata = Parser().parsestr(text)
    expected = {
        "Name": expected_name,
        "Version": expected_version,
        "License-Expression": "AGPL-3.0-or-later",
    }
    for field, value in expected.items():
        if metadata.get(field) != value:
            raise CandidateError(f"{expected_name} metadata {field} does not equal {value!r}")
    if metadata.get("Requires-Python") != ">=3.12":
        raise CandidateError(f"{expected_name} has an unexpected Requires-Python")
    if not metadata.get("Summary") or not str(metadata.get_payload()).strip():
        raise CandidateError(f"{expected_name} has no summary or long description")
    urls = metadata.get_all("Project-URL", [])
    if not any(REPOSITORY in value for value in urls):
        raise CandidateError(f"{expected_name} metadata does not name the source repository")
    requirements = metadata.get_all("Requires-Dist", [])
    for dependency in INTERNAL_DEPENDENCIES[expected_name]:
        exact = f"{dependency}=={expected_version}"
        if exact not in requirements:
            raise CandidateError(f"{expected_name} does not pin {exact} in release metadata")


def _validate_wheel(path: Path, *, name: str, version: str) -> None:
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        names = [member.filename for member in members]
        _validate_member_names(names)
        for member in members:
            mode = member.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise CandidateError(f"{path.name} carries a symbolic link")
            kind = stat.S_IFMT(mode)
            if kind not in {0, stat.S_IFREG, stat.S_IFDIR}:
                raise CandidateError(f"{path.name} carries a non-regular archive member")
        metadata_names = [member for member in names if member.endswith(".dist-info/METADATA")]
        license_names = [member for member in names if ".dist-info/licenses/LICENSE" in member]
        if len(metadata_names) != 1 or len(license_names) != 1:
            raise CandidateError(f"{path.name} must carry one METADATA and one LICENSE")
        text = archive.read(metadata_names[0]).decode("utf-8")
    _metadata_fields(text, expected_name=name, expected_version=version)


def _validate_sdist(path: Path, *, name: str, version: str) -> None:
    with tarfile.open(path, mode="r:gz") as archive:
        members = archive.getmembers()
        _validate_member_names(member.name for member in members)
        for member in members:
            if member.type not in {tarfile.REGTYPE, tarfile.AREGTYPE, tarfile.DIRTYPE}:
                raise CandidateError(f"{path.name} carries a non-regular archive member")
        metadata = [member for member in members if member.name.endswith("/PKG-INFO")]
        licenses = [member for member in members if member.name.endswith("/LICENSE")]
        if len(metadata) != 1 or len(licenses) != 1:
            raise CandidateError(f"{path.name} must carry one PKG-INFO and one LICENSE")
        stream = archive.extractfile(metadata[0])
        if stream is None:
            raise CandidateError(f"{path.name} PKG-INFO is not readable")
        text = stream.read().decode("utf-8")
    _metadata_fields(text, expected_name=name, expected_version=version)


def _validate_artifacts(directory: Path, versions: dict[str, str]) -> None:
    expected_count = len(versions) * 2
    artifacts = sorted(path for path in directory.iterdir() if path.is_file())
    if len(artifacts) != expected_count:
        raise CandidateError(f"expected {expected_count} distributions, found {len(artifacts)}")
    for name, version in versions.items():
        stem = name.replace("-", "_")
        wheels = list(directory.glob(f"{stem}-{version}-*.whl"))
        sdists = list(directory.glob(f"{stem}-{version}.tar.gz"))
        if len(wheels) != 1 or len(sdists) != 1:
            raise CandidateError(f"{name} did not produce exactly one wheel and sdist")
        _validate_wheel(wheels[0], name=name, version=version)
        _validate_sdist(sdists[0], name=name, version=version)


def _sbom(*, git_sha: str, source_date_epoch: int) -> bytes:
    raw = _run(
        (
            "uv",
            "export",
            "--preview-features",
            "sbom-export",
            "--format",
            "cyclonedx1.5",
            "--package",
            "ai-stp-cli",
            "--no-dev",
            "--locked",
        )
    )
    document = cast(dict[str, Any], json.loads(raw))
    document["serialNumber"] = (
        f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, REPOSITORY + '/commit/' + git_sha)}"
    )
    metadata = document.get("metadata")
    if not isinstance(metadata, dict):
        raise CandidateError("CycloneDX export has no metadata object")
    metadata["timestamp"] = (
        datetime.fromtimestamp(source_date_epoch, tz=UTC)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )
    return (
        json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()


def _artifact_rows(paths: Iterable[Path]) -> list[dict[str, object]]:
    return [
        {"name": path.name, "sha256": _sha256(path), "size_bytes": path.stat().st_size}
        for path in sorted(paths)
    ]


def verify_candidate_evidence(directory: Path) -> CandidateEvidence:
    """Prove that an existing output is one complete candidate we own.

    ``--replace`` is a convenience for the default ignored output directory,
    not authority to recursively delete an arbitrary caller-selected directory.
    A generated candidate is self-describing and checksums every file, so use
    that evidence as the ownership marker and refuse anything incomplete,
    altered or containing an extra entry.
    """
    try:
        info = directory.lstat()
    except OSError as error:
        raise CandidateError(f"cannot inspect existing release output: {directory}") from error
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise CandidateError(f"release output is not a real directory: {directory}")

    entries = sorted(directory.iterdir(), key=lambda path: path.name)
    for entry in entries:
        try:
            entry_info = entry.lstat()
        except OSError as error:
            raise CandidateError(
                f"cannot inspect existing candidate entry: {entry.name}"
            ) from error
        if stat.S_ISLNK(entry_info.st_mode) or not stat.S_ISREG(entry_info.st_mode):
            raise CandidateError(
                f"existing release output is not a verified candidate: {entry.name}"
            )

    manifest_path = directory / "release-manifest.json"
    sums_path = directory / "SHA256SUMS"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        sum_lines = sums_path.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CandidateError("existing release output has no valid candidate evidence") from error
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_version") != 1
        or manifest.get("repository") != REPOSITORY
    ):
        raise CandidateError("existing release output has no valid candidate manifest")

    expected: dict[str, str] = {}
    for line in sum_lines:
        digest, separator, name = line.partition("  ")
        if (
            separator != "  "
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            or _safe_member(name) != name
            or "/" in name
            or name in expected
        ):
            raise CandidateError("existing release output has invalid SHA256SUMS")
        expected[name] = digest

    observed = {entry.name for entry in entries if entry.name != "SHA256SUMS"}
    if set(expected) != observed:
        raise CandidateError("existing release output is not exactly covered by SHA256SUMS")
    for name, digest in expected.items():
        if _sha256(directory / name) != digest:
            raise CandidateError(f"existing release output was modified: {name}")
    return CandidateEvidence(
        identity=(info.st_dev, info.st_ino),
        manifest=cast(dict[str, object], manifest),
        digests=expected,
    )


def _replaceable_candidate_identity(directory: Path) -> tuple[int, int]:
    """Return identity only after the public evidence verifier succeeds."""
    return verify_candidate_evidence(directory).identity


def build_candidate(
    output: Path,
    *,
    allow_dirty: bool,
    expected_version: str | None,
    require_tag: bool,
    replace: bool,
) -> dict[str, object]:
    """Build the verified candidate and place it at ``output``."""
    versions = _versions()
    version = next(iter(versions.values()))
    if expected_version is not None and version != expected_version:
        raise CandidateError(f"package version is {version}, expected {expected_version}")

    git_sha = _git("rev-parse", "HEAD")
    dirty = bool(_git("status", "--porcelain"))
    if dirty and not allow_dirty:
        raise CandidateError("release candidates require a clean worktree")
    if require_tag:
        tag = _git("describe", "--tags", "--exact-match", "HEAD")
        if tag != f"v{version}":
            raise CandidateError(f"release tag is {tag!r}, expected 'v{version}'")
    source_date_epoch = int(_git("show", "-s", "--format=%ct", "HEAD"))

    if output.is_symlink():
        raise CandidateError(f"unsafe release output: {output}")
    destination = output.resolve()
    forbidden = {Path("/").resolve(), Path.home().resolve(), ROOT.resolve()}
    if destination in forbidden:
        raise CandidateError(f"unsafe release output: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    existing_identity: tuple[int, int] | None = None
    if destination.exists():
        if not destination.is_dir():
            raise CandidateError(f"release output is not a directory: {destination}")
        if not replace:
            raise CandidateError(f"release output already exists: {destination}")
        existing_identity = _replaceable_candidate_identity(destination)

    with tempfile.TemporaryDirectory(prefix="ai-stp-release-") as held:
        temporary = Path(held)
        first = temporary / "first"
        second = temporary / "second"
        candidate = temporary / "candidate"
        first.mkdir()
        second.mkdir()
        candidate.mkdir()
        _build_once(first, source_date_epoch=source_date_epoch)
        _build_once(second, source_date_epoch=source_date_epoch)
        if _digests(first) != _digests(second):
            raise CandidateError("two builds from the same tree are not byte-identical")
        _validate_artifacts(first, versions)

        for artifact in sorted(first.iterdir()):
            shutil.copyfile(artifact, candidate / artifact.name)

        sbom = _sbom(git_sha=git_sha, source_date_epoch=source_date_epoch)
        if sbom != _sbom(git_sha=git_sha, source_date_epoch=source_date_epoch):
            raise CandidateError("normalized CycloneDX export is not deterministic")
        (candidate / "ai-stp-cli.cdx.json").write_bytes(sbom)

        distributions = [
            path
            for path in candidate.iterdir()
            if path.suffix == ".whl" or path.name.endswith(".tar.gz")
        ]
        manifest: dict[str, object] = {
            "schema_version": 1,
            "repository": REPOSITORY,
            "git_sha": git_sha,
            "dirty": dirty,
            "source_date_epoch": source_date_epoch,
            "version": version,
            "install_command": f"uv tool install ai-stp-cli=={version}",
            "packages": list(PUBLISHABLE),
            "artifacts": _artifact_rows(distributions),
            "sbom": _artifact_rows([candidate / "ai-stp-cli.cdx.json"])[0],
        }
        (candidate / "release-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        checksummed = [path for path in candidate.iterdir() if path.name != "SHA256SUMS"]
        sums = "".join(f"{_sha256(path)}  {path.name}\n" for path in sorted(checksummed))
        (candidate / "SHA256SUMS").write_text(sums, encoding="ascii")

        staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
        try:
            shutil.rmtree(staging)
            shutil.copytree(candidate, staging)
            if destination.exists():
                current_identity = _replaceable_candidate_identity(destination)
                if current_identity != existing_identity:
                    raise CandidateError("existing release output changed during candidate build")
                shutil.rmtree(destination)
            staging.replace(destination)
        finally:
            if staging.exists():
                shutil.rmtree(staging)

    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "release-candidate")
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument("--expected-version")
    parser.add_argument("--require-tag", action="store_true")
    parser.add_argument("--replace", action="store_true")
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    options = _parser().parse_args(arguments)
    try:
        manifest = build_candidate(
            options.output,
            allow_dirty=options.allow_dirty,
            expected_version=options.expected_version,
            require_tag=options.require_tag,
            replace=options.replace,
        )
    except CandidateError as error:
        print(f"release-candidate: {error}", file=sys.stderr)
        return 1
    print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
