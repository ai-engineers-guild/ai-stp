"""Publication qualification must exercise the same remote object it claims."""

from __future__ import annotations

import json
import socket
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from ai_stp_cli import agy_qualify as qualify
from ai_stp_cli.application.qualify import CellStatus


@pytest.mark.parametrize("kind", ["component", "setup"])
def test_publication_readback_uses_the_published_object_kind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    workspace = qualify.prepare_workspace(tmp_path)
    identifier = f"{kind}_01ARZ3NDEKTSV4RRFFQ69G5FAV"
    calls: list[list[str]] = []

    def cli(_workspace: qualify.Workspace, argv: Sequence[str]) -> dict[str, object]:
        args = list(argv)
        calls.append(args)
        assert args[args.index("--kind") + 1] == kind
        if args[1] == "version":
            return {
                "ok": True,
                "data": {
                    "source": "online",
                    "passport": {
                        "stable_id": identifier,
                        "version": "1.0",
                        "artifact": {"digest": "sha256:artifact"},
                    },
                },
            }
        return {"ok": True, "data": {"source": "online", "digest": "sha256:artifact"}}

    monkeypatch.setattr(qualify, "cell_cli", cli)
    assert qualify.publication_readback(workspace, identifier, "1.0", private=True) == "verified"
    assert [call[1] for call in calls] == ["version", "fetch"]


@pytest.mark.parametrize(
    ("anonymous", "expected"),
    [("unavailable", "not_run"), ("fail", "fail"), ("verified", "fail"), ("absent", "pass")],
)
def test_private_publication_requires_observed_anonymous_denial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, anonymous: str, expected: str
) -> None:
    workspace = qualify.prepare_workspace(tmp_path)

    def snapshots(_home: Path) -> tuple[dict[str, object], ...]:
        return (
            {
                "intent": "publish",
                "state": "completed",
                "goal_satisfied": True,
                "outcome": {
                    "kind": "publish",
                    "object_id": "setup_01ARZ3NDEKTSV4RRFFQ69G5FAV",
                    "object_version": "1.0",
                    "visibility": "private",
                    "state": "published",
                    "readable": True,
                },
            },
        )

    def readback(*_args: object, private: bool) -> str:
        return "verified" if private else anonymous

    def boundary(_workspace: qualify.Workspace) -> None:
        return None

    monkeypatch.setattr(qualify, "task_snapshots", snapshots)
    monkeypatch.setattr(qualify, "publication_readback", readback)
    monkeypatch.setattr(qualify, "capture_boundary", boundary)
    assert qualify.publish_verified(workspace, visibility="private") == expected


@pytest.mark.parametrize("driver_fails", [False, True])
def test_capture_lives_through_scoring_and_closes_on_driver_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, driver_fails: bool
) -> None:
    captures: list[qualify.RequestCapture] = []
    original_capture = qualify.RequestCapture

    def capture(upstream: str) -> qualify.RequestCapture:
        result = original_capture(upstream)
        captures.append(result)
        return result

    def listening() -> bool:
        port = urlsplit(captures[0].url).port
        assert port is not None
        with socket.socket() as client:
            client.settimeout(1)
            return client.connect_ex(("127.0.0.1", port)) == 0

    def drive(workspace: qualify.Workspace, **_kwargs: object) -> int:
        if driver_fails:
            raise OSError("driver interrupted")
        (workspace.root / "agy.stdout").write_text("done", encoding="utf-8")
        (workspace.root / "agy.stderr").write_text("", encoding="utf-8")
        return 0

    def score(_scenario: str, workspace: qualify.Workspace) -> CellStatus:
        assert listening(), "publication readback still uses the cell's configured proxy"
        assert (workspace.root / qualify.CAPTURE_FILE).is_file()
        return "pass"

    monkeypatch.setattr(qualify, "RequestCapture", capture)
    monkeypatch.setattr(qualify, "run_agy", drive)
    monkeypatch.setattr(qualify, "score", score)

    def run() -> int:
        return qualify.qualify_one(
            root=tmp_path / "cell",
            scenario=qualify.NO_REINIT,
            run=0,
            measured=tmp_path / "measured.json",
            agy=Path("agy"),
            timeout=5,
            probe=False,
        )

    try:
        if driver_fails:
            with pytest.raises(OSError, match="driver interrupted"):
                run()
        else:
            assert run() == 0
            assert json.loads((tmp_path / "measured.json").read_text())["agent"]
        assert not listening(), "the recorder must close even when the driver raises"
    finally:
        for held in captures:
            held.close()
