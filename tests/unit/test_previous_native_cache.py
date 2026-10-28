"""Exercise cache identity refusals; actual historical writers retain their CI owner."""

from __future__ import annotations

import subprocess
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux historical writer owner")
SCRIPT = Path(__file__).resolve().parents[2] / ".github/scripts/previous-native-cache.py"
IDENTITY = ("a" * 40, "b" * 40, "c" * 64, "synthetic pinned compiler")
PAYLOAD = b"\x7fELF" + b"synthetic non-executable fixture\n" * 256


def load() -> ModuleType:
    spec = spec_from_file_location("previous_native_cache", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def entry(root: Path) -> Path:
    cache = root / "cache"
    cache.mkdir()
    binary = cache / "ai-stp"
    binary.write_bytes(PAYLOAD)
    binary.chmod(0o755)
    return cache


def test_identical_cache_verification_preserves_original_bytes_and_mtimes(tmp_path: Path) -> None:
    module, cache = load(), entry(tmp_path)
    digest = module.check(cache, *IDENTITY, "create")
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in cache.iterdir()}
    assert module.check(cache, *IDENTITY, "verify") == digest
    assert before == {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in cache.iterdir()}


@pytest.mark.parametrize(
    "change",
    [
        "commit",
        "tree",
        "recipe",
        "compiler",
        "binary",
        "mode",
        "oversized_binary",
        "record",
        "oversized_record",
        "missing_record",
        "extra_file",
        "binary_symlink",
        "record_symlink",
        "directory_symlink",
    ],
)
def test_cache_refuses_changed_identity_or_files(tmp_path: Path, change: str) -> None:
    module, cache = load(), entry(tmp_path)
    module.check(cache, *IDENTITY, "create")
    identity = list(IDENTITY)
    binary, record = cache / "ai-stp", cache / "record.json"
    if change in {"commit", "tree", "recipe", "compiler"}:
        index = ["commit", "tree", "recipe", "compiler"].index(change)
        identity[index] = "d" * len(identity[index])
    elif change == "binary":
        binary.write_bytes(PAYLOAD + b"changed")
    elif change == "mode":
        binary.chmod(0o644)
    elif change == "oversized_binary":
        with binary.open("r+b") as stream:
            stream.truncate(512 * 1024 * 1024 + 1)
    elif change == "record":
        record.write_bytes(record.read_bytes() + b" ")
    elif change == "oversized_record":
        record.write_bytes(b" " * 32769)
    elif change == "missing_record":
        record.unlink()
    elif change == "extra_file":
        (cache / "unexpected").write_bytes(b"not part of this cache")
    elif change in {"binary_symlink", "record_symlink"}:
        source = binary if change == "binary_symlink" else record
        outside = tmp_path / "outside"
        outside.write_bytes(source.read_bytes())
        outside.chmod(source.stat().st_mode & 0o777)
        source.unlink()
        source.symlink_to(outside)
    else:
        alias = tmp_path / "alias"
        alias.symlink_to(cache, target_is_directory=True)
        cache = alias
    with pytest.raises((OSError, ValueError)):
        module.check(cache, *identity, "verify")


def test_optimized_python_cannot_skip_refusal_or_expose_fixture_paths(tmp_path: Path) -> None:
    module, cache = load(), entry(tmp_path)
    module.check(cache, *IDENTITY, "create")
    command = [sys.executable, "-B", "-O", str(SCRIPT), str(cache), *IDENTITY, "verify"]
    accepted = subprocess.run(command, capture_output=True, text=True, check=False, timeout=10)
    assert accepted.returncode == 0 and not accepted.stderr
    (cache / "ai-stp").write_bytes(PAYLOAD + b"changed")
    refused = subprocess.run(command, capture_output=True, text=True, check=False, timeout=10)
    assert refused.returncode == 1 and not refused.stdout
    assert refused.stderr == "Previous writer cache refused (ValueError).\n"
    assert str(tmp_path) not in refused.stderr
