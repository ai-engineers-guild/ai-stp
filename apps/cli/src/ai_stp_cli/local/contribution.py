"""Assembling the full bytes of a host file a component contributes a key to.

`ADR-0129`: three of seven harnesses have an `mcp` component and no kind to
deliver it under, because the server is a key inside a file the provider already
owns — `mcp_servers` in codex's and grok-build's `config.toml`, `mcp` in
opencode's `opencode.json`. Claude-code's `hook` is the same shape, a `hooks`
key inside the owned `settings.json`.

So the component compiles into a contribution rather than a surface of its own.
The provider is handed `replace` of the `setting` kind — one it does declare —
with the complete bytes it must write, and the consumer is what assembles them,
because the consumer already knows every one of these formats and the provider
is bytes-in/bytes-out by contract.

**Ownership, not merge.** The key belongs to the component and everything else
in the file stays exactly as it was. That is the difference from merging two
setups, where the question is which is newer; here there is no contest, only a
declared owner of one key.

**Format-preserving, and that is the reason for the dependency.** `config.toml`
is a file its user maintains. Round-tripping it through parse-and-serialise
erases every comment they wrote, and losing comments in a file we did not create
is data damage rather than cosmetics. `tomllib` only reads; `tomlkit` writes
back what it read.
"""

from __future__ import annotations

import json
from pathlib import PurePosixPath
from typing import Final, cast

import tomlkit

from ai_stp_cli.errors import CliFailure
from ai_stp_foundation.canonical import JsonValue

#: Host formats this can assemble, by suffix.
TOML: Final[str] = ".toml"
JSON: Final[str] = ".json"
SUPPORTED: Final[frozenset[str]] = frozenset({TOML, JSON})


def assemble(*, host: str, current: bytes | None, key: str, value: JsonValue) -> bytes:
    """The host file's full bytes with one key replaced by a component's content.

    `current` is `None` when the target has no such file yet, which is an
    ordinary first install rather than an error: the result is a file holding
    just this key.

    A host that cannot be parsed is refused rather than replaced. Overwriting a
    file whose contents could not be read is the one outcome worse than not
    installing — everything in it that the component does not know about would
    be gone, and nothing would have said so.
    """
    suffix = PurePosixPath(host).suffix.casefold()
    if suffix not in SUPPORTED:
        raise _refused(
            "this host file format cannot be assembled",
            host=host,
            detail=f"supported: {', '.join(sorted(SUPPORTED))}",
        )
    if not key:
        raise _refused("a contribution must name the key it owns", host=host, detail="empty key")
    if suffix == TOML:
        return _toml(host=host, current=current, key=key, value=value)
    return _json(host=host, current=current, key=key, value=value)


def _toml(*, host: str, current: bytes | None, key: str, value: JsonValue) -> bytes:
    """Replace one key, keeping every comment and every unrelated line."""
    if current is None:
        document = tomlkit.document()
    else:
        try:
            document = tomlkit.parse(current.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as error:
            raise _refused(
                "the host file is not readable TOML",
                host=host,
                detail=type(error).__name__,
            ) from error
    document[key] = value
    return tomlkit.dumps(document).encode("utf-8")


def _json(*, host: str, current: bytes | None, key: str, value: JsonValue) -> bytes:
    """Replace one key in a JSON host.

    JSON carries no comments, so a round trip loses layout and nothing else.
    The layout change is visible in the plan's diff, which `ADR-0129` requires
    the operator to confirm before anything is written.

    A `.jsonc` host is refused by `assemble` above rather than handled here.
    Comments are exactly what that format exists for, and a writer that drops
    them is the data damage the format-preserving requirement forbids.
    """
    if current is None:
        document: dict[str, JsonValue] = {}
    else:
        try:
            loaded = json.loads(current.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as error:
            raise _refused(
                "the host file is not readable JSON",
                host=host,
                detail=type(error).__name__,
            ) from error
        if not isinstance(loaded, dict):
            raise _refused(
                "the host file is JSON but not an object",
                host=host,
                detail=type(loaded).__name__,
            )
        document = cast("dict[str, JsonValue]", loaded)
    document[key] = value
    return (json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def _refused(message: str, *, host: str, detail: str) -> CliFailure:
    return CliFailure(
        "AI_STP_PRECONDITION_FAILED",
        message,
        details={"host": host, "detail": detail},
        next_actions=["install plan --json"],
    )
