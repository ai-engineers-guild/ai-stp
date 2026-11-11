"""Native image acceptance owned by the isolated scanner-runtime workflow."""

from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import uuid
from pathlib import Path
from typing import Any, cast

import pytest

pytestmark = pytest.mark.platform


@pytest.fixture
def runtime_image() -> str:
    image = os.environ.get("AI_STP_SAFETY_RUNTIME_IMAGE")
    if not image:
        pytest.skip("Requires the separate exact-image native runtime qualification owner")
    return image


def probe(image: str, case: str) -> dict[str, Any]:
    source = os.environ["AI_STP_SAFETY_RUNTIME_SOURCE"]
    assert re.fullmatch(r"[0-9a-f]{40}", source)
    expected_arch = os.environ["AI_STP_SAFETY_RUNTIME_ARCH"]
    assert expected_arch in {"amd64", "arm64"}
    assert platform.machine() == {"amd64": "x86_64", "arm64": "aarch64"}[expected_arch]
    assert image == f"ai-stp-safety-qualified:{source}-{expected_arch}"
    information = cast(
        list[dict[str, Any]],
        json.loads(subprocess.check_output(["docker", "image", "inspect", image], text=True)),
    )[0]
    assert information["Config"]["Labels"]["org.opencontainers.image.revision"] == source
    token = uuid.uuid4().hex
    name = f"ai-stp-runtime-{token}"
    fixture = Path(__file__).resolve().parents[2] / "fixtures" / "safety_runtime_probe.py"
    try:
        completed = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--interactive",
                "--name",
                name,
                "--label",
                f"ai-stp.qualification-owner={token}",
                "--network",
                "none",
                "--security-opt",
                "seccomp=unconfined",
                "--security-opt",
                "apparmor=ai-stp-worker",
                "--env",
                "AI_STP_SAFETY_REQUIRE_BWRAP=1",
                "--env",
                "AI_STP_SAFETY_EXTERNAL_CLI=1",
                "--env",
                "AI_STP_RUNTIME_PRIVATE_CANARY=controlled-private-runtime-value",
                image,
                "python",
                "-",
                case,
            ],
            input=fixture.read_text(),
            capture_output=True,
            text=True,
            check=False,
            timeout=180,
        )
        assert completed.returncode == 0, completed.stderr[-2000:]
        result = cast(dict[str, Any], json.loads(completed.stdout))
    finally:
        remaining = subprocess.run(
            ["docker", "inspect", name], capture_output=True, text=True, check=False, timeout=10
        )
        if remaining.returncode == 0:
            record = cast(list[dict[str, Any]], json.loads(remaining.stdout))[0]
            assert record["Config"]["Labels"].get("ai-stp.qualification-owner") == token
            subprocess.run(["docker", "rm", "--force", record["Id"]], check=True, timeout=10)
    assert information["Architecture"] == expected_arch
    assert result["architecture"] == {"amd64": "x86_64", "arm64": "aarch64"}[expected_arch]
    assert result["sandbox"] == "bwrap"
    proof = {
        "schema_version": 1,
        "source_sha": source,
        "image_id": information["Id"],
        "architecture": expected_arch,
        "release_authorized": False,
        "result": result,
    }
    destination = Path(os.environ["AI_STP_SAFETY_RUNTIME_PROOF_DIR"])
    destination.mkdir(parents=True, exist_ok=True)
    (destination / f"{case}.json").write_text(json.dumps(proof, indent=2) + "\n")
    return result


def test_native_go_reports_and_local_database_lifecycle(runtime_image: str) -> None:
    result = probe(runtime_image, "go")
    assert len(result["checks"]) == 7


def test_strict_runtime_environment_and_network(runtime_image: str) -> None:
    result = probe(runtime_image, "boundary")
    assert result["checks"] == {
        "private_environment_filtered": True,
        "network_namespace_distinct": True,
        "loopback_denied": True,
    }
