"""Qualify one docs image in a bounded, isolated, disposable native container."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import signal
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

ROLE = "ai-stp.qualification.role"
SOURCE = "ai-stp.qualification.source"
ATTEMPT = "ai-stp.qualification.attempt"


def docker(*arguments: str, timeout: int = 10) -> str:
    return subprocess.check_output(["docker", *arguments], text=True, timeout=timeout)


def inspect_container(name: str) -> dict[str, Any] | None:
    result = subprocess.run(
        ["docker", "container", "inspect", "--format", "{{json .}}", name],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode:
        if "No such" in result.stderr:
            return None
        raise RuntimeError("cannot inspect the owned docs fixture")
    value = json.loads(result.stdout)
    if not isinstance(value, dict):
        raise ValueError("invalid container inspection")
    return value


def owned_id(metadata: dict[str, Any], source: str, attempt: str) -> str:
    container_id = metadata.get("Id")
    labels = metadata.get("Config", {}).get("Labels") or {}
    if (
        not isinstance(container_id, str)
        or re.fullmatch("[0-9a-f]{64}", container_id) is None
        or labels.get(ROLE) != "docs-runtime"
        or labels.get(SOURCE) != source
        or labels.get(ATTEMPT) != attempt
    ):
        raise ValueError("docs fixture ownership changed")
    return container_id


def validate_runtime(metadata: dict[str, Any], status: str) -> dict[str, Any]:
    fields = dict(line.split(":", 1) for line in status.splitlines() if ":" in line)
    uids = [int(v) for v in fields.get("Uid", "").split()]
    gids = [int(v) for v in fields.get("Gid", "").split()]
    host = metadata["HostConfig"]
    configured_user = metadata["Config"].get("User")
    if (
        fields.get("Name", "").strip() != "nginx"
        or len(uids) != 4
        or len(gids) != 4
        or any(v <= 0 for v in [*uids, *gids])
        or int(fields.get("CapEff", "1"), 16) != 0
        or metadata["State"]["Running"] is not True
        or not isinstance(configured_user, str)
        or configured_user.split(":", 1)[0] in {"", "0", "root"}
        or host["ReadonlyRootfs"] is not True
        or host["NetworkMode"] != "none"
        or host["Memory"] != 256 * 1024 * 1024
        or host["PidsLimit"] != 128
        or host["NanoCpus"] != 1_000_000_000
        or host["IpcMode"] != "private"
        or host["PidMode"] != ""
        or "ALL" not in (host["CapDrop"] or [])
        or not any(v.startswith("no-new-privileges") for v in host["SecurityOpt"] or [])
    ):
        raise ValueError("docs runtime is privileged or lacks fixture isolation")
    return {"uids": uids, "gids": gids, "effective_capabilities": 0}


def page_proof(body: str, language: str) -> dict[str, Any]:
    match = re.search(r"""<html\b[^>]*\blang=["']([^"']+)["']""", body, re.IGNORECASE)
    if len(body.encode()) > 2 * 1024 * 1024 or match is None or match[1] != language:
        raise ValueError("docs page is missing or has the wrong language")
    return {"language": language, "sha256": hashlib.sha256(body.encode()).hexdigest()}


def qualify(image: str, source: str) -> dict[str, Any]:
    if re.fullmatch("[0-9a-f]{40}", source) is None:
        raise ValueError("exact source commit required")
    image_id = docker("image", "inspect", "--format", "{{.Id}}", image).strip()
    if re.fullmatch("sha256:[0-9a-f]{64}", image_id) is None:
        raise ValueError("exact image identity required")
    attempt = uuid.uuid4().hex
    name = "ai-stp-docs-qualification-" + attempt
    try:
        container_id = docker(
            "run",
            "--detach",
            "--name",
            name,
            "--label",
            ROLE + "=docs-runtime",
            "--label",
            SOURCE + "=" + source,
            "--label",
            ATTEMPT + "=" + attempt,
            "--network",
            "none",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,noexec,size=32m",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            "128",
            "--memory",
            "256m",
            "--cpus",
            "1",
            image_id,
            timeout=20,
        ).strip()
        metadata = inspect_container(name)
        if metadata is None or owned_id(metadata, source, attempt) != container_id:
            raise ValueError("docs fixture identity changed after creation")
        deadline = time.monotonic() + 30
        while True:
            try:
                russian = docker(
                    "exec",
                    container_id,
                    "wget",
                    "-qO-",
                    "-T",
                    "3",
                    "http://127.0.0.1:8080/",
                    timeout=5,
                )
                break
            except subprocess.CalledProcessError:
                metadata = inspect_container(name)
                if (
                    metadata is None
                    or metadata["State"]["Running"] is not True
                    or time.monotonic() >= deadline
                ):
                    raise RuntimeError("docs fixture did not become ready") from None
                time.sleep(0.25)
        english = docker(
            "exec", container_id, "wget", "-qO-", "-T", "3", "http://127.0.0.1:8080/en/", timeout=5
        )
        metadata = inspect_container(name)
        if metadata is None or owned_id(metadata, source, attempt) != container_id:
            raise ValueError("docs fixture identity changed during observation")
        identity = validate_runtime(metadata, docker("exec", container_id, "cat", "/proc/1/status"))
        proof = {
            "schema_version": 1,
            "evidence_type": "isolated_native_docs_runtime",
            "source_commit": source,
            "image_id": image_id,
            "configured_user": metadata["Config"]["User"],
            **identity,
            "read_only_rootfs": True,
            "memory_bytes": metadata["HostConfig"]["Memory"],
            "pids_limit": metadata["HostConfig"]["PidsLimit"],
            "cpu_limit": 1,
            "network": "none",
            "no_new_privileges": True,
            "pages": {"/": page_proof(russian, "ru"), "/en/": page_proof(english, "en")},
        }
    finally:
        metadata = inspect_container(name)
        if metadata is not None:
            docker("rm", "--force", owned_id(metadata, source, attempt), timeout=20)
    return {**proof, "owned_fixture_removed": True}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--proof", type=Path, required=True)
    args = parser.parse_args()

    def interrupted(_number: int, _frame: object) -> None:
        raise InterruptedError("docs fixture interrupted")

    signal.signal(signal.SIGTERM, interrupted)
    proof = qualify(args.image, args.source)
    args.proof.write_text(json.dumps(proof, indent=2) + "\n")
    print(json.dumps(proof, indent=2))


if __name__ == "__main__":
    main()
