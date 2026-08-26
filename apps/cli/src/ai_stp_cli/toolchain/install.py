"""Installing a pinned tool without trusting it (`SPEC-014` REQ-1404 to REQ-1413).

An archive from the internet is hostile input, and every step here is arranged
so that being wrong about that costs nothing. Bytes are verified before anything
is unpacked, unpacking happens beside the installation rather than into it, and
the installation only becomes current when a single rename says so. Nothing from
the archive is ever executed: `REQ-1406` disables install scripts by default, and
the way to disable them is to have no code that runs one.

The layout is a versioned directory and a pointer:

    <data>/toolchain/cache/<sha256>          verified artifact bytes
    <data>/toolchain/tools/<tool>/<version>/ one unpacked installation
    <data>/toolchain/tools/<tool>/current    a pointer to one of them
    <data>/toolchain/ownership.json          every path this module created

The cache entry is named by its own digest, so the name *is* the integrity
proof: a lookup that finds a file at `cache/<digest>` and re-reads it cannot be
satisfied by different bytes. `REQ-1412` asks offline installs to accept a
verified cache and refuse an unknown artifact, and this makes both the same
check rather than two that could drift apart.

`REQ-1404` is why the pointer exists at all. A tool is invoked by its exact path
under `current`, never by name: the surrounding `PATH` belongs to the user and
may have anything in it, and a managed toolchain that resolved through it would
not be managed.
"""

import hashlib
import hmac
import json
import os
import re
import shutil
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.paths import DIRECTORY_MODE, data_dir, ensure_directory
from ai_stp_cli.toolchain import Artifact, Tool

#: The pointer every invocation goes through (`REQ-1404`).
CURRENT: Final[str] = "current"

#: Where the ownership manifest lives (`REQ-1411`). One file, so an uninstall
#: reads a list rather than deciding what looks like ours.
OWNERSHIP: Final[str] = "ownership.json"

#: What an unpacked installation may weigh and how many members it may hold. A
#: correctly-sized archive that expands to fill a disk is a real attack and the
#: only defence is to stop.
MAX_UNPACKED_BYTES: Final[int] = 2 * 1024 * 1024 * 1024
MAX_MEMBERS: Final[int] = 100_000


def root() -> Path:
    """The managed toolchain root. Under the CLI's data directory, never `/usr`."""
    return data_dir() / "toolchain"


def cache_dir() -> Path:
    return root() / "cache"


def tool_dir(tool_id: str) -> Path:
    return root() / "tools" / tool_id


def installed_path(tool_id: str, version: str) -> Path:
    return tool_dir(tool_id) / version


def pointer(tool_id: str) -> Path:
    return tool_dir(tool_id) / CURRENT


@dataclass(frozen=True)
class Plan:
    """What an install would do, named exactly, before it does any of it.

    `REQ-1405` asks for a plan and this is it: every path that would be created
    is listed here, so the ownership manifest and the uninstall are derived from
    the same statement the user approved rather than from what happened to end
    up on disk.
    """

    tool_id: str
    version: str
    source: str
    digest: str
    target: Path
    cached: Path

    #: `install`, `already_installed`, or `needs_user_action` when something
    #: outside this directory would have to change (`REQ-1410`).
    action: str
    reason: str

    #: Whether the plan can be carried out with no network at all (`REQ-1413`).
    offline_capable: bool


def plan(tool: Tool, artifact: Artifact, *, offline: bool = False) -> Plan:
    """Decide what installing this tool would take, without doing any of it."""
    target = installed_path(tool.tool_id, tool.version)
    cached = cache_dir() / digest_name(artifact.digest)

    if _is_installed(tool, target):
        return Plan(
            tool.tool_id,
            tool.version,
            artifact.url,
            artifact.digest,
            target,
            cached,
            "already_installed",
            "this exact version is installed and current",
            offline_capable=True,
        )
    if offline and not cached.exists():
        return Plan(
            tool.tool_id,
            tool.version,
            artifact.url,
            artifact.digest,
            target,
            cached,
            "needs_user_action",
            "offline, and this artifact is not in the verified cache",
            offline_capable=False,
        )
    return Plan(
        tool.tool_id,
        tool.version,
        artifact.url,
        artifact.digest,
        target,
        cached,
        "install",
        "not installed",
        offline_capable=cached.exists(),
    )


