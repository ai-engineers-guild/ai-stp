"""Isolation every test in this repository gets, whether it asks for it or not.

`#73` requires that tests never touch the developer's real credential store, and
a rule that each test must remember is a rule that will be forgotten once. So
the isolation is automatic and repository-wide: a test has to work to reach the
real keyring, rather than work to avoid it.

Two things are redirected. The XDG directories point into a per-test temporary
tree, so nothing reads or writes the developer's configuration, device identity
or registry. And credential-store detection answers "no operating system store",
so the file tier is used and the real Secret Service, Keychain or Credential
Locker is never opened. A test that wants the other tier injects a fake — see
`tests/unit/test_cli_secrets.py`.
"""

import os
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest


def _in_memory_keyring() -> tuple[ModuleType, ModuleType]:
    """A stand-in for the `keyring` library that never leaves the process."""
    errors = ModuleType("keyring.errors")

    class PasswordDeleteError(Exception):
        pass

    errors.PasswordDeleteError = PasswordDeleteError  # pyright: ignore[reportAttributeAccessIssue]

    held: dict[tuple[str, str], str] = {}

    def get_password(service: str, name: str) -> str | None:
        return held.get((service, name))

    def set_password(service: str, name: str, value: str) -> None:
        held[(service, name)] = value

    def delete_password(service: str, name: str) -> None:
        if (service, name) not in held:
            raise PasswordDeleteError(name)
        del held[(service, name)]

    class _Untrusted:
        """Detection must not accept this, so the file tier stays the default."""

    module = ModuleType("keyring")
    module.get_password = get_password  # pyright: ignore[reportAttributeAccessIssue]
    module.set_password = set_password  # pyright: ignore[reportAttributeAccessIssue]
    module.delete_password = delete_password  # pyright: ignore[reportAttributeAccessIssue]
    module.get_keyring = _Untrusted  # pyright: ignore[reportAttributeAccessIssue]
    module.errors = errors  # pyright: ignore[reportAttributeAccessIssue]
    return module, errors


@pytest.fixture(autouse=True)
def isolated_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point every user-visible location at a temporary tree."""
    home = tmp_path / "home"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(home / "data"))
    monkeypatch.setenv("HOME", str(home))
    # Windows Path.home() / expanduser prefer USERPROFILE over HOME.
    monkeypatch.setenv("USERPROFILE", str(home))
    if os.name == "nt":
        drive = Path(home).drive or "C:"
        tail = str(home)[len(drive) :] if drive and str(home).startswith(drive) else str(home)
        monkeypatch.setenv("HOMEDRIVE", drive)
        monkeypatch.setenv("HOMEPATH", tail or "\\")
    # setup-python's interpreter needs LD_LIBRARY_PATH, which the provider
    # boundary deliberately does not forward. The workflow captures a PATH
    # where a standalone system python3 wins before `uv run` prepends its venv;
    # restore it here so executable Python fixtures exercise the real boundary.
    provider_path = os.environ.get("AI_STP_TEST_PROVIDER_PATH")
    if provider_path:
        monkeypatch.setenv("PATH", provider_path)
    yield home


@pytest.fixture(autouse=True)
def no_real_credential_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never open the machine's actual credential store.

    Patched at the detection point rather than by unsetting a bus address: an
    environment variable is one platform's mechanism, and this has to hold on
    macOS and Windows too, where nothing in the environment governs it.

    Detection alone is not enough, and that gap was not theoretical. A test that
    fakes `selected_backend` gets a real `KeyringStore`, whose methods import the
    real library — so `just test-code` wrote `ai-stp/thing` into the developer's
    GNOME keyring, and an earlier manual run replaced their `device-key`. The XDG
    variables cannot prevent this: the operating system store belongs to the
    user, not to a home directory. So the library itself is replaced too, and a
    test now has to work to reach the real store rather than work to avoid it.
    """
    module, errors = _in_memory_keyring()
    monkeypatch.setitem(sys.modules, "keyring", module)
    monkeypatch.setitem(sys.modules, "keyring.errors", errors)
    monkeypatch.setattr("ai_stp_cli.secrets.selected_backend", lambda: None)


def _permission_denial_is_unconstructible() -> str | None:
    """Why this process cannot be told "no" by a file's own permissions.

    A test that chmods something to `0o000` and asserts the refusal is asserting
    a property of the code under test, not of the filesystem — but it can only
    observe that property from a process the filesystem actually restricts. Two
    processes are not restricted, for different reasons, and both of them run
    this suite:

    - Windows does not derive access from POSIX mode bits at all, so `chmod`
      changes nothing a later read has to obey;
    - root bypasses mode bits by design, and owns every file it creates, so a
      test cannot even construct "a path somebody else owns". The repository
      gate runs as root because `check` runs inside a container image
      (`.github/workflows/check.yml`), which is also why this is not theoretical.

    Skipping under root costs no coverage on any commit: `back-python-3.12`
    runs the same suite on the same commit as an ordinary user on the host, and
    these tests are proved there.
    """
    if os.name == "nt":
        return "Windows access is not derived from POSIX mode bits"
    if getattr(os, "geteuid", None) is not None and os.geteuid() == 0:
        return "root bypasses mode bits and owns every file the test creates"
    return None


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Skip `unprivileged` tests when the process cannot be denied access."""
    reason = _permission_denial_is_unconstructible()
    if reason is None:
        return
    skip = pytest.mark.skip(reason=reason)
    for item in items:
        if item.get_closest_marker("unprivileged") is not None:
            item.add_marker(skip)
