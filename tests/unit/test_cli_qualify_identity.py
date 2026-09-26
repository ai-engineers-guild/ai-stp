"""A score belongs to the bytes that actually ran, not just a version label."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_stp_cli import agy_qualify as qualify
from ai_stp_cli import qualify_identity as identity


def test_payload_digest_detects_edits_but_ignores_interpreter_cache(tmp_path: Path) -> None:
    source = tmp_path / "example.py"
    source.write_text("original", encoding="utf-8")
    first = identity.payload_digest({"example": tmp_path})
    cache = tmp_path / "__pycache__"
    cache.mkdir()
    (cache / "example.pyc").write_bytes(b"generated")
    assert identity.payload_digest({"example": tmp_path}) == first
    source.write_text("changed", encoding="utf-8")
    assert identity.payload_digest({"example": tmp_path}) != first


@pytest.mark.parametrize("missing", [False, True])
def test_candidate_mismatch_preserves_history_before_any_effect(
    tmp_path: Path, missing: bool
) -> None:
    measured = tmp_path / "measured.json"
    qualify.write_cell(measured, qualify.NO_REINIT, 0, "pass")
    body = json.loads(measured.read_text())
    if missing:
        del body["execution_identity"]
    else:
        body["execution_identity"]["skill_digest"] = "sha256:" + "0" * 64
    measured.write_text(json.dumps(body), encoding="utf-8")
    before = measured.read_bytes()
    root = tmp_path / "must-not-exist"
    assert (
        qualify.main(
            [
                "--root",
                str(root),
                "--measured",
                str(measured),
                "--invalidate",
                qualify.NO_REINIT,
                "--agy",
                "absent-driver",
            ]
        )
        == 2
    )
    assert measured.read_bytes() == before
    assert not root.exists()
    qualify.write_native_cell(measured, "cursor", "linux-x86_64", "pass")
    after = json.loads(measured.read_text())
    assert after.get("execution_identity") == body.get("execution_identity")


def test_installed_runner_copies_the_packaged_skill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(identity, "installation", lambda: "distribution")
    path = identity.canonical_skill(tmp_path)
    assert path == Path(identity.__file__).parent / "skills" / "canonical"
    assert (path / "SKILL.md").is_file()


def test_code_change_during_model_run_cannot_create_a_score(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    values = iter(({"payload": "before"}, {"payload": "after"}))

    def changing_identity(*_args: object, **_kwargs: object) -> dict[str, str]:
        return next(values)

    monkeypatch.setattr(qualify, "execution_identity", changing_identity)

    def drive(workspace: qualify.Workspace, **_kwargs: object) -> int:
        (workspace.root / "agy.stdout").write_text("No reinitialization needed.")
        (workspace.root / "agy.stderr").write_text("")
        return 0

    monkeypatch.setattr(qualify, "run_agy", drive)
    measured = tmp_path / "measured.json"
    with pytest.raises(ValueError, match="changed during the attempt"):
        qualify.qualify_one(
            root=tmp_path / "cell",
            scenario=qualify.NO_REINIT,
            run=0,
            measured=measured,
            agy=Path("absent-driver"),
            timeout=5,
            probe=False,
        )
    assert not measured.exists()
    assert (tmp_path / "cell" / "execution-identity.json").is_file()
    assert (tmp_path / "cell" / "agy.stdout").is_file()
