"""Bounded source adapters for native component provenance (`#231`).

Harness state is untrusted input. This module reads only declared, bounded
metadata manifests and returns allowlisted facts. It never invokes Git, follows
an `installLocation` from a manifest, contacts a remote, or reflects parser
errors and arbitrary manifest values into diagnostics.
"""

import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final, cast
from urllib.parse import urlsplit

MAX_MANIFEST_BYTES: Final[int] = 4 * 1024 * 1024
MAX_DIAGNOSTICS: Final[int] = 100
MAX_SOURCE_ENTRIES: Final[int] = 2000
GIT_SHA: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{40}$")
GITHUB_SLUG: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9_.-]*[A-Za-z0-9])?/[A-Za-z0-9_.-]+$"
)
PLUGIN_KEY: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_.-]*@[A-Za-z0-9][A-Za-z0-9_.-]*$"
)


@dataclass(frozen=True)
class Diagnostic:
    """One safe reason source provenance could not be established."""

    code: str
    source: str
    reason: str


@dataclass(frozen=True)
class Candidate:
    """One installed global plugin with honest package/source provenance."""

    absolute: Path
    kind: str
    state: str
    repository: str | None
    revision: str | None
    subpath: str | None
    package_name: str
    package_version: str | None
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class Result:
    candidates: tuple[Candidate, ...]
    diagnostics: tuple[Diagnostic, ...]


def claude_plugins(config_root: Path) -> Result:
    """Find global Claude plugins and exact GitHub origins where proven.

    The adapter recognizes Claude's current v2 installation ledger. A different
    version is not guessed. Marketplace locations are reconstructed from the
    documented config layout; the untrusted `installLocation` value is ignored.
    """
    plugin_root = config_root / "plugins"
    installed_path = plugin_root / "installed_plugins.json"
    known_path = plugin_root / "known_marketplaces.json"
    try:
        installed_path.stat()
    except FileNotFoundError:
        return Result((), ())
    except OSError:
        # `_object` turns this into a bounded diagnostic without reflecting the
        # platform error string.
        pass

    diagnostics: list[Diagnostic] = []
    installed = _object(
        installed_path, "claude-installed-plugins", diagnostics, allowed_root=plugin_root
    )
    known = _object(known_path, "claude-known-marketplaces", diagnostics, allowed_root=plugin_root)
    if installed is None:
        return Result((), tuple(diagnostics))
    known = known or {}
    if installed.get("version") != 2 or not isinstance(installed.get("plugins"), dict):
        _diagnose(
            diagnostics,
            "unsupported_manifest",
            "claude-installed-plugins",
            "the installed plugin ledger is not supported version 2",
        )
        return Result((), tuple(diagnostics))

    cache_root = (plugin_root / "cache").resolve()
    marketplace_root = plugin_root / "marketplaces"
    manifest_cache: dict[str, dict[str, object] | None] = {}
    candidates: list[Candidate] = []
    plugins = cast(dict[str, object], installed["plugins"])
    for key in sorted(plugins):
        if PLUGIN_KEY.fullmatch(key) is None:
            _diagnose(
                diagnostics,
                "invalid_record",
                "claude-installed-plugins",
                "an installed plugin key has an invalid shape",
            )
            continue
        plugin_name, marketplace_name = key.rsplit("@", 1)
        records = plugins[key]
        if not isinstance(records, list):
            _record_problem(diagnostics, key)
            continue

        marketplace = known.get(marketplace_name)
        repository = _marketplace_repository(marketplace)
        if marketplace_name not in manifest_cache:
            manifest_path = (
                marketplace_root / marketplace_name / ".claude-plugin" / "marketplace.json"
            )
            manifest_cache[marketplace_name] = _object(
                manifest_path,
                f"claude-marketplace:{marketplace_name}",
                diagnostics,
                allowed_root=marketplace_root,
            )
        manifest = manifest_cache[marketplace_name]
        entry = _plugin_entry(manifest, plugin_name)
        if entry is None:
            _diagnose(
                diagnostics,
                "missing_source_entry",
                f"claude-plugin:{key}",
                "the installed plugin has no matching marketplace source entry",
            )

        for record in cast(list[object], records):
            candidate = _installed_candidate(
                key=key,
                plugin_name=plugin_name,
                marketplace_name=marketplace_name,
                marketplace_repository=repository,
                entry=entry,
                record=record,
                cache_root=cache_root,
                diagnostics=diagnostics,
            )
            if candidate is not None:
                candidates.append(candidate)

    unique = {
        (
            item.absolute,
            item.repository,
            item.revision,
            item.subpath,
            item.package_name,
            item.package_version,
        ): item
        for item in candidates
    }
    ordered = sorted(
        unique.values(),
        key=lambda item: (str(item.absolute), item.repository or "", item.revision or ""),
    )
    return Result(tuple(ordered), tuple(diagnostics))


