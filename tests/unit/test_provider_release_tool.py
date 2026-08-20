from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from ai_stp_cli.provider import release

TOOL = Path(__file__).parents[2] / "apps" / "cli" / "tools" / "provider_release.py"


def _run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), *arguments],
        text=True,
        capture_output=True,
        check=False,
    )


@pytest.mark.skipif(os.name == "nt", reason="provider release signing requires POSIX ownership")
def test_keygen_sign_and_verify_exact_artifact(tmp_path: Path) -> None:
    private = tmp_path / "release-key.pem"
    keygen = _run("keygen", "--private-key", str(private))
    assert keygen.returncode == 0, keygen.stderr
    key = json.loads(keygen.stdout)
    if os.name != "nt":
        assert private.stat().st_mode & 0o077 == 0

    artifact = tmp_path / "provider-1.2.3"
    artifact.write_bytes(b"#!/usr/bin/env python3\n")
    artifact.chmod(0o755)
    manifest = tmp_path / "provider-1.2.3.manifest.json"
    sign = _run(
        "sign",
        "--private-key",
        str(private),
        "--provider-id",
        "provider-example",
        "--provider-version",
        "1.2.3",
        "--repository",
        "github.com/NDDev-it-com/provider-example",
        "--commit",
        "a" * 40,
        "--license",
        "AGPL-3.0-or-later",
        "--artifact",
        str(artifact),
        "--artifact-url",
        "https://github.com/NDDev-it-com/provider-example/releases/download/1.2.3/provider-1.2.3",
        "--entry-point",
        artifact.name,
        "--protocol-version",
        "3",
        "--sequence",
        "1",
        "--supported-os",
        "linux",
        "--supported-arch",
        "x86_64",
        "--output",
        str(manifest),
    )
    assert sign.returncode == 0, sign.stderr
    signed = release.parse_manifest(manifest.read_text("utf-8"))
    assert signed.signature
    assert signed.signing_key == key["key_id"]

    verified = _run(
        "verify",
        "--manifest",
        str(manifest),
        "--artifact",
        str(artifact),
        "--public-key",
        key["public_key"],
        "--key-id",
        key["key_id"],
        "--platform",
        "linux/x86_64",
    )
    assert verified.returncode == 0, verified.stderr
    assert json.loads(verified.stdout)["accepted"] is True

    artifact.write_bytes(b"tampered")
    refused = _run(
        "verify",
        "--manifest",
        str(manifest),
        "--artifact",
        str(artifact),
        "--public-key",
        key["public_key"],
        "--key-id",
        key["key_id"],
        "--platform",
        "linux/x86_64",
    )
    assert refused.returncode == 2
    assert "digest_mismatch" in refused.stderr


def test_private_key_with_exposed_permissions_is_refused(tmp_path: Path) -> None:
    private = tmp_path / "release-key.pem"
    assert _run("keygen", "--private-key", str(private)).returncode == 0
    private.chmod(0o644)
    artifact = tmp_path / "provider"
    artifact.write_bytes(b"provider")
    result = _run(
        "sign",
        "--private-key",
        str(private),
        "--provider-id",
        "provider-example",
        "--provider-version",
        "1.0.0",
        "--repository",
        "github.com/NDDev-it-com/provider-example",
        "--commit",
        "a" * 40,
        "--license",
        "AGPL-3.0-or-later",
        "--artifact",
        str(artifact),
        "--artifact-url",
        "https://example.invalid/provider-1.0.0",
        "--entry-point",
        "provider",
        "--protocol-version",
        "3",
        "--sequence",
        "1",
        "--supported-os",
        "linux",
        "--supported-arch",
        "x86_64",
        "--output",
        str(tmp_path / "manifest.json"),
    )
    if os.name == "nt":
        # Windows has no Unix mode bits for owner-only secrets; tool still runs.
        assert result.returncode in {0, 2}
    else:
        assert result.returncode == 2
        assert "permissions" in result.stderr


def test_outputs_inside_checkout_are_refused(tmp_path: Path) -> None:
    forbidden = TOOL.parent / ".forbidden-release-key"
    result = _run("keygen", "--private-key", str(forbidden))
    assert result.returncode == 2
    assert "outside" in result.stderr
    assert not forbidden.exists()
