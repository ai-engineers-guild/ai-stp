"""A request field is the mirror of `ADR-0125`, and the inference is wrong.

`ADR-0125` orders *response* fields: the consumer accepts, ships, and only then
may a provider declare. An argument sent *to* a provider is the other way round
— an unknown flag is refused outright rather than ignored — so the provider must
tolerate it before any consumer sends it.

Which means the consumer needs something to read. The tempting inference is that
a provider declaring a scoped projection profile understands scopes and will
take `--target-scope`. It is measurably false: codex declares `user_root` in
`0.0.10` and accepts the flag only in the release after it, so a consumer acting
on that inference sends an unknown argument to a provider behaving correctly.

So the provider says which request fields it accepts, and the set is closed.
"""

from __future__ import annotations

import pytest

from ai_stp_cli.local.bundle import BUNDLE_FORMAT
from ai_stp_cli.provider import operation_v3, protocol_v3
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_canonical

pytestmark = pytest.mark.cli


def _arguments(**overrides: object) -> tuple[str, ...]:
    facts: dict[str, object] = {
        "operation": protocol_v3.Operation.INSTALL,
        "release_digest": "sha256:" + "a" * 64,
        "operation_id": "operation_01J0000000000000000000000A",
        "expires_at": "2026-08-28T00:00:00.000Z",
    }
    facts.update(overrides)
    return operation_v3.plan_operation_arguments(**facts)  # pyright: ignore[reportArgumentType]


def test_the_flag_is_absent_when_the_provider_has_not_declared_the_field() -> None:
    """The case every released provider is in today."""
    assert "--target-scope" not in _arguments(target_scope="user_root")


def test_the_flag_is_absent_for_the_global_scope_even_when_declared() -> None:
    """`global` is what an argv with no scope has always meant.

    Sending it would be a second way to say one thing, which is a defect even
    while the two agree — and it would make every existing plan digest change
    for a target whose root did not move.
    """
    assert "--target-scope" not in _arguments(
        target_scope="global", accepted_request_fields=frozenset({"target_scope"})
    )


def test_the_flag_is_sent_when_the_scope_is_real_and_the_provider_takes_it() -> None:
    arguments = _arguments(
        target_scope="user_root", accepted_request_fields=frozenset({"target_scope"})
    )
    assert arguments[-2:] == ("--target-scope", "user_root")


def test_a_provider_naming_a_request_field_this_build_cannot_send_is_refused() -> None:
    """Not ignored. An unsendable field is a promise nothing will keep.

    The refusal names the value and the set, for the same reason the scope
    refusal does: "provider-info fields differ from the closed v3 schema" sent a
    provider author looking for a schema-wide fault when one enum member was the
    whole of it.
    """
    with pytest.raises(ValueError, match="target_scope"):
        protocol_v3.parse_capabilities(_info(plan_request_fields=["prefix_override"]))


def test_a_provider_declaring_nothing_extra_still_parses() -> None:
    """The field is optional, and its absence is the ordinary case."""
    capabilities = protocol_v3.parse_capabilities(_info())
    assert capabilities.plan_request_fields == frozenset()


def test_the_declared_field_reaches_the_capabilities_a_caller_reads() -> None:
    capabilities = protocol_v3.parse_capabilities(_info(plan_request_fields=["target_scope"]))
    assert capabilities.plan_request_fields == frozenset({"target_scope"})


def _info(**overrides: object) -> dict[str, object]:
    # The digest binds the declaration, so it is computed rather than written:
    # a literal here would make every fixture edit a digest edit, and the first
    # one forgotten would be a test asserting its own stale copy.
    body: dict[str, JsonValue] = {
        "profile_id": "codex/native-files/1",
        "component_kinds": ["instruction"],
        "projection_kinds": ["native_files"],
        "native_namespaces": ["AGENTS.md"],
        "bundle_formats": [BUNDLE_FORMAT],
        "max_files": 64,
        "max_bytes": 1024,
    }
    profile = {**body, "digest": digest_canonical(protocol_v3.PROJECTION_DOMAIN, body)}
    info: dict[str, object] = {
        "protocol_version": protocol_v3.VERSION,
        "provider_id": "codex-setup-system",
        "harness_id": "codex",
        "provider_version": "0.0.11",
        "provider_build_digest": "sha256:" + "c" * 64,
        "supported_commands": list(protocol_v3.CORE_COMMANDS),
        "supported_operations": [item.value for item in protocol_v3.CORE_OPERATIONS],
        "supported_os": ["linux"],
        "supported_arch": ["x86_64"],
        "permission_profiles": ["standard"],
        "projection_profile": profile,
    }
    info.update(overrides)
    return info