def verify(content: bytes, expected: str) -> str:
    """Check bytes against their pinned digest. Returns the digest computed.

    Constant-time comparison, because a digest check that leaks how far it got
    is a check an attacker can steer. There is no cheap correctness argument for
    the fast comparison here and no cost to the safe one.
    """
    computed = "sha256:" + hashlib.sha256(content).hexdigest()
    if not hmac.compare_digest(computed, expected):
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the downloaded artifact does not match its pinned digest",
            details={"expected": expected, "computed": computed},
            next_actions=["toolchain profile --json"],
        )
    return computed


def remember(content: bytes, digest: str) -> Path:
    """Put verified bytes in the cache, named by their own digest.

    Verified first and always: an unverified artifact never reaches the cache,
    because `REQ-1412` lets an offline install trust what is in there and a
    cache that could hold anything would make that trust unfounded.
    """
    verify(content, digest)
    ensure_directory(cache_dir())
    target = cache_dir() / digest_name(digest)
    # Written beside and renamed, so an interrupted write cannot leave a short
    # file under a name that asserts its contents.
    handle, staged = tempfile.mkstemp(dir=cache_dir(), prefix=".staging-")
    with os.fdopen(handle, "wb") as writer:
        writer.write(content)
    Path(staged).replace(target)
    return target


def cached_bytes(digest: str) -> bytes:
    """Read a cached artifact and re-verify it (`REQ-1412`).

    Re-verified on the way out even though it was verified on the way in. The
    file has been at rest on a disk the CLI does not control since then, and the
    check costs one read of something already being read.
    """
    target = cache_dir() / digest_name(digest)
    if not target.exists():
        raise CliFailure(
            "AI_STP_DEPENDENCY_UNAVAILABLE",
            "this artifact is not in the verified cache",
            details={"digest": digest},
            next_actions=["toolchain install --tool <id>"],
        )
    content = target.read_bytes()
    verify(content, digest)
    return content


def unpack(content: bytes, into: Path) -> list[Path]:
    """Unpack an archive into a fresh directory, executing nothing.

    `REQ-1406` in the only form that is worth anything: there is no code path
    here that runs a script, so an archive containing `install.sh` leaves a file
    named `install.sh` on disk and nothing else happens.

    Traversal, absolute paths, links pointing outside the destination, device
    nodes and setuid bits are all refused — by `tarfile`'s own `data` filter
    (PEP 706), which is maintained by the people who maintain the format and
    knows more edge cases than a hand-written check would. It is passed
    explicitly rather than relied on as a default, because the default differs
    between the Python versions this supports.
    """
    ensure_directory(into)
    with tempfile.TemporaryDirectory(prefix="ai-stp-artifact-") as scratch:
        holder = Path(scratch) / "artifact"
        holder.write_bytes(content)
        try:
            if zipfile.is_zipfile(holder):
                _unpack_zip(holder, into)
            else:
                _unpack_tar(holder, into)
        except (tarfile.TarError, zipfile.BadZipFile, OSError) as error:
            # Including everything the `data` filter refuses: traversal, an
            # absolute member, a link leaving the destination, a device node.
            # One answer for all of them, because from here they are one thing —
            # an archive that cannot be trusted to unpack where it was told.
            raise CliFailure(
                "AI_STP_PRECONDITION_FAILED",
                "the artifact could not be safely unpacked",
                details={"refused": f"{type(error).__name__}: {error}"},
            ) from error
    return sorted(path for path in into.rglob("*"))


def activate(target: Path, tool_id: str) -> Path:
    """Point `current` at an installation, atomically (`REQ-1405`).

    A symlink created beside the pointer and renamed onto it. `rename` is atomic,
    so there is no instant at which `current` is missing or half-written: a
    concurrent invocation sees either the old installation or the new one, and
    both of those work.
    """
    link = pointer(tool_id)
    ensure_directory(link.parent)
    staged = link.parent / f".{CURRENT}.staging"
    staged.unlink(missing_ok=True)
    if os.name == "nt":
        # Windows cannot atomically replace a directory reparse point with
        # ``os.replace``. A regular text pointer has the same exact-path and
        # atomic-swap semantics and works without Developer Mode or elevation.
        staged.write_text(f"path:{target}", encoding="utf-8")
    else:
        staged.symlink_to(target, target_is_directory=True)
    staged.replace(link)
    return link


