# pyright: reportPrivateUsage=false
"""CLI self-update (`SPEC-072`): selection, plan digest, apply, lock, rollback."""

from __future__ import annotations

import hashlib
import subprocess
import threading
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.runtime import DISTRIBUTION
from ai_stp_cli.self_update import method as method_mod
from ai_stp_cli.self_update import service, store
from ai_stp_cli.self_update.index import PypiIndex, WheelFile
from ai_stp_cli.self_update.method import Installation, current_installation, fingerprint

pytestmark = pytest.mark.cli


def _observe(version: str) -> object:
    def _run(_executable: Path) -> str:
        return version

    return _run


def _wheel(
    version: str,
    body: bytes,
    *,
    yanked: bool = False,
    requires_python: str | None = None,
) -> tuple[WheelFile, bytes]:
    filename = f"{DISTRIBUTION.replace('-', '_')}-{version}-py3-none-any.whl"
    return (
        WheelFile(
            version=version,
            filename=filename,
            url=f"https://files.pythonhosted.org/packages/{filename}",
            size=len(body),
            sha256=hashlib.sha256(body).hexdigest(),
            yanked=yanked,
            requires_python=requires_python,
        ),
        body,
    )


class FakeIndex:
    origin = "https://pypi.org"

    def __init__(
        self,
        wheels: Sequence[tuple[WheelFile, bytes]],
        *,
        simple: Sequence[WheelFile] | None = None,
        error: CliFailure | None = None,
    ) -> None:
        self.wheels = list(wheels)
        self.simple = list(simple) if simple is not None else [item[0] for item in wheels]
        self.error = error
        self.project_calls = 0

    def project(self, project: str, *, timeout: float) -> Mapping[str, object]:
        self.project_calls += 1
        if self.error is not None:
            raise self.error
        releases: dict[str, list[dict[str, object]]] = {}
        for wheel, _body in self.wheels:
            releases.setdefault(wheel.version, []).append(
                {
                    "packagetype": "bdist_wheel",
                    "filename": wheel.filename,
                    "url": wheel.url,
                    "size": wheel.size,
                    "digests": {"sha256": wheel.sha256},
                    "yanked": wheel.yanked,
                    "requires_python": wheel.requires_python,
                }
            )
        return {"info": {}, "releases": releases}

    def simple_files(self, project: str, *, timeout: float) -> Sequence[WheelFile]:
        if self.error is not None:
            raise self.error
        return tuple(self.simple)

    def download(self, url: str, destination: Path, *, expected_size: int) -> None:
        for wheel, body in self.wheels:
            if wheel.url == url:
                destination.write_bytes(body)
                return
        raise CliFailure("AI_STP_NOT_FOUND", "no such wheel in the fake index")


def _held(
    tmp_path: Path,
    *,
    version: str = "0.0.20",
    method: str = "pip_venv",
    apply_ready: bool = True,
) -> Installation:
    prefix = tmp_path / "prefix"
    binary = prefix / "bin" / "ai-stp"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    receipt = prefix / "uv-receipt.toml"
    if method == "uv_tool":
        receipt.write_text("tool = 'ai-stp-cli'\n", encoding="utf-8")
    return Installation(
        method=method,  # type: ignore[arg-type]
        executable=binary,
        prefix=prefix,
        python=prefix / "bin" / "python",
        version=version,
        receipt=receipt if method == "uv_tool" else None,
        apply_ready=apply_ready,
        reason="test installation",
    )


def test_a_uv_receipt_is_classified_as_uv_tool(tmp_path: Path) -> None:
    prefix = tmp_path / "tools" / "ai-stp-cli"
    prefix.mkdir(parents=True)
    (prefix / "uv-receipt.toml").write_text("[tool]\n", encoding="utf-8")
    executable = prefix / "bin" / "ai-stp"
    executable.parent.mkdir()
    executable.write_text("", encoding="utf-8")
    python = prefix / "bin" / "python"
    python.write_text("", encoding="utf-8")
    held = current_installation(prefix=prefix, executable=executable, python=python)
    assert held.method == "uv_tool"
    assert held.apply_ready is True
    assert fingerprint(held).startswith("sha256:")


