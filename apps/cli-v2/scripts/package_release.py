"""Build and verify the bounded, standalone Rust preview release archives."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import re
import stat
import subprocess
import tarfile
import tempfile
import tomllib
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
CRATE = ROOT / "apps" / "cli-v2"
TARGETS = {
    "x86_64-unknown-linux-gnu": "ai-stp-v2",
    "aarch64-apple-darwin": "ai-stp-v2",
    "x86_64-pc-windows-msvc": "ai-stp-v2.exe",
}
MAX_ARCHIVE = 256 * 1024 * 1024


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def refuse(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def probe(binary: Path, version: str) -> None:
    with tempfile.TemporaryDirectory(prefix="ai-stp-release-home-") as directory:
        environment = {
            key: value
            for key, value in os.environ.items()
            if key.upper() in {"SYSTEMROOT", "WINDIR"}
        }
        environment.update(
            PATH="",
            HOME=directory,
            USERPROFILE=directory,
            XDG_DATA_HOME=directory,
            XDG_CONFIG_HOME=directory,
            XDG_CACHE_HOME=directory,
        )
        result = subprocess.run(
            [str(binary.resolve()), "version", "--json"],
            cwd=directory,
            env=environment,
            capture_output=True,
            timeout=30,
            check=True,
        )
        refuse(not result.stderr, "the standalone binary wrote unexpected stderr")
        data = json.loads(result.stdout)["data"]
        refuse(
            data["cli_version"] == version
            and data["runtime"] == "rust"
            and data["release_channel"] == "preview",
            "the executable does not identify the requested Rust preview",
        )


def archive_bytes(files: dict[str, bytes], binary: str, windows: bool) -> bytes:
    buffer = io.BytesIO()
    if windows:
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in sorted(files.items()):
                entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                entry.create_system = 3
                entry.external_attr = (stat.S_IFREG | (0o755 if name == binary else 0o644)) << 16
                entry.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(entry, data)
    else:
        with (
            gzip.GzipFile(fileobj=buffer, mode="wb", filename="", mtime=0) as compressed,
            tarfile.open(fileobj=compressed, mode="w", format=tarfile.USTAR_FORMAT) as archive,
        ):
            for name, data in sorted(files.items()):
                entry = tarfile.TarInfo(name)
                entry.size = len(data)
                entry.mode = 0o755 if name == binary else 0o644
                archive.addfile(entry, io.BytesIO(data))
    return buffer.getvalue()


def build(args: argparse.Namespace) -> None:
    package = tomllib.loads((CRATE / "Cargo.toml").read_text(encoding="utf-8"))["package"]
    refuse(package["version"] == args.version, "Cargo version differs from the requested version")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    refuse(revision == args.revision, "checkout differs from the requested source revision")
    compiler = subprocess.check_output(["rustc", "-vV"], cwd=CRATE, text=True)
    refuse(f"host: {args.target}\n" in compiler, "compiler host differs from the archive target")
    binary = TARGETS[args.target]
    refuse(args.binary.is_file() and not args.binary.is_symlink(), "binary must be a regular file")
    probe(args.binary, args.version)
    executable = args.binary.read_bytes()
    license_bytes = (ROOT / "LICENSE").read_bytes()
    manifest = {
        "schema_version": 1,
        "package": "ai-stp-cli-v2",
        "version": args.version,
        "release_channel": "preview",
        "source_commit": revision,
        "target": args.target,
        "binary": binary,
        "binary_sha256": sha256(executable),
        "license_sha256": sha256(license_bytes),
    }
    files = {
        binary: executable,
        "LICENSE": license_bytes,
        "release.json": (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode(),
    }
    windows = args.target.endswith("windows-msvc")
    extension = "zip" if windows else "tar.gz"
    name = f"ai-stp-cli-v2-{args.version}-{args.target}.{extension}"
    data = archive_bytes(files, binary, windows)
    refuse(len(data) <= MAX_ARCHIVE, "archive exceeds the release size bound")
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / name).write_bytes(data)
    (args.output / f"{name}.sha256").write_text(f"{sha256(data)}  {name}\n", encoding="ascii")
    print(json.dumps({"archive": name, "sha256": sha256(data), "source_commit": revision}))


def read_archive(path: Path, binary: str) -> dict[str, bytes]:
    refuse(path.stat().st_size <= MAX_ARCHIVE, "archive exceeds the release size bound")
    limits = {binary: MAX_ARCHIVE, "LICENSE": 64 * 1024, "release.json": 4096}
    expected = set(limits)
    files: dict[str, bytes] = {}
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            refuse(len(entries) == 3, "archive must contain exactly three regular files")
            for entry in entries:
                mode = entry.external_attr >> 16
                refuse(
                    entry.filename in expected
                    and entry.filename not in files
                    and mode == stat.S_IFREG | (0o755 if entry.filename == binary else 0o644)
                    and entry.file_size <= limits[entry.filename],
                    "unexpected archive member",
                )
                files[entry.filename] = archive.read(entry)
    else:
        with tarfile.open(path, "r:gz") as archive:
            for entry in archive:
                refuse(
                    entry.name in expected
                    and entry.name not in files
                    and entry.isfile()
                    and entry.size <= limits[entry.name]
                    and entry.mode == (0o755 if entry.name == binary else 0o644),
                    "unexpected archive member",
                )
                stream = archive.extractfile(entry)
                refuse(stream is not None, "archive member has no payload")
                if stream is not None:
                    files[entry.name] = stream.read(limits[entry.name] + 1)
    refuse(set(files) == expected, "archive member inventory differs")
    return files


def verify(args: argparse.Namespace) -> None:
    binary = TARGETS[args.target]
    files = read_archive(args.archive, binary)
    manifest: dict[str, Any] = json.loads(files["release.json"])
    expected = {
        "schema_version": 1,
        "package": "ai-stp-cli-v2",
        "version": args.version,
        "release_channel": "preview",
        "source_commit": args.revision,
        "target": args.target,
        "binary": binary,
        "binary_sha256": sha256(files[binary]),
        "license_sha256": sha256(files["LICENSE"]),
    }
    refuse(manifest == expected, "archive manifest or payload identity differs")
    # Never use extractall: only the three validated, literal members are written.
    args.install_directory.mkdir(parents=True, exist_ok=False)
    for name, data in files.items():
        path = args.install_directory / name
        with path.open("xb") as stream:
            stream.write(data)
        path.chmod(0o755 if name == binary else 0o644)
    probe(args.install_directory / binary, args.version)
    print(json.dumps({"verified": str(args.archive), "source_commit": args.revision}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("build", "verify"):
        command = commands.add_parser(name)
        command.add_argument("--version", required=True)
        command.add_argument("--revision", required=True)
        command.add_argument("--target", choices=sorted(TARGETS), required=True)
        if name == "build":
            command.add_argument("--binary", type=Path, required=True)
            command.add_argument("--output", type=Path, required=True)
        else:
            command.add_argument("--archive", type=Path, required=True)
            command.add_argument("--install-directory", type=Path, required=True)
    args = parser.parse_args()
    refuse(
        bool(re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+-preview\.[0-9]+", args.version)),
        "preview version required",
    )
    refuse(bool(re.fullmatch(r"[0-9a-f]{40}", args.revision)), "exact Git revision required")
    (build if args.command == "build" else verify)(args)


if __name__ == "__main__":
    main()