def pi_git_packages(config_root: Path) -> Result:
    """Find exact GitHub checkouts in Pi's documented global Git cache.

    Pi settings may contain unrelated sensitive values, so discovery does not
    parse them. The documented cache layout supplies the repository identity;
    bounded Git administrative files supply the exact checked-out revision.
    No Git command, hook, package code or network operation is executed.
    """
    git_root = config_root / "git"
    if not git_root.exists():
        return Result((), ())
    diagnostics: list[Diagnostic] = []
    candidates: list[Candidate] = []
    hosts = _directories(git_root, "pi-git-cache", diagnostics)
    for host in hosts:
        if host.name.lower() != "github.com":
            continue
        for owner in _directories(host, "pi-git-cache:github.com", diagnostics):
            if _github_segment(owner.name) is None:
                _diagnose(
                    diagnostics,
                    "invalid_record",
                    "pi-git-cache:github.com",
                    "a repository owner directory has an invalid shape",
                )
                continue
            for repository_path in _directories(
                owner, f"pi-git-cache:github.com/{owner.name}", diagnostics
            ):
                repository = _github_repository(f"{owner.name}/{repository_path.name}")
                if repository is None:
                    _diagnose(
                        diagnostics,
                        "invalid_record",
                        f"pi-git-cache:github.com/{owner.name}",
                        "a repository directory has an invalid shape",
                    )
                    continue
                revision = _checkout_revision(repository_path, diagnostics)
                if revision is None:
                    continue
                candidates.append(
                    Candidate(
                        absolute=repository_path.resolve(),
                        kind="github",
                        state="exact",
                        repository=repository,
                        revision=revision,
                        subpath=None,
                        package_name=f"git:github.com/{owner.name}/{repository_path.name}",
                        package_version=None,
                        evidence=("pi:git-cache-layout", "git:checked-out-head"),
                    )
                )
    return Result(
        tuple(sorted(candidates, key=lambda item: (item.repository or "", str(item.absolute)))),
        tuple(diagnostics),
    )


def _installed_candidate(
    *,
    key: str,
    plugin_name: str,
    marketplace_name: str,
    marketplace_repository: str | None,
    entry: dict[str, object] | None,
    record: object,
    cache_root: Path,
    diagnostics: list[Diagnostic],
) -> Candidate | None:
    if not isinstance(record, dict):
        _record_problem(diagnostics, key)
        return None
    held = cast(dict[str, object], record)
    if held.get("scope") not in {"user", "managed"}:
        return None
    install_path = held.get("installPath")
    held_revision = held.get("gitCommitSha")
    version = held.get("version")
    if not isinstance(install_path, str) or (version is not None and not isinstance(version, str)):
        _record_problem(diagnostics, key)
        return None

    absolute = Path(install_path).expanduser()
    try:
        resolved = absolute.resolve(strict=True)
    except OSError:
        _record_problem(diagnostics, key, "the declared cache path is unavailable")
        return None
    expected = cache_root / marketplace_name / plugin_name
    relative = resolved.relative_to(expected) if resolved.is_relative_to(expected) else None
    if (
        not resolved.is_dir()
        or absolute.is_symlink()
        or relative is None
        or len(relative.parts) != 1
        or not resolved.is_relative_to(cache_root)
    ):
        _record_problem(diagnostics, key, "the declared cache path leaves its plugin cache root")
        return None

    installed_revision = (
        held_revision
        if isinstance(held_revision, str) and GIT_SHA.fullmatch(held_revision)
        else None
    )
    exact = (
        _github_source(entry.get("source"), marketplace_repository, installed_revision)
        if entry is not None
        else None
    )
    repository, source_revision, subpath = exact or (None, None, None)
    evidence = ["claude:installed_plugins:v2"]
    if entry is not None:
        evidence.append("claude:marketplace")
        if isinstance(entry.get("source"), str) and marketplace_repository is not None:
            evidence.append("claude:known_marketplaces")
    return Candidate(
        absolute=resolved,
        kind="github" if exact is not None else "package",
        state="exact" if exact is not None else "observed",
        repository=repository,
        revision=source_revision,
        subpath=subpath,
        package_name=key,
        package_version=version,
        evidence=tuple(evidence),
    )


