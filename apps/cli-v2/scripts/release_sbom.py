"""Deterministic Cargo dependency inventory for one native release target.

This describes resolved normal/build dependencies, not a linker trace. Cargo's
stable metadata interface does not enumerate OS libraries or compiler internals.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tomllib
from pathlib import Path
from typing import Any

NAME = "ai-stp-cli.cdx.json"
LIMIT = 4 * 1024 * 1024
REGISTRY = "registry+https://github.com/rust-lang/crates.io-index"


def encode(document: dict[str, Any]) -> bytes:
    return (json.dumps(document, sort_keys=True, indent=2) + "\n").encode()


def inventory(
    metadata: dict[str, Any],
    lock: bytes,
    *,
    version: str,
    revision: str,
    target: str,
    binary_digest: str,
) -> bytes:
    """Keep only reachable non-dev edges and bind every registry package to its lock hash."""
    packages = {package["id"]: package for package in metadata["packages"]}
    graph = {node["id"]: node for node in metadata["resolve"]["nodes"]}
    root = metadata["resolve"]["root"]
    if packages[root]["name"] != "ai-stp-cli-v2" or packages[root]["version"] != version:
        raise ValueError("SBOM root differs from the release package")
    locked = {
        (package["name"], package["version"], package.get("source")): package
        for package in tomllib.loads(lock.decode())["package"]
    }
    edges: dict[str, list[str]] = {}
    pending = [root]
    while pending:
        identifier = pending.pop()
        if identifier in edges:
            continue
        edges[identifier] = sorted(
            {
                dependency["pkg"]
                for dependency in graph[identifier]["deps"]
                if any(kind["kind"] in (None, "build") for kind in dependency["dep_kinds"])
            }
        )
        pending.extend(edges[identifier])

    references: dict[str, str] = {}
    components: list[dict[str, Any]] = []
    for identifier in sorted(edges):
        package = packages[identifier]
        name, resolved_version, source = package["name"], package["version"], package["source"]
        if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
            raise ValueError("invalid Cargo package name in SBOM")
        reference = f"pkg:cargo/{name}@{resolved_version}"
        references[identifier] = reference
        if identifier == root:
            continue
        if source != REGISTRY:
            raise ValueError("native SBOM supports only locked crates.io dependencies")
        checksum = locked[(name, resolved_version, source)].get("checksum", "")
        if not re.fullmatch(r"[0-9a-f]{64}", checksum):
            raise ValueError("registry package has no exact source checksum")
        component: dict[str, Any] = {
            "type": "library",
            "bom-ref": reference,
            "purl": reference,
            "name": name,
            "version": resolved_version,
            "hashes": [{"alg": "SHA-256", "content": checksum}],
        }
        # Preserve the author's declaration, including legacy Cargo expressions.
        # A license name is not a claim that an SPDX expression was validated.
        if package.get("license"):
            component["licenses"] = [{"license": {"name": package["license"]}}]
        components.append(component)
    if len(set(references.values())) != len(references):
        raise ValueError("ambiguous package identity in SBOM")
    document = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "bom-ref": references[root],
                "name": "ai-stp-cli-v2",
                "version": version,
                "hashes": [{"alg": "SHA-256", "content": binary_digest}],
                "licenses": [{"license": {"name": packages[root]["license"]}}],
            },
            "properties": [
                {"name": "ai-stp:source-commit", "value": revision},
                {"name": "ai-stp:target", "value": target},
                {"name": "ai-stp:cargo-lock-sha256", "value": hashlib.sha256(lock).hexdigest()},
                {"name": "ai-stp:inventory", "value": "cargo-resolved-normal-and-build"},
            ],
        },
        "components": sorted(components, key=lambda component: component["bom-ref"]),
        "dependencies": sorted(
            [
                {"ref": references[key], "dependsOn": sorted(references[dep] for dep in deps)}
                for key, deps in edges.items()
            ],
            key=lambda edge: edge["ref"],
        ),
        "compositions": [{"aggregate": "incomplete", "assemblies": [references[root]]}],
    }
    result = encode(document)
    if len(result) > LIMIT:
        raise ValueError("native SBOM exceeds its size bound")
    return result


def build(
    crate: Path,
    *,
    version: str,
    revision: str,
    target: str,
    binary_digest: str,
) -> bytes:
    metadata = json.loads(
        subprocess.check_output(
            [
                "cargo",
                "metadata",
                "--format-version",
                "1",
                "--locked",
                "--offline",
                "--filter-platform",
                target,
            ],
            cwd=crate,
            timeout=120,
        )
    )
    return inventory(
        metadata,
        (crate / "Cargo.lock").read_bytes(),
        version=version,
        revision=revision,
        target=target,
        binary_digest=binary_digest,
    )
