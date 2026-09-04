"""PEP 740 index path (`SPEC-008` REQ-850). GitHub remains the default acquire."""

from __future__ import annotations

import base64
import hashlib
import importlib
import json
import shutil
import subprocess
import tempfile
import zipfile
from collections.abc import Callable, Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import httpx
import pytest

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.provider import index_attestation, index_bind, index_wheel, protocol_v3, release
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_canonical
from ai_stp_foundation.harnesses import HARNESS_IDS


def _digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _statement(name: str, digest: str) -> str:
    hex_digest = digest.removeprefix("sha256:")
    body = json.dumps(
        {
            "_type": "https://in-toto.io/Statement/v1",
            "subject": [{"name": name, "digest": {"sha256": hex_digest}}],
            "predicateType": "https://docs.pypi.org/attestations/publish/v1",
            "predicate": None,
        },
        separators=(",", ":"),
    )
    return base64.urlsafe_b64encode(body.encode()).decode().rstrip("=")


def _provenance(
    *,
    filename: str,
    digest: str,
    repository: str = "NDDev-OpenNetwork/pi-setup-system",
    workflow: str = "publish-pypi.yml",
    environment: str = "pypi",
) -> dict[str, object]:
    return {
        "version": 1,
        "attestation_bundles": [
            {
                "publisher": {
                    "kind": "GitHub",
                    "repository": repository,
                    "workflow": workflow,
                    "environment": environment,
                },
                "attestations": [
                    {
                        "version": 1,
                        "envelope": {"statement": _statement(filename, digest), "signature": "Zg"},
                        "verification_material": {
                            "certificate": "Zg==",
                            "transparency_entries": [{}],
                        },
                    }
                ],
            }
        ],
    }


def _record_line(name: str, payload: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).rstrip(b"=").decode()
    return f"{name},sha256={digest},{len(payload)}"


def _wheel_bytes(
    *,
    project: str = "pi-setup-system",
    version: str = "0.0.1",
    platform_name: str | None = None,
    extra_binaries: tuple[str, ...] = (),
    traversal: str | None = None,
    symlink: bool = False,
    corrupt_record: bool = False,
) -> bytes:
    platform_name = platform_name or release.current_platform()
    package = project.replace("-", "_")
    suffix = ".exe" if platform_name.startswith("windows/") else ""
    binary_name = f"{package}/bin/{project}{suffix}"
    binary = b"provider-bytes"
    init = b""
    metadata = (f"Name: {project}\nVersion: {version}\nLicense: AGPL-3.0-or-later\n").encode()
    wheel_meta = b"Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: false\n"
    members: list[tuple[str, bytes]] = [
        (f"{package}/__init__.py", init),
        (binary_name, binary),
        (f"{package}-{version}.dist-info/METADATA", metadata),
        (f"{package}-{version}.dist-info/WHEEL", wheel_meta),
    ]
    for extra in extra_binaries:
        members.append((f"{package}/bin/{extra}", b"extra"))
    if traversal:
        members.append((traversal, b"escape"))
    record_name = f"{package}-{version}.dist-info/RECORD"
    lines = [_record_line(name, payload) for name, payload in members]
    lines.append(f"{record_name},,")
    record = ("\n".join(lines) + "\n").encode()
    if corrupt_record:
        record = b"not-a-record\n"
    members.append((record_name, record))
    from io import BytesIO

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as held:
        for name, payload in members:
            info = zipfile.ZipInfo(name)
            if symlink:
                info.external_attr = (0o120777 << 16) | 0o777
            held.writestr(info, payload)
    return buffer.getvalue()


