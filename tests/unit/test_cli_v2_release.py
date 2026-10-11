"""Native archives bind a portable dependency inventory to the exact executable."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "apps" / "cli-v2" / "scripts"


def _load(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sbom = _load("release_sbom")
packaging = _load("package_release")
VERSION = "0.1.0-preview.2"
REVISION = "a" * 40
TARGET = "x86_64-unknown-linux-gnu"


def _inventory() -> tuple[dict[str, Any], bytes]:
    packages: list[dict[str, Any]] = []
    nodes: list[dict[str, Any]] = []
    lock = "version = 4\n"
    rows: list[tuple[str, str, list[tuple[str, str | None]]]] = [
        ("ai-stp-cli-v2", VERSION, [("runtime", None), ("builder", "build"), ("test", "dev")]),
        ("runtime", "1.2.3", [("shared", None)]),
        ("builder", "4.0.0", [("shared", None)]),
        ("shared", "2.0.0", []),
        ("test", "1.0.0", [("test-only", None)]),
        ("test-only", "1.0.0", []),
    ]
    for name, version, deps in rows:
        packages.append(
            {
                "id": name,
                "name": name,
                "version": version,
                "source": None if name == "ai-stp-cli-v2" else sbom.REGISTRY,
                "license": "MIT/Apache-2.0",
                "manifest_path": "/private/build/path/Cargo.toml",
            }
        )
        nodes.append(
            {
                "id": name,
                "deps": [
                    {"pkg": dependency, "dep_kinds": [{"kind": kind}]} for dependency, kind in deps
                ],
            }
        )
        lock += f'\n[[package]]\nname = "{name}"\nversion = "{version}"\n'
        if name != "ai-stp-cli-v2":
            lock += f'source = "{sbom.REGISTRY}"\nchecksum = "{"b" * 64}"\n'
    return {
        "packages": packages,
        "resolve": {"root": "ai-stp-cli-v2", "nodes": nodes},
    }, lock.encode()


def _build(metadata: dict[str, Any], lock: bytes, target: str = TARGET) -> bytes:
    return sbom.inventory(
        metadata,
        lock,
        version=VERSION,
        revision=REVISION,
        target=target,
        binary_digest=packaging.sha256(b"binary"),
    )


def test_sbom_keeps_build_and_runtime_graph_without_dev_or_local_paths() -> None:
    metadata, lock = _inventory()
    value = _build(metadata, lock)
    document = json.loads(value)
    assert [component["name"] for component in document["components"]] == [
        "builder",
        "runtime",
        "shared",
    ]
    assert document["dependencies"][0]["dependsOn"] == [
        "pkg:cargo/builder@4.0.0",
        "pkg:cargo/runtime@1.2.3",
    ]
    assert document["components"][0]["hashes"][0]["content"] == "b" * 64
    assert b"/private" not in value
    metadata["packages"].reverse()
    metadata["resolve"]["nodes"].reverse()
    assert _build(metadata, lock) == value
    with pytest.raises(ValueError, match="no exact source checksum"):
        _build(metadata, lock.replace(b"b" * 64, b"invalid"))
    next(package for package in metadata["packages"] if package["name"] == "runtime")["source"] = (
        "git+https://example.invalid/unlocked"
    )
    with pytest.raises(ValueError, match=r"only locked crates\.io"):
        _build(metadata, lock)


@pytest.mark.parametrize("windows", [False, True])
def test_archive_refuses_missing_or_changed_sbom_before_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    windows: bool,
) -> None:
    metadata, lock = _inventory()
    binary = "ai-stp-v2.exe" if windows else "ai-stp-v2"
    target = "x86_64-pc-windows-msvc" if windows else TARGET
    files = {binary: b"binary", "LICENSE": b"license", sbom.NAME: _build(metadata, lock, target)}
    manifest = {
        "schema_version": 2,
        "package": "ai-stp-cli-v2",
        "version": VERSION,
        "release_channel": "preview",
        "source_commit": REVISION,
        "target": target,
        "binary": binary,
        "binary_sha256": packaging.sha256(files[binary]),
        "license_sha256": packaging.sha256(files["LICENSE"]),
        "sbom": sbom.NAME,
        "sbom_sha256": packaging.sha256(files[sbom.NAME]),
    }
    files["release.json"] = json.dumps(manifest).encode()
    archive = tmp_path / ("release.zip" if windows else "release.tar.gz")
    packed = packaging.archive_bytes(files, binary, windows)
    assert packaging.archive_bytes(dict(reversed(list(files.items()))), binary, windows) == packed
    archive.write_bytes(packed)
    assert packaging.read_archive(archive, binary) == files
    missing = {name: value for name, value in files.items() if name != sbom.NAME}
    archive.write_bytes(packaging.archive_bytes(missing, binary, windows))
    with pytest.raises(ValueError, match=r"archive (member inventory|must contain)"):
        packaging.read_archive(archive, binary)
    calls: list[Path] = []

    def probe(path: Path, _version: str) -> None:
        calls.append(path)

    monkeypatch.setattr(packaging, "probe", probe)
    altered = files.copy()
    altered[sbom.NAME] = b"{}"
    archive.write_bytes(packaging.archive_bytes(altered, binary, windows))
    options = argparse.Namespace(
        archive=archive,
        target=target,
        version=VERSION,
        revision=REVISION,
        install_directory=tmp_path / "installed",
    )
    with pytest.raises(ValueError, match="manifest or payload identity differs"):
        packaging.verify(options)
    assert not calls and not options.install_directory.exists()
    wrong_identity = json.loads(files[sbom.NAME])
    wrong_identity["metadata"]["component"]["version"] = "0.0.0"
    altered[sbom.NAME] = json.dumps(wrong_identity).encode()
    changed_manifest = {**manifest, "sbom_sha256": packaging.sha256(altered[sbom.NAME])}
    altered["release.json"] = json.dumps(changed_manifest).encode()
    archive.write_bytes(packaging.archive_bytes(altered, binary, windows))
    with pytest.raises(ValueError, match="SBOM differs from the archive identity"):
        packaging.verify(options)
    assert not calls and not options.install_directory.exists()
    archive.write_bytes(packed)
    packaging.verify(options)
    assert calls == [options.install_directory / binary]
