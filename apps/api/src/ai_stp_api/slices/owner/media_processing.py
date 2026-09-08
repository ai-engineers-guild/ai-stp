"""Small server-side media normalization step for owner uploads."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import tempfile
from pathlib import Path

from ai_stp_contracts.owner import COMPONENT_MEDIA_MAX_BYTES


class MediaProcessingError(RuntimeError):
    """The uploaded video could not be normalized safely."""


async def normalize_upload(payload: bytes, content_type: str) -> bytes:
    """Remove video audio tracks in a bounded ffmpeg subprocess."""
    if not content_type.startswith("video/"):
        return payload
    return await asyncio.to_thread(_normalize_video, payload, content_type)


def _normalize_video(payload: bytes, content_type: str) -> bytes:
    binary = shutil.which("ffmpeg")
    if binary is None:
        raise MediaProcessingError("video processing is unavailable")
    suffix = ".mp4" if content_type == "video/mp4" else ".webm"
    with tempfile.TemporaryDirectory(prefix="ai-stp-media-") as directory:
        root = Path(directory)
        source = root / f"source{suffix}"
        output = root / f"video{suffix}"
        source.write_bytes(payload)
        result = subprocess.run(
            [
                binary,
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(source),
                "-map",
                "0:v:0",
                "-map_metadata",
                "-1",
                "-an",
                "-c:v",
                "copy",
                "-fs",
                str(COMPONENT_MEDIA_MAX_BYTES),
                "-y",
                str(output),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=20,
            check=False,
        )
        if result.returncode != 0 or not output.is_file():
            raise MediaProcessingError("video processing failed")
        if output.stat().st_size <= 0 or output.stat().st_size > COMPONENT_MEDIA_MAX_BYTES:
            raise MediaProcessingError("processed video size is out of bounds")
        return output.read_bytes()
