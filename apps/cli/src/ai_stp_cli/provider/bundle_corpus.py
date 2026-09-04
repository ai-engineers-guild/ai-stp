"""Literal HarnessBundle artifacts for provider conformance.

The corpus is materialized for one run and removed afterwards.  Providers see
the same absolute, content-addressed ZIP paths and immutable binding fields as
the installation lifecycle; no JSON-shaped stand-in crosses the process
boundary.
"""

from __future__ import annotations

import hashlib
import io
import json
import stat
import tempfile
import warnings
import zipfile
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

from ai_stp_cli.local import bundle
from ai_stp_cli.provider import bundle_protocol
from ai_stp_foundation.canonical import JsonValue, canonize
from ai_stp_foundation.digests import digest_canonical
from ai_stp_passports import SetupVersionPassport, seal_envelope


@dataclass(frozen=True)
class ArtifactCase:
    """One malformed literal artifact and the exact refusal it requires."""

    name: str
    refusal: str
    binding: bundle_protocol.Binding


@dataclass(frozen=True)
class Corpus:
    """A valid planning artifact plus the closed malicious corpus."""

    valid: bundle_protocol.Binding
    malicious: tuple[ArtifactCase, ...]


CASE_REASONS: Final[tuple[tuple[str, str], ...]] = (
    ("path_escapes_target", "path_escapes_target"),
    ("path_not_relative", "path_not_relative"),
    ("path_duplicate", "path_duplicate"),
    ("symbolic_link_not_allowed", "link_not_allowed"),
    ("hard_link_not_allowed", "link_not_allowed"),
    ("special_file_not_allowed", "special_file_not_allowed"),
    ("limit_exceeded", "limit_exceeded"),
    ("unknown_native_surface", "unknown_native_surface"),
    ("digest_mismatch", "digest_mismatch"),
    ("unsupported_protocol_version", "unsupported_protocol_version"),
)

#: v3 refuses two classes v2 has no vocabulary for, so the corpus that drives a
#: v3 provider is larger. Keeping one shared list made the v2 run demand a
#: refusal its own protocol cannot name.
CASE_REASONS_V3: Final[tuple[tuple[str, str], ...]] = (
    *CASE_REASONS,
    ("unsupported_bundle_format", "unsupported_bundle_format"),
    ("unsupported_component_kind", "unsupported_component_kind"),
)
_COMPOSITION: Final[dict[str, JsonValue]] = {"complete": True}
_CONVERSION: Final[dict[str, JsonValue]] = {"complete": True}


@contextmanager
def materialized(*, protocol_version: int, harness_id: str) -> Generator[Corpus]:
    """Create exact corpus bytes for the lifetime of one conformance run."""
    with tempfile.TemporaryDirectory(prefix="ai-stp-provider-conformance-") as held:
        root = Path(held)
        base = _base_manifest(protocol_version, harness_id)
        valid = _store(root, "valid", base, (("files/config.md", b"safe\n", _regular()),))
        cases = tuple(
            ArtifactCase(name, refusal, _malicious(root, base, name, protocol_version))
            for name, refusal in CASE_REASONS
        )
        yield Corpus(valid=valid, malicious=cases)