def _info(*, harness_id: str = "pi") -> dict[str, JsonValue]:
    os_name, architecture = release.current_platform().split("/", 1)
    profile: dict[str, JsonValue] = {
        "profile_id": f"{harness_id}/test",
        "component_kinds": ["instruction"],
        "projection_kinds": ["native_files"],
        "native_namespaces": ["AGENTS.md"],
        "bundle_formats": ["ai-stp-bundle/1"],
        "max_files": 2000,
        "max_bytes": 64 * 1024 * 1024,
    }
    commands = cast(list[JsonValue], list(protocol_v3.CORE_COMMANDS))
    operations = cast(list[JsonValue], sorted(item.value for item in protocol_v3.CORE_OPERATIONS))
    os_names: list[JsonValue] = [os_name]
    arch_names: list[JsonValue] = [architecture]
    profiles: list[JsonValue] = []
    return {
        "protocol_version": protocol_v3.VERSION,
        "provider_id": f"{harness_id}-setup-system",
        "harness_id": harness_id,
        "provider_version": "0.0.1",
        "provider_build_digest": "sha256:" + "b" * 64,
        "supported_commands": commands,
        "supported_operations": operations,
        "supported_os": os_names,
        "supported_arch": arch_names,
        "permission_profiles": profiles,
        "projection_profile": {
            **profile,
            "digest": digest_canonical(protocol_v3.PROJECTION_DOMAIN, profile),
        },
    }


class _Index:
    def __init__(
        self,
        *,
        blob: bytes,
        filename: str,
        url: str = "https://files.pythonhosted.org/packages/ab/cd/pi_setup_system-0.0.1-py3-none-manylinux_2_34_x86_64.whl",
        provenance: dict[str, object] | None = None,
        version: str = "0.0.1",
    ) -> None:
        self.blob = blob
        self.filename = filename
        self.url = url
        self._provenance = provenance
        self.version = version

    def resolve_version(self, project: str, version: str | None) -> str:
        return version or self.version

    def wheel(self, project: str, version: str, platform_name: str) -> index_bind.IndexFile:
        return index_bind.IndexFile(filename=self.filename, url=self.url, size=len(self.blob))

    def download(self, url: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self.blob)

    def provenance(self, project: str, version: str, filename: str) -> dict[str, object] | None:
        return self._provenance


class _Verifier:
    def __init__(self, *, commit: str = "a" * 40, fail: bool = False) -> None:
        self.calls: list[str] = []
        self.commit = commit
        self.fail = fail

    def verify(
        self,
        artifact: Path,
        provenance: Mapping[str, object],
        rule: release.IndexPublisherRule,
    ) -> index_attestation.PublisherIdentity:
        self.calls.append("verify")
        if self.fail:
            raise CliFailure(
                "AI_STP_PRECONDITION_FAILED",
                "the provider wheel has no acceptable PEP 740 provenance",
                details={"project": rule.pypi_project},
            )
        identity = index_attestation.parse_identity(provenance)
        return index_attestation.PublisherIdentity(
            repository=rule.repository,
            workflow=rule.workflow,
            environment=rule.environment,
            subject_name=identity.subject_name,
            subject_digest=identity.subject_digest,
            source_commit=self.commit,
        )


def _inspect(harness_id: str = "pi") -> Callable[[Path], protocol_v3.ProviderCapabilities]:
    payload = _info(harness_id=harness_id)

    def inspect(executable: Path) -> protocol_v3.ProviderCapabilities:
        assert executable.is_file()
        return protocol_v3.parse_capabilities(payload)

    return inspect


def _filename() -> str:
    tag = index_bind.wheel_tag(release.current_platform())
    return f"pi_setup_system-0.0.1-py3-none-{tag}.whl"


def test_every_supported_harness_has_a_pinned_index_publisher() -> None:
    policy = release.pinned_policy()
    projects = {repository.rsplit("/", 1)[-1] for repository in policy.build_attestations}
    assert set(policy.index_publishers) == projects
    assert all(rule.workflow == "publish-pypi.yml" for rule in policy.index_publishers.values())
    assert all(rule.environment == "pypi" for rule in policy.index_publishers.values())
    assert {index_bind.project_for_harness(name) for name in HARNESS_IDS} == set(
        policy.index_publishers
    )


