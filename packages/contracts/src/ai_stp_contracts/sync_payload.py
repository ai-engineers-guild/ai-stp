"""What a private sync payload may carry (SPEC-025, docs/contracts/sync-event.md).

This policy has two enforcers and therefore needs one owner. The client refuses
before it opens a socket, because a secret that left the machine has already
left it; the server refuses again, because a client is not an authority about
its own payload. Both refusals are the same rule, and a rule stated twice is a
rule that will diverge.

It already had. Both sides carried a byte-identical fragment list, and only the
client grew the `required_env` carve-out — so a complete canonical passport
passed the half that was optional and was rejected by the half that decides.

The list is fragments, not field names, and matches anywhere inside a key. That
is deliberate — `github_token`, `oauth_secret` and `api_key_value` are all
caught without enumerating them — and it is also why `required_env` needs an
explicit carve-out rather than a narrower fragment: the canonical field cannot
represent a value at all (`EnvVarRequirement` is `name` and `purpose`, frozen
and closed), so its safety is a property of the type, not of its name.

The same collision reached `requires_authorization`, a closed three-value
enum, through the fragment `authorization` — and that one rejected every object
in the launch corpus, not an edge case. Two collisions in a closed passport are
the mechanism showing its limit: a name blacklist over a typed document refuses
fields whose type already makes them safe. Replacing it with schema-driven
validation is the real answer and a decision with an owner; until then each
collision is admitted by checking its shape, and `_DECLARED_SAFE` is the list of
them, so the cost stays visible instead of being spread through the walker.

`session`, `backup` and `environment` still forbid any key containing them. No
canonical passport field collides with those today — the corpus test is what
says so, rather than a reading.
"""

import re
from collections.abc import Callable
from typing import Final, cast

#: Fragments that make a key forbidden wherever they appear inside it.
FORBIDDEN_KEY_FRAGMENTS: Final[frozenset[str]] = frozenset(
    {
        "password",
        "secret",
        "token",
        "private_key",
        "api_key",
        "authorization",
        "cookie",
        "session",
        "env",
        "environment",
        "absolute_path",
        "home_path",
        "file_path",
        "backup",
        "artifact_bytes",
        "project_index",
        "project_passport",
        "device_passport",
    }
)

#: Canonical passport fields whose names collide with a fragment and whose types
#: cannot carry what the fragment is there to stop. Each is admitted by checking
#: its shape, never by trusting its name: `required_env` would be caught by
#: `env`, `requires_authorization` by `authorization`.
REQUIRED_ENV_KEY: Final[str] = "required_env"
REQUIRED_ENV_FIELDS: Final[frozenset[str]] = frozenset({"name", "purpose"})
MAX_REQUIRED_ENV_ENTRIES: Final[int] = 128

REQUIRES_AUTHORIZATION_KEY: Final[str] = "requires_authorization"
REQUIRES_AUTHORIZATION_VALUES: Final[frozenset[str]] = frozenset(
    {"none", "user_account", "external_service"}
)

#: POSIX, Windows drive and UNC roots. A path that starts at a root describes
#: this machine and means nothing on another one.
ABSOLUTE_PATH_PATTERN: Final[str] = r"^(?:[A-Za-z]:[\\/]|/|\\\\)"
_ABSOLUTE_PATH: Final[re.Pattern[str]] = re.compile(ABSOLUTE_PATH_PATTERN)


class SyncPayloadRejection(ValueError):
    """A payload field the sync boundary refuses, named by path and never by value.

    The path is what makes the refusal actionable; the value is exactly what
    must not travel, so it is not carried here and must not be added.
    """

    def __init__(self, reason: str, *, path: str) -> None:
        super().__init__(reason)
        self.reason = reason
        self.path = path


def _reject(reason: str, path: str) -> SyncPayloadRejection:
    return SyncPayloadRejection(reason, path=path or "/")


def _check_required_env(value: object, path: str) -> None:
    bounded = "required_env must be a bounded list of name and purpose records"
    if not isinstance(value, list):
        raise _reject(bounded, path)
    entries = cast(list[object], value)
    if len(entries) > MAX_REQUIRED_ENV_ENTRIES:
        raise _reject(bounded, path)
    for index, entry in enumerate(entries):
        at = f"{path}[{index}]"
        if not isinstance(entry, dict):
            raise _reject("required_env may contain only name and purpose", at)
        fields = cast(dict[object, object], entry)
        named = {key for key in fields if isinstance(key, str)}
        if len(named) != len(fields) or named != set(REQUIRED_ENV_FIELDS):
            raise _reject("required_env may contain only name and purpose", at)
        if not all(isinstance(fields[name], str) for name in sorted(REQUIRED_ENV_FIELDS)):
            raise _reject("required_env values must be text", at)


def _check_requires_authorization(value: object, path: str) -> None:
    if not isinstance(value, str) or value not in REQUIRES_AUTHORIZATION_VALUES:
        raise _reject("requires_authorization must be one of the declared classes", path)


#: One entry per collision, each admitted by its own shape check. A table rather
#: than a chain of special cases: the next collision should be obvious to add
#: and impossible to add without saying what makes the field safe.
_DECLARED_SAFE: Final[dict[str, Callable[[object, str], None]]] = {
    REQUIRED_ENV_KEY: _check_required_env,
    REQUIRES_AUTHORIZATION_KEY: _check_requires_authorization,
}


def check_sync_payload(value: object, *, path: str = "") -> None:
    """Raise `SyncPayloadRejection` for anything this boundary refuses to carry."""
    if isinstance(value, dict):
        for key, item in cast(dict[object, object], value).items():
            if not isinstance(key, str):
                raise _reject("sync payload keys must be text", path)
            at = f"{path}.{key}" if path else key
            lowered = key.lower()
            declared = _DECLARED_SAFE.get(lowered)
            if declared is not None:
                declared(item, at)
                continue
            if any(fragment in lowered for fragment in FORBIDDEN_KEY_FRAGMENTS):
                raise _reject("sync payload contains a forbidden field", at)
            check_sync_payload(item, path=at)
        return
    if isinstance(value, list):
        for index, item in enumerate(cast(list[object], value)):
            check_sync_payload(item, path=f"{path}[{index}]")
        return
    if isinstance(value, str) and _ABSOLUTE_PATH.match(value) is not None:
        raise _reject("sync payload contains an absolute path", path)
    if isinstance(value, bytes | bytearray):
        raise _reject("sync payload contains binary bytes", path)