@contextmanager
def materialized_v3(
    *,
    harness_id: str,
    component_kind: str,
    native_surface: str,
    target_path: str,
    profile_id: str,
    profile_digest: str,
    target_scope: str,
) -> Generator[Corpus]:
    """Create a semantically valid v3 literal for one declared native route."""
    with tempfile.TemporaryDirectory(prefix="ai-stp-provider-conformance-v3-") as held:
        root = Path(held)
        passport = _passport(harness_id)
        component = cast(list[dict[str, JsonValue]], passport["components"])[0]
        stable_id = str(component["stable_id"])
        composition: dict[str, JsonValue] = {
            "complete": True,
            "chosen": [
                {"stable_id": stable_id, "version": str(component["version"]), "lane": "main"}
            ],
            "operations": [],
        }
        conversion: dict[str, JsonValue] = {
            "complete": True,
            "entries": [
                {
                    "stable_id": stable_id,
                    "component_type": component_kind,
                    "native_surface": native_surface,
                    "state": "complete",
                    "losses": [],
                }
            ],
        }
        payload = b"safe provider v3 conformance literal\n"
        setup_digest = digest_canonical(bundle.PASSPORT_DOMAIN, passport)
        passport_digest = "sha256:" + "4" * 64
        projection_digest = "sha256:" + "5" * 64
        compiled = bundle.compile_bundle(
            (bundle.Source(target_path, payload, stable_id),),
            setup_stable_id=str(passport["stable_id"]),
            setup_version="1.0",
            setup_digest=setup_digest,
            harness_id=harness_id,
            declared_paths=frozenset({target_path}),
            setup_passport=passport,
            composition_report=composition,
            conversion_report=conversion,
            input_digest="sha256:" + "3" * 64,
            target_scope=target_scope,
            bundle_format=bundle.BUNDLE_FORMAT_V2,
            projection_profile=bundle.ProjectionProfileBinding(
                profile_id=profile_id,
                profile_digest=profile_digest,
                target_scope=target_scope,
            ),
            adaptation_bindings=(
                bundle.ComponentAdaptationBinding(
                    stable_id=stable_id,
                    version=str(component["version"]),
                    passport_digest=passport_digest,
                    adaptation_id="adaptation_" + "6" * 64,
                    projection_artifact_digest=projection_digest,
                    projection_artifact_size=len(payload),
                    provider_component_kind=component_kind,
                    projection_kind="native_files",
                    member_paths=(target_path,),
                ),
            ),
        )
        if not compiled.compiled:  # pragma: no cover - construction is constant
            raise RuntimeError("the v3 conformance bundle did not compile")
        manifest = cast(dict[str, JsonValue], json.loads(json.dumps(compiled.manifest)))
        manifest = _with_digest(manifest)
        valid = _store(root, "valid", manifest, ((f"files/{target_path}", payload, _regular()),))
        cases = tuple(
            ArtifactCase(
                name,
                "unsupported_native_surface" if name == "unknown_native_surface" else refusal,
                _malicious(
                    root,
                    manifest,
                    name,
                    bundle.PROTOCOL_VERSION,
                    native_consistent=True,
                ),
            )
            for name, refusal in CASE_REASONS_V3
        )
        yield Corpus(valid=valid, malicious=cases)


def _base_manifest(protocol_version: int, harness_id: str) -> dict[str, JsonValue]:
    passport = _passport(harness_id)
    setup_digest = digest_canonical(bundle.PASSPORT_DOMAIN, passport)
    compiled = bundle.compile_bundle(
        (bundle.Source("config.md", b"safe\n", "conformance"),),
        setup_stable_id=str(passport["stable_id"]),
        setup_version="1.0",
        setup_digest=setup_digest,
        harness_id=harness_id,
        declared_paths=frozenset({"config.md"}),
        setup_passport=passport,
        composition_report=_COMPOSITION,
        conversion_report=_CONVERSION,
        input_digest="sha256:" + "1" * 64,
    )
    if not compiled.compiled:  # pragma: no cover - construction is constant
        raise RuntimeError("the built-in conformance bundle did not compile")
    manifest = cast(dict[str, JsonValue], json.loads(json.dumps(compiled.manifest)))
    manifest["protocol_version"] = protocol_version
    return _with_digest(manifest)


def _passport(harness_id: str) -> dict[str, JsonValue]:
    """Build one deterministic, schema-valid SetupVersionPassport fixture."""
    data: dict[str, JsonValue] = {
        "kind": "setup",
        "stable_id": "setup_00000000000000000000000000",
        "parent_revision_ids": [],
        "owner_id": "account_00000000000000000000000000",
        "created_at": "2026-01-01T00:00:00.000Z",
        "visibility": "public",
        "name": "provider-conformance",
        "description": "Literal provider conformance fixture.",
        "version": "1.0",
        "tags": ["conformance"],
        "artifact": {"digest": "sha256:" + "0" * 64, "size_bytes": 0},
        "harness_id": harness_id,
        "license": {"spdx_id": "MIT", "redistribution_allowed": True},
        "purpose": "Validate provider safety and exact bundle binding.",
        "target_role": "provider-conformance",
        # A conformance bundle is not published on the posture axis.
        "posture": None,
        "components": [
            {
                "stable_id": "component_00000000000000000000000000",
                "version": "1.0",
                "passport_digest": "sha256:" + "1" * 64,
            }
        ],
        "supported_os": ["linux", "macos"],
        "supported_arch": ["x86_64", "arm64"],
    }
    sealed = seal_envelope(data)
    passport = SetupVersionPassport.model_validate(sealed.model_dump(mode="json"))
    return cast(dict[str, JsonValue], passport.model_dump(mode="json"))


