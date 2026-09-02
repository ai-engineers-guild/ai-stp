"""The content-addressed cache of public catalogue answers (issue #76).

Two jobs, kept apart on purpose. Bytes are stored under the digest of their own
content, so a corrupted or truncated file cannot be read back as if it were
sound — the name stops matching. And an entry records *when* it was fetched, so
an offline read can say "this is what the catalogue said at 14:02" instead of
claiming to know the current cloud state.

Writes are atomic and owner-only through the same primitive `ADR-0058` uses:
a partially written cache entry that still had a valid-looking name would be the
one failure content addressing is meant to make impossible.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, cast

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.paths import (
    FILE_MODE,
    POSIX,
    data_dir,
    ensure_directory,
    is_private,
    read_private,
    write_private,
    write_private_bytes,
)
from ai_stp_foundation.canonical import JsonValue, canonize, from_json_bytes
from ai_stp_foundation.digests import digest_canonical
from ai_stp_foundation.timestamps import format_timestamp
from ai_stp_passports.versions import ArtifactRef

#: The hash domain the passport digest is computed in. Shared with
#: `packages/passports`, which seals the same bytes.
PASSPORT_DOMAIN: Final[str] = "ai-stp:passport:v1"
ARTIFACT_DOMAIN: Final[str] = "ai-stp:artifact:v1"

#: Where cached answers live. Separate from the registry: this is discardable,
#: and deleting it must cost nothing but a round trip.
CACHE_DIRECTORY: Final[str] = "cache"


def cache_dir() -> Path:
    return data_dir() / CACHE_DIRECTORY


@dataclass(frozen=True)
class Entry:
    """One cached answer and when it was true."""

    key: str
    checked_at: str
    document: dict[str, JsonValue]


def key_for(kind: str, stable_id: str) -> str:
    """A stable, filesystem-safe name for one catalogue object.

    Hashed rather than composed from the identifier: an object name is not
    guaranteed to be a safe path segment, and a cache whose file names are
    attacker-influenced is a directory traversal waiting to be written.
    """
    return hashlib.sha256(f"{kind}:{stable_id}".encode()).hexdigest()


def digest_of(passport: JsonValue) -> str:
    """The digest of a passport, exactly as the catalogue computes it.

    Domain-separated through `ai-stp:passport:v1`, not a bare hash of the
    canonical bytes. Getting this wrong is not a near miss: every verification
    would fail against a conforming server, and the check would look like a
    corrupted download.
    """
    return digest_canonical(PASSPORT_DOMAIN, passport)


def _path(key: str) -> Path:
    return cache_dir() / f"{key}.json"


def store(key: str, document: dict[str, JsonValue], *, checked_at: str | None = None) -> Entry:
    """Cache one answer, atomically and owner-only."""
    entry = Entry(
        key=key,
        checked_at=checked_at or format_timestamp(datetime.now(UTC)),
        document=document,
    )
    ensure_directory(cache_dir())
    write_private(
        _path(key),
        json.dumps(
            {"key": entry.key, "checked_at": entry.checked_at, "document": entry.document},
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n",
    )
    return entry


def load(key: str) -> Entry | None:
    """Read a cached answer, or `None`. A damaged entry is refused, not guessed."""
    path = _path(key)
    if not path.exists():
        return None
    try:
        parsed: object = json.loads(read_private(path))
    except ValueError as error:
        raise _damaged(error) from error
    if not isinstance(parsed, dict):
        raise _damaged(TypeError("cache entry is not an object"))
    record = cast(dict[str, JsonValue], parsed)
    document = record.get("document")
    checked_at = record.get("checked_at")
    if not isinstance(document, dict) or not isinstance(checked_at, str):
        raise _damaged(ValueError("cache entry is missing its document or its timestamp"))
    return Entry(key=key, checked_at=checked_at, document=cast(dict[str, JsonValue], document))


def _damaged(error: BaseException) -> CliFailure:
    return CliFailure(
        "AI_STP_VALIDATION_ERROR",
        "a cache entry is unreadable",
        details={"exception": type(error).__name__},
        next_actions=["registry search --kind <kind> --json"],
    )


def verify(passport: JsonValue, expected_digest: str) -> None:
    """Refuse a passport whose digest does not match what the catalogue promised.

    Independent of the transport: a truncated download and a substituted body
    are the same thing to this check, which is why it is done on the decoded
    content rather than on a byte count.
    """
    actual = digest_of(passport)
    if actual != expected_digest:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the passport does not match the digest the catalogue published",
            details={"expected": expected_digest, "actual": actual},
        )


#: Version artifacts and deliberately raw-SHA payloads have separate namespaces.
#: The digest string does not encode its hash domain, so sharing one directory
#: would allow the same spelling to select bytes verified under another rule.
VERSION_ARTIFACT_DIRECTORY: Final[str] = "version-artifacts"
RAW_ARTIFACT_DIRECTORY: Final[str] = "raw-artifacts"
PROVIDER_PLAN_DIRECTORY: Final[str] = "provider-plans-v3"
PROVIDER_PLAN_DOMAIN: Final[str] = "ai-stp:provider-plan:v3"
_SHA256: Final[re.Pattern[str]] = re.compile(r"sha256:[0-9a-f]{64}")


def version_artifact_path(digest: str) -> Path:
    """Where version artifact bytes with this domain-separated digest belong.

    Addressed by content rather than by object and version. Two versions that
    happen to ship identical bytes are one file, and a file that is present is
    known to be the right one — there is no name to get wrong.
    """
    _require_sha256(digest)
    # Filename uses the hex only: ``sha256:`` is not a legal path segment on Windows.
    return (
        data_dir()
        / CACHE_DIRECTORY
        / VERSION_ARTIFACT_DIRECTORY
        / f"{digest.removeprefix('sha256:')}.bin"
    )


def raw_artifact_path(digest: str) -> Path:
    """Where bytes named by a deliberately raw SHA-256 digest belong."""
    _require_sha256(digest)
    return (
        data_dir()
        / CACHE_DIRECTORY
        / RAW_ARTIFACT_DIRECTORY
        / f"{digest.removeprefix('sha256:')}.bin"
    )


def provider_plan_path(digest: str) -> Path:
    """The owner-only canonical v3 provider-plan artifact named by its digest."""
    _require_sha256(digest)
    # Filename uses the hex only: ``sha256:`` is not a legal path segment on Windows.
    return (
        data_dir()
        / CACHE_DIRECTORY
        / PROVIDER_PLAN_DIRECTORY
        / f"{digest.removeprefix('sha256:')}.json"
    )


def store_provider_plan(plan: dict[str, JsonValue], expected_digest: str) -> Path:
    """Persist the exact provider plan whose logical digest was approved."""
    _require_sha256(expected_digest)
    if digest_canonical(PROVIDER_PLAN_DOMAIN, plan) != expected_digest:
        raise _artifact_refused(
            "the provider plan does not match its expected logical digest",
            {"expected": expected_digest},
        )
    payload = canonize(plan)
    present = stored_provider_plan(expected_digest)
    if present is not None:
        return present
    target = provider_plan_path(expected_digest)
    write_private_bytes(target, payload)
    return target


def stored_provider_plan(digest: str) -> Path | None:
    """Return an exact private canonical plan, deleting a corrupt cache entry."""
    path = provider_plan_path(digest)
    if not path.exists():
        return None
    try:
        held = path.lstat()
        if path.is_symlink() or not path.is_file() or not is_private(path):
            raise ValueError("provider plan cache entry is not one private regular file")
        payload = path.read_bytes()
        value = from_json_bytes(payload)
        if not isinstance(value, dict) or canonize(value) != payload:
            raise ValueError("provider plan cache entry is not canonical JSON")
        plan = cast(dict[str, JsonValue], value)
        if digest_canonical(PROVIDER_PLAN_DOMAIN, plan) != digest:
            raise ValueError("provider plan cache entry has another digest")
        if held.st_size != len(payload):
            raise ValueError("provider plan cache entry changed during read")
    except (OSError, ValueError):
        path.unlink(missing_ok=True)
        return None
    return path


def store_raw_artifact_bytes(payload: bytes, expected_digest: str) -> Path:
    """Verify and atomically cache bytes identified by raw SHA-256.

    HarnessBundle compilation already owns the complete bounded ZIP in memory.
    Writing those bytes through a second temporary download would add another
    mutable copy without adding evidence, so this primitive verifies the raw
    bytes and installs them directly under their content address.
    """
    _require_sha256(expected_digest)
    actual = f"sha256:{hashlib.sha256(payload).hexdigest()}"
    if actual != expected_digest:
        raise _artifact_refused(
            "the artifact bytes do not match their expected digest",
            {"expected": expected_digest, "received": actual},
        )
    present = stored_raw_artifact(expected_digest)
    if present is not None:
        return present
    target = raw_artifact_path(expected_digest)
    write_private_bytes(target, payload)
    return target


def stored_raw_artifact(digest: str) -> Path | None:
    """Cached raw-SHA bytes, or `None`, verified again before answering.

    A cache hit is only a hit if the bytes still hash to what was asked for. A
    file can be truncated by a full disk or edited by anything with write
    access, and returning it unchecked would make the cache the one place the
    content guarantee stops holding.
    """
    return _stored(digest, raw_artifact_path(digest), domain=None)


def stored_version_artifact(digest: str) -> Path | None:
    """Cached version artifact bytes, verified in the artifact digest domain."""
    return _stored(digest, version_artifact_path(digest), domain=ARTIFACT_DOMAIN)


def keep_version_artifact(source: Path, expected: ArtifactRef) -> Path:
    """Move domain-verified version artifact bytes into the cache atomically.

    The caller has already streamed them somewhere temporary; this checks size
    and digest and then puts the file in place with a rename, so a reader never
    sees a partial artifact under a name that promises a complete one.
    """
    actual_size = source.stat().st_size
    if actual_size != expected.size_bytes:
        raise _artifact_refused(
            "the artifact is not the size its passport declares",
            {"expected": str(expected.size_bytes), "received": str(actual_size)},
        )
    actual = _digest_of_file(source, domain=ARTIFACT_DOMAIN)
    if actual != expected.digest:
        raise _artifact_refused(
            "the artifact does not hash to what its passport declares",
            {"expected": expected.digest, "received": actual},
        )
    target = version_artifact_path(expected.digest)
    ensure_directory(target.parent)
    if POSIX:
        source.chmod(FILE_MODE)
    source.replace(target)
    return target


def _stored(digest: str, path: Path, *, domain: str | None) -> Path | None:
    if not path.exists():
        return None
    if not is_private(path) or _digest_of_file(path, domain=domain) != digest:
        path.unlink(missing_ok=True)
        return None
    return path


def _digest_of_file(path: Path, *, domain: str | None) -> str:
    reader = hashlib.sha256()
    if domain is not None:
        reader.update(domain.encode("ascii") + b"\x00")
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            reader.update(block)
    return f"sha256:{reader.hexdigest()}"


def _artifact_refused(message: str, details: dict[str, str]) -> CliFailure:
    return CliFailure(
        "AI_STP_PRECONDITION_FAILED",
        message,
        details=details,
        next_actions=["registry version --kind <kind> --id <id> --version <version> --json"],
    )


def _require_sha256(digest: str) -> None:
    if _SHA256.fullmatch(digest) is None:
        raise _artifact_refused(
            "the artifact digest is not a canonical SHA-256 identifier",
            {"digest": digest},
        )
