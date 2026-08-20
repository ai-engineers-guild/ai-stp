"""The credential store: the right tier, named honestly, never silently."""

import os
from pathlib import Path

import pytest

from ai_stp_cli import paths, secrets
from ai_stp_cli.errors import CliFailure

# POSIX st_mode widening checks are skipped in production when os.name == "nt".
_POSIX = os.name != "nt"

#: The undecorated detection function, captured before the autouse fixture in
#: `tests/conftest.py` replaces it.
_real_detection = secrets.selected_backend


class FakeBackend:
    """Stands in for a backend class so detection can be exercised by name."""


def _as_backend(module: str, name: str) -> type:
    backend = type(name, (FakeBackend,), {})
    backend.__module__ = module
    return backend


def _install(monkeypatch: pytest.MonkeyPatch, module: str, name: str) -> None:
    """Make `selected_backend` see a backend of the given dotted name.

    Patched into `sys.modules`, which `monkeypatch` restores, so the real
    library is untouched and no test can reach the machine's actual store.
    """
    import sys

    class FakeKeyring:
        @staticmethod
        def get_keyring() -> object:
            return _as_backend(module, name)()

    monkeypatch.setitem(sys.modules, "keyring", FakeKeyring)


def test_a_real_operating_system_backend_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    # The repository-wide fixture forces "no store"; this test is about the
    # detection itself, so it restores the real function first.
    monkeypatch.setattr(secrets, "selected_backend", _real_detection)
    _install(monkeypatch, "keyring.backends.SecretService", "Keyring")
    assert secrets.selected_backend() == "keyring.backends.SecretService.Keyring"


