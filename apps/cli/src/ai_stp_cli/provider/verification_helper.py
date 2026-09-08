"""Cryptographic verification inside the CLI's isolated, pinned verifier runtime.

This script is launched by filename with its own dependency environment. It does
not import the CLI or execute provider code. Only a verified attestation supplies
its returned publisher, subject and source commit.
"""

import hashlib
import importlib
import json
import platform
import re
import sys
from pathlib import Path
from typing import Any, cast


def verify(artifact: Path, provenance: dict[str, Any], expected: dict[str, str]) -> dict[str, str]:
    api = cast(Any, importlib.import_module("pypi_attestations"))

    distribution = api.Distribution.from_file(artifact)
    document = api.Provenance.model_validate(provenance)
    policy = api.GitHubPublisher(
        repository=expected["repository"],
        workflow=expected["workflow"],
        environment=expected["environment"],
    )
    for bundle in document.attestation_bundles:
        for attestation in bundle.attestations:
            try:
                attestation.verify(identity=policy, dist=distribution, offline=True)
            except api.VerificationError:
                continue
            claims = attestation.certificate_claims
            source = next(
                (
                    claims[key]
                    for key in ("1.3.6.1.4.1.57264.1.13", "1.3.6.1.4.1.57264.1.3")
                    if re.fullmatch(r"[0-9a-f]{40}", claims.get(key, ""))
                ),
                "",
            )
            if not source:
                continue
            return {
                "repository": expected["repository"],
                "workflow": expected["workflow"],
                "environment": expected["environment"],
                "subject_name": artifact.name,
                "subject_digest": "sha256:" + hashlib.sha256(artifact.read_bytes()).hexdigest(),
                "source_commit": source,
                "runtime_architecture": platform.machine(),
                "runtime_python": platform.python_version(),
            }
    raise ValueError("no attestation verified against the pinned publisher and source commit")


if __name__ == "__main__":
    try:
        artifact = Path(sys.argv[1])
        provenance = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
        policy = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
        print(json.dumps(verify(artifact, provenance, policy), sort_keys=True))
    except Exception as error:
        stage = "dependency" if isinstance(error, (ImportError, OSError)) else "verification"
        print(json.dumps({"stage": stage, "error": type(error).__name__}), file=sys.stderr)
        raise SystemExit(1) from None