def rollback(tool_id: str, previous: Path | None) -> str:
    """Return to the installation that was current before (`REQ-1405`).

    A rollback with nowhere to go removes the pointer rather than leaving it
    aimed at a half-installed directory. A pointer to something broken is worse
    than no pointer, because only one of the two is obviously wrong.
    """
    link = pointer(tool_id)
    if previous is None or not previous.exists():
        link.unlink(missing_ok=True)
        return "no previous installation; the pointer was removed"
    activate(previous, tool_id)
    return f"returned to {previous.name}"


def current_target(tool_id: str) -> Path | None:
    """What `current` points at, or `None`. Never raises on a broken pointer."""
    link = pointer(tool_id)
    try:
        if os.name == "nt":
            if not link.is_file():
                return None
            value = link.read_text(encoding="utf-8").strip()
            if not value.startswith("path:"):
                return None
            resolved = Path(value.removeprefix("path:"))
            return resolved if resolved.is_absolute() else (link.parent / resolved)
        if not link.is_symlink():
            return None
        resolved = link.readlink()
    except OSError:
        return None
    return resolved if resolved.is_absolute() else (link.parent / resolved)


def binary(tool: Tool) -> Path:
    """The exact path a tool is invoked by (`REQ-1404`).

    Through `current`, never through `PATH`. The surrounding environment belongs
    to the user and may hold anything under this name; a managed toolchain that
    resolved through it would be managed by whoever wrote that `PATH`.
    """
    if os.name == "nt":
        base = current_target(tool.tool_id) or pointer(tool.tool_id)
    else:
        base = pointer(tool.tool_id)
    entry = base / tool.entry_point
    if os.name == "nt" and not entry.exists() and not entry.suffix:
        executable = entry.with_name(f"{entry.name}.exe")
        if executable.exists():
            return executable
    return entry


def record_ownership(created: list[Path]) -> Path:
    """Add paths to the ownership manifest (`REQ-1411`).

    Only what this module created is listed, and an uninstall removes only what
    is listed. Deciding at removal time which files "look like ours" is how a
    cleanup takes a user's data with it.
    """
    manifest = root() / OWNERSHIP
    held = owned()
    for path in created:
        text = str(path)
        if text not in held:
            held.append(text)
    ensure_directory(root())
    manifest.write_text(json.dumps(sorted(held), indent=2) + "\n", encoding="utf-8")
    return manifest


def owned() -> list[str]:
    """Every path this module claims. An unreadable manifest claims nothing."""
    manifest = root() / OWNERSHIP
    if not manifest.exists():
        return []
    try:
        held = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(held, list):
        return []
    entries: list[str] = [item for item in held if isinstance(item, str)]  # pyright: ignore[reportUnknownVariableType]
    return entries


def remove(tool_id: str) -> tuple[list[str], list[str]]:
    """Remove one tool. Returns what was removed and what was left, with reasons.

    `REQ-1411`: a path outside the manifest is left alone and said so. A tool
    directory that a user put something into is theirs; the manifest is what
    this module may undo, not everything that happens to be nearby.
    """
    mine = tool_dir(tool_id)
    removed: list[str] = []
    kept: list[str] = []
    claimed = {item for item in owned() if item == str(mine) or item.startswith(f"{mine}{os.sep}")}

    for path in sorted((p for p in mine.rglob("*") if p.is_file() or p.is_symlink()), reverse=True):
        if str(path) in claimed:
            path.unlink(missing_ok=True)
            removed.append(str(path))
        else:
            kept.append(f"{path}: not in the ownership manifest")

    for directory in sorted((p for p in mine.rglob("*") if p.is_dir()), reverse=True):
        if not any(directory.iterdir()):
            directory.rmdir()
    if mine.exists() and not any(mine.iterdir()):
        mine.rmdir()

    remaining = [item for item in owned() if item not in claimed]
    ensure_directory(root())
    (root() / OWNERSHIP).write_text(
        json.dumps(sorted(remaining), indent=2) + "\n", encoding="utf-8"
    )
    return removed, kept


def _is_installed(tool: Tool, target: Path) -> bool:
    """Whether this exact version is both unpacked and current."""
    if not target.is_dir():
        return False
    active = current_target(tool.tool_id)
    return active is not None and active.resolve() == target.resolve()


def digest_name(digest: str) -> str:
    """A cache file name from a digest, with no separator left in it."""
    return digest.replace(":", "-")