@pytest.mark.parametrize(
    ("module", "name"),
    [
        ("keyring.backends.fail", "Keyring"),
        ("keyring.backends.chainer", "ChainerBackend"),
        ("keyring.backends.null", "Keyring"),
        ("keyrings.alt.file", "PlaintextKeyring"),
        ("keyrings.alt.file", "EncryptedKeyring"),
    ],
)
def test_a_backend_that_is_not_an_operating_system_store_is_refused(
    module: str, name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `keyrings.alt.file.PlaintextKeyring` is the reason this check exists.
    # Measured: with that package installed it wins backend selection,
    # `set_password` succeeds, and the secret lands on disk base64-encoded while
    # the library reports success. Believing the library would make this CLI
    # report "operating system credential store" about a plain file.
    monkeypatch.setattr(secrets, "selected_backend", _real_detection)
    _install(monkeypatch, module, name)
    assert secrets.selected_backend() is None


def test_without_a_store_the_file_tier_is_chosen_and_says_so() -> None:
    store, warning = secrets.open_store()
    assert store.tier == "file"
    assert warning is not None
    assert "owner-only file" in warning
    assert "owner-only file" in store.detail


def test_with_a_store_there_is_nothing_to_warn_about(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(secrets, "selected_backend", lambda: "keyring.backends.macOS.Keyring")
    store, warning = secrets.open_store()
    assert store.tier == "os_keyring"
    assert warning is None
    assert store.detail == "macOS"


def test_the_file_tier_round_trips_and_stays_owner_only() -> None:
    store = secrets.FileStore()
    assert store.get("thing") is None
    store.put("thing", "value")
    assert store.get("thing") == "value"
    written = next(paths.secrets_dir().glob("*.secret"))
    assert paths.is_private(written)
    store.drop("thing")
    assert store.get("thing") is None
    # Dropping what is absent is the state the caller asked for.
    store.drop("thing")


def test_a_json_document_round_trips_and_a_broken_one_is_refused() -> None:
    store = secrets.FileStore()
    assert secrets.load_json(store, "thing") is None
    secrets.store_json(store, "thing", {"a": "1"})
    assert secrets.load_json(store, "thing") == {"a": "1"}

    store.put("broken", "{not json")
    with pytest.raises(CliFailure, match="not valid JSON"):
        secrets.load_json(store, "broken")

    store.put("list", "[1, 2]")
    with pytest.raises(CliFailure, match="not an object"):
        secrets.load_json(store, "list")


def test_promotion_removes_the_file_copy_once_the_store_holds_the_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Leaving the file copy behind is how `openai/codex#14704` kept stale
    # credentials readable on disk after the machine gained a real store.
    file_store = secrets.FileStore()
    file_store.put("thing", "value")
    monkeypatch.setattr(secrets, "selected_backend", lambda: "keyring.backends.macOS.Keyring")
    store, _warning = secrets.open_store()
    secrets.promote(store, "thing")
    assert file_store.get("thing") is None
    # The half this test used to omit, and the half that matters: the value has
    # to be somewhere afterwards. Asserting only the deletion passes just as
    # happily when promotion destroys the secret instead of moving it.
    assert store.get("thing") == "value"


def test_promotion_refuses_two_copies_that_disagree(monkeypatch: pytest.MonkeyPatch) -> None:
    # Neither copy can be shown to be the live one, and picking either destroys
    # a credential. Both are kept.
    secrets.FileStore().put("thing", "from the file")
    monkeypatch.setattr(secrets, "selected_backend", lambda: "keyring.backends.macOS.Keyring")
    store, _warning = secrets.open_store()
    store.put("thing", "from the store")

    with pytest.raises(CliFailure, match="do not agree"):
        secrets.promote(store, "thing")

    assert secrets.FileStore().get("thing") == "from the file"
    assert store.get("thing") == "from the store"


def test_dropping_a_secret_clears_both_tiers(monkeypatch: pytest.MonkeyPatch) -> None:
    # A file copy left behind would disagree with the next minted value, and
    # `promote` fails closed on a disagreement — which would strand the install.
    secrets.FileStore().put("thing", "value")
    monkeypatch.setattr(secrets, "selected_backend", lambda: "keyring.backends.macOS.Keyring")
    store, _warning = secrets.open_store()
    store.put("thing", "value")

    secrets.drop_everywhere(store, "thing")

    assert store.get("thing") is None
    assert secrets.FileStore().get("thing") is None


def test_promotion_does_nothing_on_the_file_tier() -> None:
    store, _warning = secrets.open_store()
    store.put("thing", "value")
    secrets.promote(store, "thing")
    assert store.get("thing") == "value"


def test_a_deletion_failure_during_promotion_is_reported_not_swallowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secrets.FileStore().put("thing", "value")
    monkeypatch.setattr(secrets, "selected_backend", lambda: "keyring.backends.macOS.Keyring")

    def refuse(self: object, name: str) -> None:
        raise OSError("read-only file system")

    monkeypatch.setattr(secrets.FileStore, "drop", refuse)
    store, _warning = secrets.open_store()
    with pytest.raises(CliFailure, match="remains in a file") as raised:
        secrets.promote(store, "thing")
    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"


def test_promotion_is_a_no_op_when_no_file_copy_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(secrets, "selected_backend", lambda: "keyring.backends.macOS.Keyring")
    store, _warning = secrets.open_store()
    secrets.promote(store, "absent")


def test_the_keyring_tier_talks_to_keyring_and_translates_its_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stored: dict[str, str] = {}

    class FakeErrors:
        class PasswordDeleteError(Exception):
            pass

    class FakeKeyring:
        errors = FakeErrors

        @staticmethod
        def get_password(service: str, name: str) -> str | None:
            return stored.get(name)

        @staticmethod
        def set_password(service: str, name: str, value: str) -> None:
            stored[name] = value

        @staticmethod
        def delete_password(service: str, name: str) -> None:
            if name not in stored:
                raise FakeErrors.PasswordDeleteError
            del stored[name]

    import sys

    monkeypatch.setitem(sys.modules, "keyring", FakeKeyring)
    monkeypatch.setitem(sys.modules, "keyring.errors", FakeErrors)

    store = secrets.KeyringStore("keyring.backends.SecretService.Keyring")
    assert store.get("thing") is None
    store.put("thing", "value")
    assert store.get("thing") == "value"
    store.drop("thing")
    assert store.get("thing") is None
    # Deleting an absent entry is not a failure.
    store.drop("thing")


@pytest.mark.skipif(
    not _POSIX,
    reason="POSIX mode widening is not enforced on Windows (paths.POSIX is false)",
)
def test_a_file_written_by_someone_else_is_refused_by_the_store(tmp_path: Path) -> None:
    store = secrets.FileStore(tmp_path)
    store.put("thing", "value")
    (tmp_path / "thing.secret").chmod(0o644)
    with pytest.raises(CliFailure, match="readable by more than its owner"):
        store.get("thing")


def test_a_keyring_that_raises_becomes_a_typed_dependency_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys

    class Boom(Exception):
        pass

    class FakeErrors:
        class PasswordDeleteError(Exception):
            pass

    class FakeKeyring:
        errors = FakeErrors

        @staticmethod
        def get_password(service: str, name: str) -> str | None:
            raise Boom("dbus: /run/user/1000/bus is unreachable")

        @staticmethod
        def set_password(service: str, name: str, value: str) -> None:
            raise Boom("dbus: /run/user/1000/bus is unreachable")

        @staticmethod
        def delete_password(service: str, name: str) -> None:
            raise Boom("dbus: /run/user/1000/bus is unreachable")

    monkeypatch.setitem(sys.modules, "keyring", FakeKeyring)
    monkeypatch.setitem(sys.modules, "keyring.errors", FakeErrors)
    store = secrets.KeyringStore("keyring.backends.SecretService.Keyring")

    for call in (lambda: store.get("t"), lambda: store.put("t", "v"), lambda: store.drop("t")):
        with pytest.raises(CliFailure) as raised:
            call()
        assert raised.value.code == "AI_STP_DEPENDENCY_UNAVAILABLE"
        assert raised.value.retryable
        # The exception text carries a bus address, so only the type is
        # published (`SPEC-011` REQ-1108).
        assert raised.value.details == {"exception": "Boom"}
        assert "bus" not in raised.value.message


@pytest.mark.skipif(
    not _POSIX,
    reason="POSIX mode widening is not enforced on Windows (paths.POSIX is false)",
)
def test_promotion_surfaces_a_widened_file_rather_than_masking_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secrets.FileStore().put("thing", "value")
    (paths.secrets_dir() / "thing.secret").chmod(0o644)
    monkeypatch.setattr(secrets, "selected_backend", lambda: "keyring.backends.macOS.Keyring")
    store, _warning = secrets.open_store()
    with pytest.raises(CliFailure, match="readable by more than its owner"):
        secrets.promote(store, "thing")


def test_a_selected_store_that_does_not_answer_falls_back_and_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Selection is not availability.

    `keyring` picks a backend from what is installed, and on a headless machine
    `SecretService` is routinely installed with no daemon behind it — SSH, a
    container, a CI runner. Refusing there made every command fail on exactly the
    setup `ADR-0058` calls primary.
    """

    import sys

    class Deaf:
        errors = type("errors", (), {"PasswordDeleteError": Exception})

        @staticmethod
        def get_password(service: str, name: str) -> str | None:
            raise RuntimeError("no session bus")

        @staticmethod
        def set_password(service: str, name: str, value: str) -> None:
            raise RuntimeError("no session bus")

    monkeypatch.setitem(sys.modules, "keyring", Deaf)
    monkeypatch.setattr(
        secrets, "selected_backend", lambda: "keyring.backends.SecretService.Keyring"
    )

    store, warning = secrets.open_store()

    assert store.tier == "file"
    assert warning is not None
    assert "did not answer" in warning
    # Usable, not merely reported: the whole point is that local work continues.
    store.put("thing", "value")
    assert store.get("thing") == "value"
