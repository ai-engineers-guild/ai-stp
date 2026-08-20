"""Isolated workdir lifecycle for safety scans."""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

# Soft limits for MVP unpack (bytes / file count / depth).
MAX_ARTIFACT_BYTES = 100 * 1024 * 1024
MAX_FILE_COUNT = 20_000
MAX_DEPTH = 32


class WorkdirError(RuntimeError):
    """Workdir or unpack policy failure."""


@contextmanager
def isolated_workdir(prefix: str = "ai-stp-safety-") -> Generator[Path]:
    """Create a temporary workdir and always wipe it."""
    base = Path(tempfile.mkdtemp(prefix=prefix))
    try:
        yield base
    finally:
        shutil.rmtree(base, ignore_errors=True)


def materialize_artifact(
    workdir: Path, payload: bytes, *, max_bytes: int = MAX_ARTIFACT_BYTES
) -> Path:
    """Write and unpack artifact into workdir/tree. Returns tree root.

    Supports plain directory zip and raw single-tree tar-less zip bytes.
    Non-zip payloads are written as a single file ``artifact.bin`` plus a
    ``tree/`` mirror of extracted text when zip is detected.
    """
    if len(payload) > max_bytes:
        raise WorkdirError(f"artifact exceeds max size {max_bytes}")
    raw_path = workdir / "artifact.bin"
    raw_path.write_bytes(payload)
    tree = workdir / "tree"
    tree.mkdir(parents=True, exist_ok=True)

    if _is_zip(payload):
        import zipfile

        try:
            with zipfile.ZipFile(raw_path) as zf:
                _safe_extract(zf, tree)
        except zipfile.BadZipFile as exc:
            raise WorkdirError("invalid zip artifact") from exc
    else:
        # Treat as a single content blob (e.g. tests injecting a file tree via
        # pre-built directory is preferred; for flat bytes store as content).
        (tree / "content.bin").write_bytes(payload)
    return tree


def _is_zip(payload: bytes) -> bool:
    return len(payload) >= 4 and payload[:2] == b"PK"


def _safe_extract(zf: object, dest: Path) -> None:
    import zipfile

    assert isinstance(zf, zipfile.ZipFile)
    members = zf.infolist()
    if len(members) > MAX_FILE_COUNT:
        raise WorkdirError("zip file count exceeds policy")
    total = 0
    for info in members:
        total += info.file_size
        if total > MAX_ARTIFACT_BYTES:
            raise WorkdirError("zip uncompressed size exceeds policy")
        name = info.filename.replace("\\", "/")
        if name.startswith("/") or ".." in name.split("/"):
            raise WorkdirError(f"unsafe zip path: {name}")
        depth = len([p for p in name.split("/") if p])
        if depth > MAX_DEPTH:
            raise WorkdirError("zip path depth exceeds policy")
        target = dest / name
        if info.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info) as src, target.open("wb") as out:
            shutil.copyfileobj(src, out)


def env_no_network() -> dict[str, str]:
    """Environment for child processes (hint; OS isolation is preferred)."""
    env = os.environ.copy()
    # Clear proxy vars that might encourage egress.
    for key in list(env):
        if key.lower().endswith("_proxy") or key in {"ALL_PROXY", "all_proxy"}:
            env.pop(key, None)
    env["AI_STP_SAFETY_NETWORK"] = "deny"
    return env
