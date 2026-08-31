"""A grant is written down before it is made, so a killed process leaves no reach.

`ADR-0133` chose AppContainer and named the consequence in the same breath:
"появляется новая обязанность: снимать ACE и профиль после успеха, отказа,
таймаута и краха". The first three were covered by a `finally`. The fourth was
not covered by anything — a `finally` does not run when the process is killed,
the package SID is stable by design, and the grant therefore survives into the
next isolated phase, which selected a different target.

These exercise the lease on every platform, because the bug is in the record
keeping rather than in the Windows API: the sweep is what a later run does with
what an earlier one wrote, and that is ordinary file handling.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_stp_cli.provider import windows_launcher

pytestmark = pytest.mark.cli


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    return tmp_path / "data"


def test_a_grant_is_recorded_before_it_is_made(data_dir: Path, tmp_path: Path) -> None:
    """Written first, because a grant with no record is the failure that matters."""
    windows_launcher._lease_write("S-1-15-2-1", tmp_path / "target")  # pyright: ignore[reportPrivateUsage]

    held = windows_launcher._lease_path().read_text(encoding="utf-8")  # pyright: ignore[reportPrivateUsage]
    assert json.loads(held.strip()) == {"package": "S-1-15-2-1", "path": str(tmp_path / "target")}


def test_a_revoked_grant_stops_being_recorded(data_dir: Path, tmp_path: Path) -> None:
    windows_launcher._lease_write("S-1-15-2-1", tmp_path / "a")  # pyright: ignore[reportPrivateUsage]
    windows_launcher._lease_write("S-1-15-2-1", tmp_path / "b")  # pyright: ignore[reportPrivateUsage]

    windows_launcher._lease_clear("S-1-15-2-1", tmp_path / "a")  # pyright: ignore[reportPrivateUsage]

    held = windows_launcher._lease_path().read_text(encoding="utf-8")  # pyright: ignore[reportPrivateUsage]
    assert str(tmp_path / "a") not in held
    assert str(tmp_path / "b") in held


def test_the_last_revoke_removes_the_lease(data_dir: Path, tmp_path: Path) -> None:
    windows_launcher._lease_write("S-1-15-2-1", tmp_path / "a")  # pyright: ignore[reportPrivateUsage]

    windows_launcher._lease_clear("S-1-15-2-1", tmp_path / "a")  # pyright: ignore[reportPrivateUsage]

    assert not windows_launcher._lease_path().exists()  # pyright: ignore[reportPrivateUsage]


def test_a_grant_a_killed_run_left_is_taken_back(
    data_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The falsification: record two grants, never revoke, and sweep."""
    revoked: list[tuple[str, str]] = []

    def record(package: str, target: Path) -> None:
        revoked.append((package, str(target)))

    monkeypatch.setattr(windows_launcher, "_revoke", record)
    windows_launcher._lease_write("S-1-15-2-1", tmp_path / "target")  # pyright: ignore[reportPrivateUsage]
    windows_launcher._lease_write("S-1-15-2-1", tmp_path / "runtime")  # pyright: ignore[reportPrivateUsage]

    swept = windows_launcher.sweep_abandoned_grants()

    assert revoked == [
        ("S-1-15-2-1", str(tmp_path / "target")),
        ("S-1-15-2-1", str(tmp_path / "runtime")),
    ]
    assert set(swept) == {str(tmp_path / "target"), str(tmp_path / "runtime")}
    assert not windows_launcher._lease_path().exists()  # pyright: ignore[reportPrivateUsage]


def test_sweeping_nothing_is_not_an_error(data_dir: Path) -> None:
    assert windows_launcher.sweep_abandoned_grants() == ()


def test_an_unreadable_lease_line_does_not_stop_the_rest(
    data_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A truncated write must not strand every grant recorded after it."""
    revoked: list[str] = []

    def record(_package: str, target: Path) -> None:
        revoked.append(str(target))

    monkeypatch.setattr(windows_launcher, "_revoke", record)
    place = windows_launcher._lease_path()  # pyright: ignore[reportPrivateUsage]
    place.parent.mkdir(parents=True, exist_ok=True)
    place.write_text(
        '{"package": "S-1-15-2-1", "pa\n'
        + json.dumps({"package": "S-1-15-2-1", "path": str(tmp_path / "good")})
        + "\n",
        encoding="utf-8",
    )

    windows_launcher.sweep_abandoned_grants()

    assert revoked == [str(tmp_path / "good")]


def test_the_job_kills_on_close_rather_than_on_a_remembered_call() -> None:
    """The one limit the tree's lifetime depends on."""
    assert windows_launcher._JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE == 0x2000  # pyright: ignore[reportPrivateUsage]


def test_the_process_starts_suspended_so_nothing_escapes_the_job() -> None:
    """Assigned before it runs, or a fast child is outside the job that owns it."""
    source = Path(windows_launcher.__file__).read_text(encoding="utf-8")
    creation = source[source.index("created = api.kernel.CreateProcessW") :]
    assert "_CREATE_SUSPENDED" in source
    assert "AssignProcessToJobObject" in creation[: creation.index("ResumeThread")]
