"""Actual locked scanner behavior inside the disposable worker image."""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import tempfile
import threading
import zipfile
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from ai_stp_platform.safety.adapters import _cli, gosec, govulncheck
from ai_stp_platform.safety.policy import CHECK_REGISTRY
from ai_stp_platform.safety.sandbox import sandbox_status
from ai_stp_platform.safety.types import ArtifactManifest


def database(root: Path, fixed: str) -> Path:
    identity = "GO-2026-999999"
    date = "2026-01-01T00:00:00Z"
    record = {
        "schema_version": "1.6.0",
        "id": identity,
        "modified": date,
        "published": date,
        "summary": "Controlled synthetic qualification record",
        "database_specific": {"url": "https://example.invalid/qualification"},
        "affected": [
            {
                "package": {"ecosystem": "Go", "name": "stdlib"},
                "ranges": [{"type": "SEMVER", "events": [{"introduced": "0"}, {"fixed": fixed}]}],
                "ecosystem_specific": {"imports": [{"path": "fmt", "symbols": ["Println"]}]},
            }
        ],
    }
    entries: dict[str, object] = {
        "index/db.json": {"modified": date},
        "index/modules.json": [
            {"path": "stdlib", "vulns": [{"id": identity, "modified": date, "fixed": fixed}]}
        ],
        "index/vulns.json": [{"id": identity, "modified": date, "aliases": []}],
        f"ID/{identity}.json": record,
    }
    archive = root / "database.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        for name, value in entries.items():
            bundle.writestr(name, json.dumps(value))
    target = root / "govulncheck"
    subprocess.run(
        [
            sys.executable,
            "/opt/ai_stp/scripts/safety/prepare_go_db.py",
            str(archive),
            str(target),
            "65536",
            "100",
        ],
        check=True,
        capture_output=True,
        timeout=10,
    )
    assert (target / "STATUS.txt").is_file()
    assert (target / ".ai_stp_osv_refreshed_at").is_file()
    return target


def go_cases(root: Path) -> dict[str, Any]:
    tree = root / "module"
    tree.mkdir()
    (tree / "go.mod").write_text("module example.invalid/qualification\n\ngo 1.27.0\n")
    main = tree / "main.go"
    manifest = ArtifactManifest(component_type="skill", languages={"go"})
    sast = next(spec for spec in CHECK_REGISTRY if spec.check_id == "sast_gosec")
    sca = next(spec for spec in CHECK_REGISTRY if spec.check_id == "sca_govulncheck")
    results: dict[str, Any] = {}
    for name, text, expected in [
        ("clean", 'package main\nimport "fmt"\nfunc main() { fmt.Println("fixture") }\n', "passed"),
        (
            "risk",
            'package main\nimport ("os"; "os/exec")\n'
            'func main() { if err := exec.Command("sh", "-c", os.Args[1]).Run(); '
            "err != nil { panic(err) } }\n",
            "warning",
        ),
        ("incomplete", "package main\nfunc main( {\n", "degraded"),
    ]:
        main.write_text(text)
        result = gosec.run(tree, manifest, sast)
        assert result.result == expected, (name, result.result, result.detail)
        if name == "risk":
            assert result.findings and result.severity_max in {"high", "critical"}
        if name == "incomplete":
            assert result.detail.get("reason") == "analysis_incomplete"
        results[f"gosec_{name}"] = {
            "result": result.result,
            "findings": len(result.findings),
            "severity": result.severity_max,
        }
    main.write_text('package main\nimport "fmt"\nfunc main() { fmt.Println("fixture") }\n')
    cache_root = Path("/var/lib/ai_stp/osv")
    for name, fixed, expected in [
        ("clean", "1.0.0", "passed"),
        ("vulnerable", "99.0.0", "warning"),
    ]:
        cache = cache_root / name
        cache.mkdir()
        prepared = database(cache, fixed)
        os.environ["AI_STP_OSV_OFFLINE_DIR"] = str(cache)
        result = govulncheck.run(tree, manifest, sca)
        assert result.result == expected, (name, result.result, result.detail)
        results[f"govulncheck_{name}"] = {"result": result.result, "findings": len(result.findings)}
        if name == "vulnerable":
            marker = prepared / ".ai_stp_osv_refreshed_at"
            os.utime(marker, (0, 0))
            stale = govulncheck.run(tree, manifest, sca)
            assert stale.result == "not_run" and stale.detail.get("reason") == "offline_db_stale"
            results["govulncheck_stale"] = {
                "result": stale.result,
                "reason": stale.detail["reason"],
            }
            marker.write_text(datetime.now(UTC).isoformat())
            (prepared / "index" / "db.json").unlink()
            missing = govulncheck.run(tree, manifest, sca)
            assert missing.result == "not_run"
            assert missing.detail.get("reason") == "offline_db_missing"
            results["govulncheck_missing"] = {
                "result": missing.result,
                "reason": missing.detail["reason"],
            }
    return results


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


def main() -> None:
    assert os.geteuid() == 10001, "image must retain its declared non-root worker"
    assert sys.version_info[:2] == (3, 14)
    status = sandbox_status()
    assert status["mode"] == "bwrap", status
    assert os.environ.get("AI_STP_SAFETY_REQUIRE_BWRAP") == "1"
    assert sys.argv[1] in {"go", "boundary"}
    with tempfile.TemporaryDirectory(prefix="ai-stp-image-qualification-") as temporary:
        root = Path(temporary)
        checks = go_cases(root) if sys.argv[1] == "go" else boundary_cases(root)
    print(
        json.dumps(
            {
                "architecture": platform.machine(),
                "python": platform.python_version(),
                "sandbox": status["mode"],
                "checks": checks,
            }
        )
    )


if __name__ == "__main__":
    main()
