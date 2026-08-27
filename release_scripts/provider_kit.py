"""Generate the immutable public provider-protocol v3 conformance kit."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Final

from ai_stp_cli.provider import protocol_v3

KIT_SCHEMA: Final[str] = "ai-stp-provider-conformance-kit/1"
KIT_IDENTITY_SCHEMA: Final[str] = "ai-stp-provider-kit-identity/1"

#: Bumped to 0.2.0 because 0.1.0 named two different contracts. The commit that
#: introduced protocol v3 and the one immediately after it both published
#: `0.1.0`, and the second added `recover-operation` to the command sets, two
#: provenance fields, and new bounds in the wire schema. A provider claiming
#: "kit 0.1.0" therefore cannot say which of the two it implemented.
#:
#: 0.2.1 adds `unsupported_permission_profile`. The closed list had no reason
#: for a caller naming a profile outside `permission_profiles`: the operation
#: itself is supported, and `projection_profile_mismatch` is a different kind
#: of profile.
#:
#: 0.2.4 adds `user_root` to the target scopes a scoped projection may name
#: (`ADR-0127`). Its own version rather than a change inside 0.2.3: the
#: provider side pins the aggregate digest, `0.2.3` is
#: `sha256:2bf26243478620f018d5891d4e42f27611d37d36c2a6af507d2ecb9df85d833a`,
#: and it is already pinned in released work. A version whose bytes moved is
#: the same defect as a republished immutable `X.Y` — the pin would either
#: fail or, worse, keep matching a name that now means something else.
KIT_VERSION: Final[str] = "0.2.4"

#: Files the aggregate identity covers, in the order `SHA256SUMS` lists them.
MACHINE_FILES: Final[tuple[str, ...]] = (
    "conformance-cases.json",
    "manifest.json",
    "provider-info.schema.json",
)
OUTPUT_FILES: Final[tuple[str, ...]] = (
    "manifest.json",
    "provider-info.schema.json",
    "conformance-cases.json",
    "SHA256SUMS",
    "KIT-IDENTITY.json",
)

#: Exact kit schema bytes, served at the `$id` URL. Kept in lockstep with the
#: kit file so a validator that follows the identifier gets those bytes, not a
#: second hand copy.
_REPO: Final[Path] = Path(__file__).resolve().parents[1]
API_SCHEMA: Final[Path] = (
    _REPO
    / "apps"
    / "api"
    / "src"
    / "ai_stp_api"
    / "slices"
    / "schemas"
    / "provider-info.schema.json"
)


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _manifest() -> dict[str, object]:
    network = {
        operation.value: [
            {
                "phase": policy.phase.value,
                "network_requirement": policy.requirement.value,
            }
            for policy in policies
        ]
        for operation, policies in protocol_v3.OPERATION_NETWORK.items()
    }
    return {
        "schema": KIT_SCHEMA,
        "kit_version": KIT_VERSION,
        "protocol_version": protocol_v3.VERSION,
        "commands": list(protocol_v3.COMMANDS),
        "core_commands": list(protocol_v3.CORE_COMMANDS),
        "optional_commands": list(protocol_v3.OPTIONAL_COMMANDS),
        "read_commands": sorted(protocol_v3.READ_COMMANDS),
        "apply_commands": sorted(protocol_v3.APPLY_COMMANDS),
        "core_operations": sorted(operation.value for operation in protocol_v3.CORE_OPERATIONS),
        "optional_operations": sorted(
            operation.value for operation in protocol_v3.OPTIONAL_OPERATIONS
        ),
        "component_kinds": [kind.value for kind in protocol_v3.ComponentKind],
        "projection_kinds": [kind.value for kind in protocol_v3.ProjectionKind],
        "unsupported_reasons": [reason.value for reason in protocol_v3.UnsupportedReason],
        "provenance_fields": list(protocol_v3.PROVENANCE_FIELDS),
        "operation_network": network,
        # One owner each, rather than a list of three "normative sources". This
        # file is the vocabulary; a projection that names three sources of truth
        # for its own content is the duplication it was supposed to end.
        "generated_from": "apps/cli/src/ai_stp_cli/provider/protocol_v3.py",
        "requirements": "specs/active/SPEC-008-provider-installation.md",
        "decision": "docs/adr/ADR-0061-capability-negotiated-provider-protocol-v3.md",
    }


def _cases() -> dict[str, object]:
    bundle_cases = [
        {"case": reason, "expected_reason": reason}
        for reason in sorted(protocol_v3.BUNDLE_REJECTIONS)
    ]
    capability_cases = [
        {"case": reason.value, "expected_reason": reason.value}
        for reason in protocol_v3.UnsupportedReason
    ]
    return {
        "schema": "ai-stp-provider-conformance-cases/1",
        "protocol_version": protocol_v3.VERSION,
        "bundle_rejections": bundle_cases,
        "capability_rejections": capability_cases,
        "pure_commands": sorted(protocol_v3.READ_COMMANDS),
        # Derived, not listed. The literal said `["apply-operation", "launch"]`
        # and left `recover-operation` in neither list, though `APPLY_COMMANDS`
        # holds it beside `apply-operation`. A provider author reads this file
        # and nothing else: two lists that do not partition the command set say
        # a mutating command might be invoked during safe conformance, and they
        # then either make it safe to call or are surprised. The run never
        # invoked it, so the behaviour was right and only the promise was
        # narrow. Deriving keeps them one fact.
        "forbidden_in_safe_conformance": sorted(
            set(protocol_v3.COMMANDS) - protocol_v3.READ_COMMANDS
        ),
    }


def aggregate_digest(checksums: bytes) -> str:
    """One name for one exact revision of the whole kit.

    Taken over the canonical `SHA256SUMS` bytes, which already cover every
    machine file, so a change anywhere inside the kit changes this string.

    A semantic version is a label somebody maintains; this is what a provider
    can pin without trusting anyone to have maintained it. That is why the
    identity lives beside the kit rather than inside `manifest.json`: the
    manifest is itself covered by `SHA256SUMS`, so writing the aggregate into it
    would make the digest an input to itself.
    """
    return f"sha256:{hashlib.sha256(checksums).hexdigest()}"


def _identity(checksums: bytes) -> dict[str, object]:
    return {
        "schema": KIT_IDENTITY_SCHEMA,
        "kit_version": KIT_VERSION,
        "protocol_version": protocol_v3.VERSION,
        "aggregate_digest": aggregate_digest(checksums),
        "files": list(MACHINE_FILES),
    }


def render() -> dict[str, bytes]:
    """Return every generated file before its checksums are calculated."""
    files = {
        "manifest.json": _json_bytes(_manifest()),
        "provider-info.schema.json": _json_bytes(protocol_v3.WIRE_SCHEMA),
        "conformance-cases.json": _json_bytes(_cases()),
    }
    checksums = "".join(
        f"{hashlib.sha256(content).hexdigest()}  {name}\n"
        for name, content in sorted(files.items())
    ).encode()
    return {
        **files,
        "SHA256SUMS": checksums,
        "KIT-IDENTITY.json": _json_bytes(_identity(checksums)),
    }


def synchronize(output: Path, *, check: bool) -> tuple[str, ...]:
    """Write or verify the closed generated set and return mismatched paths."""
    expected = render()
    mismatches: list[str] = []
    actual_names = {path.name for path in output.iterdir()} if output.is_dir() else set()
    unexpected = actual_names - set(OUTPUT_FILES) - {"README.md"}
    mismatches.extend(str(output / name) for name in sorted(unexpected))
    for name in OUTPUT_FILES:
        path = output / name
        content = expected[name]
        if path.is_file() and path.read_bytes() == content:
            continue
        mismatches.append(str(path))
        if not check:
            output.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    schema = expected["provider-info.schema.json"]
    if API_SCHEMA.is_file() and API_SCHEMA.read_bytes() == schema:
        return tuple(mismatches)
    mismatches.append(str(API_SCHEMA))
    if not check:
        API_SCHEMA.parent.mkdir(parents=True, exist_ok=True)
        API_SCHEMA.write_bytes(schema)
    return tuple(mismatches)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("output", type=Path)
    return parser


def main() -> int:
    arguments = _parser().parse_args()
    mismatches = synchronize(arguments.output, check=arguments.check)
    if arguments.check and mismatches:
        for mismatch in mismatches:
            print(f"provider kit differs: {mismatch}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
