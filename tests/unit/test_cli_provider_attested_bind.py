"""Consumer-bound attested manifests (`SPEC-008` REQ-847)."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

from ai_stp_cli.commands import select
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.provider import attested_bind, build_attestation, protocol_v3, release
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_canonical
from ai_stp_foundation.harnesses import HARNESS_IDS


def _digest(character: str) -> str:
    return "sha256:" + character * 64


def _info(*, harness_id: str = "pi") -> dict[str, JsonValue]:
    os_name, architecture = release.current_platform().split("/", 1)
    profile: dict[str, JsonValue] = {
        "profile_id": f"{harness_id}/test",
        "component_kinds": cast(list[JsonValue], ["instruction"]),
        "projection_kinds": cast(list[JsonValue], ["native_files"]),
        "native_namespaces": cast(list[JsonValue], ["AGENTS.md"]),
        "bundle_formats": cast(list[JsonValue], ["ai-stp-bundle/1"]),
        "max_files": 2000,
        "max_bytes": 64 * 1024 * 1024,
    }
    return {
        "protocol_version": protocol_v3.VERSION,
        "provider_id": f"nddev-{harness_id}-app",
        "harness_id": harness_id,
        "provider_version": "0.0.1",
        "provider_build_digest": _digest("b"),
        "supported_commands": cast(list[JsonValue], list(protocol_v3.CORE_COMMANDS)),
        "supported_operations": cast(
            list[JsonValue], sorted(item.value for item in protocol_v3.CORE_OPERATIONS)
        ),
        "supported_os": cast(list[JsonValue], [os_name]),
        "supported_arch": cast(list[JsonValue], [architecture]),
        "permission_profiles": cast(list[JsonValue], []),
        "projection_profile": {
            **profile,
            "digest": digest_canonical(protocol_v3.PROJECTION_DOMAIN, profile),
        },
    }


def _provider_script(harness_id: str = "pi") -> bytes:
    payload = json.dumps(_info(harness_id=harness_id))
    return (
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        f"INFO = json.loads({payload!r})\n"
        "command = sys.argv[1] if len(sys.argv) > 1 else ''\n"
        "if command != 'provider-info':\n"
        "    raise SystemExit(1)\n"
        "print(json.dumps(INFO))\n"
    ).encode()


class _Github:
    def __init__(
        self,
        *,
        tag: str = "0.0.1",
        commit: str = "f" * 40,
        license_id: str = "AGPL-3.0-or-later",
        blob: bytes = b"attested-bytes",
        assets: frozenset[str] | None = None,
    ) -> None:
        self.tag = tag
        self.commit = commit
        self.license_id = license_id
        self.blob = blob
        self.assets = assets

    def resolve_tag(self, repository: str, tag: str | None) -> str:
        return tag or self.tag

    def facts(self, repository: str, tag: str) -> attested_bind.ReleaseFacts:
        asset = attested_bind.asset_name(repository, release.current_platform())
        names = self.assets if self.assets is not None else frozenset({asset})
        return attested_bind.ReleaseFacts(
            tag=tag, commit=self.commit, license_id=self.license_id, assets=names
        )

    def download(self, repository: str, tag: str, asset: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self.blob)


def _inspect(harness_id: str = "pi") -> Callable[[Path], protocol_v3.ProviderCapabilities]:
    payload = _info(harness_id=harness_id)

    def inspect(executable: Path) -> protocol_v3.ProviderCapabilities:
        assert executable.is_file()
        return protocol_v3.parse_capabilities(payload)

    return inspect


def _attest(monkeypatch: pytest.MonkeyPatch, order: list[str] | None = None) -> None:
    def verify(
        artifact: Path,
        held: build_attestation.Policy,
        *,
        bundle: Path | None = None,
    ) -> build_attestation.Evidence:
        if order is not None:
            order.append("attest")
        assert held.verified_publisher is True
        assert bundle is None
        assert artifact.is_file()
        return build_attestation.Evidence(
            trust_level="verified_publisher",
            digest=_digest("c"),
            document="[]",
        )

    monkeypatch.setattr(build_attestation, "verify", verify)


def test_every_supported_harness_maps_to_one_opennetwork_attestation() -> None:
    policy = release.pinned_policy()
    opennetwork = {
        name
        for name in policy.build_attestations
        if name.startswith("github.com/NDDev-OpenNetwork/")
    }
    assert set(attested_bind.HARNESS_REPOSITORIES) == set(HARNESS_IDS)
    assert set(attested_bind.HARNESS_REPOSITORIES.values()) == opennetwork


@pytest.mark.parametrize(
    ("tag", "sequence"),
    [("0.0.1", 1), ("v1.2.3", 1_002_003), ("0.0.0", 0), ("2.0.0", 2_000_000)],
)
def test_sequence_is_encoded_from_the_exact_semver_tag(tag: str, sequence: int) -> None:
    assert attested_bind.sequence_from_tag(tag) == sequence


@pytest.mark.parametrize("tag", ["latest", "main", "0.0.1-rc.1", "1.0", "01.0.0", ""])
def test_a_floating_or_open_tag_does_not_encode_a_sequence(tag: str) -> None:
    with pytest.raises(CliFailure) as raised:
        attested_bind.sequence_from_tag(tag)
    assert raised.value.code == "AI_STP_VALIDATION_ERROR"


def test_artifact_url_contains_the_tag_not_a_floating_name() -> None:
    url = attested_bind.artifact_url(
        "github.com/NDDev-OpenNetwork/pi-setup-system",
        "0.0.1",
        "pi-setup-system-x86_64-unknown-linux-gnu",
    )
    assert "/releases/download/0.0.1/" in url
    assert "latest" not in url.casefold()


def test_fetch_writes_a_closed_manifest_after_attestation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    order: list[str] = []
    _attest(monkeypatch, order)
    payload = _info()

    def inspect(executable: Path) -> protocol_v3.ProviderCapabilities:
        order.append("inspect")
        return protocol_v3.parse_capabilities(payload)

    bound = attested_bind.fetch(
        harness="pi",
        tag="0.0.1",
        directory=tmp_path,
        github=_Github(),
        inspect=inspect,
    )
    assert order == ["attest", "inspect"]
    assert bound.trust_level == "verified_publisher"
    assert bound.sequence == 1
    assert bound.commit == "f" * 40
    assert bound.artifact.is_file()
    assert bound.manifest_path.is_file()
    parsed = release.parse_manifest(bound.manifest_path.read_text("utf-8"))
    assert parsed == bound.manifest
    assert parsed.signing_key == attested_bind.ATTESTED_SIGNING_KEY
    assert parsed.signature == ""
    assert parsed.protocol_version == protocol_v3.VERSION
    assert "latest" not in parsed.artifact_url.casefold()
    verdict = release.verify_attested(
        parsed,
        release.pinned_policy(),
        known_sequence=0,
        observed_digest=bound.artifact_digest,
        observed_size=bound.artifact.stat().st_size,
        platform=release.current_platform(),
    )
    assert verdict.accepted
    view = select.provider_trust({"manifest": str(bound.manifest_path)}).payload
    assert view.accepted is True
    assert view.refusals == []


def test_fetch_refuses_a_missing_platform_asset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _attest(monkeypatch)
    with pytest.raises(CliFailure) as raised:
        attested_bind.fetch(
            harness="pi",
            tag="0.0.1",
            directory=tmp_path,
            github=_Github(assets=frozenset({"SHA256SUMS"})),
            inspect=_inspect(),
        )
    assert raised.value.code == "AI_STP_NOT_FOUND"


def test_fetch_refuses_a_harness_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _attest(monkeypatch)
    with pytest.raises(CliFailure) as raised:
        attested_bind.fetch(
            harness="pi",
            tag="0.0.1",
            directory=tmp_path,
            github=_Github(),
            inspect=_inspect("claude-code"),
        )
    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"


def test_provider_fetch_command_binds_into_the_named_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _attest(monkeypatch)
    payload = _info()

    def inspect(executable: Path) -> protocol_v3.ProviderCapabilities:
        return protocol_v3.parse_capabilities(payload)

    monkeypatch.setattr(attested_bind, "GithubReleases", lambda: _Github())
    monkeypatch.setattr(attested_bind, "inspect_provider", inspect)
    view = select.provider_fetch(
        {"harness": "pi", "tag": "0.0.1", "directory": str(tmp_path)}
    ).payload
    assert view.harness_id == "pi"
    assert view.tag == "0.0.1"
    assert view.trust_level == "verified_publisher"
    assert view.sequence == 1
    assert view.manifest.endswith("release.json")


def test_fetch_runs_provider_info_only_after_attestation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _attest(monkeypatch)
    bound = attested_bind.fetch(
        harness="pi",
        tag="0.0.1",
        directory=tmp_path,
        github=_Github(blob=_provider_script()),
    )
    assert bound.provider_id == "nddev-pi-app"
    parsed = release.parse_manifest(bound.manifest_path.read_text("utf-8"))
    assert parsed.entry_point == bound.artifact.name


def test_fetch_binds_an_existing_artifact_without_downloading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _attest(monkeypatch)
    source = tmp_path / "local-provider"
    source.write_bytes(_provider_script())
    bound = attested_bind.fetch(
        harness="pi",
        tag="0.0.1",
        directory=tmp_path / "out",
        artifact=source,
        github=_Github(blob=b"unused"),
    )
    assert bound.artifact.parent == (tmp_path / "out").resolve()
    assert bound.artifact.read_bytes() == source.read_bytes()


def test_fetch_refuses_a_missing_attestation_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _attest(monkeypatch)
    with pytest.raises(CliFailure) as raised:
        attested_bind.fetch(
            harness="pi",
            tag="0.0.1",
            directory=tmp_path,
            attestation_bundle=tmp_path / "absent.json",
            github=_Github(),
            inspect=_inspect(),
        )
    assert raised.value.code == "AI_STP_NOT_FOUND"


def test_fetch_refuses_an_undeclared_license(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _attest(monkeypatch)
    with pytest.raises(CliFailure) as raised:
        attested_bind.fetch(
            harness="pi",
            tag="0.0.1",
            directory=tmp_path,
            github=_Github(license_id="NOASSERTION"),
            inspect=_inspect(),
        )
    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"


def test_fetch_refuses_a_commit_that_is_not_a_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _attest(monkeypatch)
    with pytest.raises(CliFailure) as raised:
        attested_bind.fetch(
            harness="pi",
            tag="0.0.1",
            directory=tmp_path,
            github=_Github(commit="HEAD"),
            inspect=_inspect(),
        )
    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"


def test_fetch_refuses_a_destination_that_is_not_a_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _attest(monkeypatch)
    place = tmp_path / "not-a-dir"
    place.write_text("x", encoding="utf-8")
    with pytest.raises(CliFailure) as raised:
        attested_bind.fetch(
            harness="pi",
            tag="0.0.1",
            directory=place,
            github=_Github(),
            inspect=_inspect(),
        )
    assert raised.value.code == "AI_STP_VALIDATION_ERROR"


def test_an_unknown_platform_has_no_attested_asset() -> None:
    with pytest.raises(CliFailure) as raised:
        attested_bind.asset_name("github.com/NDDev-OpenNetwork/pi-setup-system", "plan9/x86_64")
    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"


def test_an_unknown_harness_has_no_repository() -> None:
    with pytest.raises(CliFailure) as raised:
        attested_bind.repository_for_harness("not-a-harness")
    assert raised.value.code == "AI_STP_VALIDATION_ERROR"


def test_inspect_provider_refuses_a_non_v3_payload(tmp_path: Path) -> None:
    place = tmp_path / "broken"
    place.write_text(
        "#!/usr/bin/env python3\nimport json\nprint(json.dumps({'error': 'no'}))\n",
        encoding="utf-8",
    )
    place.chmod(0o700)
    with pytest.raises(CliFailure) as raised:
        attested_bind.inspect_provider(place)
    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"


def test_inspect_provider_refuses_a_payload_that_fails_the_v3_schema(tmp_path: Path) -> None:
    place = tmp_path / "partial"
    place.write_text(
        "#!/usr/bin/env python3\nimport json\nprint(json.dumps({'protocol_version': 3}))\n",
        encoding="utf-8",
    )
    place.chmod(0o700)
    with pytest.raises(CliFailure) as raised:
        attested_bind.inspect_provider(place)
    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"


def _gh_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
    joined = " ".join(command)
    if "commits/" in joined:
        return subprocess.CompletedProcess(command, 0, json.dumps({"sha": "a" * 40}), "")
    if len(command) >= 2 and command[1] == "api":
        return subprocess.CompletedProcess(
            command, 0, json.dumps({"license": {"spdx_id": "AGPL-3.0-or-later"}}), ""
        )
    if len(command) >= 3 and command[1] == "release" and command[2] == "download":
        destination = Path(command[command.index("--dir") + 1])
        asset = command[command.index("--pattern") + 1]
        destination.mkdir(parents=True, exist_ok=True)
        (destination / asset).write_bytes(b"downloaded")
        return subprocess.CompletedProcess(command, 0, "", "")
    return subprocess.CompletedProcess(
        command,
        0,
        json.dumps(
            {
                "tagName": "0.0.1",
                "assets": [{"name": "pi-setup-system-x86_64-unknown-linux-gnu"}],
            }
        ),
        "",
    )


def test_github_resolves_the_current_release_to_a_closed_tag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(subprocess, "run", _gh_run)
    resolved = attested_bind.GithubReleases().resolve_tag(
        "github.com/NDDev-OpenNetwork/pi-setup-system", None
    )
    assert resolved == "0.0.1"


def test_github_reads_commit_license_and_assets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(subprocess, "run", _gh_run)
    facts = attested_bind.GithubReleases().facts(
        "github.com/NDDev-OpenNetwork/pi-setup-system", "0.0.1"
    )
    assert facts.commit == "a" * 40
    assert facts.license_id == "AGPL-3.0-or-later"
    assert "pi-setup-system-x86_64-unknown-linux-gnu" in facts.assets


def test_github_downloads_the_named_asset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(subprocess, "run", _gh_run)
    destination = tmp_path / "pi-setup-system-x86_64-unknown-linux-gnu"
    attested_bind.GithubReleases().download(
        "github.com/NDDev-OpenNetwork/pi-setup-system",
        "0.0.1",
        destination.name,
        destination,
    )
    assert destination.read_bytes() == b"downloaded"


def test_github_refuses_invalid_metadata_json(monkeypatch: pytest.MonkeyPatch) -> None:
    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, "not-json", "")

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(CliFailure) as raised:
        attested_bind.GithubReleases().resolve_tag(
            "github.com/NDDev-OpenNetwork/pi-setup-system", None
        )
    assert raised.value.code == "AI_STP_DEPENDENCY_UNAVAILABLE"


def test_github_refuses_a_missing_tag_name(monkeypatch: pytest.MonkeyPatch) -> None:
    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, json.dumps({"tagName": ""}), "")

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(CliFailure) as raised:
        attested_bind.GithubReleases().resolve_tag(
            "github.com/NDDev-OpenNetwork/pi-setup-system", None
        )
    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"


def test_github_is_unavailable_when_gh_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    def run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd="gh", timeout=1)

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(CliFailure) as raised:
        attested_bind.GithubReleases().resolve_tag(
            "github.com/NDDev-OpenNetwork/pi-setup-system", None
        )
    assert raised.value.code == "AI_STP_DEPENDENCY_UNAVAILABLE"


def test_github_refuses_a_failed_release_view(monkeypatch: pytest.MonkeyPatch) -> None:
    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, "", "no release")

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(CliFailure) as raised:
        attested_bind.GithubReleases().resolve_tag(
            "github.com/NDDev-OpenNetwork/pi-setup-system", None
        )
    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"


def test_github_refuses_a_non_object_release_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, json.dumps(["tagName"]), "")

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(CliFailure) as raised:
        attested_bind.GithubReleases().resolve_tag(
            "github.com/NDDev-OpenNetwork/pi-setup-system", None
        )
    assert raised.value.code == "AI_STP_DEPENDENCY_UNAVAILABLE"


def test_github_facts_refuse_assets_that_are_not_a_list(monkeypatch: pytest.MonkeyPatch) -> None:
    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        joined = " ".join(command)
        if "commits/" in joined:
            return subprocess.CompletedProcess(command, 0, json.dumps({"sha": "a" * 40}), "")
        if len(command) >= 2 and command[1] == "api":
            return subprocess.CompletedProcess(
                command, 0, json.dumps({"license": {"spdx_id": "MIT"}}), ""
            )
        return subprocess.CompletedProcess(command, 0, json.dumps({"assets": "nope"}), "")

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(CliFailure) as raised:
        attested_bind.GithubReleases().facts(
            "github.com/NDDev-OpenNetwork/pi-setup-system", "0.0.1"
        )
    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"


def test_github_download_refuses_when_the_file_never_arrives(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", run)
    destination = tmp_path / "missing-asset"
    with pytest.raises(CliFailure) as raised:
        attested_bind.GithubReleases().download(
            "github.com/NDDev-OpenNetwork/pi-setup-system",
            "0.0.1",
            destination.name,
            destination,
        )
    assert raised.value.code == "AI_STP_NOT_FOUND"


def test_a_non_github_repository_cannot_form_an_artifact_url() -> None:
    with pytest.raises(CliFailure) as raised:
        attested_bind.artifact_url("gitlab.example/x/y", "0.0.1", "asset")
    assert raised.value.code == "AI_STP_VALIDATION_ERROR"


def test_fetch_binds_an_existing_artifact_in_place(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _attest(monkeypatch)
    repository = attested_bind.repository_for_harness("pi")
    source = tmp_path / attested_bind.asset_name(repository, release.current_platform())
    source.write_bytes(_provider_script())
    bound = attested_bind.fetch(
        harness="pi",
        tag="0.0.1",
        artifact=source,
        github=_Github(blob=b"unused"),
    )
    assert bound.artifact.resolve() == source.resolve()
    assert bound.manifest_path.parent == source.parent