def test_a_workspace_editable_install_is_source_managed() -> None:
    from importlib.metadata import distribution

    dist = distribution(DISTRIBUTION)
    names = {Path(str(item)).name for item in dist.files or ()}
    if not any(name.startswith("_editable") and name.endswith(".pth") for name in names):
        pytest.skip("this interpreter is not an editable checkout")
    held = current_installation()
    assert held.method == "source_managed"
    assert held.apply_ready is False


def test_check_reports_available_current_yanked_prerelease_and_python(
    tmp_path: Path,
) -> None:
    held = _held(tmp_path)
    yanked = _wheel("0.0.21", b"yanked-wheel", yanked=True)
    pre = _wheel("0.0.22a1", b"pre-wheel")
    py4 = _wheel("0.0.21", b"py4-wheel", requires_python=">=4")

    available = service.check(
        {}, installation=held, releases=FakeIndex([_wheel("0.0.20", b"c"), _wheel("0.0.21", b"n")])
    )
    assert available.state == "available"
    assert available.candidate_version == "0.0.21"

    current_report = service.check(
        {}, installation=held, releases=FakeIndex([_wheel("0.0.20", b"c")])
    )
    assert current_report.state == "current"

    yanked_report = service.check(
        {},
        installation=held,
        releases=FakeIndex([_wheel("0.0.20", b"c"), yanked]),
    )
    assert yanked_report.state == "current"
    assert "yanked" in yanked_report.reason

    stable = service.check(
        {"channel": "stable"},
        installation=held,
        releases=FakeIndex([_wheel("0.0.20", b"c"), pre]),
    )
    assert stable.state == "current"
    assert "pre-release" in stable.reason

    pre_ok = service.check(
        {"channel": "prerelease"},
        installation=held,
        releases=FakeIndex([_wheel("0.0.20", b"c"), pre]),
    )
    assert pre_ok.state == "available"
    assert pre_ok.candidate_version == "0.0.22a1"

    python = service.check(
        {},
        installation=held,
        releases=FakeIndex([_wheel("0.0.20", b"c"), py4]),
    )
    assert python.state == "current"
    assert "Python" in python.reason


def test_a_local_version_is_source_managed(tmp_path: Path) -> None:
    held = _held(tmp_path, version="0.0.20+local")
    report = service.check({}, installation=held, releases=FakeIndex([_wheel("0.0.21", b"n")]))
    assert report.state == "source_managed"


def test_simple_index_lag_is_stale_not_available(tmp_path: Path) -> None:
    held = _held(tmp_path)
    current = _wheel("0.0.20", b"c")
    newer = _wheel("0.0.21", b"n")
    report = service.check(
        {},
        installation=held,
        releases=FakeIndex([current, newer], simple=[current[0]]),
    )
    assert report.state == "stale"
    assert report.simple_index_ready is False


def test_offline_without_cache_is_unknown(tmp_path: Path) -> None:
    held = _held(tmp_path)
    report = service.check({"offline": True}, installation=held, releases=FakeIndex([]))
    assert report.state == "unknown"
    assert "offline" in report.reason


def test_index_failure_with_cache_is_stale(tmp_path: Path) -> None:
    held = _held(tmp_path)
    first = service.check(
        {}, installation=held, releases=FakeIndex([_wheel("0.0.20", b"c"), _wheel("0.0.21", b"n")])
    )
    assert first.state == "available"
    failed = service.check(
        {},
        installation=held,
        releases=FakeIndex(
            [],
            error=CliFailure("AI_STP_DEPENDENCY_UNAVAILABLE", "the package index timed out"),
        ),
    )
    assert failed.state == "stale"


def test_plan_digest_survives_a_newer_index_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    held = _held(tmp_path)
    current = _wheel("0.0.20", b"current-bytes")
    first = _wheel("0.0.21", b"first-bytes")
    later = _wheel("0.0.22", b"later-bytes")
    client = FakeIndex([current, first])
    planned = service.plan({}, installation=held, releases=client)
    digest = planned.plan_digest
    assert planned.target_version == "0.0.21"
    client.wheels = [current, first, later]
    client.simple = [item[0] for item in client.wheels]
    monkeypatch.setattr(service, "_observe_version", _observe("0.0.21"))
    result = service.apply(
        {"expected-plan-digest": digest},
        installation=held,
        releases=client,
        runner=lambda argv: subprocess.CompletedProcess(argv, 0, "", ""),
    )
    assert result.outcome == "replaced"
    assert result.target_version == "0.0.21"
    assert result.plan_digest == digest