def _unpack_tar(holder: Path, into: Path) -> None:
    with tarfile.open(holder, "r:*") as archive:
        members = archive.getmembers()
        _within_budget(len(members), sum(item.size for item in members))
        # PEP 706's `data` filter: refuses absolute paths, `..`, links leaving
        # the destination, device nodes and setuid bits. Named explicitly
        # because the default is not the same on every version supported here.
        archive.extractall(into, filter="data")


def _unpack_zip(holder: Path, into: Path) -> None:
    with zipfile.ZipFile(holder) as archive:
        entries = archive.infolist()
        _within_budget(len(entries), sum(item.file_size for item in entries))
        # `ZipFile.extract` sanitises member names — absolute paths and `..` are
        # stripped — and zip has no symlink to follow, so there is nothing here
        # the tar filter is needed for.
        archive.extractall(into)
    for path in into.rglob("*"):
        if path.is_dir():
            path.chmod(DIRECTORY_MODE)


def _within_budget(members: int, unpacked: int) -> None:
    """Refuse an archive that unpacks to more than it may (`REQ-1408`)."""
    if members > MAX_MEMBERS:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the artifact holds more entries than an installation may",
            details={"members": str(members), "limit": str(MAX_MEMBERS)},
        )
    if unpacked > MAX_UNPACKED_BYTES:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the artifact unpacks to more than an installation may weigh",
            details={"unpacked_bytes": str(unpacked), "limit": str(MAX_UNPACKED_BYTES)},
        )


def perform(tool: Tool, artifact: Artifact, content: bytes) -> tuple[Path, list[Path]]:
    """Carry out one install: verify, stage, swap, and roll back on failure.

    The order is the whole point. Bytes are verified before anything is unpacked,
    unpacking happens into a staging directory beside the target rather than
    into it, and `current` moves only once a complete installation exists. A
    failure at any step leaves the previous installation current and untouched.
    """
    remember(content, artifact.digest)
    target = installed_path(tool.tool_id, tool.version)
    previous = current_target(tool.tool_id)

    staging = target.with_name(f".{target.name}.staging")
    if staging.exists():
        shutil.rmtree(staging)
    try:
        created = unpack(content, staging)
        if target.exists():
            shutil.rmtree(target)
        staging.replace(target)
        activate(target, tool.tool_id)
    except (CliFailure, OSError):
        shutil.rmtree(staging, ignore_errors=True)
        rollback(tool.tool_id, previous)
        raise

    owned_paths = [target, pointer(tool.tool_id)] + [
        target / item.relative_to(staging) for item in created
    ]
    record_ownership(owned_paths)
    return target, owned_paths


#: How long a download may take, and how large an artifact may be. A tool that
#: does not arrive in this is a tool this cannot install.
DOWNLOAD_TIMEOUT_SECONDS: Final[float] = 120.0
MAX_ARTIFACT_BYTES: Final[int] = 512 * 1024 * 1024

#: The slowest link a download is still expected to finish over. A fixed 120 s
#: is a size limit wearing a clock: it passes a 60 MB artifact and fails a
#: 167 MB one on the same connection, and the failure looks like the larger
#: vendor's fault. Deriving the deadline from the length the plan already states
#: makes the limit the same for every artifact — this rate — instead of
#: different for each size.
MINIMUM_DOWNLOAD_BYTES_PER_SECOND: Final[int] = 512 * 1024


def download_deadline(byte_length: int) -> float:
    """How long an artifact of a stated length may take to arrive.

    Never shorter than the flat timeout, so nothing that used to fit stops
    fitting.
    """
    return max(
        DOWNLOAD_TIMEOUT_SECONDS,
        DOWNLOAD_TIMEOUT_SECONDS + byte_length / MINIMUM_DOWNLOAD_BYTES_PER_SECOND,
    )


#: Where a GitHub release asset is allowed to hand its bytes over, and nowhere
#: else. Closed and observed rather than assumed: on 2026-08-20 a `GET` of a
#: pinned `github.com/.../releases/download/...` answered `302` with a signed
#: `release-assets.githubusercontent.com` URL. `objects.githubusercontent.com`
#: is the older host and is still served.
_RELEASE_ASSET_HOSTS: Final[frozenset[str]] = frozenset(
    {"release-assets.githubusercontent.com", "objects.githubusercontent.com"}
)

