from pathlib import Path

import pytest
from release_scripts import verify_software_slice as software


def test_an_unreachable_vendor_does_not_manufacture_dependent_failures(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[list[str]] = []

    def answering(
        arguments: list[str], *, home: Path, python: str, allow_failure: bool = False
    ) -> dict[str, object]:
        del home, python
        calls.append(arguments)
        if arguments[:2] == ["provider", "fetch"]:
            return {"ok": True, "data": {}}
        if arguments[:2] == ["harness", "install"] and allow_failure:
            return {
                "ok": False,
                "error": {
                    "code": "AI_STP_DEPENDENCY_UNAVAILABLE",
                    "message": "the pinned artifact could not be fetched",
                    "details": {"reason": "ReadTimeout"},
                },
            }
        raise AssertionError(f"dependent stage was called: {arguments}")

    artifact = tmp_path / "cursor-setup-system"
    artifact.write_bytes(b"provider")

    def selected_artifact(_directory: Path) -> Path:
        return artifact

    monkeypatch.setattr(software, "cli", answering)
    monkeypatch.setattr(software, "_artifact", selected_artifact)

    row = software._row(  # pyright: ignore[reportPrivateUsage]
        "cursor",
        root=tmp_path,
        home=tmp_path / "home",
        tag="0.0.58",
        python="python",
    )

    assert row["outcome"] == software.INCONCLUSIVE
    assert [stage["outcome"] for stage in row["stages"]] == [
        software.INCONCLUSIVE,
        software.NOT_EXERCISED,
        software.NOT_EXERCISED,
        software.NOT_EXERCISED,
    ]
    assert len(calls) == 2


def test_transparent_mode_exercises_acquisition_and_reuses_the_managed_provider(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[list[str]] = []
    home = tmp_path / "home"

    def answering(
        arguments: list[str], *, home: Path, python: str, allow_failure: bool = False
    ) -> dict[str, object]:
        del python, allow_failure
        calls.append(arguments)
        if arguments[:2] == ["harness", "install"]:
            release = home / "data/ai-stp/providers/cursor/0.0.60"
            release.mkdir(parents=True)
            (release / "release.json").write_text("{}", encoding="utf-8")
            (release / "cursor-setup-system").write_bytes(b"provider")
        return {"ok": True, "data": {"state": "verified"}}

    monkeypatch.setattr(software, "cli", answering)

    row = software._row(  # pyright: ignore[reportPrivateUsage]
        "cursor",
        root=tmp_path,
        home=home,
        tag="0.0.60",
        python="python",
        acquire=True,
    )

    assert row["outcome"] == software.PASSED
    assert row["acquisition"] == "transparent"
    assert [call[:2] for call in calls] == [
        ["harness", "install"],
        ["harness", "status"],
        ["harness", "update"],
        ["harness", "remove"],
    ]
    assert all("--provider" not in call for call in calls)
    assert all("--provider-manifest" not in call for call in calls)