def test_missing_provenance_is_refused_before_spawn(tmp_path: Path) -> None:
    blob = _wheel_bytes()
    spawned = False

    def inspect(executable: Path) -> protocol_v3.ProviderCapabilities:
        nonlocal spawned
        spawned = True
        raise AssertionError("provider-info must not run before provenance")

    with pytest.raises(CliFailure) as raised:
        index_bind.fetch(
            harness="pi",
            tag="0.0.1",
            directory=tmp_path,
            index=_Index(blob=blob, filename=_filename(), provenance=None),
            inspect=inspect,
            verifier=_Verifier(),
        )
    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"
    assert "no provenance" in raised.value.message
    assert spawned is False


def test_wrong_publisher_is_refused_before_spawn(tmp_path: Path) -> None:
    blob = _wheel_bytes()
    filename = _filename()
    provenance = _provenance(
        filename=filename, digest=_digest(blob), repository="evil/other", workflow="evil.yml"
    )
    spawned = False

    def inspect(executable: Path) -> protocol_v3.ProviderCapabilities:
        nonlocal spawned
        spawned = True
        raise AssertionError("must not spawn")

    with pytest.raises(CliFailure) as raised:
        index_bind.fetch(
            harness="pi",
            tag="0.0.1",
            directory=tmp_path,
            index=_Index(blob=blob, filename=filename, provenance=provenance),
            inspect=inspect,
            verifier=_Verifier(),
        )
    assert "not pinned" in raised.value.message
    assert spawned is False


def test_digest_mismatch_is_refused_before_spawn(tmp_path: Path) -> None:
    blob = _wheel_bytes()
    filename = _filename()
    provenance = _provenance(filename=filename, digest="sha256:" + "0" * 64)
    spawned = False

    def inspect(executable: Path) -> protocol_v3.ProviderCapabilities:
        nonlocal spawned
        spawned = True
        raise AssertionError("must not spawn")

    with pytest.raises(CliFailure) as raised:
        index_bind.fetch(
            harness="pi",
            tag="0.0.1",
            directory=tmp_path,
            index=_Index(blob=blob, filename=filename, provenance=provenance),
            inspect=inspect,
            verifier=_Verifier(),
        )
    assert "not the subject" in raised.value.message
    assert spawned is False


def test_extra_executable_is_refused_before_verify(tmp_path: Path) -> None:
    blob = _wheel_bytes(extra_binaries=("other",))
    filename = _filename()
    verifier = _Verifier()
    with pytest.raises(CliFailure) as raised:
        index_bind.fetch(
            harness="pi",
            tag="0.0.1",
            directory=tmp_path,
            index=_Index(
                blob=blob,
                filename=filename,
                provenance=_provenance(filename=filename, digest=_digest(blob)),
            ),
            inspect=_inspect(),
            verifier=verifier,
        )
    assert "exactly one executable" in raised.value.message
    assert verifier.calls == []


def test_archive_traversal_is_refused() -> None:
    blob = _wheel_bytes(traversal="../escape")
    with pytest.raises(CliFailure) as raised:
        index_wheel.inspect(
            _write_wheel(blob),
            project="pi-setup-system",
            version="0.0.1",
            platform_name=release.current_platform(),
        )
    assert "leaves the archive" in raised.value.message


def test_symlink_member_is_refused() -> None:
    blob = _wheel_bytes(symlink=True)
    with pytest.raises(CliFailure) as raised:
        index_wheel.inspect(
            _write_wheel(blob),
            project="pi-setup-system",
            version="0.0.1",
            platform_name=release.current_platform(),
        )
    assert "symbolic link" in raised.value.message


def test_record_mismatch_is_refused() -> None:
    blob = _wheel_bytes(corrupt_record=True)
    with pytest.raises(CliFailure) as raised:
        index_wheel.inspect(
            _write_wheel(blob),
            project="pi-setup-system",
            version="0.0.1",
            platform_name=release.current_platform(),
        )
    assert "RECORD" in raised.value.message


