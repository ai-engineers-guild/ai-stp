"""Device identity: created once, signs, resets to something genuinely new."""

import json
from pathlib import Path

import pytest

from ai_stp_cli import identity, paths, secrets
from ai_stp_cli.errors import CliFailure
from ai_stp_foundation.ids import is_valid_id
from ai_stp_foundation.timestamps import is_valid_timestamp


def test_the_first_run_creates_an_identity() -> None:
    current, warning = identity.load_or_create()
    assert is_valid_id(current.device_id, "device")
    assert is_valid_timestamp(current.created_at)
    assert current.state == "active"
    # The repository fixture removes the operating system store, so the file
    # tier is used and says so.
    assert current.store.tier == "file"
    assert warning is not None


def test_a_second_run_returns_the_same_identity() -> None:
    first, _ = identity.load_or_create()
    second, _ = identity.load_or_create()
    assert first.device_id == second.device_id
    assert first.report().public_key == second.report().public_key
    assert first.created_at == second.created_at


def test_both_halves_of_the_identity_are_owner_only() -> None:
    current, _ = identity.load_or_create()
    entry = identity.key_entry(current.device_id)
    assert paths.is_private(paths.device_file())
    assert paths.is_private(paths.secrets_dir() / f"{entry}.secret")


def test_the_private_key_is_not_representable_in_the_report() -> None:
    # `SPEC-011` REQ-1108. Not "we remembered not to print it": the report model
    # has no field that could carry it.
    current, _ = identity.load_or_create()
    report = current.report()
    rendered = json.dumps(report.model_dump(mode="json"))
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        NoEncryption,
        PrivateFormat,
    )

    seed = current.private_key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    assert seed.hex() not in rendered
    assert "private" not in rendered


