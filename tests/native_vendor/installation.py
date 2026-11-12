"""Exercise public native installation only inside disposable native CI users."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Any, cast

from release_scripts.cli_artifacts import check_checksum_files, digest, names
from tests.support.native_runner import disposable_runner

from .common import environment


def prepare(root: Path, source: str) -> tuple[Path, dict[str, Any]] | None:
    selected = os.environ.get("AI_STP_REQUIRE_ENGINE", "false")
    assert selected in {"true", "false"}
    location = os.environ.get("AI_STP_NATIVE_ENGINE_ARCHIVES", "")
    assert bool(location) == (selected == "true"), "Engine owner selection is incomplete"
    if not location:
        return None
    disposable_runner()
    assert re.fullmatch(r"[0-9a-f]{40}", source)
    producer = os.environ.get("AI_STP_NATIVE_ENGINE_SOURCE_RUN", "")
    expected_source = os.environ.get("AI_STP_NATIVE_ENGINE_SOURCE", "")
    diagnostic = bool(producer)
    assert bool(expected_source) == diagnostic
    if diagnostic:
        assert producer.isdecimal() and os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
        assert re.fullmatch(r"[0-9a-f]{40}", expected_source)
    else:
        expected_source = source
    directory = Path(location)
    target, executable_name, extension = {
        "Linux": ("x86_64-unknown-linux-gnu", "ai-stp", "tar.gz"),
        "Darwin": ("aarch64-apple-darwin", "ai-stp", "tar.gz"),
        "Windows": ("x86_64-pc-windows-msvc", "ai-stp.exe", "zip"),
    }[platform.system()]
    declaration = directory / f"qualification-{target}.json"
    assert declaration.is_file() and not declaration.is_symlink()
    assert declaration.stat().st_size < 16 * 1024
    proof = json.loads(declaration.read_bytes())
    assert proof["schema_version"] == 1 and proof["source_sha"] == expected_source
    assert proof["target"] == target
    version = proof["version"]
    expected = names(version, target)
    assert {path.name for path in directory.iterdir()} == expected | {declaration.name}
    assert set(proof["files"]) == expected
    for name, expected_digest in proof["files"].items():
        assert digest(directory / name) == expected_digest
    check_checksum_files(directory, proof["files"])
    archive = directory / f"ai-stp-cli-{version}-{target}.{extension}"
    members = {executable_name, "LICENSE", "ai-stp-cli.cdx.json", "release.json"}
    if extension == "zip":
        with zipfile.ZipFile(archive) as bundle:
            assert set(bundle.namelist()) == members and len(bundle.infolist()) == len(members)
            assert all(0 < item.file_size < 256 * 1024 * 1024 for item in bundle.infolist())
            documents = {name: bundle.read(name) for name in members}
    else:
        with tarfile.open(archive, "r:gz") as bundle:
            records = bundle.getmembers()
            assert len(records) == len(members) and {item.name for item in records} == members
            assert all(item.isfile() and 0 < item.size < 256 * 1024 * 1024 for item in records)
            documents: dict[str, bytes] = {}
            for name in members:
                stream = bundle.extractfile(name)
                assert stream is not None
                with stream:
                    documents[name] = stream.read()
    manifest = json.loads(documents["release.json"])
    assert manifest["schema_version"] == 2 and manifest["source_commit"] == expected_source
    assert manifest["target"] == target and manifest["version"] == version
    assert manifest["binary"] == executable_name
    for name, key in [
        (executable_name, "binary_sha256"),
        ("LICENSE", "license_sha256"),
        ("ai-stp-cli.cdx.json", "sbom_sha256"),
    ]:
        assert hashlib.sha256(documents[name]).hexdigest() == manifest[key]
    executable = root / executable_name
    with executable.open("xb") as destination:
        destination.write(documents[executable_name])
    executable.chmod(0o700)
    return executable.resolve(), {
        "source_sha": expected_source,
        "producer_run_id": producer or os.environ["GITHUB_RUN_ID"],
        "diagnostic_only": diagnostic,
        "version": version,
        "binary_sha256": manifest["binary_sha256"],
        "target": target,
    }


def passport_digest(document: dict[str, Any]) -> str:
    """This controlled fixture uses the ASCII/integer subset of JCS."""

    def supported(value: Any) -> bool:
        if isinstance(value, dict):
            return all(
                isinstance(key, str) and key.isascii() and supported(child)
                for key, child in cast(dict[object, object], value).items()
            )
        if isinstance(value, list):
            return all(supported(child) for child in cast(list[object], value))
        if isinstance(value, str):
            return value.isascii()
        return value is None or type(value) is bool or (type(value) is int and abs(value) < 2**53)

    assert supported(document), "Fixture passport is outside its declared JCS subset"
    encoded = json.dumps(
        document, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode()
    return "sha256:" + hashlib.sha256(b"ai-stp:passport:v1\0" + encoded).hexdigest()


class Installation:
    """Separate CLI processes retain the original context and exact reviewed operation."""

    def __init__(self, executable: Path, root: Path, vendor_variable: str) -> None:
        disposable_runner()
        self.executable = executable
        self.root = root
        root.mkdir()
        self.home, self.vendor_home, self.project = root / "h", root / "v", root / "p"
        self.state, self.source = root / "s", root / "q"
        for path in [
            self.home,
            self.vendor_home,
            self.project,
            self.state,
            self.source,
            root / "t",
        ]:
            path.mkdir()
        self.environment = environment(root, vendor_variable, self.vendor_home)
        self.unowned = self.vendor_home / "user-note"
        self.unowned.write_bytes(b"unowned fixture remains\n")
        custody = self.run(["configuration", "native", "custody"])
        assert custody["operations"] == [] and custody["pending"] is None
        initial = self.run(
            [
                "device",
                "initialize",
                "plan",
                "--credential-store",
                "os_keyring" if os.name == "nt" else "file",
            ]
        )
        self.enact(initial, ["device", "initialize", "apply"])
        contexts: list[str] = []
        for label in ["Original vendor fixture", "Another fixture view"]:
            review = self.run(["context", "create", "plan", "--label", label])
            identifier = review["plan"]["change"]["context"]["context_id"]
            assert isinstance(identifier, str)
            contexts.append(identifier)
            self.enact(review, ["context", "apply"])
        self.context, self.other = contexts

    def run(self, arguments: list[str], *, refused: bool = False) -> dict[str, Any]:
        command = [str(self.executable), *arguments]
        if arguments[:2] != ["context", "apply"] and arguments[:3] != [
            "device",
            "initialize",
            "apply",
        ]:
            command.extend(["--state-dir", str(self.state)])
        command.append("--json")
        with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
            result = subprocess.run(
                command,
                cwd=self.root,
                env=self.environment,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=errors,
                check=False,
                timeout=30,
            )
            assert output.tell() < 8 * 1024 * 1024 and errors.tell() == 0
            output.seek(0)
            envelope = json.load(output)
        if refused:
            assert result.returncode != 0 and envelope["ok"] is False
            assert envelope["error"]["code"] == "AI_STP_PRECONDITION_FAILED"
            return cast(dict[str, Any], envelope["error"])
        if result.returncode != 0:
            self.inspect_failure(arguments)
        assert result.returncode == 0 and envelope["ok"] is True, envelope
        return cast(dict[str, Any], envelope["data"])

    def inspect_failure(self, arguments: list[str]) -> None:
        if os.name != "nt":
            return
        executable = shutil.which("pwsh")
        if executable is None:
            print("Native fixture ACL inspection is unavailable", file=sys.stderr)
            return
        paths = {
            "case": str(self.root),
            "temporary": str(self.root.parent),
            "state": str(self.state),
            "vendor": str(self.vendor_home),
            "control": str(self.vendor_home / ".ai-stp-native"),
        }
        try:
            result = subprocess.run(
                [
                    executable,
                    "-NoProfile",
                    "-NonInteractive",
                    "-File",
                    str(Path(__file__).with_name("inspect-fixture.ps1")),
                ],
                env={**self.environment, "AI_STP_FIXTURE_DIRECTORIES": json.dumps(paths)},
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
            )
            print(
                json.dumps(
                    {
                        "fixture_command": arguments[:3],
                        "directory_metadata": result.stdout[: 16 * 1024],
                        "inspection_exit": result.returncode,
                    }
                ),
                file=sys.stderr,
            )
        except (OSError, subprocess.TimeoutExpired):
            print("Native fixture ACL inspection failed", file=sys.stderr)

    def enact(self, review: dict[str, Any], command: list[str]) -> dict[str, Any]:
        plan = self.root / (review["plan"]["operation_id"] + ".json")
        plan.write_text(json.dumps(review["plan"]), encoding="utf-8")
        return self.run([*command, "--plan", str(plan), "--plan-digest", review["plan_digest"]])

    def install(self, harness: str, kind: str, name: str, scope: str) -> dict[str, Any]:
        author_input = self.root / "author.json"
        author_input.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "directory": str(self.source),
                    "harness_id": harness,
                    "component_type": kind,
                    "name": name,
                    "license_spdx": "MIT",
                }
            )
        )
        authored = self.run(
            [
                "task",
                "start",
                "--intent",
                "author",
                "--idempotency-key",
                "native-vendor-author-0001",
                "--input",
                str(author_input),
            ]
        )
        assert authored["state"] == "completed"
        setup = authored["outcome"]["setup_id"]
        self.component_id = str(authored["outcome"]["component_id"])
        version = self.run(
            ["local", "version", "show", "--kind", "setup", "--id", setup, "--version", "1.0"]
        )

        def passport(value: Any) -> dict[str, Any] | None:
            if isinstance(value, dict):
                mapping = cast(dict[str, Any], value)
                if mapping.get("kind") == "setup" and mapping.get("stable_id") == setup:
                    return mapping
                for child in mapping.values():
                    if (found := passport(child)) is not None:
                        return found
            return None

        document = passport(version)
        assert document is not None
        request = self.root / "native.json"
        request.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "setup": {
                        "stable_id": setup,
                        "version": "1.0",
                        "passport_digest": passport_digest(document),
                    },
                    "harness_id": harness,
                    "operation": "install",
                    "roots": {scope: str(self.vendor_home)},
                }
            )
        )
        review = self.run(
            ["configuration", "native", "plan", "--context", self.context, "--input", str(request)]
        )
        assert review["configuration_changed"] is False
        selected = self.run(["context", "select", "plan", "--context", self.other])
        self.enact(selected, ["context", "apply"])
        self.enact(review, ["configuration", "native", "prepare"])
        return self.apply(review)

    @staticmethod
    def apply_arguments(review: dict[str, Any]) -> list[str]:
        return [
            "configuration",
            "native",
            "apply",
            "--operation",
            review["plan"]["operation_id"],
            "--plan-digest",
            review["plan_digest"],
        ]

    def apply(self, review: dict[str, Any]) -> dict[str, Any]:
        receipt = self.run(self.apply_arguments(review))
        assert receipt["configuration_changed"] is True and receipt["load_state"] == "not_observed"
        assert receipt["original_context"]["context_id"] == self.context
        assert self.run(self.apply_arguments(review)) == receipt
        assert self.unowned.read_bytes() == b"unowned fixture remains\n"
        return receipt

    def remove(self, receipt: dict[str, Any]) -> dict[str, Any]:
        review = self.run(
            [
                "configuration",
                "native",
                "remove",
                "plan",
                "--operation",
                receipt["operation_id"],
                "--plan-digest",
                receipt["review_digest"],
            ]
        )
        self.enact(review, ["configuration", "native", "prepare"])
        pending = self.run(["configuration", "native", "pending"])["pending"]
        assert pending["operation_id"] == review["plan"]["operation_id"]
        assert pending["plan_digest"] == review["plan_digest"]
        assert pending["original_context"]["context_id"] == self.context
        return review

    def removed(self) -> None:
        assert self.run(["configuration", "native", "pending"])["pending"] is None
        assert (
            self.run(["configuration", "native", "effective", "--context", self.context])["setups"]
            == []
        )
        assert (
            self.run(["configuration", "native", "effective", "--context", self.other])["setups"]
            == []
        )
        assert self.run(["context", "list"])["selected"]["context_id"] == self.other
        assert self.unowned.read_bytes() == b"unowned fixture remains\n"