def _malicious(
    root: Path,
    base: dict[str, JsonValue],
    name: str,
    protocol_version: int,
    *,
    native_consistent: bool = False,
) -> bundle_protocol.Binding:
    manifest = cast(dict[str, JsonValue], json.loads(json.dumps(base)))
    content = b"hostile\n"
    digest = "sha256:" + hashlib.sha256(content).hexdigest()
    base_files = manifest.get("files")
    base_record = (
        cast(dict[str, JsonValue], cast(list[JsonValue], base_files)[0])
        if native_consistent
        and isinstance(base_files, list)
        and base_files
        and isinstance(base_files[0], dict)
        else {}
    )
    record: dict[str, JsonValue] = {
        "path": str(base_record.get("path", "hostile.md")),
        "digest": digest,
        "byte_length": len(content),
        "mode": bundle.MODE_FILE,
        "owner": str(base_record.get("owner", "conformance")),
    }
    members: list[tuple[str, bytes, int]] = []

    if name == "path_escapes_target":
        record["path"] = "../outside.md"
        members.append(("files/../outside.md", content, _regular()))
    elif name == "path_not_relative":
        record["path"] = "/etc/passwd"
        members.append(("/etc/passwd", content, _regular()))
    elif name == "path_duplicate":
        manifest["files"] = [record, dict(record)]
        manifest["managed_paths"] = [record["path"], record["path"]]
        member = f"files/{record['path']}"
        members.extend(((member, content, _regular()), (member, content, _regular())))
        return _store(root, name, _with_digest(manifest), tuple(members))
    elif name == "symbolic_link_not_allowed":
        record["kind"] = "symlink"
        members.append((f"files/{record['path']}", b"outside", _symlink()))
    elif name == "hard_link_not_allowed":
        # ZIP has no portable hard-link member type.  The hostile manifest
        # therefore carries the forbidden kind explicitly; a provider must not
        # reinterpret it as an ordinary file merely because the container can.
        record["kind"] = "hardlink"
        members.append((f"files/{record['path']}", content, _regular()))
    elif name == "special_file_not_allowed":
        record["kind"] = "special"
        members.append((f"files/{record['path']}", content, _fifo()))
    elif name == "limit_exceeded":
        record["byte_length"] = bundle.MAX_FILE_BYTES + 1
        members.append((f"files/{record['path']}", content, _regular()))
    elif name == "unknown_native_surface":
        if native_consistent:
            record["path"] = "unknown-native-surface/hostile.md"
        else:
            record["surface"] = "unknown"
        members.append((f"files/{record['path']}", content, _regular()))
    elif name == "digest_mismatch":
        record["digest"] = "sha256:" + "0" * 64
        members.append((f"files/{record['path']}", content, _regular()))
    elif name == "unsupported_protocol_version":
        manifest["protocol_version"] = protocol_version + 1
        members.append((f"files/{record['path']}", content, _regular()))
    elif name == "unsupported_component_kind":
        # The kind is declared by the conversion report, not by the manifest or
        # the setup passport — the passport carries component references and no
        # kinds at all. So the hostile document is that report, and its record
        # under `documents` has to be recomputed with it: leaving the old digest
        # would make the provider refuse a digest mismatch, which is a different
        # refusal and would pass this case for the wrong reason.
        conversion: dict[str, JsonValue] = {
            "complete": True,
            "entries": [
                {
                    "stable_id": "component_00000000000000000000000000",
                    "component_type": "quantum-manifest",
                    "native_surface": str(record["path"]),
                    "state": "complete",
                    "losses": [],
                }
            ],
        }
        manifest["conversion_report"] = conversion
        rendered = canonize(cast(JsonValue, conversion))
        documents = dict(cast(dict[str, JsonValue], manifest["documents"]))
        documents["conversion_report"] = {
            "path": "conversion-report.json",
            "digest": "sha256:" + hashlib.sha256(rendered).hexdigest(),
            "byte_length": len(rendered),
        }
        manifest["documents"] = cast(JsonValue, documents)
        members.append((f"files/{record['path']}", content, _regular()))
    elif name == "unsupported_bundle_format":
        # A container this provider was never told how to read. The bytes stay
        # a well-formed archive on purpose: refusing it has to come from the
        # declared format, not from the parser failing to open the file.
        manifest["bundle_format"] = "ai-stp-bundle/999"
        members.append((f"files/{record['path']}", content, _regular()))
    else:  # pragma: no cover - closed constant above
        raise KeyError(name)

    if not members:
        members.append((f"files/{record['path']}", content, _regular()))

    if name in {"path_escapes_target", "path_not_relative", "unknown_native_surface"}:
        raw_bindings = manifest.get("component_adaptations")
        if isinstance(raw_bindings, list) and raw_bindings and isinstance(raw_bindings[0], dict):
            binding = cast(dict[str, JsonValue], raw_bindings[0])
            binding["member_paths"] = [record["path"]]
    manifest["files"] = [record]
    manifest["managed_paths"] = [record["path"]]
    return _store(root, name, _with_digest(manifest), tuple(members))


