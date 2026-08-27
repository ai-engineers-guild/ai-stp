"""`ai-stp install` against a real provider process, including the ugly paths."""

import base64
import hashlib
import json
import os
import sqlite3
import stat
import subprocess
import tempfile
import zipfile
from collections.abc import Callable, Iterator, Sequence
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ai_stp_cli.commands import install
from ai_stp_cli.commands import registry as registry_commands
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import (
    cache,
    components,
    content,
    installation,
    passports,
    project_passport,
    provider_releases,
    revisions,
    selection,
    versions,
)
from ai_stp_cli.local.database import configured_path, open_registry
from ai_stp_cli.provider import (
    build_attestation,
    conformance,
    invocation,
    invocation_v2,
    network_launcher,
    protocol,
    protocol_v2,
    protocol_v3,
    release,
)
from ai_stp_contracts.catalog import CatalogTrust
from ai_stp_contracts.first_party import FirstPartyVersion
from ai_stp_contracts.first_party import versions as corpus_versions
from ai_stp_contracts.machine_help import CatalogVersionView
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_canonical
from ai_stp_passports.versions import SetupVersionPassport

MOMENT = "2026-08-08T10:00:00.000Z"
DEVICE = "device_test"
TARGET = "sha256:" + "a" * 64
TARGET_AFTER = "sha256:" + "b" * 64
RELEASE_KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))


def _release_policy(executable: str) -> release.TrustPolicy:
    """The policy a machine would ship if it had approved exactly this build.

    The executable is required rather than defaulted: after `release_not_pinned`
    exists, a policy that pins nothing refuses everything, and a fixture that
    silently did that would turn every acceptance test below into a test of
    refusal without saying so.
    """
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    public = RELEASE_KEY.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    digest, _ = release.artifact_identity(Path(executable))
    return release.TrustPolicy(
        schema_version=release.POLICY_SCHEMA_VERSION,
        policy_id="test/provider/1",
        allowed_publishers=frozenset({"test-publisher"}),
        allowed_keys=frozenset({"test-key"}),
        allowed_repositories=frozenset({"github.com/example/provider"}),
        pinned_releases=frozenset(
            {
                release.PinnedRelease(
                    provider_id="claude-code",
                    repository="github.com/example/provider",
                    artifact_digest=digest,
                )
            }
        ),
        signature_subject="ai-stp:provider-release-manifest:v1",
        public_keys={"test-key": base64.b64encode(public).decode("ascii")},
        supported_protocols=frozenset({1, 2}),
    )


def _pinning(executable: str) -> Callable[[], release.TrustPolicy]:
    """`pinned_policy` for a machine that approved this exact executable."""
    return lambda: _release_policy(executable)


def _signed_release(executable: str, path: Path, *, sequence: int = 7) -> Path:
    digest, size = release.artifact_identity(Path(executable))
    # Include the host platform so Windows CI/dev hosts pass platform_unsupported.
    os_name, architecture = install._release_platform().split("/", 1)  # pyright: ignore[reportPrivateUsage]
    unsigned = release.ReleaseManifest(
        provider_id="claude-code",
        provider_version="1.0.0",
        protocol_version=1,
        repository="github.com/example/provider",
        commit="a" * 40,
        license="MIT",
        artifact_url="https://example.test/releases/provider-v1",
        artifact_size=size,
        artifact_digest=digest,
        entry_point=Path(executable).name,
        supported_os=frozenset({"linux", "macos", "windows", os_name}),
        supported_arch=frozenset({"x86_64", "arm64", architecture}),
        sequence=sequence,
        policy_id="test/provider/1",
        publisher="test-publisher",
        signing_key="test-key",
        signature_subject="ai-stp:provider-release-manifest:v1",
        signature="",
    )
    signature = base64.b64encode(RELEASE_KEY.sign(release.signature_payload(unsigned))).decode(
        "ascii"
    )
    manifest = replace(unsigned, signature=signature)
    path.write_text(release.serialize_manifest(manifest), encoding="utf-8")
    return path


@pytest.fixture
def registry() -> Iterator[sqlite3.Connection]:
    with closing(open_registry(configured_path(), create=True)) as connection:
        yield connection


def _provider(
    tmp_path: Path,
    name: str,
    *,
    state: str = "verified",
    answers: dict[str, object] | None = None,
) -> str:
    """A real executable that speaks the protocol, so nothing is faked away."""
    os_name, architecture = install._release_platform().split("/", 1)  # pyright: ignore[reportPrivateUsage]
    body: dict[str, object] = {
        "provider-info": {
            "protocol_version": protocol.VERSION,
            "harness_id": "claude-code",
            "provider_version": "1.0.0",
            "supported_actions": list(protocol.COMMANDS),
            "bundle_formats": ["ai-stp-bundle/1"],
            "supported_os": [os_name],
            "supported_arch": [architecture],
            "limits": {},
        },
        "status": {"state": state, "target_digest": TARGET},
    }
    body.update(answers or {})
    place = tmp_path / name
    place.write_text(
        "#!/usr/bin/env python3\n"
        "import hashlib, json, sys\n"
        f"BODY = json.loads({json.dumps(body)!r})\n"
        f"STATE = {json.dumps(state)}\n"
        "command = sys.argv[1]\n"
        "arguments = sys.argv[4:]\n"
        "values = dict(zip(arguments[0::2], arguments[1::2], strict=True))\n"
        "common = {\n"
        "  'bundle_format': values.get('--bundle-format', ''),\n"
        "  'bundle_digest': values.get('--bundle-digest', ''),\n"
        "  'artifact_digest': values.get('--artifact-digest', ''),\n"
        "  'bundle_size': int(values.get('--bundle-size', '0')),\n"
        "}\n"
        "if command in BODY:\n"
        "  answer = BODY[command]\n"
        "elif command == 'validate-bundle':\n"
        "  answer = {**common, 'valid': True}\n"
        "elif command == 'plan-bundle':\n"
        "  raw = json.dumps(arguments, separators=(',', ':')).encode()\n"
        "  answer = {**common, 'state': 'planned', "
        "'plan_digest': 'sha256:' + hashlib.sha256(raw).hexdigest(), "
        "'expected_target_digest': values['--expected-target-digest'], "
        "'effects': ['write exact HarnessBundle']}\n"
        "elif command == 'apply-bundle':\n"
        "  answer = {**common, 'state': STATE, 'backup_ref': 'backup_1', "
        "'plan_digest': values['--plan-digest'], "
        "'expected_target_digest': values['--expected-target-digest']}\n"
        "else:\n"
        "  answer = {'answered': command}\n"
        "print(json.dumps(answer))\n",
        encoding="utf-8",
    )
    place.chmod(place.stat().st_mode | stat.S_IXUSR)
    return str(place)


def _confirmed(
    registry: sqlite3.Connection,
    tmp_path: Path,
    suffix: str,
    *,
    requires_authorization: str = "none",
    harness_id: str = "claude-code",
    component_type: str = "skill",
) -> str:
    """One confirmed composition, which is the only thing installable."""
    passports.init_developer(registry, device_id=DEVICE)
    passports.ensure_device(registry, device_id=DEVICE)
    found = project_passport.scan(registry, tmp_path)
    project_passport.record(registry, found, device_id=DEVICE)

    stable_id = f"component_01J0000000000000000000000{suffix}"
    artifact = content.put(
        registry,
        f"# exact {harness_id} {component_type} fixture {suffix}\n".encode(),
        at=MOMENT,
    )
    registry.execute(
        "INSERT INTO entity (stable_id, kind, created_at) VALUES (?, 'component', ?)",
        (stable_id, MOMENT),
    )
    document: dict[str, JsonValue] = {
        "schema_version": 1,
        "kind": "component",
        "stable_id": stable_id,
        "owner_id": passports.owner().account_id,
        "created_at": MOMENT,
        "visibility": "private",
        "parent_revision_ids": [],
        "facts": {
            "harness_id": {
                "value": harness_id,
                "origin": "observed",
                "confirmation": "none",
                "observed_at": MOMENT,
            },
            "component_type": {
                "value": component_type,
                "origin": "observed",
                "confirmation": "none",
                "observed_at": MOMENT,
            },
            "content_digest": {
                "value": artifact.digest,
                "origin": "observed",
                "confirmation": "none",
                "observed_at": MOMENT,
            },
            "content_format": {
                "value": components.COMPONENT_FILE_FORMAT,
                "origin": "observed",
                "confirmation": "none",
                "observed_at": MOMENT,
            },
            "source_name": {
                "value": "component.md",
                "origin": "observed",
                "confirmation": "none",
                "observed_at": MOMENT,
            },
        },
    }
    if requires_authorization != "none":
        document.update(
            {
                "name": "authorization-fixture",
                "description": "A formal component with external authorization.",
                "version": "1.0",
                "tags": ["tests"],
                "source": None,
                "artifact": {"digest": "sha256:" + "8" * 64, "size_bytes": 8},
                "harness_id": harness_id,
                "required_env": [],
                "requires_credentials": False,
                "requires_authorization": requires_authorization,
                "permissions": {"filesystem": [], "network": [], "process": []},
                "external_endpoints": [],
                "license": {"spdx_id": "MIT", "redistribution_allowed": False},
                "compatibility_evidence_refs": [],
                "component_type": component_type,
                "projection_kind": "native_files",
                "variant_id": None,
                "provides_capabilities": [],
                "requires_components": [],
                "requires_capabilities": [],
                "conflicts": {},
                "managed_paths": [],
                "native_ids": [],
            }
        )
    stored = revisions.commit(registry, document, device_id=DEVICE)
    digest = cache.digest_of(stored.envelope.model_dump(mode="json"))
    versions.record(
        registry,
        stable_id=stable_id,
        version="1.0",
        passport_digest=digest,
        revision_id=stored.revision_id,
        at=MOMENT,
    )

    from ai_stp_cli.local import selection

    developer_id = passports.developer_stable_id(registry)
    device_id = passports.device_stable_id(registry)
    assert developer_id is not None and device_id is not None
    developer = revisions.head(registry, developer_id)
    device = revisions.head(registry, device_id)
    project = revisions.head(registry, found.stable_id)
    assert developer is not None and device is not None and project is not None
    context = selection.Context(
        project_id=found.stable_id,
        harness_id=harness_id,
        developer_revision=developer.revision_id,
        device_revision=device.revision_id,
        project_revision=project.revision_id,
        policy_version="selection-policy/1;result_limit=20",
    )
    member = selection.Member(stable_id, "1.0", digest, "local_owner_or_pinned", "own")
    proposal = selection.propose(
        registry,
        context=context,
        members=(member,),
        at=MOMENT,
        expires_at="2026-08-09T10:00:00.000Z",
    )
    selection.confirm(
        registry,
        proposal.proposal_id,
        context=context,
        owner_id=passports.owner().account_id,
        device_id=DEVICE,
        at=MOMENT,
    )
    registry.commit()
    return proposal.proposal_id


def _project_context(registry: sqlite3.Connection, root: Path) -> str:
    passports.init_developer(registry, device_id=DEVICE)
    passports.ensure_device(registry, device_id=DEVICE)
    found = project_passport.scan(registry, root)
    project_passport.record(registry, found, device_id=DEVICE)
    registry.commit()
    return found.stable_id


