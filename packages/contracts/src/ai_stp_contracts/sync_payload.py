"""Private-sync payload exclusions shared by Python services and the native CLI.

The packaged JSON resource owns the constants. Safe declarations are admitted by
shape; rejection reports a field path, never the excluded value.
"""

import json
import re
from collections.abc import Callable
from importlib.resources import files
from typing import Final, TypedDict, cast


class _Policy(TypedDict):
    forbidden_payload_kinds: list[str]
    forbidden_key_fragments: list[str]
    required_env_key: str
    required_env_fields: list[str]
    max_required_env_entries: int
    requires_authorization_key: str
    requires_authorization_values: list[str]
    absolute_path_pattern: str


_POLICY: Final[_Policy] = cast(
    _Policy,
    json.loads(
        files("ai_stp_contracts").joinpath("sync_payload_policy.json").read_text(encoding="utf-8")
    ),
)
FORBIDDEN_KEY_FRAGMENTS: Final[frozenset[str]] = frozenset(_POLICY["forbidden_key_fragments"])
FORBIDDEN_PAYLOAD_KINDS: Final[frozenset[str]] = frozenset(_POLICY["forbidden_payload_kinds"])
REQUIRED_ENV_KEY: Final[str] = _POLICY["required_env_key"]
REQUIRED_ENV_FIELDS: Final[frozenset[str]] = frozenset(_POLICY["required_env_fields"])
MAX_REQUIRED_ENV_ENTRIES: Final[int] = _POLICY["max_required_env_entries"]
REQUIRES_AUTHORIZATION_KEY: Final[str] = _POLICY["requires_authorization_key"]
REQUIRES_AUTHORIZATION_VALUES: Final[frozenset[str]] = frozenset(
    _POLICY["requires_authorization_values"]
)
ABSOLUTE_PATH_PATTERN: Final[str] = _POLICY["absolute_path_pattern"]
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
