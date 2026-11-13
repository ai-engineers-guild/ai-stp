"""Actual mandatory scanner environment and network boundaries."""

from __future__ import annotations

import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from ai_stp_platform.safety.adapters import _cli


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"controlled-loopback")

    def log_message(self, format: str, *args: object) -> None:
        return


def boundary_cases(root: Path) -> dict[str, Any]:
    canary = "controlled-private-runtime-value"
    assert os.environ.get("AI_STP_RUNTIME_PRIVATE_CANARY") == canary
    code, out, _, _ = _cli.run_cli(
        [
            "python",
            "-c",
            "import os; print(os.environ.get('AI_STP_RUNTIME_PRIVATE_CANARY', 'absent'))",
        ],
        cwd=root,
        timeout=10,
    )
    assert code == 0 and out.strip() == "absent"
    parent_namespace = str(Path("/proc/self/ns/net").readlink())
    code, out, _, _ = _cli.run_cli(["readlink", "/proc/self/ns/net"], cwd=root, timeout=10)
    assert code == 0 and out.strip().startswith("net:[") and out.strip() != parent_namespace
    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}/"
            positive = subprocess.run(
                ["curl", "--fail", "--silent", "--max-time", "2", url],
                capture_output=True,
                check=True,
                timeout=5,
            )
            assert positive.stdout == b"controlled-loopback"
            code, _, _, _ = _cli.run_cli(
                ["curl", "--fail", "--silent", "--max-time", "2", url], cwd=root, timeout=5
            )
            assert code == 7, code
        finally:
            server.shutdown()
            thread.join(timeout=2)
            assert not thread.is_alive()
    return {
        "private_environment_filtered": True,
        "network_namespace_distinct": True,
        "loopback_denied": True,
    }
