"""Exercise fixture observations with real owned children and HTTP responses in CI."""

from __future__ import annotations

import http.client
import json
import os
import signal
import sys
import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux installed fixture owner")
SCRIPT = Path(__file__).resolve().parents[2] / ".github/scripts/qualify-installed-desktop.py"


def load() -> ModuleType:
    spec = spec_from_file_location("installed_webdriver", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def owned_driver(
    module: ModuleType, root: Path, *, child_code: str = "import time; time.sleep(60)"
) -> Generator[Any, None, None]:
    executable = root / "owned-driver"
    executable.write_text(
        f"#!{sys.executable}\n"
        "import os, pathlib, subprocess, sys, time\n"
        f"child = subprocess.Popen([sys.executable, '-c', {child_code!r}])\n"
        "print('Error serving connection: PRIVATE_DRIVER_CANARY', flush=True)\n"
        "pathlib.Path(os.environ['FIXTURE_CHILD']).write_text(str(child.pid))\n"
        "time.sleep(60)\n"
    )
    executable.chmod(0o700)
    driver = module.Driver(
        executable,
        {**os.environ, "FIXTURE_CHILD": str(root / "child"), "FIXTURE_ROOT": str(root)},
        root / "driver.log",
    )
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            assert driver.process.poll() is None
            if (root / "child").is_file() and (root / "child").read_text().isdecimal():
                break
            time.sleep(0.01)
        assert (root / "child").is_file()
        yield driver
    finally:
        driver.close()


def test_observation_distinguishes_dead_native_child_from_live_proxy_without_private_logs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    module = load()
    with owned_driver(module, tmp_path) as driver:
        observed = module.driver_children(driver.process.pid)
        assert observed == {
            "observation": "read",
            "direct_children": 1,
            "running": 1,
            "exit_codes": [],
        }
        child = int((tmp_path / "child").read_text())
        assert os.getpgid(child) == driver.process.pid
        os.kill(child, signal.SIGTERM)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            observed = module.driver_children(driver.process.pid)
            if observed.get("exit_codes") == [-signal.SIGTERM]:
                break
            time.sleep(0.01)
        assert observed == {
            "observation": "read",
            "direct_children": 1,
            "running": 0,
            "exit_codes": [-signal.SIGTERM],
        }
        assert driver.process.poll() is None
        with pytest.raises(ValueError, match="owned native WebDriver exited before readiness"):
            driver.start()
        assert driver.session is None and sum(driver.readiness_observations.values()) == 0
        driver.diagnostics()
        output = capsys.readouterr().out
        assert "PRIVATE_DRIVER_CANARY" not in output
        assert str(tmp_path) not in output
        assert json.loads(output)["driver_children"] == observed
        assert json.loads(output)["markers"]["proxy_connection_error"] is True


def test_close_waits_for_the_exact_native_child_after_the_proxy_exits(tmp_path: Path) -> None:
    module = load()
    child_code = (
        "import os, pathlib, signal, time\n"
        "root = pathlib.Path(os.environ['FIXTURE_ROOT'])\n"
        "def stop(_signal, _frame):\n"
        "    time.sleep(0.25)\n"
        "    (root / 'child-stopped').write_text('finished')\n"
        "    raise SystemExit(0)\n"
        "signal.signal(signal.SIGTERM, stop)\n"
        "(root / 'child-ready.tmp').write_text('ready')\n"
        "(root / 'child-ready.tmp').replace(root / 'child-ready')\n"
        "time.sleep(60)\n"
    )
    with owned_driver(module, tmp_path, child_code=child_code) as driver:
        deadline = time.monotonic() + 5
        while not (tmp_path / "child-ready").exists() and time.monotonic() < deadline:
            assert driver.process.poll() is None
            time.sleep(0.01)
        assert (tmp_path / "child-ready").read_text() == "ready"
        assert not (tmp_path / "child-stopped").exists()
        driver.close()
        assert driver.process.returncode is not None
        assert (tmp_path / "child-stopped").read_text() == "finished"
        assert driver.log.closed


def test_malformed_readiness_cannot_start_or_replay_an_application_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    requests: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:
            requests.append(self.command + " " + self.path)
            body = b'{"value":{"ready":"false"}}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            requests.append(self.command + " " + self.path)
            self.send_error(500)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    connection = http.client.HTTPConnection

    def fixture_connection(_host: str, _port: int, *, timeout: float) -> http.client.HTTPConnection:
        return connection("127.0.0.1", server.server_port, timeout=timeout)

    module = load()
    monkeypatch.setattr(module.http.client, "HTTPConnection", fixture_connection)
    try:
        with owned_driver(module, tmp_path) as driver:
            with pytest.raises(ValueError, match="invalid readiness observation"):
                driver.start()
            assert requests == ["GET /status"]
            assert driver.session is None
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
        assert not worker.is_alive()