#: The only shape of pinned URL whose redirect is followed at all.
_RELEASE_DOWNLOAD: Final[re.Pattern[str]] = re.compile(
    r"^https://github\.com/[^/]+/[^/]+/releases/download/[^/]+/(?P<asset>[^/?#]+)$"
)

_REDIRECT_CODES: Final[frozenset[int]] = frozenset({301, 302, 303, 307, 308})


def _release_asset_target(source: str, location: str) -> str:
    """The one redirect a pinned release URL may take, or a refusal.

    GitHub answers **every** release asset with a redirect to a signed CDN URL,
    so refusing all redirects made the canonical pinned form unusable: a Windows
    `toolchain install --tool ruff` could not fetch the asset at all, and the
    whole managed toolchain stayed empty on that platform (`#376`).

    Following redirects generally is the wrong answer to that. What makes this
    one safe is not trust in the hop but that three things are checked before
    it: the source is a GitHub release download, the target is `https` on a host
    from the closed set above, and the target still names the same asset. The
    digest is verified after the bytes arrive and before anything is unpacked,
    as it was; this only decides which request is made.
    """
    from urllib.parse import parse_qs, urlparse

    pinned = _RELEASE_DOWNLOAD.match(source)
    refusal = "the pinned source redirected somewhere it may not"
    actions = ["toolchain install --tool <id> --offline", "toolchain profile --json"]
    if pinned is None:
        raise CliFailure(
            "AI_STP_DEPENDENCY_UNAVAILABLE",
            refusal,
            details={"source": source, "reason": "not_a_release_asset"},
            next_actions=actions,
        )
    target = urlparse(location)
    if target.scheme != "https" or target.hostname not in _RELEASE_ASSET_HOSTS:
        raise CliFailure(
            "AI_STP_DEPENDENCY_UNAVAILABLE",
            refusal,
            details={"source": source, "host": target.hostname or "", "scheme": target.scheme},
            next_actions=actions,
        )
    asset = pinned.group("asset")
    disposition = " ".join(parse_qs(target.query).get("response-content-disposition", []))
    if asset not in disposition:
        raise CliFailure(
            "AI_STP_DEPENDENCY_UNAVAILABLE",
            refusal,
            details={"source": source, "reason": "different_asset", "asset": asset},
            next_actions=actions,
        )
    return location


def download(
    url: str,
    *,
    transport: object | None = None,
    timeout: float = DOWNLOAD_TIMEOUT_SECONDS,
) -> bytes:
    """Fetch an artifact from its pinned source, deliberately without much.

    Not the cloud client, and not by accident. That one carries a schema header,
    a bearer token and the API base URL, and none of those belong on a request
    to a vendor's download host — sending a token to whatever the manifest names
    would be handing it to a third party.

    Redirects are not followed in general, and `follow_redirects` stays off: one
    hop is taken by hand, only for a GitHub release asset, and only to the same
    asset on a host from a closed set. See `_release_asset_target`.
    """
    import httpx

    try:
        with httpx.Client(
            timeout=httpx.Timeout(timeout, connect=10.0),
            follow_redirects=False,
            transport=transport,  # pyright: ignore[reportArgumentType]
            headers={"Accept": "application/octet-stream"},
        ) as client:
            answer = client.get(url)
            if answer.status_code in _REDIRECT_CODES:
                answer = client.get(_release_asset_target(url, answer.headers.get("location", "")))
    except httpx.HTTPError as error:
        raise CliFailure(
            "AI_STP_DEPENDENCY_UNAVAILABLE",
            "the pinned artifact could not be fetched",
            details={"source": url, "reason": type(error).__name__},
            next_actions=["toolchain install --tool <id> --offline"],
        ) from error

    if answer.status_code != 200:
        raise CliFailure(
            "AI_STP_DEPENDENCY_UNAVAILABLE",
            f"the pinned source answered {answer.status_code}",
            details={"source": url, "status": str(answer.status_code)},
            # A refusal that names no way forward leaves an agent guessing. The
            # cache is the offline path and the profile says what is pinned.
            next_actions=["toolchain install --tool <id> --offline", "toolchain profile --json"],
        )
    content = answer.content
    if len(content) > MAX_ARTIFACT_BYTES:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the artifact is larger than one may be",
            details={"bytes": str(len(content)), "limit": str(MAX_ARTIFACT_BYTES)},
        )
    return content