def test_fetch_verifies_before_provider_info(tmp_path: Path) -> None:
    blob = _wheel_bytes()
    filename = _filename()
    order: list[str] = []
    verifier = _Verifier()

    def inspect(executable: Path) -> protocol_v3.ProviderCapabilities:
        order.append("inspect")
        return protocol_v3.parse_capabilities(_info())

    original = verifier.verify

    def wrapped(
        artifact: Path,
        provenance: Mapping[str, object],
        rule: release.IndexPublisherRule,
    ) -> index_attestation.PublisherIdentity:
        order.append("verify")
        return original(artifact, provenance, rule)

    verifier.verify = wrapped  # type: ignore[method-assign]
    bound = index_bind.fetch(
        harness="pi",
        tag="0.0.1",
        directory=tmp_path,
        index=_Index(
            blob=blob,
            filename=filename,
            provenance=_provenance(filename=filename, digest=_digest(blob)),
        ),
        inspect=inspect,
        verifier=verifier,
    )
    assert order == ["verify", "inspect"]
    assert bound.trust_level == "verified_publisher"
    assert bound.commit == "a" * 40
    assert bound.artifact.is_file()
    assert bound.manifest.signing_key == "attested"
    assert bound.manifest.signature == ""
    assert "latest" not in bound.artifact_url.casefold()


def test_subject_name_mismatch_is_refused(tmp_path: Path) -> None:
    blob = _wheel_bytes()
    filename = _filename()
    provenance = _provenance(filename="other.whl", digest=_digest(blob))
    with pytest.raises(CliFailure) as raised:
        index_bind.fetch(
            harness="pi",
            tag="0.0.1",
            directory=tmp_path,
            index=_Index(blob=blob, filename=filename, provenance=provenance),
            inspect=_inspect(),
            verifier=_Verifier(),
        )
    assert "not the subject" in raised.value.message


def test_wrong_workflow_and_environment_are_refused(tmp_path: Path) -> None:
    blob = _wheel_bytes()
    filename = _filename()
    for provenance in (
        _provenance(filename=filename, digest=_digest(blob), workflow="other.yml"),
        _provenance(filename=filename, digest=_digest(blob), environment="staging"),
    ):
        with pytest.raises(CliFailure) as raised:
            index_bind.fetch(
                harness="pi",
                tag="0.0.1",
                directory=tmp_path,
                index=_Index(blob=blob, filename=filename, provenance=provenance),
                inspect=_inspect(),
                verifier=_Verifier(),
            )
        assert "not pinned" in raised.value.message


def test_a_failing_bundle_verifier_is_refused_before_spawn(tmp_path: Path) -> None:
    blob = _wheel_bytes()
    filename = _filename()
    spawned = False

    def inspect(executable: Path) -> protocol_v3.ProviderCapabilities:
        nonlocal spawned
        spawned = True
        raise AssertionError("must not spawn")

    with pytest.raises(CliFailure) as raised:
        index_bind.fetch(
            harness="pi",
            tag="0.0.1",
            directory=tmp_path,
            index=_Index(
                blob=blob,
                filename=filename,
                provenance=_provenance(filename=filename, digest=_digest(blob)),
            ),
            inspect=inspect,
            verifier=_Verifier(fail=True),
        )
    assert "no acceptable PEP 740" in raised.value.message
    assert spawned is False


def test_malformed_provenance_is_refused() -> None:
    with pytest.raises(CliFailure) as raised:
        index_attestation.parse_identity({"attestation_bundles": []})
    assert "integrity document" in raised.value.message


def _write_wheel(blob: bytes) -> Path:
    place = Path(tempfile.mkdtemp()) / "pi_setup_system-0.0.1-py3-none-any.whl"
    place.write_bytes(blob)
    return place


def test_empty_source_commit_is_refused_after_verify(tmp_path: Path) -> None:
    blob = _wheel_bytes()
    filename = _filename()
    with pytest.raises(CliFailure) as raised:
        index_bind.fetch(
            harness="pi",
            tag="0.0.1",
            directory=tmp_path,
            index=_Index(
                blob=blob,
                filename=filename,
                provenance=_provenance(filename=filename, digest=_digest(blob)),
            ),
            inspect=_inspect(),
            verifier=_Verifier(commit=""),
        )
    assert "source commit" in raised.value.message


