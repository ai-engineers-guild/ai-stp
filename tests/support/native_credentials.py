"""Credential-loss faults restricted to keys created by this disposable fixture."""

from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path

from tests.support.native_runner import disposable_runner

from ai_stp_foundation.ids import parse_id


def lose_enrollment_key(state: Path, device_id: str, credential_store: str) -> None:
    assert parse_id(device_id)[0] == "device"
    name = f"device-key.{device_id}"
    path = state / "ai-stp-v2-connections" / name
    if credential_store == "file":
        assert path.is_file() and not path.is_symlink()
        path.unlink()
        return
    assert credential_store == "os_keyring"
    disposable_runner()
    temporary = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
    relative = state.resolve(strict=True).relative_to(temporary)
    assert len(relative.parts) == 3
    assert relative.parts[0].startswith("ai-stp-native-corporate-")
    assert relative.parts[1:] == ("corporate", "state")
    assert not path.exists(), "The OS-vault fault cannot delete a file-backend key"
    if platform.system() == "Darwin":
        observed = subprocess.run(
            ["/usr/bin/security", "default-keychain", "-d", "user"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )
        keychain = Path(observed.stdout.strip().strip('"')).resolve(strict=True)
        assert keychain.is_relative_to(Path.home() / "Library/Keychains")
        arguments = [
            "/usr/bin/security",
            "delete-generic-password",
            "-s",
            "ai-stp-v2",
            "-a",
            name,
            str(keychain),
        ]
    else:
        assert platform.system() == "Windows"
        arguments = [
            "pwsh",
            "-NoProfile",
            "-NonInteractive",
            "-File",
            ".github/scripts/remove-owned-native-credential.ps1",
            "-DeviceId",
            device_id,
        ]
    deleted = subprocess.run(
        arguments, stdin=subprocess.DEVNULL, capture_output=True, timeout=30, check=False
    )
    assert deleted.returncode == 0, ("owned native enrollment-key loss", deleted.returncode)
