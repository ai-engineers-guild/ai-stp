"""Bounded video normalization tests."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_stp_api.slices.owner import media_processing


@pytest.mark.asyncio
async def test_normalize_video_removes_audio_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_which(_binary: object) -> str:
        return "ffmpeg"

    monkeypatch.setattr(shutil, "which", fake_which)

    def fake_run(command: list[str], **_: object) -> SimpleNamespace:
        calls.append(command)
        output = Path(command[-1])
        output.write_bytes(b"normalized")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = await media_processing.normalize_upload(b"input", "video/mp4")
    assert result == b"normalized"
    assert "-an" in calls[0]
    assert "-map" in calls[0]


@pytest.mark.asyncio
async def test_normalize_image_is_unchanged() -> None:
    payload = b"image"
    assert await media_processing.normalize_upload(payload, "image/png") == payload
