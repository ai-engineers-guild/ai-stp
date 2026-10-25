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

VERSION = "1.59.0"

# SHA256 values for official archives, keyed case-sensitively by GitHub Release
# asset name. Update this table before updating its consumers.
SHA256 = {
    "just-1.59.0-x86_64-unknown-linux-musl.tar.gz": (
        "409044617b6f06517c1035e55ca38c8c856ff8b650e41bc2aa1ef82d5903a23e"
    ),
    "just-1.59.0-aarch64-unknown-linux-musl.tar.gz": (
        "23871b1702bfd550fb5f901778fd4290ecf2ee034a45a889fbe96d89b188086d"
    ),
    "just-1.59.0-aarch64-apple-darwin.tar.gz": (
        "6574cea774ed4cae12e24b6aa11857de33e80dab4667cf628fd5840df96a2a9d"
    ),
    "just-1.59.0-x86_64-apple-darwin.tar.gz": (
        "036ead9df9bc31dbae9934ae3b4236ed124d0bafcffd33439460ae084d5c9cb7"
    ),
    "just-1.59.0-x86_64-pc-windows-msvc.zip": (
        "9c5463e2d0974e31bee71346aa5cbf19167de1585a4abc1bae7b3b04604ea9c0"
    ),
    "just-1.59.0-aarch64-pc-windows-msvc.zip": (
        "a72808bc8f8028c25aaae87cf26405d2bd85d2769a779380b344c69607216971"
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
