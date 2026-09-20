#!/usr/bin/env python3
"""Download the pinned just binary without a curl|bash installer.

CI does not call `just`: workflows execute commands directly. This script is for
developers whose package manager does not provide just.
"""

from __future__ import annotations

import hashlib
import http.client
import os
import platform
import shutil
import stat
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path

VERSION = "1.58.0"

# SHA256 values for official archives, keyed case-sensitively by GitHub Release
# asset name. Update this table before updating its consumers.
SHA256 = {
    "just-1.58.0-x86_64-unknown-linux-musl.tar.gz": (
        "4a5cc2f53e6f0f8c59092a6cc38291eb729d46a7dd95d3ae582008881b84931d"
    ),
    "just-1.58.0-aarch64-unknown-linux-musl.tar.gz": (
        "748237128c4c40cbdabc65e841d05ceba13cc23a91eaba395495894c1d9764df"
    ),
    "just-1.58.0-aarch64-apple-darwin.tar.gz": (
        "50ae3e996c974a0bf32ea7d10f495070df33f1b43e0616b2769e3d4821ed8f48"
    ),
    "just-1.58.0-x86_64-apple-darwin.tar.gz": (
        "9a09cfef66aaa79da58203970103a0684307716caaabd3e9844cacc4dc0f4023"
    ),
    "just-1.58.0-x86_64-pc-windows-msvc.zip": (
        "759f16fb7aa17c5c8b9594b6d4a8c1a6630dfd042cf2b3ff84841454d3d188dc"
    ),
    "just-1.58.0-aarch64-pc-windows-msvc.zip": (
        "3a39ed629eb67678976c811a4da46f7985a2c22f4dbabe017b8b2eb5ceb5d01c"
    ),
}


#: Platform suffixes in asset names. macOS is included because developers need
#: `just` locally even though the paid CI runner was removed.
#:
#: Windows is included for the same local-development reason. The public
#: cross-platform job used `choco`, a community feed without a pinned checksum;
#: this uses the same pinned archive and SHA256 comparison as the other systems.
ASSET_FOR = {
    ("linux", "x86_64"): f"just-{VERSION}-x86_64-unknown-linux-musl.tar.gz",
    ("linux", "aarch64"): f"just-{VERSION}-aarch64-unknown-linux-musl.tar.gz",
    ("darwin", "arm64"): f"just-{VERSION}-aarch64-apple-darwin.tar.gz",
    ("darwin", "x86_64"): f"just-{VERSION}-x86_64-apple-darwin.tar.gz",
    ("windows", "x86_64"): f"just-{VERSION}-x86_64-pc-windows-msvc.zip",
    ("windows", "arm64"): f"just-{VERSION}-aarch64-pc-windows-msvc.zip",
}

#: The same hardware is named differently depending on the caller.
ALIASES = {"amd64": "x86_64", "aarch64": "aarch64", "arm64": "arm64"}

DOWNLOAD_ATTEMPTS = 4
RETRY_DELAYS_SECONDS = (5, 15, 30)

type Download = Callable[[str, Path], object]
type Sleep = Callable[[float], object]


def target_asset() -> str:
    system = platform.system().lower()
    machine = ALIASES.get(platform.machine().lower(), platform.machine().lower())
    if system == "linux" and machine == "arm64":
        machine = "aarch64"
    if system == "darwin" and machine == "aarch64":
        machine = "arm64"
    if system == "windows" and machine == "aarch64":
        machine = "arm64"
    asset = ASSET_FOR.get((system, machine))
    if asset is None:
        raise RuntimeError(
            f"unsupported platform for just bootstrap: {platform.system()} {platform.machine()}"
        )
    return asset


def download_verified(
    url: str,
    archive: Path,
    expected_sha256: str,
    *,
    download: Download = urllib.request.urlretrieve,
    sleep: Sleep = time.sleep,
) -> None:
    """Download one pinned asset, retrying only failures that may be transient."""
    for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
        archive.unlink(missing_ok=True)
        try:
            download(url, archive)
        except urllib.error.HTTPError as error:
            if error.code < 500 or error.code >= 600 or attempt == DOWNLOAD_ATTEMPTS:
                raise
            _wait_before_retry(attempt, error, sleep)
            continue
        except (
            urllib.error.URLError,
            ConnectionError,
            TimeoutError,
            http.client.HTTPException,
        ) as error:
            if attempt == DOWNLOAD_ATTEMPTS:
                raise
            _wait_before_retry(attempt, error, sleep)
            continue

        actual = hashlib.sha256(archive.read_bytes()).hexdigest()
        if actual != expected_sha256:
            raise RuntimeError(f"SHA256 mismatch for {archive.name}: {actual}")
        return


def _wait_before_retry(attempt: int, error: BaseException, sleep: Sleep) -> None:
    delay = RETRY_DELAYS_SECONDS[attempt - 1]
    print(
        f"bootstrap_just: download attempt {attempt}/{DOWNLOAD_ATTEMPTS} failed "
        f"({type(error).__name__}); retrying in {delay}s",
        file=sys.stderr,
    )
    sleep(delay)


def main() -> int:
    asset = target_asset()
    expected = SHA256[asset]
    if expected.startswith("REPLACE_"):
        raise RuntimeError(f"missing SHA256 for {asset}")

    url = f"https://github.com/casey/just/releases/download/{VERSION}/{asset}"
    install_dir = Path(os.environ.get("JUST_INSTALL_DIR", "/usr/local/bin"))
    install_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp_raw:
        tmp = Path(tmp_raw)
        archive = tmp / asset
        download_verified(url, archive, expected)

        binary = "just.exe" if asset.endswith(".zip") else "just"
        extracted = tmp / binary
        if asset.endswith(".zip"):
            with zipfile.ZipFile(archive) as bundle:
                name = next((item for item in bundle.namelist() if Path(item).name == binary), None)
                if name is None:
                    raise RuntimeError("just binary not found in archive")
                extracted.write_bytes(bundle.read(name))
        else:
            with tarfile.open(archive, "r:gz") as tar:
                member = next((m for m in tar.getmembers() if Path(m.name).name == binary), None)
                if member is None:
                    raise RuntimeError("just binary not found in archive")
                source = tar.extractfile(member)
                if source is None:
                    raise RuntimeError("just binary cannot be read from archive")
                extracted.write_bytes(source.read())

        target = install_dir / binary
        shutil.copy2(extracted, target)
        # Windows decides executability by extension, and `chmod` there accepts
        # only the read-only bit — asking for the POSIX bits is meaningless
        # rather than harmful, so it is simply not asked.
        if os.name != "nt":
            target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"bootstrap_just: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