def test_a_signature_verifies_with_the_public_half_and_not_with_another(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current, _ = identity.load_or_create()
    payload = b"attestation bytes"
    signature = current.sign(payload)
    assert identity.verify(current.public_key, payload, signature)
    assert not identity.verify(current.public_key, b"different bytes", signature)

    other, _ = identity.reset()
    assert not identity.verify(other.public_key, payload, signature)


def test_the_public_key_and_fingerprint_match_the_frozen_wire_forms() -> None:
    import re

    from ai_stp_contracts.auth import PUBLIC_KEY_PATTERN

    report = identity.load_or_create()[0].report()
    assert re.fullmatch(PUBLIC_KEY_PATTERN, report.public_key)
    assert re.fullmatch(r"[0-9a-f]{2}(:[0-9a-f]{2}){15}", report.key_fingerprint)


def test_reset_reuses_neither_the_identifier_nor_the_key() -> None:
    # `SPEC-002` REQ-207: resuming cloud access needs a new sign-in and a new
    # key, so reuse of either would defeat the requirement.
    before, _ = identity.load_or_create()
    after, _ = identity.reset()
    assert after.device_id != before.device_id
    assert after.report().public_key != before.report().public_key
    assert after.state == "active"


def test_reset_remembers_what_it_retired() -> None:
    # Not reusing a revoked device means remembering it.
    first, _ = identity.load_or_create()
    second, _ = identity.reset()
    third, _ = identity.reset()
    retired = identity.retired_identities()
    assert [item.device_id for item in retired] == [first.device_id, second.device_id]
    assert all(is_valid_timestamp(item.retired_at) for item in retired)
    assert third.device_id not in {item.device_id for item in retired}


def test_reset_keeps_local_data(isolated_environment: Path) -> None:
    # `SPEC-002` REQ-205: revocation is forward-acting and never destroys what
    # is already on the machine.
    identity.load_or_create()
    keepsake = paths.data_dir() / "registry.sqlite"
    keepsake.write_text("local rows", encoding="utf-8")
    config = isolated_environment / "config" / "ai-stp" / "config.yaml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text("catalog:\n  enabled: false\n", encoding="utf-8")

    identity.reset()

    assert keepsake.read_text(encoding="utf-8") == "local rows"
    assert config.read_text(encoding="utf-8") == "catalog:\n  enabled: false\n"


def test_a_public_record_without_its_key_is_refused_rather_than_re_minted() -> None:
    # Re-minting would change an identity a server may already know, silently.
    current, _ = identity.load_or_create()
    secrets.FileStore().drop(identity.key_entry(current.device_id))
    with pytest.raises(CliFailure, match="record but no key") as raised:
        identity.load_or_create()
    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"
    assert raised.value.details["device_id"] == current.device_id


def test_a_key_left_behind_by_a_deleted_data_directory_is_not_touched() -> None:
    # The credential store is per user and outlives any one data directory:
    # deleting `~/.local/share/ai-stp` leaves the operating system keyring
    # untouched. Starting over must work without a manual reset — and must not
    # disturb the key that is still there, because naming keys per device means
    # it may belong to an installation that is very much alive.
    first, _ = identity.load_or_create()
    left_behind = secrets.FileStore().get(identity.key_entry(first.device_id))
    assert left_behind is not None
    paths.device_file().unlink()

    second, _warning = identity.load_or_create()
    assert second.device_id != first.device_id
    assert second.report().public_key != first.report().public_key
    assert secrets.FileStore().get(identity.key_entry(first.device_id)) == left_behind
    # Idempotent from there on.
    assert identity.load_or_create()[0].device_id == second.device_id


def test_a_second_installation_does_not_overwrite_the_first_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The defect this naming exists to end.

    Two installations share one operating-system credential store, because it
    belongs to the user rather than to a home directory — which is exactly why
    the file tier cannot model this and the store tier has to. Under a single
    entry name the second installation minted its identity over the first one's
    key, and the first was left with a record it could no longer sign for. This
    repository's own `just check` did that to the developer's keyring.
    """
    monkeypatch.setattr(secrets, "selected_backend", lambda: "keyring.backends.macOS.Keyring")
    store, _warning = secrets.open_store()

    first, _ = identity.load_or_create()
    first_key = store.get(identity.key_entry(first.device_id))
    assert first_key is not None

    # A second installation: its own data directory, the same credential store.
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "second"))
    second, _ = identity.load_or_create()

    assert second.device_id != first.device_id
    assert store.get(identity.key_entry(first.device_id)) == first_key
    assert store.get(identity.key_entry(second.device_id)) not in (None, first_key)


@pytest.mark.parametrize(
    "template",
    [
        "{not json",
        '["a list"]',
        '{"device_id": "not-an-id"}',
        # A valid identifier, so these two really exercise the field they name
        # rather than failing earlier on the identifier.
        '{"device_id": "DEVICE", "state": "confused"}',
        '{"device_id": "DEVICE", "retired": "not a list"}',
    ],
)
def test_a_damaged_device_record_is_named_not_guessed(template: str) -> None:
    current, _ = identity.load_or_create()
    paths.write_private(paths.device_file(), template.replace("DEVICE", current.device_id))
    with pytest.raises(CliFailure, match="cannot be read"):
        identity.load_or_create()


def test_damaged_key_material_is_named_too() -> None:
    current, _ = identity.load_or_create()
    entry = identity.key_entry(current.device_id)
    store = secrets.FileStore()
    secrets.store_json(store, entry, {"seed": "not base64!!"})
    with pytest.raises(CliFailure, match="cannot be read"):
        identity.load_or_create()

    secrets.store_json(store, entry, {"wrong": "field"})
    with pytest.raises(CliFailure, match="cannot be read"):
        identity.load_or_create()


def test_retired_identities_is_empty_before_anything_exists() -> None:
    assert identity.retired_identities() == ()


def test_gaining_a_credential_store_does_not_destroy_the_device_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The regression for the worst defect this track has had.

    A machine runs headless first, so the key lands in an owner-only file. Later
    it gains a real credential store — the user logs into a desktop session, or
    `gnome-keyring` arrives with an update. Promotion used to delete the file
    without ever writing the value, so the only copy of the key was destroyed and
    every command afterwards refused with "record but no key". The only exit
    offered was `device reset`, which throws away an identifier the account may
    already have approved.
    """
    first, _warning = identity.load_or_create()

    monkeypatch.setattr(secrets, "selected_backend", lambda: "keyring.backends.macOS.Keyring")
    second, _warning = identity.load_or_create()

    assert second.device_id == first.device_id
    assert second.store.tier == "os_keyring"
    assert identity.encode_public_key(second.public_key) == identity.encode_public_key(
        first.public_key
    )
    assert secrets.FileStore().get(identity.key_entry(second.device_id)) is None


def test_a_reset_leaves_no_file_copy_to_disagree_with_the_new_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`reset` has to retire both halves, or the next command fails closed."""
    first, _warning = identity.load_or_create()
    assert secrets.FileStore().get(identity.key_entry(first.device_id)) is not None

    monkeypatch.setattr(secrets, "selected_backend", lambda: "keyring.backends.macOS.Keyring")
    fresh, _warning = identity.reset()

    assert secrets.FileStore().get(identity.key_entry(first.device_id)) is None
    # The installation still works after the reset: a stale file copy would make
    # the next promotion refuse and strand it.
    again, _warning = identity.load_or_create()
    assert again.device_id == fresh.device_id


def test_a_key_stored_under_the_old_shared_name_is_adopted_once() -> None:
    """An installation that predates per-device naming keeps its identity.

    The key is copied under the device's own name and verified before the old
    entry goes, so a failure half-way leaves the original reachable. The old
    entry is then removed: leaving it would let a second installation adopt the
    same key, which is what the naming exists to prevent.
    """
    current, _ = identity.load_or_create()
    store = secrets.FileStore()
    seed = store.get(identity.key_entry(current.device_id))
    assert seed is not None

    # Put the key back where an earlier version of the CLI kept it.
    store.put(identity.LEGACY_KEY_ENTRY, seed)
    store.drop(identity.key_entry(current.device_id))

    adopted, _warning = identity.load_or_create()

    assert adopted.device_id == current.device_id
    assert identity.encode_public_key(adopted.public_key) == identity.encode_public_key(
        current.public_key
    )
    assert store.get(identity.key_entry(current.device_id)) == seed
    assert store.get(identity.LEGACY_KEY_ENTRY) is None


def test_an_adopted_key_that_cannot_be_read_back_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Adoption verifies the copy before retiring the original.

    A store that accepts a write and keeps nothing would otherwise leave the
    installation with neither copy — the same shape as the promotion defect.
    """
    current, _ = identity.load_or_create()
    plain = secrets.FileStore()
    seed = plain.get(identity.key_entry(current.device_id))
    assert seed is not None
    plain.put(identity.LEGACY_KEY_ENTRY, seed)
    plain.drop(identity.key_entry(current.device_id))

    class Deaf(secrets.FileStore):
        def put(self, name: str, value: str) -> None:
            if name != identity.LEGACY_KEY_ENTRY:
                return
            super().put(name, value)

    monkeypatch.setattr(identity, "open_store", lambda: (Deaf(), None))
    with pytest.raises(CliFailure, match="cannot be read"):
        identity.load_or_create()

    assert plain.get(identity.LEGACY_KEY_ENTRY) == seed


def test_reading_the_identity_of_a_clean_home_creates_nothing() -> None:
    """`SPEC-009` REQ-902: reading does not bring state into existence."""
    found, warning = identity.current()
    assert found is None
    assert warning is not None
    assert not paths.device_file().exists()
    assert not list(paths.secrets_dir().glob("*.secret")) if paths.secrets_dir().exists() else True

    made, _warning = identity.load_or_create()
    again, _warning = identity.current()
    assert again is not None
    assert again.device_id == made.device_id