def _github_source(
    source: object, marketplace_repository: str | None, installed_revision: str | None
) -> tuple[str, str, str | None] | None:
    if isinstance(source, str):
        subpath = _relative_subpath(source)
        if subpath is None or marketplace_repository is None or installed_revision is None:
            return None
        return marketplace_repository, installed_revision, subpath
    if not isinstance(source, dict):
        return None
    held = cast(dict[str, object], source)

    kind = held.get("source")
    repository: str | None = None
    subpath: str | None = None
    if kind == "github":
        repository = _github_repository(held.get("repo"))
    elif kind in {"url", "git-subdir"}:
        repository = _github_url_repository(held.get("url"))
        if kind == "git-subdir":
            subpath = _clean_subpath(held.get("path"))
            if subpath is None:
                return None
    if repository is None:
        return None
    declared = held.get("sha")
    revision = (
        declared
        if isinstance(declared, str) and GIT_SHA.fullmatch(declared)
        else installed_revision
    )
    if revision is None:
        return None
    return repository, revision, subpath


def _marketplace_repository(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    held = cast(dict[str, object], value)
    source = held.get("source")
    if not isinstance(source, dict):
        return None
    held_source = cast(dict[str, object], source)
    if held_source.get("source") != "github":
        return None
    return _github_repository(held_source.get("repo"))


def _github_repository(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    slug = value.removesuffix(".git")
    if GITHUB_SLUG.fullmatch(slug) is None:
        return None
    return f"https://github.com/{slug}"


def _github_url_repository(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    if value.startswith("git@github.com:"):
        return _github_repository(value.removeprefix("git@github.com:"))
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "github.com"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        return None
    return _github_repository(parsed.path.strip("/"))


def _relative_subpath(value: str) -> str | None:
    if not value.startswith("./"):
        return None
    return _clean_subpath(value[2:])


def _clean_subpath(value: object) -> str | None:
    if not isinstance(value, str) or not value or "//" in value or value.endswith("/"):
        return None
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        return None
    return path.as_posix()


def _plugin_entry(manifest: dict[str, object] | None, name: str) -> dict[str, object] | None:
    if manifest is None or not isinstance(manifest.get("plugins"), list):
        return None
    matches: list[dict[str, object]] = []
    for value in cast(list[object], manifest["plugins"]):
        if isinstance(value, dict):
            held = cast(dict[str, object], value)
            if held.get("name") == name:
                matches.append(held)
    return matches[0] if len(matches) == 1 else None


def _directories(root: Path, source: str, diagnostics: list[Diagnostic]) -> tuple[Path, ...]:
    try:
        resolved_root = root.resolve(strict=True)
        if root.is_symlink() or not resolved_root.is_dir():
            raise ValueError("not a directory")
        entries: list[Path] = []
        with os.scandir(root) as scan:
            for index, entry in enumerate(scan):
                if index >= MAX_SOURCE_ENTRIES:
                    raise ValueError("entry limit")
                path = Path(entry.path)
                if entry.is_symlink():
                    _diagnose(
                        diagnostics,
                        "invalid_record",
                        source,
                        "a symbolic link in a declared source directory was not followed",
                    )
                    continue
                if entry.is_dir(follow_symlinks=False):
                    entries.append(path)
    except (OSError, ValueError):
        _diagnose(
            diagnostics,
            "invalid_manifest",
            source,
            "a declared source directory is unreadable, unsafe or over its entry limit",
        )
        return ()
    return tuple(sorted(entries))


def _github_segment(value: str) -> str | None:
    return value if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value) else None


def _checkout_revision(repository: Path, diagnostics: list[Diagnostic]) -> str | None:
    git = repository / ".git"
    source = "pi-git-checkout"
    try:
        resolved_repository = repository.resolve(strict=True)
        resolved_git = git.resolve(strict=True)
        if (
            git.is_symlink()
            or not resolved_git.is_dir()
            or not resolved_git.is_relative_to(resolved_repository)
        ):
            raise ValueError("unsafe git directory")
        head = _text(git / "HEAD", allowed_root=git).strip()
        if GIT_SHA.fullmatch(head):
            return head
        if not head.startswith("ref: "):
            raise ValueError("invalid head")
        reference = head.removeprefix("ref: ")
        if (
            re.fullmatch(r"refs/(?:heads|tags)/[A-Za-z0-9][A-Za-z0-9._/-]*", reference) is None
            or "//" in reference
            or reference.endswith("/")
        ):
            raise ValueError("invalid reference")
        if any(part in {"", ".", ".."} for part in PurePosixPath(reference).parts):
            raise ValueError("unsafe reference")
        loose = git.joinpath(*PurePosixPath(reference).parts)
        if loose.exists():
            revision = _text(loose, allowed_root=git).strip()
            if not GIT_SHA.fullmatch(revision):
                raise ValueError("invalid loose reference")
            return revision
        packed = _text(git / "packed-refs", allowed_root=git)
        for line in packed.splitlines():
            if not line or line.startswith(("#", "^")):
                continue
            fields = line.split(" ", 1)
            if len(fields) == 2 and fields[1] == reference and GIT_SHA.fullmatch(fields[0]):
                return fields[0]
    except (FileNotFoundError, OSError, UnicodeError, ValueError):
        pass
    _diagnose(
        diagnostics,
        "invalid_record",
        source,
        "a Git package checkout has no safe exact HEAD revision",
    )
    return None


def _text(path: Path, *, allowed_root: Path) -> str:
    resolved_root = allowed_root.resolve(strict=True)
    resolved_path = path.resolve(strict=True)
    if not resolved_path.is_relative_to(resolved_root):
        raise ValueError("outside root")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as stream:
        metadata = os.fstat(stream.fileno())
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("not regular")
        payload = stream.read(MAX_MANIFEST_BYTES + 1)
    if len(payload) > MAX_MANIFEST_BYTES:
        raise ValueError("oversized")
    return payload.decode("utf-8")


def _object(
    path: Path,
    source: str,
    diagnostics: list[Diagnostic],
    *,
    allowed_root: Path,
) -> dict[str, object] | None:
    try:
        resolved_root = allowed_root.resolve(strict=True)
        resolved_path = path.resolve(strict=True)
        if not resolved_path.is_relative_to(resolved_root):
            raise ValueError("outside root")
        flags = (
            os.O_RDONLY
            | getattr(os, "O_BINARY", 0)
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as stream:
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError("not regular")
            payload = stream.read(MAX_MANIFEST_BYTES + 1)
        if len(payload) > MAX_MANIFEST_BYTES:
            raise ValueError("oversized")
        value = json.loads(payload)
    except FileNotFoundError:
        _diagnose(diagnostics, "missing_manifest", source, "a required source manifest is absent")
        return None
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        _diagnose(
            diagnostics,
            "invalid_manifest",
            source,
            "a required source manifest is unreadable, oversized or malformed",
        )
        return None
    if not isinstance(value, dict):
        _diagnose(
            diagnostics, "invalid_manifest", source, "a required source manifest is not an object"
        )
        return None
    return cast(dict[str, object], value)


def _record_problem(
    diagnostics: list[Diagnostic], key: str, reason: str = "an installed plugin record is invalid"
) -> None:
    _diagnose(diagnostics, "invalid_record", f"claude-plugin:{key}", reason)


def _diagnose(diagnostics: list[Diagnostic], code: str, source: str, reason: str) -> None:
    if len(diagnostics) < MAX_DIAGNOSTICS:
        diagnostics.append(Diagnostic(code=code, source=source, reason=reason))