def _with_digest(manifest: dict[str, JsonValue]) -> dict[str, JsonValue]:
    identity = {name: value for name, value in manifest.items() if name != "bundle_digest"}
    return {**identity, "bundle_digest": digest_canonical(bundle.BUNDLE_DOMAIN, identity)}


def _store(
    root: Path,
    label: str,
    manifest: dict[str, JsonValue],
    files: tuple[tuple[str, bytes, int], ...],
) -> bundle_protocol.Binding:
    archive = _archive(manifest, files)
    artifact_digest = "sha256:" + hashlib.sha256(archive).hexdigest()
    case_root = root / label
    case_root.mkdir(mode=0o700)
    path = case_root / f"{artifact_digest.removeprefix('sha256:')}.zip"
    path.write_bytes(archive)
    path.chmod(0o600)
    logical = str(manifest["bundle_digest"])
    return bundle_protocol.binding(
        path,
        bundle_format=str(manifest["bundle_format"]),
        bundle_digest=logical,
        artifact_digest=artifact_digest,
        bundle_size=len(archive),
    )


def _archive(manifest: dict[str, JsonValue], files: tuple[tuple[str, bytes, int], ...]) -> bytes:
    composition = manifest.get("composition_report", _COMPOSITION)
    conversion = manifest.get("conversion_report", _CONVERSION)
    documents: tuple[tuple[str, bytes, int], ...] = (
        ("bundle.json", canonize(manifest), _regular()),
        ("setup-passport.json", canonize(_passport(str(manifest["harness_id"]))), _regular()),
        ("composition-report.json", canonize(composition), _regular()),
        ("conversion-report.json", canonize(conversion), _regular()),
        ("files/", b"", _directory()),
    )
    holder = io.BytesIO()
    with warnings.catch_warnings(), zipfile.ZipFile(holder, "w", zipfile.ZIP_STORED) as archive:
        warnings.simplefilter("ignore", UserWarning)
        members = (*documents, *files, ("attestations/", b"", _directory()))
        for name, content, external_attr in members:
            info = zipfile.ZipInfo(name, date_time=bundle.ZIP_TIMESTAMP)
            info.create_system = 3
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = external_attr
            archive.writestr(info, content)
    return holder.getvalue()


def _regular() -> int:
    return (stat.S_IFREG | bundle.MODE_FILE) << 16


def _directory() -> int:
    return (stat.S_IFDIR | bundle.MODE_EXECUTABLE) << 16


def _symlink() -> int:
    return (stat.S_IFLNK | 0o777) << 16


def _fifo() -> int:
    return (stat.S_IFIFO | bundle.MODE_FILE) << 16