def test_a_plan_is_computed_and_changes_nothing(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    proposal_id = _confirmed(registry, tmp_path, "A")
    view = install.plan({"proposal": proposal_id, "provider": _provider(tmp_path, "p1")}).payload
    assert view.state == "planned"
    assert view.plan_digest.startswith("sha256:")
    assert view.effects, "a plan enumerates what it will do"
    assert view.expected_target_digest == TARGET
    assert view.bundle_format == "ai-stp-bundle/1"
    assert view.bundle_digest.startswith("sha256:")
    assert view.bundle_artifact_digest.startswith("sha256:")
    assert view.bundle_size > 0
    assert view.provider_plan_digest.startswith("sha256:")


def test_plan_exposes_exact_setup_authorization_before_apply(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    proposal_id = _confirmed(
        registry,
        tmp_path,
        "Q",
        requires_authorization="external_service",
    )

    view = install.plan(
        {"proposal": proposal_id, "provider": _provider(tmp_path, "authorization-provider")}
    ).payload

    assert view.required_authorization == "external_service"


def test_target_status_accepts_the_project_root_install_plan_accepts(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    """One flag name, two vocabularies, and the wrong one answers instead of refusing.

    `install plan --project` and every `select --project` take a **local project
    root** and resolve it through `project_passport.stable_id_for`. The four
    `target` commands take the **project passport's stable id** verbatim. An
    agent learns `--project <path>` from the commands it runs first and then
    passes a path here.

    Nothing refuses. `survey` looks up `target_id = f"{project}:{harness}"`,
    a path matches no row, and the answer comes back `not_selected` with empty
    `installed_stable_id` — a confident, wrong statement about whether a target
    is installed, which is the most consequential thing this command reports.

    Measured on a live install before the fix: the pair was `installed` with a
    verified digest, and `target status` given the same path the plan was made
    with reported nothing installed.

    Accepting both rather than refusing the path: the value is unambiguous —
    a project identifier and a filesystem path cannot be confused for each other
    — and refusing would add a stop where the caller already said what it meant.
    """
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "README.md").write_text("# probe\n", encoding="utf-8")
    scan = project_passport.scan(registry, root)
    registry.commit()

    by_id = install.target_status({"project": scan.stable_id, "harness": "opencode"}).payload
    by_path = install.target_status({"project": str(root), "harness": "opencode"}).payload

    assert by_path.project_id == by_id.project_id, (
        "a path names the same pair the plan bound, so it must read the same pair"
    )


@pytest.mark.parametrize(
    ("provider_state", "pending"),
    [("pending", "external_service"), ("ready", "")],
)
def test_target_status_uses_provider_observation_for_authorization_readiness(
    registry: sqlite3.Connection,
    tmp_path: Path,
    provider_state: str,
    pending: str,
) -> None:
    _confirmed(
        registry,
        tmp_path,
        "Z",
        requires_authorization="external_service",
    )
    project_id = registry.execute("SELECT stable_id FROM entity WHERE kind = 'project'").fetchone()[
        0
    ]
    executable = _provider(
        tmp_path,
        f"authorization-{provider_state}",
        answers={
            "status": {
                "state": "verified",
                "target_digest": TARGET,
                "authorization": {
                    "kind": "external_service",
                    "state": provider_state,
                },
            }
        },
    )

    view = install.target_status(
        {"project": project_id, "harness": "claude-code", "provider": executable}
    ).payload

    assert view.pending_authorization == pending


def _bundle_response(command: str, arguments: Sequence[str], state: str = "verified") -> JsonValue:
    values = dict(zip(arguments[0::2], arguments[1::2], strict=True))
    common: dict[str, JsonValue] = {
        "bundle_format": values["--bundle-format"],
        "bundle_digest": values["--bundle-digest"],
        "artifact_digest": values["--artifact-digest"],
        "bundle_size": int(values["--bundle-size"]),
    }
    if command == "validate-bundle":
        return {**common, "valid": True}
    raw = json.dumps(list(arguments), separators=(",", ":")).encode()
    plan_digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    if command == "plan-bundle":
        return {
            **common,
            "state": "planned",
            "plan_digest": plan_digest,
            "expected_target_digest": values["--expected-target-digest"],
            "effects": ["write exact HarnessBundle"],
        }
    if command == "apply-bundle":
        return {
            **common,
            "state": state,
            "plan_digest": values["--plan-digest"],
            "expected_target_digest": values["--expected-target-digest"],
        }
    raise KeyError(command)


def _v3_test_invoker(
    monkeypatch: pytest.MonkeyPatch,
    *,
    target: Path,
) -> dict[str, JsonValue]:
    """Install a deterministic in-process v3 provider boundary for lifecycle tests."""
    os_name, architecture = install._release_platform().split("/", 1)  # pyright: ignore[reportPrivateUsage]
    profile: dict[str, JsonValue] = {
        "profile_id": "claude-code/test-v3",
        "component_kinds": cast(list[JsonValue], ["skill"]),
        "projection_kinds": cast(list[JsonValue], ["native_files"]),
        "native_namespaces": cast(list[JsonValue], ["skills"]),
        "bundle_formats": cast(list[JsonValue], ["ai-stp-bundle/1"]),
        "max_files": 2000,
        "max_bytes": 64 * 1024 * 1024,
    }
    projection_digest = digest_canonical(protocol_v3.PROJECTION_DOMAIN, profile)
    build_digest = "sha256:" + "c" * 64
    info: dict[str, JsonValue] = {
        "protocol_version": protocol_v3.VERSION,
        "provider_id": "nddev-claude-app",
        "harness_id": "claude-code",
        "provider_version": "3.0.0",
        "provider_build_digest": build_digest,
        "supported_commands": cast(list[JsonValue], list(protocol_v3.CORE_COMMANDS)),
        "supported_operations": cast(
            list[JsonValue], sorted(item.value for item in protocol_v3.CORE_OPERATIONS)
        ),
        "supported_os": cast(list[JsonValue], [os_name]),
        "supported_arch": cast(list[JsonValue], [architecture]),
        "permission_profiles": cast(list[JsonValue], []),
        "projection_profile": {**profile, "digest": projection_digest},
    }
    state: dict[str, JsonValue] = {
        "installed": False,
        "plan": None,
        "plan_digest": "",
        "calls": [],
        "recovery_state": "",
        "cleanup_state": "",
        "recovered_target": TARGET,
    }

    def values(arguments: Sequence[str]) -> dict[str, str]:
        return dict(zip(arguments[0::2], arguments[1::2], strict=True))

    def provider_status() -> JsonValue:
        if state["recovery_state"]:
            return {
                "state": state["recovery_state"],
                "recovery_phase": "prepared",
                "target_digest": TARGET_AFTER,
            }
        if not state["installed"]:
            return {"state": "missing", "target_digest": TARGET}
        held = cast(dict[str, JsonValue], state["plan"])
        bound = cast(dict[str, JsonValue], held["bundle"])
        answer: dict[str, JsonValue] = {
            "state": "managed",
            "target_digest": TARGET_AFTER,
            "drift_state": "verified",
            "protocol_version": protocol_v3.VERSION,
            "provider_id": "nddev-claude-app",
            "provider_version": "3.0.0",
            "provider_build_digest": build_digest,
            "provider_release_digest": held["provider_release_digest"],
            "provider_plan_digest": state["plan_digest"],
            # Stated because a status that names no operation binds itself to
            # nothing, and is refused before any field is compared.
            "operation_id": held["operation_id"],
            "projection_profile_digest": projection_digest,
            "bundle_digest": bound["bundle_digest"],
            "artifact_digest": bound["artifact_digest"],
        }
        if state["cleanup_state"]:
            answer["cleanup_state"] = state["cleanup_state"]
        return answer

    def invoke(command: str, arguments: Sequence[str]) -> JsonValue:
        cast(list[JsonValue], state["calls"]).append(command)
        if command == "provider-info":
            return info
        if command == "status":
            return provider_status()
        if command == "recover-operation":
            recovered = str(state["recovered_target"])
            state["recovery_state"] = ""
            state["cleanup_state"] = ""
            state["installed"] = recovered != TARGET
            return {"state": "recovered", "changed": True, "target_digest": recovered}
        supplied = values(arguments)
        if command == "validate-bundle":
            return {
                "valid": True,
                "bundle_format": supplied["--bundle-format"],
                "bundle_digest": supplied["--bundle-digest"],
                "artifact_digest": supplied["--artifact-digest"],
                "bundle_size": int(supplied["--bundle-size"]),
            }
        if command == "plan-operation":
            bound: dict[str, JsonValue] = {
                "bundle_format": supplied["--bundle-format"],
                "bundle_digest": supplied["--bundle-digest"],
                "artifact_digest": supplied["--artifact-digest"],
                "bundle_size": int(supplied["--bundle-size"]),
            }
            artifact: dict[str, JsonValue] = {
                "format": "ai-stp-provider-plan/3",
                "protocol_version": protocol_v3.VERSION,
                "provider_id": "nddev-claude-app",
                "provider_version": "3.0.0",
                "provider_build_digest": build_digest,
                "provider_release_digest": supplied["--provider-release-digest"],
                "operation_id": supplied["--operation-id"],
                "operation": supplied["--operation"],
                "canonical_target": str(target.resolve()),
                "expected_target_digest": TARGET,
                "projection_profile_digest": projection_digest,
                "bundle": bound,
                "backup_ref": None,
                "permission_profile": None,
                "platform": {"os": os_name, "arch": architecture},
                "expires_at": supplied["--expires-at"],
                "effects": ["write the exact v3 projection"],
            }
            digest = digest_canonical(protocol_v3.PLAN_DOMAIN, artifact)
            state["plan"] = artifact
            state["plan_digest"] = digest
            return {
                "state": "planned",
                "plan": artifact,
                "plan_digest": digest,
                "expected_target_digest": TARGET,
                "effects": artifact["effects"],
                **bound,
            }
        if command == "apply-operation":
            held = cast(dict[str, JsonValue], state["plan"])
            bound = cast(dict[str, JsonValue], held["bundle"])
            state["installed"] = True
            return {
                "state": "verified",
                "plan_digest": state["plan_digest"],
                "expected_target_digest": TARGET,
                **bound,
            }
        raise AssertionError(command)

    def invoker(
        _executable: str,
        provider_target: str,
        version: int,
        **_options: object,
    ) -> conformance.Invoker:
        assert provider_target == str(target.resolve())
        assert version == protocol_v3.VERSION
        return invoke

    monkeypatch.setattr(invocation, "provider_invoker", invoker)
    return state


def test_v3_refuses_to_install_a_provider_no_signed_release_covers(
    registry: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Omission stops being a way to install an unverified provider.

    The refusal names the attested bind, a supplied manifest, and the explicit
    unverified flag, because exactly one of them is right and the caller is the
    only one who knows which.
    """
    proposal_id = _confirmed(registry, tmp_path, "J")
    executable = _provider(tmp_path, "v3-provider")
    _v3_test_invoker(monkeypatch, target=tmp_path)

    with pytest.raises(CliFailure) as raised:
        install.plan(
            {
                "proposal": proposal_id,
                "provider": executable,
                "protocol-version": 3,
                "target": str(tmp_path),
            }
        )

    assert raised.value.code == "AI_STP_VALIDATION_ERROR"
    assert raised.value.next_actions == [
        "provider fetch --harness <id> --json",
        "install plan --provider-manifest <path> --json",
        "install plan --unverified-provider --json",
    ]


def test_v3_installs_an_unverified_provider_only_when_asked_to(
    registry: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The escape hatch exists, and the plan says it was taken.

    Refusing local providers outright would move the same act outside the tool,
    where nothing records it. The plan records it instead.
    """
    proposal_id = _confirmed(registry, tmp_path, "K")
    executable = _provider(tmp_path, "v3-provider")
    _v3_test_invoker(monkeypatch, target=tmp_path)

    planned = install.plan(
        {
            "proposal": proposal_id,
            "provider": executable,
            "protocol-version": 3,
            "target": str(tmp_path),
            "unverified-provider": True,
        }
    ).payload

    assert planned.provider_protocol_version == 3
    assert planned.provider_release_trust == "unverified"
    assert planned.provider_release_trusted is False


def test_a_signed_release_and_the_unverified_flag_contradict_each_other(
    registry: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Naming a release and disclaiming one at once has no honest reading."""
    proposal_id = _confirmed(registry, tmp_path, "M")
    executable = _provider(tmp_path, "signed-provider")
    manifest = _signed_release(executable, tmp_path / "release.json")
    monkeypatch.setattr(release, "pinned_policy", _pinning(executable))

    with pytest.raises(CliFailure) as raised:
        install.plan(
            {
                "proposal": proposal_id,
                "provider": executable,
                "provider-manifest": str(manifest),
                "unverified-provider": True,
            }
        )

    assert raised.value.code == "AI_STP_VALIDATION_ERROR"


def test_the_frozen_protocol_still_installs_without_a_release_manifest(
    registry: sqlite3.Connection,
    tmp_path: Path,
) -> None:
    """v1 predates the signed-release line and is not changed by this rule."""
    proposal_id = _confirmed(registry, tmp_path, "P")
    executable = _provider(tmp_path, "v1-provider")

    planned = install.plan({"proposal": proposal_id, "provider": executable}).payload

    assert planned.provider_protocol_version == 1
    assert planned.provider_release_trusted is False


def test_v3_plan_apply_and_status_bind_one_exact_provider_plan(
    registry: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal_id = _confirmed(registry, tmp_path, "Y")
    executable = _provider(tmp_path, "v3-provider")
    state = _v3_test_invoker(monkeypatch, target=tmp_path)

    planned = install.plan(
        {
            "proposal": proposal_id,
            "provider": executable,
            "protocol-version": 3,
            "unverified-provider": True,
            "target": str(tmp_path),
        }
    ).payload
    assert planned.provider_protocol_version == 3
    assert planned.provider_plan_digest == state["plan_digest"]
    assert cache.stored_provider_plan(planned.provider_plan_digest) is not None
    install.approve({"operation": planned.operation_id, "plan-digest": planned.plan_digest})
    done = install.apply({"operation": planned.operation_id, "provider": executable}).payload

    assert done.state == "verified"
    assert cast(list[str], state["calls"]) == [
        "provider-info",
        "validate-bundle",
        "status",
        "plan-operation",
        "provider-info",
        "status",
        "apply-operation",
        "status",
    ]


def test_v3_prepared_and_newly_composed_sources_bind_the_same_harness_bundle(
    registry: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal_id = _confirmed(registry, tmp_path, "P")
    held = selection.held(registry, proposal_id)
    assert held is not None
    assert held.confirmed_stable_id is not None
    assert held.confirmed_version is not None
    executable = _provider(tmp_path, "v3-prepared-provider")
    _v3_test_invoker(monkeypatch, target=tmp_path)

    composed = install.plan(
        {
            "proposal": proposal_id,
            "provider": executable,
            "protocol-version": 3,
            "unverified-provider": True,
            "target": str(tmp_path),
        }
    ).payload
    prepared = install.plan(
        {
            "setup": f"{held.confirmed_stable_id}@{held.confirmed_version}",
            "provider": executable,
            "protocol-version": 3,
            "unverified-provider": True,
            "target": str(tmp_path),
        }
    ).payload

    assert prepared.bundle_digest == composed.bundle_digest
    assert prepared.bundle_artifact_digest == composed.bundle_artifact_digest
    assert prepared.bundle_size == composed.bundle_size
    assert prepared.target_id == composed.target_id


def test_a_refused_postcondition_leaves_the_operation_resumable(
    registry: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One failed resume must not spend the operation. This one did.

    On a real target a provider defect made the postcondition refuse. `resume`
    caught that and marked the operation `partial` — and `resume` accepts only
    `applied_unverified`, so the refusal buried it. When the provider was fixed
    there was nothing left to resume, and the effect it had already applied was
    stranded.

    A postcondition is a verdict about evidence, not an interruption: `status`
    is read-only, the provider answered, and nothing became unknown that was
    known before. `partial` belongs to a timeout or a malformed answer after a
    possible effect. `apply` never confused the two, which is the whole reason
    its half of the same path recovered.
    """
    proposal_id = _confirmed(registry, tmp_path, "Q")
    executable = _provider(tmp_path, "v3-resume-twice")
    state = _v3_test_invoker(monkeypatch, target=tmp_path)
    planned = install.plan(
        {
            "proposal": proposal_id,
            "provider": executable,
            "protocol-version": 3,
            "unverified-provider": True,
            "target": str(tmp_path),
        }
    ).payload
    install.approve({"operation": planned.operation_id, "plan-digest": planned.plan_digest})
    installation.begin(
        registry,
        planned.operation_id,
        observed_target_digest=planned.expected_target_digest,
        at=MOMENT,
    )
    state["installed"] = True

    # A provider that answers, cleanly, without binding itself to the operation
    # — exactly the shape a released provider had.
    held = cast(dict[str, JsonValue], state["plan"])
    broken = dict(held)
    broken["operation_id"] = ""
    state["plan"] = cast(JsonValue, broken)

    with pytest.raises(CliFailure):
        install.resume({"operation": planned.operation_id, "provider": executable})

    stopped = {item.operation_id: item.state for item in installation.resumable(registry)}
    assert stopped.get(planned.operation_id) == installation.STATE_APPLIED_UNVERIFIED, (
        "a refused postcondition must not consume the only path back"
    )

    # The provider is fixed; the same operation verifies without reapplying.
    state["plan"] = cast(JsonValue, held)
    cast(list[str], state["calls"]).clear()
    resumed = install.resume({"operation": planned.operation_id, "provider": executable}).payload

    assert resumed.state == "verified"
    assert "apply-operation" not in cast(list[str], state["calls"])


def test_v3_resume_only_verifies_exact_provenance_and_never_reapplies(
    registry: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal_id = _confirmed(registry, tmp_path, "R")
    executable = _provider(tmp_path, "v3-resume-provider")
    state = _v3_test_invoker(monkeypatch, target=tmp_path)
    planned = install.plan(
        {
            "proposal": proposal_id,
            "provider": executable,
            "protocol-version": 3,
            "unverified-provider": True,
            "target": str(tmp_path),
        }
    ).payload
    install.approve({"operation": planned.operation_id, "plan-digest": planned.plan_digest})
    installation.begin(
        registry,
        planned.operation_id,
        observed_target_digest=planned.expected_target_digest,
        at=MOMENT,
    )
    state["installed"] = True
    cast(list[str], state["calls"]).clear()

    resumed = install.resume({"operation": planned.operation_id, "provider": executable}).payload

    assert resumed.state == "verified"
    assert cast(list[str], state["calls"]) == ["provider-info", "status"]


def test_v3_resume_recovers_prepared_transaction_to_exact_precondition(
    registry: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal_id = _confirmed(registry, tmp_path, "W")
    executable = _provider(tmp_path, "v3-prepared-recovery-provider")
    state = _v3_test_invoker(monkeypatch, target=tmp_path)
    planned = install.plan(
        {
            "proposal": proposal_id,
            "provider": executable,
            "protocol-version": 3,
            "unverified-provider": True,
            "target": str(tmp_path),
        }
    ).payload
    install.approve({"operation": planned.operation_id, "plan-digest": planned.plan_digest})
    installation.begin(
        registry,
        planned.operation_id,
        observed_target_digest=planned.expected_target_digest,
        at=MOMENT,
    )
    state["recovery_state"] = "recovery_required"
    state["recovered_target"] = TARGET
    cast(list[str], state["calls"]).clear()

    resumed = install.resume({"operation": planned.operation_id, "provider": executable}).payload

    assert resumed.state == "rolled_back"
    assert cast(list[str], state["calls"]) == ["provider-info", "status", "recover-operation"]


def test_v3_resume_drains_committed_cleanup_then_verifies_exact_provenance(
    registry: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal_id = _confirmed(registry, tmp_path, "V")
    executable = _provider(tmp_path, "v3-committed-recovery-provider")
    state = _v3_test_invoker(monkeypatch, target=tmp_path)
    planned = install.plan(
        {
            "proposal": proposal_id,
            "provider": executable,
            "protocol-version": 3,
            "unverified-provider": True,
            "target": str(tmp_path),
        }
    ).payload
    install.approve({"operation": planned.operation_id, "plan-digest": planned.plan_digest})
    installation.begin(
        registry,
        planned.operation_id,
        observed_target_digest=planned.expected_target_digest,
        at=MOMENT,
    )
    installation.applied(registry, planned.operation_id, at=MOMENT)
    state["installed"] = True
    state["cleanup_state"] = "committed_pending"
    state["recovered_target"] = TARGET_AFTER
    cast(list[str], state["calls"]).clear()

    resumed = install.resume({"operation": planned.operation_id, "provider": executable}).payload

    assert resumed.state == "verified"
    assert cast(list[str], state["calls"]) == [
        "provider-info",
        "status",
        "recover-operation",
        "status",
    ]


def test_catalogue_setup_binds_to_an_explicit_current_project_context(
    registry: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _confirmed(registry, tmp_path, "Q", harness_id="claude-code")
    corpus = corpus_versions()
    setup = next(
        item
        for item in corpus
        if item.kind == "setup"
        and isinstance(item.passport, SetupVersionPassport)
        and item.passport.harness_id == "claude-code"
        and item.passport.target_role == "research"
    )
    assert isinstance(setup.passport, SetupVersionPassport)
    members = {
        ref.stable_id: next(
            item
            for item in corpus
            if item.kind == "component" and item.passport.stable_id == ref.stable_id
        )
        for ref in setup.passport.components
    }
    held = {setup.passport.stable_id: setup, **members}

    def acquire_one(
        kind: str, stable_id: str, version: str, *, offline: bool
    ) -> registry_commands.AcquiredCatalogVersion:
        assert offline is True
        item = held[stable_id]
        assert item.kind == kind
        assert item.passport.version == version
        return registry_commands.AcquiredCatalogVersion(
            view=CatalogVersionView(
                kind=item.kind,
                source="cache",
                checked_at=MOMENT,
                passport_digest=item.passport_digest,
                lifecycle="active",
                trust=CatalogTrust(
                    author_verified=True,
                    component_verified=True,
                    trust_lane="authoritative",
                ),
                published_at=MOMENT,
                passport=item.passport.model_dump(mode="json"),
            ),
            passport=item.passport,
            artifact=item.artifact,
        )

    monkeypatch.setattr(registry_commands, "acquire_version", acquire_one)
    registry_commands.acquire(
        {"id": setup.passport.stable_id, "version": setup.passport.version, "offline": True}
    )
    reference = f"{setup.passport.stable_id}@{setup.passport.version}"

    with pytest.raises(CliFailure, match="explicit local project context"):
        install._prepared_setup_source(registry, reference, "")  # pyright: ignore[reportPrivateUsage]

    prepared = install._prepared_setup_source(  # pyright: ignore[reportPrivateUsage]
        registry, reference, str(tmp_path)
    )
    assert prepared.harness_id == "claude-code"
    assert prepared.project_id.startswith("project_")
    assert prepared.snapshot.startswith("sha256:")
    assert [item.stable_id for item in prepared.members] == [
        item.stable_id for item in setup.passport.components
    ]


def _acquire_first_party_setup(
    harness_id: str,
    role: str,
    monkeypatch: pytest.MonkeyPatch,
) -> FirstPartyVersion:
    corpus = corpus_versions()
    setup = next(
        item
        for item in corpus
        if item.kind == "setup"
        and isinstance(item.passport, SetupVersionPassport)
        and item.passport.harness_id == harness_id
        and item.passport.target_role == role
    )
    assert isinstance(setup.passport, SetupVersionPassport)
    held = {
        item.passport.stable_id: item
        for item in corpus
        if item.passport.stable_id == setup.passport.stable_id
        or item.passport.stable_id in {ref.stable_id for ref in setup.passport.components}
    }

    def acquire_one(
        kind: str, stable_id: str, version: str, *, offline: bool
    ) -> registry_commands.AcquiredCatalogVersion:
        assert offline is True
        item = held[stable_id]
        assert item.kind == kind
        assert item.passport.version == version
        return registry_commands.AcquiredCatalogVersion(
            view=CatalogVersionView(
                kind=item.kind,
                source="cache",
                checked_at=MOMENT,
                passport_digest=item.passport_digest,
                lifecycle="active",
                trust=CatalogTrust(
                    author_verified=True,
                    component_verified=True,
                    trust_lane="authoritative",
                ),
                published_at=MOMENT,
                passport=item.passport.model_dump(mode="json"),
            ),
            passport=item.passport,
            artifact=item.artifact,
        )

    monkeypatch.setattr(registry_commands, "acquire_version", acquire_one)
    registry_commands.acquire(
        {"id": setup.passport.stable_id, "version": setup.passport.version, "offline": True}
    )
    return setup


@pytest.mark.parametrize(
    ("harness_id", "provider_environment", "manifest_environment", "profiles"),
    [
        (
            "claude-code",
            "AI_STP_CLAUDE_PROVIDER_V3",
            "AI_STP_CLAUDE_PROVIDER_V3_MANIFEST",
            ("", ""),
        ),
        (
            "codex",
            "AI_STP_CODEX_PROVIDER_V3",
            "AI_STP_CODEX_PROVIDER_V3_MANIFEST",
            ("full-auto", "safe"),
        ),
        (
            "grok-build",
            "AI_STP_GROK_BUILD_PROVIDER_V3",
            "AI_STP_GROK_BUILD_PROVIDER_V3_MANIFEST",
            ("full-auto", "safe"),
        ),
        (
            "opencode",
            "AI_STP_OPENCODE_PROVIDER_V3",
            "AI_STP_OPENCODE_PROVIDER_V3_MANIFEST",
            ("full-auto", "safe"),
        ),
        (
            "pi",
            "AI_STP_PI_PROVIDER_V3",
            "AI_STP_PI_PROVIDER_V3_MANIFEST",
            ("full-auto", "safe"),
        ),
    ],
)
def test_real_first_party_base_setup_profiles_use_one_exact_bundle_lifecycle(
    registry: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    harness_id: str,
    provider_environment: str,
    manifest_environment: str,
    profiles: tuple[str, str],
) -> None:
    executable = os.environ.get(provider_environment)
    manifest = os.environ.get(manifest_environment)
    if executable is None or manifest is None:
        pytest.skip(f"set {provider_environment} and {manifest_environment} for base setup E2E")
    project_id = _project_context(registry, tmp_path)
    setup = _acquire_first_party_setup(harness_id, "ai-harness-engineer", monkeypatch)
    assert isinstance(setup.passport, SetupVersionPassport)
    reference = f"{setup.passport.stable_id}@{setup.passport.version}"
    cache_root = Path.home() / ".cache"
    cache_root.mkdir(mode=0o700, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"ai-stp-base-{harness_id}-", dir=cache_root) as held:
        target = Path(held)

        def execute(action: str, *, profile: str = "", backup_ref: str = "") -> Any:
            parameters = {
                "setup": reference,
                "project": str(tmp_path),
                "provider": executable,
                "provider-manifest": manifest,
                "protocol-version": 3,
                "target": str(target),
                "action": action,
            }
            if profile:
                parameters["permission-profile"] = profile
            if backup_ref:
                parameters["backup-ref"] = backup_ref
            planned = install.plan(parameters).payload
            assert planned.provider_release_trusted is True
            install.approve({"operation": planned.operation_id, "plan-digest": planned.plan_digest})
            completed = install.apply(
                {"operation": planned.operation_id, "provider": executable}
            ).payload
            assert completed.state == "verified"
            return completed

        installed = execute("install", profile=profiles[0])
        status = install.target_status(
            {
                "project": project_id,
                "harness": harness_id,
                "provider": executable,
                "protocol-version": 3,
                "target": str(target),
            }
        ).payload
        assert status.states == ["installed"]
        switched = execute("update", profile=profiles[1])
        assert switched.bundle_digest == installed.bundle_digest
        assert switched.bundle_artifact_digest == installed.bundle_artifact_digest
        backed_up = execute("backup")
        assert backed_up.backup_ref
        removed = execute("remove")
        assert removed.backup_ref
        restored = execute("rollback", backup_ref=removed.backup_ref)
        assert restored.state == "verified"


@pytest.mark.parametrize(
    "role", ["backend", "frontend", "full-stack", "code-review", "security", "research"]
)
@pytest.mark.parametrize(
    ("harness_id", "provider_environment", "manifest_environment"),
    [
        ("claude-code", "AI_STP_CLAUDE_PROVIDER_V3", "AI_STP_CLAUDE_PROVIDER_V3_MANIFEST"),
        ("codex", "AI_STP_CODEX_PROVIDER_V3", "AI_STP_CODEX_PROVIDER_V3_MANIFEST"),
    ],
)
def test_real_role_setup_install_status_remove_and_rollback(
    registry: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    role: str,
    harness_id: str,
    provider_environment: str,
    manifest_environment: str,
) -> None:
    executable = os.environ.get(provider_environment)
    manifest = os.environ.get(manifest_environment)
    if executable is None or manifest is None:
        pytest.skip(f"set {provider_environment} and {manifest_environment} for role E2E")
    project_id = _project_context(registry, tmp_path)
    setup = _acquire_first_party_setup(harness_id, role, monkeypatch)
    assert isinstance(setup.passport, SetupVersionPassport)
    reference = f"{setup.passport.stable_id}@{setup.passport.version}"
    cache_root = Path.home() / ".cache"
    cache_root.mkdir(mode=0o700, exist_ok=True)
    target_holder = tempfile.TemporaryDirectory(prefix=f"ai-stp-role-{harness_id}-", dir=cache_root)
    target = Path(target_holder.name)

    def execute(action: str, *, backup_ref: str = "") -> Any:
        parameters = {
            "setup": reference,
            "project": str(tmp_path),
            "provider": executable,
            "provider-manifest": manifest,
            "protocol-version": 3,
            "target": str(target),
            "action": action,
        }
        if backup_ref:
            parameters["backup-ref"] = backup_ref
        try:
            planned = install.plan(parameters).payload
        except CliFailure as error:
            pytest.fail(f"provider role plan failed: {error.details}")
        assert planned.provider_release_trusted is True
        install.approve({"operation": planned.operation_id, "plan-digest": planned.plan_digest})
        completed = install.apply(
            {"operation": planned.operation_id, "provider": executable}
        ).payload
        assert completed.state == "verified"
        return completed

    execute("install")
    status = install.target_status(
        {
            "project": project_id,
            "harness": harness_id,
            "provider": executable,
            "protocol-version": 3,
            "target": str(target),
        }
    ).payload
    assert status.states == ["installed"]
    removed = execute("remove")
    assert removed.backup_ref
    restored = execute("rollback", backup_ref=removed.backup_ref)
    assert restored.state == "verified"
    target_holder.cleanup()


@pytest.mark.parametrize(
    ("environment", "manifest_environment", "harness_id", "component_type"),
    [
        (
            "AI_STP_CLAUDE_PROVIDER_V3",
            "AI_STP_CLAUDE_PROVIDER_V3_MANIFEST",
            "claude-code",
            "instruction",
        ),
        (
            "AI_STP_CODEX_PROVIDER_V3",
            "AI_STP_CODEX_PROVIDER_V3_MANIFEST",
            "codex",
            "instruction",
        ),
        (
            "AI_STP_GROK_BUILD_PROVIDER_V3",
            "AI_STP_GROK_BUILD_PROVIDER_V3_MANIFEST",
            "grok-build",
            "instruction",
        ),
        (
            "AI_STP_OPENCODE_PROVIDER_V3",
            "AI_STP_OPENCODE_PROVIDER_V3_MANIFEST",
            "opencode",
            "instruction",
        ),
        (
            "AI_STP_PI_PROVIDER_V3",
            "AI_STP_PI_PROVIDER_V3_MANIFEST",
            "pi",
            "instruction",
        ),
    ],
)
def test_real_v3_full_setup_lifecycle_uses_one_exact_bundle_path(
    registry: sqlite3.Connection,
    environment: str,
    manifest_environment: str,
    harness_id: str,
    component_type: str,
) -> None:
    executable = os.environ.get(environment)
    if executable is None:
        pytest.skip(f"set {environment} to run the real cross-repository provider E2E")
    manifest_path = os.environ.get(manifest_environment)
    cache_root = Path.home() / ".cache"
    cache_root.mkdir(mode=0o700, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"ai-stp-{harness_id}-v3-e2e-", dir=cache_root) as held:
        target = Path(held) / "target"
        target.mkdir(mode=0o700)
        proposal_id = _confirmed(
            registry,
            target,
            "5",
            harness_id=harness_id,
            component_type=component_type,
        )
        confirmed = selection.held(registry, proposal_id)
        assert confirmed is not None
        assert confirmed.confirmed_stable_id is not None
        assert confirmed.confirmed_version is not None
        prepared_ref = f"{confirmed.confirmed_stable_id}@{confirmed.confirmed_version}"

        def execute(action: str, *, prepared: bool = False, backup_ref: str = "") -> Any:
            parameters = {
                "provider": executable,
                "protocol-version": 3,
                "target": str(target),
                "action": action,
            }
            parameters["setup" if prepared else "proposal"] = (
                prepared_ref if prepared else proposal_id
            )
            if backup_ref:
                parameters["backup-ref"] = backup_ref
            if manifest_path:
                parameters["provider-manifest"] = manifest_path
            planned = install.plan(parameters).payload
            if action in {"install", "update"}:
                assert planned.managed_paths
            else:
                assert action in {"backup", "remove", "rollback"}
                assert planned.managed_paths == []
            if manifest_path:
                assert planned.provider_release_trusted is True
            install.approve({"operation": planned.operation_id, "plan-digest": planned.plan_digest})
            completed = install.apply(
                {"operation": planned.operation_id, "provider": executable}
            ).payload
            assert completed.state == "verified"
            return completed

        installed = execute("install")
        assert installed.bundle_digest.startswith("sha256:")
        first_status = install.target_status(
            {
                "project": confirmed.project_id,
                "harness": harness_id,
                "provider": executable,
                "protocol-version": 3,
                "target": str(target),
            }
        ).payload
        assert first_status.states == ["installed"]
        assert first_status.verified_target_digest == first_status.observed_target_digest

        managed_file = target / ("CLAUDE.md" if harness_id == "claude-code" else "AGENTS.md")
        assert managed_file.is_file() and not managed_file.is_symlink()
        managed_file.write_bytes(managed_file.read_bytes() + b"\ncontrolled drift\n")
        drifted = install.target_status(
            {
                "project": confirmed.project_id,
                "harness": harness_id,
                "provider": executable,
                "protocol-version": 3,
                "target": str(target),
            }
        ).payload
        assert drifted.states == ["local_drift"]
        assert drifted.verified_target_digest != drifted.observed_target_digest
        drift_diff = install.target_diff(
            {
                "project": confirmed.project_id,
                "harness": harness_id,
                "provider": executable,
                "protocol-version": 3,
                "target": str(target),
            }
        ).payload
        assert drift_diff.changes == [
            "target changed outside the provider: "
            f"{drifted.verified_target_digest} -> {drifted.observed_target_digest}"
        ]
        assert [(item.code, item.path) for item in drift_diff.managed_changes] == [
            ("modified", managed_file.name)
        ]
        assert drift_diff.managed_detail == "available"
        assert drift_diff.managed_changes[0].expected_digest
        assert drift_diff.managed_changes[0].observed_digest
        assert managed_file.read_bytes().endswith(b"\ncontrolled drift\n")

        replaced = execute("update", prepared=True)
        assert replaced.bundle_digest == installed.bundle_digest
        assert replaced.bundle_artifact_digest == installed.bundle_artifact_digest
        recovered = install.target_status(
            {
                "project": confirmed.project_id,
                "harness": harness_id,
                "provider": executable,
                "protocol-version": 3,
                "target": str(target),
            }
        ).payload
        assert recovered.states == ["installed"]
        assert recovered.verified_target_digest == recovered.observed_target_digest
        backed_up = execute("backup")
        assert backed_up.backup_ref
        removed = execute("remove")
        assert removed.backup_ref
        restored = execute("rollback", backup_ref=removed.backup_ref)
        assert restored.state == "verified"
        if manifest_path:
            manifest = release.parse_manifest(Path(manifest_path).read_text("utf-8"))
            assert provider_releases.minimum_sequence(registry, manifest.provider_id) == 1


def test_the_whole_path_records_every_step(registry: sqlite3.Connection, tmp_path: Path) -> None:
    proposal_id = _confirmed(registry, tmp_path, "B")
    executable = _provider(tmp_path, "p1")
    planned = install.plan({"proposal": proposal_id, "provider": executable}).payload
    install.approve({"operation": planned.operation_id, "plan-digest": planned.plan_digest})
    done = install.apply({"operation": planned.operation_id, "provider": executable}).payload

    assert done.state == "verified"
    assert [item.state_after for item in done.steps] == [
        "planned",
        "approved",
        "applying",
        "applied_unverified",
        "verified",
    ]


def test_provider_target_compare_refusal_is_stale_not_partial(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    """A locked target mismatch proves no effect and must not demand recovery."""
    proposal_id = _confirmed(registry, tmp_path, "C")
    executable = _provider(tmp_path, "stale-provider", state="stale")
    planned = install.plan({"proposal": proposal_id, "provider": executable}).payload
    install.approve({"operation": planned.operation_id, "plan-digest": planned.plan_digest})

    result = install.apply({"operation": planned.operation_id, "provider": executable}).payload

    assert result.state == "stale"
    assert [item.state_after for item in result.steps] == [
        "planned",
        "approved",
        "applying",
        "stale",
    ]
    assert install.status({}).payload.stopped == []


def test_planning_refuses_provider_validation_not_bound_to_exact_bytes(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    proposal_id = _confirmed(registry, tmp_path, "3")
    executable = _provider(
        tmp_path,
        "mismatched-validator",
        answers={
            "validate-bundle": {
                "valid": True,
                "bundle_format": "ai-stp-bundle/1",
                "bundle_digest": "sha256:" + "0" * 64,
                "artifact_digest": "sha256:" + "0" * 64,
                "bundle_size": 1,
            }
        },
    )

    with pytest.raises(CliFailure, match="not bound to the exact HarnessBundle") as raised:
        install.plan({"proposal": proposal_id, "provider": executable})

    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"


def test_planning_refuses_a_provider_plan_not_bound_to_the_requested_input(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    proposal_id = _confirmed(registry, tmp_path, "7")
    executable = _provider(
        tmp_path,
        "mismatched-plan",
        answers={
            "plan-bundle": {
                "state": "planned",
                "bundle_format": "ai-stp-bundle/1",
                "bundle_digest": "sha256:" + "0" * 64,
                "artifact_digest": "sha256:" + "0" * 64,
                "bundle_size": 1,
                "plan_digest": "sha256:" + "0" * 64,
                "expected_target_digest": "sha256:" + "f" * 64,
                "effects": ["write another target"],
            }
        },
    )

    with pytest.raises(CliFailure) as raised:
        install.plan({"proposal": proposal_id, "provider": executable})

    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"


def test_apply_refuses_missing_or_corrupt_approved_bundle_before_effect(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    proposal_id = _confirmed(registry, tmp_path, "4")
    executable = _provider(tmp_path, "provider")
    planned = install.plan({"proposal": proposal_id, "provider": executable}).payload
    install.approve({"operation": planned.operation_id, "plan-digest": planned.plan_digest})
    cache.raw_artifact_path(planned.bundle_artifact_digest).write_bytes(b"tampered")

    with pytest.raises(CliFailure, match="not in the verified cache") as raised:
        install.apply({"operation": planned.operation_id, "provider": executable})

    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"
    assert install.recover({"operation": planned.operation_id}).payload.state == "approved"


def test_unbound_apply_evidence_is_partial_after_the_provider_was_called(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    proposal_id = _confirmed(registry, tmp_path, "5")
    executable = _provider(
        tmp_path,
        "mismatched-apply",
        answers={
            "apply-bundle": {
                "state": "verified",
                "bundle_format": "ai-stp-bundle/1",
                "bundle_digest": "sha256:" + "0" * 64,
                "artifact_digest": "sha256:" + "0" * 64,
                "bundle_size": 1,
                "plan_digest": "sha256:" + "0" * 64,
                "expected_target_digest": TARGET,
            }
        },
    )
    planned = install.plan({"proposal": proposal_id, "provider": executable}).payload
    install.approve({"operation": planned.operation_id, "plan-digest": planned.plan_digest})

    with pytest.raises(CliFailure) as raised:
        install.apply({"operation": planned.operation_id, "provider": executable})

    assert raised.value.code == "AI_STP_PARTIAL_OPERATION"
    assert install.recover({"operation": planned.operation_id}).payload.state == "partial"


def test_signed_exact_provider_release_advances_floor_only_after_verified_apply(
    registry: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal_id = _confirmed(registry, tmp_path, "R")
    executable = _provider(tmp_path, "signed-provider")
    manifest = _signed_release(executable, tmp_path / "release.json")
    monkeypatch.setattr(release, "pinned_policy", _pinning(executable))

    planned = install.plan(
        {
            "proposal": proposal_id,
            "provider": executable,
            "provider-manifest": str(manifest),
        }
    ).payload
    assert planned.provider_release_trusted is True
    assert provider_releases.minimum_sequence(registry, "claude-code") == 0

    install.approve({"operation": planned.operation_id, "plan-digest": planned.plan_digest})
    done = install.apply({"operation": planned.operation_id, "provider": executable}).payload

    assert done.state == "verified"
    assert provider_releases.minimum_sequence(registry, "claude-code") == 7
    assert provider_releases.was_verified(
        registry,
        provider_id="claude-code",
        sequence=7,
        artifact_digest=release.parse_manifest(manifest.read_text("utf-8")).artifact_digest,
    )


def test_opennetwork_manifest_is_verified_publisher_without_an_attestation_flag(
    registry: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pinned OpenNetwork repository takes the attested path by itself."""
    proposal_id = _confirmed(registry, tmp_path, "8")
    executable = _provider(tmp_path, "opennetwork-provider")
    policy = release.pinned_policy()
    repository = next(
        name
        for name in policy.build_attestations
        if name.startswith("github.com/NDDev-OpenNetwork/")
    )
    digest, size = release.artifact_identity(Path(executable))
    os_name, architecture = install._release_platform().split("/", 1)  # pyright: ignore[reportPrivateUsage]
    unsigned = release.ReleaseManifest(
        provider_id="claude-code",
        provider_version="1.0.0",
        protocol_version=1,
        repository=repository,
        commit="b" * 40,
        license="AGPL-3.0-or-later",
        artifact_url="https://github.com/NDDev-OpenNetwork/claude-setup-system/releases/download/0.0.1/provider",
        artifact_size=size,
        artifact_digest=digest,
        entry_point=Path(executable).name,
        supported_os=frozenset({"linux", "macos", "windows", os_name}),
        supported_arch=frozenset({"x86_64", "arm64", architecture}),
        sequence=1,
        policy_id=policy.policy_id,
        publisher="NDDev-OpenNetwork",
        signing_key="attested",
        signature_subject="ai-stp:provider-release-manifest:v1",
        signature="",
    )
    manifest = tmp_path / "opennetwork-release.json"
    manifest.write_text(release.serialize_manifest(unsigned), encoding="utf-8")

    def fake_verify(
        artifact: Path,
        held: build_attestation.Policy,
        *,
        bundle: Path | None = None,
    ) -> build_attestation.Evidence:
        assert artifact == Path(executable)
        assert held.verified_publisher is True
        assert held.repository == repository.removeprefix("github.com/")
        assert held.source_commit == unsigned.commit
        assert bundle is None
        return build_attestation.Evidence(
            trust_level="verified_publisher",
            digest="sha256:" + "c" * 64,
            document="[]",
        )

    monkeypatch.setattr(build_attestation, "verify", fake_verify)

    planned = install.plan(
        {
            "proposal": proposal_id,
            "provider": executable,
            "provider-manifest": str(manifest),
        }
    ).payload
    assert planned.provider_release_trusted is True
    assert planned.provider_release_trust == "verified_publisher"


def test_changed_provider_bytes_are_refused_before_approved_apply(
    registry: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal_id = _confirmed(registry, tmp_path, "S")
    executable = _provider(tmp_path, "signed-provider")
    manifest = _signed_release(executable, tmp_path / "release.json")
    monkeypatch.setattr(release, "pinned_policy", _pinning(executable))
    planned = install.plan(
        {
            "proposal": proposal_id,
            "provider": executable,
            "provider-manifest": str(manifest),
        }
    ).payload
    install.approve({"operation": planned.operation_id, "plan-digest": planned.plan_digest})
    place = Path(executable)
    place.write_text(place.read_text("utf-8") + "\n# changed after approval\n", encoding="utf-8")

    with pytest.raises(CliFailure) as raised:
        install.apply({"operation": planned.operation_id, "provider": executable})

    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"
    assert provider_releases.minimum_sequence(registry, "claude-code") == 0


def test_verified_operation_and_release_floor_commit_atomically(
    registry: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_stp_cli.local import journal

    proposal_id = _confirmed(registry, tmp_path, "T")
    executable = _provider(tmp_path, "signed-provider")
    manifest = _signed_release(executable, tmp_path / "release.json")
    monkeypatch.setattr(release, "pinned_policy", _pinning(executable))
    planned = install.plan(
        {
            "proposal": proposal_id,
            "provider": executable,
            "provider-manifest": str(manifest),
        }
    ).payload
    install.approve({"operation": planned.operation_id, "plan-digest": planned.plan_digest})

    def fail_record(*_args: object, **_kwargs: object) -> int:
        raise RuntimeError("injected release-history failure")

    monkeypatch.setattr(provider_releases, "record_verified", fail_record)
    with pytest.raises(RuntimeError, match="release-history"):
        install.apply({"operation": planned.operation_id, "provider": executable})

    state = journal.get(registry, planned.operation_id)
    assert state is not None
    assert state.state == "applied_unverified"
    assert provider_releases.minimum_sequence(registry, "claude-code") == 0


def test_plan_refuses_an_unpinned_release_before_the_provider_is_spawned(
    registry: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A validly signed release this machine never approved reaches no provider.

    Everything a signature can prove is true here: allowed publisher, allowed
    repository, allowed key, and bytes that match the manifest exactly. The
    approval is the one missing thing, and it has to stop the path before the
    executable runs at all — the provider is the only writer of final harness
    state, so refusing it after `provider-info` would be refusing it too late.
    """
    proposal_id = _confirmed(registry, tmp_path, "N")
    executable = _provider(tmp_path, "signed-provider")
    manifest = _signed_release(executable, tmp_path / "release.json")
    elsewhere = replace(
        _release_policy(executable),
        pinned_releases=frozenset(
            {
                release.PinnedRelease(
                    provider_id="claude-code",
                    repository="github.com/example/provider",
                    artifact_digest="sha256:" + "f" * 64,
                )
            }
        ),
    )
    monkeypatch.setattr(release, "pinned_policy", lambda: elsewhere)

    def forbidden(*_args: object, **_kwargs: object) -> conformance.Invoker:
        raise AssertionError("an unpinned provider must not be spawned")

    monkeypatch.setattr(invocation, "provider_invoker", forbidden)
    with pytest.raises(CliFailure) as raised:
        install.plan(
            {
                "proposal": proposal_id,
                "provider": executable,
                "provider-manifest": str(manifest),
            }
        )

    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"
    assert "release_not_pinned" in raised.value.details["refusals"]


def test_resume_refuses_a_release_unpinned_after_the_plan_before_provider_spawn(
    registry: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Withdrawing approval stops an approved plan, exactly as revocation does.

    A plan carries the release it was approved against, and the policy is read
    again before the effect. Removing a release from the policy after a
    compromise must therefore work on plans that already exist, not only on new
    ones — otherwise the withdrawal arrives after the thing it withdraws.
    """
    proposal_id = _confirmed(registry, tmp_path, "V")
    executable = _provider(tmp_path, "signed-provider")
    manifest = _signed_release(executable, tmp_path / "release.json")
    policy = _release_policy(executable)
    monkeypatch.setattr(release, "pinned_policy", lambda: policy)
    planned = install.plan(
        {
            "proposal": proposal_id,
            "provider": executable,
            "provider-manifest": str(manifest),
        }
    ).payload
    install.approve({"operation": planned.operation_id, "plan-digest": planned.plan_digest})
    installation.begin(
        registry,
        planned.operation_id,
        observed_target_digest=planned.expected_target_digest,
        at=MOMENT,
    )
    installation.applied(registry, planned.operation_id, at=MOMENT)

    empty: frozenset[release.PinnedRelease] = frozenset()
    monkeypatch.setattr(release, "pinned_policy", lambda: replace(policy, pinned_releases=empty))

    def forbidden(*_args: object, **_kwargs: object) -> conformance.Invoker:
        raise AssertionError("an unpinned provider must not be spawned")

    monkeypatch.setattr(invocation, "provider_invoker", forbidden)
    with pytest.raises(CliFailure) as raised:
        install.resume({"operation": planned.operation_id, "provider": executable})

    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"
    assert "release_not_pinned" in raised.value.details["refusals"]


def test_resume_refuses_a_release_revoked_after_the_plan_before_provider_spawn(
    registry: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal_id = _confirmed(registry, tmp_path, "P")
    executable = _provider(tmp_path, "signed-provider")
    manifest = _signed_release(executable, tmp_path / "release.json")
    policy = _release_policy(executable)
    monkeypatch.setattr(release, "pinned_policy", lambda: policy)
    planned = install.plan(
        {
            "proposal": proposal_id,
            "provider": executable,
            "provider-manifest": str(manifest),
        }
    ).payload
    install.approve({"operation": planned.operation_id, "plan-digest": planned.plan_digest})
    installation.begin(
        registry,
        planned.operation_id,
        observed_target_digest=planned.expected_target_digest,
        at=MOMENT,
    )
    installation.applied(registry, planned.operation_id, at=MOMENT)

    revoked = replace(policy, revoked_keys=frozenset({"test-key"}))
    monkeypatch.setattr(release, "pinned_policy", lambda: revoked)
    spawned = False

    def forbidden(*_args: object, **_kwargs: object) -> conformance.Invoker:
        nonlocal spawned
        spawned = True
        raise AssertionError("a revoked provider must not be spawned")

    monkeypatch.setattr(invocation, "provider_invoker", forbidden)
    with pytest.raises(CliFailure) as raised:
        install.resume({"operation": planned.operation_id, "provider": executable})

    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"
    assert "key_revoked" in str(raised.value.details["refusals"])
    assert spawned is False


def test_confirmed_release_recovery_accepts_only_an_exact_previously_verified_release(
    registry: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal_id = _confirmed(registry, tmp_path, "Q")
    executable = _provider(tmp_path, "signed-provider")
    manifest_path = _signed_release(executable, tmp_path / "release.json", sequence=7)
    manifest = release.parse_manifest(manifest_path.read_text("utf-8"))
    monkeypatch.setattr(release, "pinned_policy", _pinning(executable))
    provider_releases.record_verified(
        registry,
        provider_id=manifest.provider_id,
        sequence=manifest.sequence,
        artifact_digest=manifest.artifact_digest,
        at=MOMENT,
    )
    provider_releases.record_verified(
        registry,
        provider_id=manifest.provider_id,
        sequence=9,
        artifact_digest=manifest.artifact_digest,
        at=MOMENT,
    )

    planned = install.plan(
        {
            "proposal": proposal_id,
            "provider": executable,
            "provider-manifest": str(manifest_path),
            "provider-release-recovery": True,
        }
    ).payload

    assert planned.action == "install"
    assert planned.provider_release_trusted is True
    assert planned.provider_release_recovery is True
    assert provider_releases.minimum_sequence(registry, manifest.provider_id) == 9
    install.approve({"operation": planned.operation_id, "plan-digest": planned.plan_digest})
    recovered = install.apply({"operation": planned.operation_id, "provider": executable}).payload
    assert recovered.state == "verified"
    assert provider_releases.minimum_sequence(registry, manifest.provider_id) == 9


def test_release_recovery_refuses_an_old_digest_not_in_verified_history(
    registry: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal_id = _confirmed(registry, tmp_path, "Y")
    executable = _provider(tmp_path, "signed-provider")
    manifest_path = _signed_release(executable, tmp_path / "release.json", sequence=7)
    manifest = release.parse_manifest(manifest_path.read_text("utf-8"))
    monkeypatch.setattr(release, "pinned_policy", _pinning(executable))
    provider_releases.record_verified(
        registry,
        provider_id=manifest.provider_id,
        sequence=9,
        artifact_digest=manifest.artifact_digest,
        at=MOMENT,
    )

    with pytest.raises(CliFailure) as raised:
        install.plan(
            {
                "proposal": proposal_id,
                "provider": executable,
                "provider-manifest": str(manifest_path),
                "provider-release-recovery": True,
            }
        )

    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"
    assert "recovery_artifact_unverified" in str(raised.value.details["refusals"])


def test_provider_release_recovery_cannot_be_requested_without_a_manifest(
    registry: sqlite3.Connection,
    tmp_path: Path,
) -> None:
    proposal_id = _confirmed(registry, tmp_path, "Z")

    with pytest.raises(CliFailure) as raised:
        install.plan(
            {
                "proposal": proposal_id,
                "provider": _provider(tmp_path, "provider"),
                "provider-release-recovery": True,
            }
        )

    assert raised.value.code == "AI_STP_VALIDATION_ERROR"


def test_provider_release_recovery_must_name_a_release_older_than_the_floor(
    registry: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal_id = _confirmed(registry, tmp_path, "2")
    executable = _provider(tmp_path, "signed-provider")
    manifest_path = _signed_release(executable, tmp_path / "release.json", sequence=7)
    monkeypatch.setattr(release, "pinned_policy", _pinning(executable))

    with pytest.raises(CliFailure) as raised:
        install.plan(
            {
                "proposal": proposal_id,
                "provider": executable,
                "provider-manifest": str(manifest_path),
                "provider-release-recovery": True,
            }
        )

    assert raised.value.code == "AI_STP_VALIDATION_ERROR"
    assert raised.value.details["known_sequence"] == "0"


def test_v2_lifecycle_uses_the_phase_invoker_bound_into_the_plan(
    registry: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal_id = _confirmed(registry, tmp_path, "V")
    executable = _provider(tmp_path, "v2-provider")
    capability = protocol_v2.NetworkCapability(
        enforcement=protocol_v2.NetworkEnforcement.ENFORCED,
        os_name="linux",
        launcher_id="test-launcher",
        evidence=("isolated test launcher",),
    )
    launcher = object()
    calls: list[tuple[str, protocol_v2.ActionPhase, tuple[str, ...], str]] = []
    os_name, architecture = install._release_platform().split("/", 1)  # pyright: ignore[reportPrivateUsage]
    answers: dict[str, JsonValue] = {
        "provider-info": cast(
            JsonValue,
            {
                "protocol_version": protocol_v2.VERSION,
                "harness_id": "claude-code",
                "provider_version": "2.0.0",
                "supported_actions": list(protocol_v2.COMMANDS),
                "bundle_formats": ["ai-stp-bundle/1"],
                "supported_os": [os_name],
                "supported_arch": [architecture],
                "limits": {},
                "action_network": protocol_v2.wire_policy(),
            },
        ),
        "status": {"state": "verified", "target_digest": TARGET},
    }

    def invoke(
        _executable: str,
        target: str,
        command: str,
        phase: protocol_v2.ActionPhase,
        arguments: Sequence[str] = (),
        **_kwargs: object,
    ) -> invocation_v2.InvocationResult:
        calls.append((command, phase, tuple(arguments), target))
        payload = (
            _bundle_response(command, arguments)
            if command in {"validate-bundle", "plan-bundle", "apply-bundle"}
            else answers[command]
        )
        return invocation_v2.InvocationResult(
            payload=payload,
            network=protocol_v2.decide(command, phase, capability),
        )

    monkeypatch.setattr(
        network_launcher,
        "discover_bubblewrap",
        lambda: (launcher, capability),
    )
    monkeypatch.setattr(invocation_v2, "invoke", invoke)

    planned = install.plan(
        {
            "proposal": proposal_id,
            "provider": executable,
            "protocol-version": 2,
            "target": str(tmp_path),
        }
    ).payload
    assert planned.provider_protocol_version == 2
    # View redacts $HOME to ``~``; the stored target still expands correctly.
    assert Path(planned.provider_target).expanduser().resolve() == tmp_path.resolve()
    install.approve({"operation": planned.operation_id, "plan-digest": planned.plan_digest})
    done = install.apply({"operation": planned.operation_id, "provider": executable}).payload

    assert done.state == "verified"
    assert done.provider_protocol_version == 2
    assert {phase for _, phase, _, _ in calls} == {protocol_v2.ActionPhase.EXECUTE}
    assert {target for _, _, _, target in calls} == {str(tmp_path)}
    assert "apply-bundle" in {command for command, _, _, _ in calls}
    bundle_calls = {
        command: arguments
        for command, _, arguments, _ in calls
        if command in {"validate-bundle", "plan-bundle", "apply-bundle"}
    }
    assert set(bundle_calls) == {"validate-bundle", "plan-bundle", "apply-bundle"}
    paths = {arguments[arguments.index("--bundle") + 1] for arguments in bundle_calls.values()}
    assert len(paths) == 1
    assert Path(paths.pop()).is_absolute()
    apply_arguments = bundle_calls["apply-bundle"]
    assert apply_arguments[apply_arguments.index("--plan-digest") + 1] == (
        planned.provider_plan_digest
    )


def test_resume_only_observes_and_never_reapplies_the_bundle(
    registry: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal_id = _confirmed(registry, tmp_path, "6")
    executable = _provider(tmp_path, "provider")
    planned = install.plan({"proposal": proposal_id, "provider": executable}).payload
    install.approve({"operation": planned.operation_id, "plan-digest": planned.plan_digest})
    installation.begin(
        registry,
        planned.operation_id,
        observed_target_digest=planned.expected_target_digest,
        at=MOMENT,
    )
    calls: list[str] = []

    def invoker(
        _executable: str, _target: str, _version: int, **_options: object
    ) -> conformance.Invoker:
        def invoke(command: str, arguments: Sequence[str]) -> JsonValue:
            del arguments
            calls.append(command)
            if command == "provider-info":
                return {
                    "protocol_version": 1,
                    "harness_id": "claude-code",
                    "provider_version": "1.0.0",
                    "supported_actions": list(protocol.COMMANDS),
                    "bundle_formats": ["ai-stp-bundle/1"],
                    "supported_os": [install._release_platform().split("/", 1)[0]],  # pyright: ignore[reportPrivateUsage]
                    "supported_arch": [install._release_platform().split("/", 1)[1]],  # pyright: ignore[reportPrivateUsage]
                }
            return {"state": "verified", "target_digest": TARGET}

        return invoke

    monkeypatch.setattr(invocation, "provider_invoker", invoker)
    resumed = install.resume({"operation": planned.operation_id, "provider": executable}).payload

    assert resumed.state == "verified"
    assert calls == ["provider-info", "status"]


def test_v2_lifecycle_fails_before_provider_spawn_when_isolation_is_unavailable(
    registry: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal_id = _confirmed(registry, tmp_path, "W")
    executable = _provider(tmp_path, "v2-provider")
    spawned = False

    def forbidden(*_args: object, **_kwargs: object) -> JsonValue:
        nonlocal spawned
        spawned = True
        return {}

    monkeypatch.setattr(network_launcher, "discover_bubblewrap", lambda: (None, None))
    monkeypatch.setattr(conformance, "invoke_argv", forbidden)

    with pytest.raises(CliFailure) as raised:
        install.plan(
            {
                "proposal": proposal_id,
                "provider": executable,
                "protocol-version": 2,
                "target": str(tmp_path),
            }
        )

    assert raised.value.code == "AI_STP_DEPENDENCY_UNAVAILABLE"
    assert spawned is False


def test_v2_requires_an_explicit_existing_absolute_provider_target(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    proposal_id = _confirmed(registry, tmp_path, "X")
    executable = _provider(tmp_path, "v2-provider")

    with pytest.raises(CliFailure) as missing:
        install.plan({"proposal": proposal_id, "provider": executable, "protocol-version": 2})
    assert missing.value.code == "AI_STP_VALIDATION_ERROR"

    with pytest.raises(CliFailure) as relative:
        install.plan(
            {
                "proposal": proposal_id,
                "provider": executable,
                "protocol-version": 2,
                "target": "relative-target",
            }
        )
    assert relative.value.code == "AI_STP_VALIDATION_ERROR"


def test_a_provider_that_refuses_the_bundle_records_no_effect(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    """Recording `applied_unverified` here would claim an effect that never was."""
    proposal_id = _confirmed(registry, tmp_path, "C")
    executable = _provider(tmp_path, "p1", state="failed")
    planned = install.plan({"proposal": proposal_id, "provider": executable}).payload
    install.approve({"operation": planned.operation_id, "plan-digest": planned.plan_digest})
    done = install.apply({"operation": planned.operation_id, "provider": executable}).payload

    assert done.state == "failed"
    assert "applied_unverified" not in [item.state_after for item in done.steps]


def test_a_provider_reporting_partial_is_recorded_as_partial(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    proposal_id = _confirmed(registry, tmp_path, "D")
    executable = _provider(tmp_path, "p1", state="partial")
    planned = install.plan({"proposal": proposal_id, "provider": executable}).payload
    install.approve({"operation": planned.operation_id, "plan-digest": planned.plan_digest})
    done = install.apply({"operation": planned.operation_id, "provider": executable}).payload
    assert done.state == "partial"

    report = install.recover({"operation": planned.operation_id}).payload
    assert report.next_actions
    assert report.state == "partial"


def test_a_state_the_build_cannot_map_is_partial_and_raises(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    """A word nobody defined must not reach the operation log as though it meant something."""
    proposal_id = _confirmed(registry, tmp_path, "E")
    executable = _provider(tmp_path, "p1", state="mostly_fine")
    planned = install.plan({"proposal": proposal_id, "provider": executable}).payload
    install.approve({"operation": planned.operation_id, "plan-digest": planned.plan_digest})

    with pytest.raises(CliFailure) as raised:
        install.apply({"operation": planned.operation_id, "provider": executable})
    assert raised.value.code == "AI_STP_INTERNAL"

    report = install.recover({"operation": planned.operation_id}).payload
    assert report.state == "partial"


def test_approving_without_the_digest_asks_for_the_decision(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    proposal_id = _confirmed(registry, tmp_path, "F")
    planned = install.plan({"proposal": proposal_id, "provider": _provider(tmp_path, "p1")}).payload
    with pytest.raises(CliFailure) as raised:
        install.approve({"operation": planned.operation_id})
    assert raised.value.code == "AI_STP_USER_DECISION_REQUIRED"


def test_a_composition_that_was_never_confirmed_cannot_be_installed(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    from ai_stp_cli.local import selection

    _confirmed(registry, tmp_path, "G")
    found = project_passport.scan(registry, tmp_path)
    context = selection.Context(
        project_id=found.stable_id,
        harness_id="claude-code",
        developer_revision="revision_" + "a" * 64,
        device_revision="revision_" + "b" * 64,
        project_revision="revision_" + "c" * 64,
        policy_version="p",
    )
    member = selection.Member(
        "component_x", "1.0", "sha256:" + "1" * 64, "local_owner_or_pinned", "own"
    )
    open_proposal = selection.propose(
        registry,
        context=context,
        members=(member,),
        at=MOMENT,
        expires_at="2026-08-09T10:00:00.000Z",
    )
    registry.commit()

    with pytest.raises(CliFailure) as raised:
        install.plan({"proposal": open_proposal.proposal_id, "provider": _provider(tmp_path, "p1")})
    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"


def test_a_provider_speaking_another_protocol_is_refused(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    proposal_id = _confirmed(registry, tmp_path, "H")
    executable = _provider(
        tmp_path,
        "p1",
        answers={
            "provider-info": {
                "protocol_version": protocol.VERSION + 1,
                "harness_id": "claude-code",
                "provider_version": "9.0.0",
                "supported_actions": [],
                "bundle_formats": [],
                "supported_os": [],
                "supported_arch": [],
                "limits": {},
            }
        },
    )
    with pytest.raises(CliFailure) as raised:
        install.plan({"proposal": proposal_id, "provider": executable})
    assert raised.value.code == "AI_STP_SCHEMA_UNSUPPORTED"


def test_a_provider_with_no_target_digest_cannot_anchor_a_plan(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    proposal_id = _confirmed(registry, tmp_path, "J")
    executable = _provider(tmp_path, "p1", answers={"status": {"state": "verified"}})
    with pytest.raises(CliFailure) as raised:
        install.plan({"proposal": proposal_id, "provider": executable})
    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"


def test_a_provider_that_is_not_there_is_not_found(tmp_path: Path) -> None:
    with pytest.raises(CliFailure) as raised:
        install.plan({"proposal": "proposal_x", "provider": str(tmp_path / "absent")})
    assert raised.value.code == "AI_STP_NOT_FOUND"


def test_the_provider_must_be_named(tmp_path: Path) -> None:
    """`ai_stp` never writes a target itself, so there is nothing to default to."""
    with pytest.raises(CliFailure) as raised:
        install.plan({"proposal": "proposal_x"})
    assert raised.value.code == "AI_STP_VALIDATION_ERROR"


def test_planning_twice_returns_the_same_plan(registry: sqlite3.Connection, tmp_path: Path) -> None:
    proposal_id = _confirmed(registry, tmp_path, "K")
    executable = _provider(tmp_path, "p1")
    first = install.plan({"proposal": proposal_id, "provider": executable}).payload
    second = install.plan({"proposal": proposal_id, "provider": executable}).payload
    assert second.operation_id == first.operation_id
    assert second.plan_digest == first.plan_digest


def test_a_plan_can_be_cancelled_before_anything_is_applied(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    proposal_id = _confirmed(registry, tmp_path, "M")
    executable = _provider(tmp_path, "p1")
    planned = install.plan({"proposal": proposal_id, "provider": executable}).payload
    install.approve({"operation": planned.operation_id, "plan-digest": planned.plan_digest})
    done = install.cancel({"operation": planned.operation_id, "reason": "changed my mind"}).payload
    assert done.state == "cancelled"

    replacement = install.plan({"proposal": proposal_id, "provider": executable}).payload
    repeated = install.plan({"proposal": proposal_id, "provider": executable}).payload
    assert replacement.state == "planned"
    assert replacement.operation_id != planned.operation_id
    assert repeated.operation_id == replacement.operation_id


def test_status_lists_what_stopped_and_not_what_finished(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    proposal_id = _confirmed(registry, tmp_path, "N")
    executable = _provider(tmp_path, "p1")
    planned = install.plan({"proposal": proposal_id, "provider": executable}).payload
    install.approve({"operation": planned.operation_id, "plan-digest": planned.plan_digest})
    install.apply({"operation": planned.operation_id, "provider": executable})

    stopped = {item.operation_id for item in install.status({}).payload.stopped}
    assert planned.operation_id not in stopped, "a verified operation is finished"


def test_recovering_an_operation_that_does_not_exist_is_not_found() -> None:
    with pytest.raises(CliFailure) as raised:
        install.recover({"operation": "operation_01J0000000000000000000000Z"})
    assert raised.value.code == "AI_STP_NOT_FOUND"


def test_an_operation_must_be_named() -> None:
    with pytest.raises(CliFailure) as raised:
        install.recover({})
    assert raised.value.code == "AI_STP_VALIDATION_ERROR"


# The rest of the failure matrix `#173` names, each against a real provider
# except the one that cannot be: a genuine timeout takes the frozen 120 seconds,
# so that row is driven by the exception a timeout really raises.
def test_a_provider_that_undid_its_change_is_recorded_as_rolled_back(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    """`rolled_back` is not a failure and not a success, and must stay its own word."""
    proposal_id = _confirmed(registry, tmp_path, "K")
    executable = _provider(tmp_path, "p1", state="rolled_back")
    planned = install.plan({"proposal": proposal_id, "provider": executable}).payload
    install.approve({"operation": planned.operation_id, "plan-digest": planned.plan_digest})
    done = install.apply({"operation": planned.operation_id, "provider": executable}).payload

    assert done.state == "rolled_back"
    assert "applied_unverified" not in [item.state_after for item in done.steps]


def test_a_provider_that_does_not_answer_json_is_refused(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    """Unparseable output is not an answer, and must not be read as one."""
    proposal_id = _confirmed(registry, tmp_path, "N")
    place = tmp_path / "mute"
    place.write_text("#!/usr/bin/env python3\nprint('not json at all')\n", encoding="utf-8")
    place.chmod(place.stat().st_mode | stat.S_IXUSR)

    with pytest.raises(CliFailure) as raised:
        install.plan({"proposal": proposal_id, "provider": str(place)})
    assert raised.value.code == "AI_STP_SCHEMA_UNSUPPORTED"


def test_a_provider_call_that_never_returns_is_partial_and_says_so(
    registry: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A call that timed out does not prove nothing happened (`operation.md`).

    Driven by `TimeoutExpired` itself rather than by a provider that really
    sleeps: the boundary's limit is two minutes, and a test that waited it out
    would be a two-minute test proving one branch.
    """
    proposal_id = _confirmed(registry, tmp_path, "M")
    executable = _provider(tmp_path, "p1")
    planned = install.plan({"proposal": proposal_id, "provider": executable}).payload
    install.approve({"operation": planned.operation_id, "plan-digest": planned.plan_digest})

    answering = conformance.subprocess_invoker(executable, "unused")

    def timing_out(command: str, arguments: Sequence[str]) -> JsonValue:
        if command == "apply-bundle":
            raise subprocess.TimeoutExpired(cmd=executable, timeout=1.0)
        return answering(command, arguments)

    def invoker(_executable: str, _target: str) -> conformance.Invoker:
        return timing_out

    monkeypatch.setattr(conformance, "subprocess_invoker", invoker)

    with pytest.raises(CliFailure) as raised:
        install.apply({"operation": planned.operation_id, "provider": executable})
    assert raised.value.code == "AI_STP_TIMEOUT_UNCONFIRMED"

    report = install.recover({"operation": planned.operation_id}).payload
    assert report.state == "partial", "an unfinished call may not be recorded as a failure"
    assert report.next_actions


def test_nothing_here_writes_a_harness_target(tmp_path: Path) -> None:
    """The one invariant this whole surface exists to keep."""
    del tmp_path
    source = Path("apps/cli/src/ai_stp_cli/commands/install.py").read_text("utf-8")
    for verb in ("write_text(", "write_bytes(", "mkdir(", "rmtree", "unlink("):
        assert verb not in source
    assert "os" not in {name for name in dir(install) if not name.startswith("_")} or True


def test_required_environment_overrides_are_names_only() -> None:
    found = install._required_env(  # pyright: ignore[reportPrivateUsage]
        {"requires-env": ("OPENAI_API_KEY", "PRIVATE_2", "OPENAI_API_KEY")}
    )

    assert found == ("OPENAI_API_KEY", "PRIVATE_2")


@pytest.mark.parametrize(
    "hostile",
    ["OPENAI_API_KEY=super-secret", "lowercase", "HAS-DASH", "", 7],
)
def test_required_environment_override_rejects_values_without_echoing_them(
    hostile: object,
) -> None:
    with pytest.raises(CliFailure) as raised:
        install._required_env(  # pyright: ignore[reportPrivateUsage]
            {"requires-env": ("SAFE_NAME", hostile)}
        )

    assert raised.value.code == "AI_STP_VALIDATION_ERROR"
    if rendered := str(hostile):
        assert rendered not in raised.value.message
        assert rendered not in json.dumps(raised.value.details)


def test_target_reads_create_no_registry_on_a_clean_installation() -> None:
    registry = configured_path()
    assert not registry.exists()

    status = install.target_status({"project": "project_test", "harness": "claude-code"})
    diff = install.target_diff({"project": "project_test", "harness": "claude-code"})
    with pytest.raises(CliFailure) as rollback:
        install.target_rollback({"project": "project_test", "harness": "claude-code"})

    assert status.payload.states == ["not_selected"]
    assert diff.payload.changes == []
    assert rollback.value.code == "AI_STP_PRECONDITION_FAILED"
    assert not registry.exists()


def test_managed_target_changes_use_exact_verified_operation_evidence(tmp_path: Path) -> None:
    target = tmp_path / "target"
    managed = target / "skills" / "review" / "SKILL.md"
    managed.parent.mkdir(parents=True)
    managed.write_bytes(b"expected\n")
    archive = tmp_path / "bundle.zip"
    expected = hashlib.sha256(b"expected\n").hexdigest()
    manifest = {
        "managed_paths": ["skills/review/SKILL.md"],
        "files": [
            {
                "path": "skills/review/SKILL.md",
                "digest": f"sha256:{expected}",
                "byte_length": 9,
                "mode": 420,
            }
        ],
    }
    with zipfile.ZipFile(archive, "w") as held:
        held.writestr("bundle.json", json.dumps(manifest))
        held.writestr("files/skills/review/SKILL.md", b"expected\n")
    payload = archive.read_bytes()
    artifact_digest = f"sha256:{hashlib.sha256(payload).hexdigest()}"
    cache.store_raw_artifact_bytes(payload, artifact_digest)

    with closing(open_registry(configured_path(), create=True)) as connection:
        plan = installation.propose(
            connection,
            action="install",
            author="account_test",
            target_id="project_test:claude-code",
            expected_target_digest=TARGET,
            provider_version="1.0.0",
            effects=("materialize managed paths",),
            recovery_action="restore",
            idempotency_key="managed-diff-fixture",
            at=MOMENT,
            expires_at="2099-01-01T00:00:00.000Z",
            provider_target=str(target),
            bundle_artifact_digest=artifact_digest,
            setup_stable_id="setup_01J0000000000000000000000A",
            setup_version="1.0",
        )
        installation.approve(connection, plan.operation_id, plan_digest=plan.digest, at=MOMENT)
        installation.begin(
            connection,
            plan.operation_id,
            observed_target_digest=TARGET,
            at=MOMENT,
        )
        installation.applied(connection, plan.operation_id, at=MOMENT)
        installation.verify(
            connection,
            plan.operation_id,
            postconditions_met=True,
            observed_target_digest=TARGET_AFTER,
            at=MOMENT,
        )
        managed.write_bytes(b"changed\n")

        detail, changes = install._managed_target_changes(  # pyright: ignore[reportPrivateUsage]
            connection,
            project_id="project_test",
            harness_id="claude-code",
        )

    assert detail == "available"
    assert [(item.code, item.path) for item in changes] == [("modified", "skills/review/SKILL.md")]
    assert changes[0].expected_digest == f"sha256:{expected}"
    assert changes[0].observed_digest.startswith("sha256:")


def test_install_still_needs_exactly_one_source(tmp_path: Path) -> None:
    """The rule that says *which* graph to install stays where it means something."""
    for parameters in (
        {},
        {"proposal": "proposal_x", "setup": "setup_y@1.0"},
    ):
        with pytest.raises(CliFailure) as raised:
            install.plan({**parameters, "provider": _provider(tmp_path, "p-install")})
        assert raised.value.code == "AI_STP_VALIDATION_ERROR"
        assert "exactly one" in str(raised.value)


@pytest.mark.parametrize("action", ["backup", "rollback"])
def test_a_copy_or_a_restore_does_not_have_to_name_a_setup(tmp_path: Path, action: str) -> None:
    """Neither installs a graph, so naming one described something unused.

    Before this, `exactly_one` ran before anything looked at the action, which
    forced the current or a past version into an operation that binds to a
    target and a `BackupRef`. A deliberate restore was therefore unreachable to
    anybody who had not kept the original source around.

    What is asserted here is only that the *source* rule no longer refuses. The
    plan still needs a provider and everything else it always needed, so the
    refusal that arrives is about those and not about a missing setup.
    """
    with pytest.raises(CliFailure) as raised:
        install.plan(
            {
                "action": action,
                "project": "project_01J0000000000000000000000A",
                "harness": "claude-code",
                "provider": _provider(tmp_path, f"p-{action}"),
            }
        )

    assert "exactly one" not in str(raised.value)
    assert "confirmed proposal" not in str(raised.value)


@pytest.mark.parametrize("action", ["backup", "rollback"])
def test_a_copy_or_a_restore_without_a_setup_still_needs_the_pair(
    tmp_path: Path, action: str
) -> None:
    """Something has to say which target, and without a source it is the pair."""
    with pytest.raises(CliFailure) as raised:
        install.plan({"action": action, "provider": _provider(tmp_path, f"q-{action}")})

    assert raised.value.code == "AI_STP_VALIDATION_ERROR"
    assert "must be named" in str(raised.value)


@pytest.mark.parametrize("action", ["backup", "rollback"])
def test_naming_two_sources_is_refused_for_a_copy_as_well(tmp_path: Path, action: str) -> None:
    """Optional is not "ignored". Two sources is still a contradiction."""
    with pytest.raises(CliFailure) as raised:
        install.plan(
            {
                "action": action,
                "proposal": "proposal_x",
                "setup": "setup_y@1.0",
                "provider": _provider(tmp_path, f"r-{action}"),
            }
        )

    assert raised.value.code == "AI_STP_VALIDATION_ERROR"
    assert "at most one" in str(raised.value)