def _force_cli_verifier(
    monkeypatch: pytest.MonkeyPatch,
    *,
    which: str | None,
    returncode: int = 0,
) -> None:
    real_import = importlib.import_module

    def missing(name: str, package: str | None = None) -> object:
        if name == "pypi_attestations":
            raise ImportError(name)
        return real_import(name, package)

    monkeypatch.setattr(importlib, "import_module", missing)

    def which_fn(_name: str) -> str | None:
        return which

    monkeypatch.setattr(shutil, "which", which_fn)
    if which is not None:

        def run_fn(*_args: object, **_kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(returncode=returncode, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", run_fn)


def test_production_verifier_is_unavailable_without_pypi_attestations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_cli_verifier(monkeypatch, which=None)
    blob = _wheel_bytes()
    filename = _filename()
    destination = tmp_path / filename
    destination.write_bytes(blob)
    provenance = _provenance(filename=filename, digest=_digest(blob))
    with pytest.raises(CliFailure) as raised:
        index_attestation.verify(
            destination,
            provenance,
            release.pinned_policy().index_publishers["pi-setup-system"],
        )
    assert raised.value.code == "AI_STP_DEPENDENCY_UNAVAILABLE"


def test_the_cli_verifier_succeeds_without_a_source_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_cli_verifier(monkeypatch, which="/usr/bin/pypi-attestations")
    blob = _wheel_bytes()
    filename = _filename()
    destination = tmp_path / filename
    destination.write_bytes(blob)
    provenance = _provenance(filename=filename, digest=_digest(blob))
    evidence = index_attestation.verify(
        destination,
        provenance,
        release.pinned_policy().index_publishers["pi-setup-system"],
    )
    assert evidence.trust_level == "verified_publisher"
    assert evidence.identity.source_commit == ""


def test_the_cli_verifier_refuses_a_failed_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_cli_verifier(monkeypatch, which="/usr/bin/pypi-attestations", returncode=1)
    blob = _wheel_bytes()
    filename = _filename()
    destination = tmp_path / filename
    destination.write_bytes(blob)
    provenance = _provenance(filename=filename, digest=_digest(blob))
    with pytest.raises(CliFailure) as raised:
        index_attestation.verify(
            destination,
            provenance,
            release.pinned_policy().index_publishers["pi-setup-system"],
        )
    assert "no acceptable PEP 740" in raised.value.message


def _pypi_client(
    handler: Callable[[httpx.Request], httpx.Response], monkeypatch: pytest.MonkeyPatch
) -> None:
    real = httpx.Client

    def factory(
        *,
        timeout: float = 30.0,
        follow_redirects: bool = False,
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Client:
        return real(
            timeout=timeout,
            follow_redirects=follow_redirects,
            headers=headers,
            transport=httpx.MockTransport(handler),
        )

    monkeypatch.setattr(httpx, "Client", factory)


def test_pypi_index_binds_a_hashed_wheel_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tag = index_bind.wheel_tag(release.current_platform())
    filename = f"pi_setup_system-0.0.1-py3-none-{tag}.whl"
    url = f"https://files.pythonhosted.org/packages/ab/cd/deadbeef/{filename}"
    blob = _wheel_bytes()
    provenance = _provenance(filename=filename, digest=_digest(blob))

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/pypi/pi-setup-system/json":
            return httpx.Response(200, json={"info": {"version": "0.0.1"}})
        if path == "/pypi/pi-setup-system/0.0.1/json":
            return httpx.Response(
                200,
                json={"urls": [{"filename": filename, "url": url, "size": len(blob)}]},
            )
        if path.endswith(f"/{filename}/provenance"):
            return httpx.Response(200, json=provenance)
        if "/packages/" in path:
            return httpx.Response(200, content=blob)
        return httpx.Response(404)

    _pypi_client(handler, monkeypatch)
    client = index_bind.PypiIndex()
    assert client.resolve_version("pi-setup-system", None) == "0.0.1"
    held = client.wheel("pi-setup-system", "0.0.1", release.current_platform())
    assert held.url == url
    destination = tmp_path / filename
    client.download(url, destination)
    assert destination.read_bytes() == blob
    assert client.provenance("pi-setup-system", "0.0.1", filename) == provenance
    assert client.provenance("pi-setup-system", "0.0.1", "missing.whl") is None
    bound = index_bind.fetch(
        harness="pi",
        tag="0.0.1",
        directory=tmp_path / "bound",
        inspect=_inspect(),
        verifier=_Verifier(),
    )
    assert bound.trust_level == "verified_publisher"
    assert bound.artifact.is_file()


def test_pypi_index_refuses_a_floating_wheel_url(monkeypatch: pytest.MonkeyPatch) -> None:
    tag = index_bind.wheel_tag(release.current_platform())
    filename = f"pi_setup_system-0.0.1-py3-none-{tag}.whl"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "urls": [
                    {
                        "filename": filename,
                        "url": "https://pypi.org/simple/pi-setup-system/latest",
                        "size": 12,
                    }
                ]
            },
        )

    _pypi_client(handler, monkeypatch)
    with pytest.raises(CliFailure) as raised:
        index_bind.PypiIndex().wheel("pi-setup-system", "0.0.1", release.current_platform())
    assert "exact bytes" in raised.value.message


def test_local_provenance_file_is_read_before_spawn(tmp_path: Path) -> None:
    blob = _wheel_bytes()
    filename = _filename()
    provenance = _provenance(filename=filename, digest=_digest(blob))
    place = tmp_path / "provenance.json"
    place.write_text(json.dumps(provenance), encoding="utf-8")
    bound = index_bind.fetch(
        harness="pi",
        tag="0.0.1",
        directory=tmp_path / "out",
        index=_Index(blob=blob, filename=filename, provenance=None),
        inspect=_inspect(),
        verifier=_Verifier(),
        provenance=place,
    )
    assert bound.trust_level == "verified_publisher"


def test_an_unknown_harness_is_refused(tmp_path: Path) -> None:
    with pytest.raises(CliFailure) as raised:
        index_bind.fetch(harness="unknown", directory=tmp_path, inspect=_inspect())
    assert raised.value.code == "AI_STP_VALIDATION_ERROR"


def test_an_unknown_platform_has_no_wheel_tag() -> None:
    with pytest.raises(CliFailure) as raised:
        index_bind.wheel_tag("plan9/mips")
    assert "no attested provider asset" in raised.value.message


def test_the_library_verifier_supplies_the_source_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _Error(Exception):
        pass

    class _Attestation:
        def verify(self, *, identity: object, dist: object) -> None:
            return None

        def certificate_claims(self) -> dict[str, str]:
            return {"sha": "d" * 40}

    class _Bundle:
        def __init__(self) -> None:
            self.attestations = [_Attestation()]

    class _Document:
        def __init__(self) -> None:
            self.attestation_bundles = [_Bundle()]

    class _Distribution:
        @staticmethod
        def from_file(_path: Path) -> object:
            return object()

    class _Provenance:
        @staticmethod
        def model_validate(_payload: object) -> _Document:
            return _Document()

    class _Publisher:
        def __init__(self, **_kwargs: object) -> None:
            return None

    fake = SimpleNamespace(
        Distribution=_Distribution,
        Provenance=_Provenance,
        GitHubPublisher=_Publisher,
        VerificationError=_Error,
    )
    real_import = importlib.import_module

    def load(name: str, package: str | None = None) -> object:
        if name == "pypi_attestations":
            return fake
        return real_import(name, package)

    monkeypatch.setattr(importlib, "import_module", load)
    blob = _wheel_bytes()
    filename = _filename()
    destination = tmp_path / filename
    destination.write_bytes(blob)
    provenance = _provenance(filename=filename, digest=_digest(blob))
    evidence = index_attestation.verify(
        destination,
        provenance,
        release.pinned_policy().index_publishers["pi-setup-system"],
    )
    assert evidence.identity.source_commit == "d" * 40
    assert evidence.trust_level == "verified_publisher"