def test_apply_refuses_a_hash_changed_wheel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    held = _held(tmp_path)
    current = _wheel("0.0.20", b"current-bytes")
    first = _wheel("0.0.21", b"first-bytes")
    client = FakeIndex([current, first])
    planned = service.plan({}, installation=held, releases=client)
    client.wheels = [current, _wheel("0.0.21", b"tampered-bytes")]
    client.simple = [item[0] for item in client.wheels]
    with pytest.raises(CliFailure, match="does not match the planned artifact") as raised:
        service.apply(
            {"expected-plan-digest": planned.plan_digest},
            installation=held,
            releases=client,
            runner=lambda argv: subprocess.CompletedProcess(argv, 0, "", ""),
        )
    assert raised.value.code == "AI_STP_PLAN_STALE"


def test_source_managed_plan_is_refused(tmp_path: Path) -> None:
    held = _held(tmp_path, apply_ready=False, method="source_managed")
    with pytest.raises(CliFailure) as raised:
        service.plan({}, installation=held, releases=FakeIndex([_wheel("0.0.21", b"n")]))
    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"


def test_shared_environment_is_not_mutated(tmp_path: Path) -> None:
    held = _held(tmp_path, method="shared_environment", apply_ready=False)
    report = service.check({}, installation=held, releases=FakeIndex([_wheel("0.0.21", b"n")]))
    assert report.install_method == "shared_environment"
    with pytest.raises(CliFailure) as raised:
        service.plan({}, installation=held, releases=FakeIndex([_wheel("0.0.21", b"n")]))
    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"


def test_concurrent_apply_contends_on_one_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    held = _held(tmp_path)
    client = FakeIndex([_wheel("0.0.20", b"c"), _wheel("0.0.21", b"n")])
    planned = service.plan({}, installation=held, releases=client)
    monkeypatch.setattr(store, "LOCK_TIMEOUT_SECONDS", 0.2)
    started = threading.Event()
    hold = threading.Event()

    def _block() -> None:
        with store.exclusive_lock():
            started.set()
            hold.wait(timeout=2)

    blocked = threading.Thread(target=_block)
    blocked.start()
    assert started.wait(timeout=2)
    with pytest.raises(CliFailure) as raised:
        service.apply(
            {"expected-plan-digest": planned.plan_digest},
            installation=held,
            releases=client,
            runner=lambda argv: subprocess.CompletedProcess(argv, 0, "", ""),
        )
    assert raised.value.code == "AI_STP_CONFLICT"
    hold.set()
    blocked.join(timeout=2)


def test_rollback_restores_the_previous_wheel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    held = _held(tmp_path)
    current = _wheel("0.0.20", b"current-bytes")
    newer = _wheel("0.0.21", b"newer-bytes")
    client = FakeIndex([current, newer])
    planned = service.plan({}, installation=held, releases=client)
    monkeypatch.setattr(service, "_observe_version", _observe("0.0.21"))
    applied = service.apply(
        {"expected-plan-digest": planned.plan_digest},
        installation=held,
        releases=client,
        runner=lambda argv: subprocess.CompletedProcess(argv, 0, "", ""),
    )
    assert applied.rollback_digest
    previous = store.stage_dir() / current[0].filename
    assert previous.is_file()
    monkeypatch.setattr(service, "_observe_version", _observe("0.0.20"))
    rolled = service.rollback(
        {"expected-plan-digest": applied.rollback_digest},
        installation=held,
        runner=lambda argv: subprocess.CompletedProcess(argv, 0, "", ""),
    )
    assert rolled.outcome == "rolled_back"
    assert rolled.target_version == "0.0.20"


