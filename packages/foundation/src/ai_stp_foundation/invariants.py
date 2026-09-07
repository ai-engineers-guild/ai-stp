"""Canonical logical and harness-invariant digests (ADR-0162, ADR-0165).

Component logical identity and setup harness invariants are shared by the CLI
and the platform. Both hash the same declared inputs in dedicated domains so
cross-runtime vectors stay byte-identical. Native, provider, assessment, and
presentation fields are excluded on purpose.
"""

from collections.abc import Mapping, Sequence
from typing import Final, cast

from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_canonical

COMPONENT_LOGICAL_DOMAIN: Final[str] = "ai-stp:component-logical:v1"
SETUP_INVARIANT_DOMAIN: Final[str] = "ai-stp:setup-harness-invariant:v1"
TARGET_ASSESSMENT_KEY_DOMAIN: Final[str] = "ai-stp:target-assessment-key:v1"


def _mapping(value: object) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        return {}
    return cast(dict[str, JsonValue], value)


def _string_list(value: object) -> list[JsonValue]:
    if not isinstance(value, list):
        return []
    return cast(list[JsonValue], sorted(str(item) for item in cast(list[object], value)))


def _ref_logical(value: object) -> JsonValue:
    item = _mapping(value)
    if not item:
        return None
    return {
        "stable_id": str(item.get("stable_id") or ""),
        "version": str(item.get("version") or ""),
        "passport_digest": str(item.get("passport_digest") or ""),
    }


def component_logical_payload(passport: Mapping[str, JsonValue]) -> JsonValue:
    """Harness-independent source/meaning of one exact component version."""
    requires_raw = passport.get("requires_components")
    requires: list[JsonValue] = []
    if isinstance(requires_raw, list):
        requires = [_ref_logical(item) for item in cast(list[object], requires_raw)]
    env_raw = passport.get("required_env")
    required_env: list[JsonValue] = []
    if isinstance(env_raw, list):
        for item in cast(list[object], env_raw):
            row = _mapping(item)
            required_env.append(
                {"name": str(row.get("name") or ""), "purpose": str(row.get("purpose") or "")}
            )
    return {
        "artifact": passport.get("artifact"),
        "component_type": passport.get("component_type"),
        "conflicts": passport.get("conflicts"),
        "license": passport.get("license"),
        "permissions": passport.get("permissions"),
        "provides_capabilities": _string_list(passport.get("provides_capabilities")),
        "required_env": required_env,
        "requires_authorization": passport.get("requires_authorization"),
        "requires_capabilities": _string_list(passport.get("requires_capabilities")),
        "requires_components": requires,
        "requires_credentials": passport.get("requires_credentials"),
        "source": passport.get("source"),
    }


def component_logical_digest(passport: Mapping[str, JsonValue]) -> str:
    """Hash the harness-independent component payload in its domain."""
    return digest_canonical(COMPONENT_LOGICAL_DOMAIN, component_logical_payload(passport))


def setup_invariant_payload(
    passport: Mapping[str, JsonValue], member_logical_digests: Sequence[str]
) -> JsonValue:
    """Harness-independent setup meaning and ordered exact logical members."""
    components_raw = passport.get("components")
    members: list[JsonValue] = []
    if isinstance(components_raw, list):
        for index, item in enumerate(cast(list[object], components_raw)):
            ref = _mapping(item)
            logical = member_logical_digests[index] if index < len(member_logical_digests) else ""
            members.append(
                {
                    "logical_digest": logical,
                    "passport_digest": str(ref.get("passport_digest") or ""),
                    "stable_id": str(ref.get("stable_id") or ""),
                    "version": str(ref.get("version") or ""),
                }
            )
    return {
        "components": members,
        "execution_profile": passport.get("execution_profile"),
        "posture": passport.get("posture"),
        "purpose": passport.get("purpose"),
        "supported_tasks": _string_list(passport.get("supported_tasks")),
    }


def setup_harness_invariant_digest(
    passport: Mapping[str, JsonValue], member_logical_digests: Sequence[str]
) -> str:
    """Hash the declared setup invariant inputs in the dedicated domain."""
    return digest_canonical(
        SETUP_INVARIANT_DOMAIN, setup_invariant_payload(passport, member_logical_digests)
    )


def target_assessment_key_digest(identity: Mapping[str, JsonValue]) -> str:
    """Hash the complete target-assessment identity. Any field change is a new key."""
    return digest_canonical(TARGET_ASSESSMENT_KEY_DOMAIN, dict(identity))
