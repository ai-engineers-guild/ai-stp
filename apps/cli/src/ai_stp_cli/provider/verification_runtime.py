"""Bootstrap a pinned verifier without changing the installed native CLI."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.paths import data_dir, ensure_directory, write_private
from ai_stp_cli.provider.release import IndexPublisherRule

PYTHON_VERSION = "3.14.6"
TIMEOUT_SECONDS = 300


def python_request() -> str:
    return PYTHON_VERSION


def verify(
    artifact: Path, provenance: Mapping[str, object], rule: IndexPublisherRule
) -> dict[str, str]:
    runtime = data_dir() / "provider-verifier"
    ensure_directory(runtime)
    provenance_file = artifact.parent / f"{artifact.name}.provenance.json"
    policy_file = artifact.parent / f"{artifact.name}.publisher.json"
    write_private(provenance_file, json.dumps(dict(provenance)))
    write_private(
        policy_file,
        json.dumps(
            {
                "repository": rule.repository,
                "workflow": rule.workflow,
                "environment": rule.environment,
            }
        ),
    )
    resources = Path(__file__).parent
    command = [
        sys.executable,
        "-m",
        "uv",
        "--no-config",
        "run",
        "--no-project",
        "--isolated",
        "--no-build",
        "--default-index",
        "https://pypi.org/simple",
        "--python",
        python_request(),
        "--with-requirements",
        str(resources / "verifier-requirements.txt"),
        "python",
        str(resources / "verification_helper.py"),
        str(artifact),
        str(provenance_file),
        str(policy_file),
    ]
    environment = {
        key: value
        for key, value in os.environ.items()
        if key
        not in {
            "PYTHONPATH",
            "PYTHONHOME",
            "VIRTUAL_ENV",
            "UV_PROJECT_ENVIRONMENT",
            "UV_INDEX",
            "UV_DEFAULT_INDEX",
            "UV_INDEX_URL",
            "UV_EXTRA_INDEX_URL",
            "UV_FIND_LINKS",
            "UV_NO_INDEX",
            "UV_PROJECT",
            "PIP_INDEX_URL",
            "PIP_EXTRA_INDEX_URL",
            "UV_WORKING_DIR",
        }
    }
    environment.update(
        UV_CACHE_DIR=str(runtime / "cache"), UV_HTTP_TIMEOUT="30", UV_HTTP_RETRIES="1"
    )
    try:
        completed = subprocess.run(
            command,
            cwd=runtime,
            env=environment,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise CliFailure(
            "AI_STP_DEPENDENCY_UNAVAILABLE",
            "index provenance verification is unavailable",
            details={"exception": type(error).__name__},
            retryable=True,
        ) from error
    if completed.returncode != 0:
        try:
            failure: object = json.loads(completed.stderr.strip().splitlines()[-1])
            verified_failure = (
                isinstance(failure, dict)
                and cast(dict[str, object], failure).get("stage") == "verification"
            )
        except (ValueError, IndexError):
            verified_failure = False
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED" if verified_failure else "AI_STP_DEPENDENCY_UNAVAILABLE",
            "the provider wheel has no acceptable PEP 740 provenance"
            if verified_failure
            else "index provenance verification is unavailable",
            details={"project": rule.pypi_project, "verifier_exit": str(completed.returncode)},
            retryable=not verified_failure,
        )
    try:
        raw: object = json.loads(completed.stdout)
        if not isinstance(raw, dict):
            raise ValueError("not an object")
        document = cast(dict[str, object], raw)
        if not all(isinstance(value, str) for value in document.values()):
            raise ValueError("invalid verification fields")
        result = cast(dict[str, str], document)
        if not all(
            result.get(key)
            for key in (
                "repository",
                "workflow",
                "environment",
                "subject_name",
                "subject_digest",
                "source_commit",
                "runtime_architecture",
            )
        ):
            raise ValueError("incomplete verification result")
    except ValueError as error:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the provider wheel has no acceptable PEP 740 provenance",
            details={"project": rule.pypi_project},
        ) from error
    write_private(
        artifact.parent / f"{artifact.name}.verification.json", json.dumps(result, sort_keys=True)
    )
    return result