def test_recover_is_idle_without_a_journal(tmp_path: Path) -> None:
    held = _held(tmp_path)
    with pytest.raises(CliFailure) as raised:
        service.recover(installation=held)
    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"


def test_requested_yanked_version_is_refused(tmp_path: Path) -> None:
    held = _held(tmp_path)
    yanked = _wheel("0.0.21", b"yanked-wheel", yanked=True)
    with pytest.raises(CliFailure) as raised:
        service.check(
            {"version": "0.0.21"},
            installation=held,
            releases=FakeIndex([_wheel("0.0.20", b"c"), yanked]),
        )
    assert raised.value.code == "AI_STP_NOT_FOUND"


def test_json_notice_uses_cache_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    held = _held(tmp_path)
    monkeypatch.setattr(method_mod, "current_installation", lambda: held)
    service.check(
        {}, installation=held, releases=FakeIndex([_wheel("0.0.20", b"c"), _wheel("0.0.21", b"n")])
    )

    def boom(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("machine notice must not contact the index")

    monkeypatch.setattr(PypiIndex, "project", boom)
    warnings, actions = service.maybe_notice(["version"], machine=True, tty=False)
    assert warnings
    assert actions == ("update plan --json",)
    assert "0.0.21" in warnings[0]


def test_user_data_survives_apply(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from ai_stp_cli import config
    from ai_stp_cli.local.database import open_registry

    held = _held(tmp_path)
    values = {item.path: item.value for item in config.effective_config().values}
    registry = Path(str(values["registry.path"]))
    open_registry(registry).close()
    marker = b"keep-me"
    registry.write_bytes(registry.read_bytes() + marker)
    client = FakeIndex([_wheel("0.0.20", b"c"), _wheel("0.0.21", b"n")])
    planned = service.plan({}, installation=held, releases=client)
    monkeypatch.setattr(service, "_observe_version", _observe("0.0.21"))
    service.apply(
        {"expected-plan-digest": planned.plan_digest},
        installation=held,
        releases=client,
        runner=lambda argv: subprocess.CompletedProcess(argv, 0, "", ""),
    )
    backup = Path(planned.data_backup)
    copies = list(backup.glob("registry.sqlite*"))
    assert copies
    assert marker in copies[0].read_bytes()
    assert marker in registry.read_bytes()


def test_uv_tool_plan_names_the_owning_installer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def which(name: str) -> str | None:
        return "/opt/uv" if name == "uv" else None

    monkeypatch.setattr("ai_stp_cli.self_update.service.shutil.which", which)
    held = _held(tmp_path, method="uv_tool")
    planned = service.plan(
        {},
        installation=held,
        releases=FakeIndex([_wheel("0.0.20", b"c"), _wheel("0.0.21", b"n")]),
    )
    assert planned.installer_argv[:4] == ["/opt/uv", "tool", "install", "--force"]
    assert planned.installer_argv[4].endswith(planned.artifact_filename)


def test_rate_limited_check_keeps_the_cache_and_is_stale(tmp_path: Path) -> None:
    held = _held(tmp_path)
    first = service.check(
        {}, installation=held, releases=FakeIndex([_wheel("0.0.20", b"c"), _wheel("0.0.21", b"n")])
    )
    assert first.state == "available"
    limited = service.check(
        {},
        installation=held,
        releases=FakeIndex(
            [],
            error=CliFailure("AI_STP_RATE_LIMITED", "the package index asked this client to wait"),
        ),
    )
    assert limited.state == "stale"
    assert limited.candidate_version == "0.0.21"


def test_a_failed_installer_leaves_recovery_required(tmp_path: Path) -> None:
    held = _held(tmp_path)
    client = FakeIndex([_wheel("0.0.20", b"c"), _wheel("0.0.21", b"n")])
    planned = service.plan({}, installation=held, releases=client)
    with pytest.raises(CliFailure) as raised:
        service.apply(
            {"expected-plan-digest": planned.plan_digest},
            installation=held,
            releases=client,
            runner=lambda argv: subprocess.CompletedProcess(argv, 1, "", "boom"),
        )
    assert raised.value.code == "AI_STP_PARTIAL_OPERATION"
    report = service.status(installation=held)
    assert report.journal_state == "recovery_required"
