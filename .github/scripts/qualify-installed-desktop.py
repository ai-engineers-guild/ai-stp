"""Exercise the installed Linux release through its UI, bundled CLI and real vault.

Run only in the disposable CI Secret Service fixture. JavaScript reads the DOM;
WebDriver sends actual clicks/keys. No IPC replacement or development server is used.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import http.client
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ELEMENT = "element-6066-11e4-a52e-4f735466cecf"
REVIEW = 'section[aria-label="Review native profile plan"]'


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


class Driver:
    def __init__(self, executable: Path, environment: dict[str, str], log: Path):
        # urllib forces Connection: close, which the intermediary forwards to
        # its pooled WebKit connection. Keep this owned HTTP/1.1 transport alive;
        # never replay a failed command, including clicks or session creation.
        self.http = http.client.HTTPConnection("127.0.0.1", 4444, timeout=90)
        self.session: str | None = None
        self.log_path = log
        self.stage = "starting"
        self.log = log.open("wb")
        self.process = subprocess.Popen(
            [
                str(executable),
                "--port",
                "4444",
                "--native-port",
                "4445",
                "--native-driver",
                "/usr/bin/WebKitWebDriver",
            ],
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=self.log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    def request(self, method: str, path: str, data: Any = None) -> Any:
        self.stage = (
            "session_stop"
            if method == "DELETE"
            else {
                "status": "status",
                "session": "session_start",
                "sync": "dom_read",
                "click": "click",
                "clear": "clear",
                "value": "keys",
            }.get(path.rsplit("/", 1)[-1], "command")
        )
        self.http.request(
            method,
            path,
            body=None if data is None else json.dumps(data).encode(),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        with self.http.getresponse() as reply:
            result = json.loads(reply.read())
            status = reply.status
        value = result["value"]
        if isinstance(value, dict) and "error" in value:
            # W3C categories are fixed public protocol data. Never include the
            # driver's free-form message, stack, DOM or application arguments.
            known = {
                "element click intercepted",
                "element not interactable",
                "invalid argument",
                "invalid element state",
                "invalid session id",
                "javascript error",
                "no such element",
                "no such window",
                "stale element reference",
                "timeout",
                "unknown command",
                "unknown error",
                "unsupported operation",
            }
            code = value["error"] if isinstance(value["error"], str) else "unknown error"
            if code not in known:
                code = "unknown error"
            raise ValueError(f"WebDriver protocol refusal (HTTP {status}; {code})")
        require(200 <= status < 300, f"WebDriver HTTP status {status}")
        return value

    def wait(self, predicate: Any, label: str) -> Any:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            require(self.process.poll() is None, "owned WebDriver exited unexpectedly")
            value = predicate()
            if value:
                return value
            time.sleep(0.2)
        raise ValueError(f"Timed out waiting for {label}")

    def start(self) -> None:
        def ready() -> bool:
            try:
                return bool(self.request("GET", "/status")["ready"])
            except (OSError, http.client.HTTPException):
                # Readiness is an observation before any application session.
                self.http.close()
                return False

        self.wait(ready, "WebDriver readiness")
        response = self.request(
            "POST",
            "/session",
            {
                "capabilities": {
                    "alwaysMatch": {"tauri:options": {"application": "/usr/bin/ai-stp-desktop"}}
                }
            },
        )
        self.session = response["sessionId"]
        self.wait(lambda: self.read("return document.querySelector('main');"), "installed UI")

    def command(self, method: str, path: str, data: Any = None) -> Any:
        require(self.session is not None, "no actual app session")
        return self.request(method, f"/session/{self.session}{path}", data)

    def read(self, script: str, *arguments: Any) -> Any:
        return self.command("POST", "/execute/sync", {"script": script, "args": list(arguments)})

    def find(self, selector: str) -> dict[str, str]:
        return dict(
            self.wait(
                lambda: self.read("return document.querySelector(arguments[0]);", selector),
                selector,
            )
        )

    def click(self, element: dict[str, str]) -> None:
        self.command("POST", f"/element/{element[ELEMENT]}/click", {})

    def button(self, text: str, selector: str = "main") -> dict[str, str]:
        return dict(
            self.wait(
                lambda: self.read(
                    "const root=document.querySelector(arguments[0]);"
                    "if(!root)return null;"
                    "const buttons=[...root.querySelectorAll('button')]"
                    ".filter(b=>b.textContent.trim()===arguments[1]&&!b.disabled);"
                    "return buttons.length===1?buttons[0]:null;",
                    selector,
                    text,
                ),
                text,
            )
        )

    def navigate(self, route: str) -> None:
        self.click(self.find(f'nav[aria-label="Main navigation"] a[href="#/{route}"]'))

    def review(self, action: str, label: str, expected_id: str | None = None) -> str:
        self.find(REVIEW)
        self.click(self.find(REVIEW + " details summary"))
        plan = json.loads(
            self.read("return document.querySelector(arguments[0]+' pre').textContent;", REVIEW)
        )
        change = plan["change"]
        context = change["context"]
        require(change["action"] == action and context["label"] == label, "UI plan changed intent")
        require(
            context["authority"] == {"kind": "local"}, "offline context acquired remote authority"
        )
        if expected_id is not None:
            require(context["context_id"] == expected_id, "UI plan selected another context")
        checkbox = self.find(REVIEW + ' input[type="checkbox"]')
        require(not self.read("return arguments[0].checked;", checkbox), "review was preconfirmed")
        self.click(checkbox)
        self.click(self.button("Apply reviewed change", REVIEW))
        self.wait(
            lambda: self.read("return !document.querySelector(arguments[0]);", REVIEW),
            "review commit",
        )
        return str(context["context_id"])

    def create_context(self, label: str) -> str:
        field = dict(
            self.wait(
                lambda: self.read(
                    "const labels=[...document.querySelectorAll('main label')];"
                    "const label=labels.find(x=>x.textContent.trim()==='Context label');"
                    "const input=label?.querySelector('input');"
                    "return input&&!input.disabled?input:null;"
                ),
                "context label input",
            )
        )
        self.command("POST", f"/element/{field[ELEMENT]}/clear", {})
        self.command("POST", f"/element/{field[ELEMENT]}/value", {"text": label})
        self.click(self.button("Review context creation"))
        return self.review("create", label)

    def select_context(self, label: str, context_id: str) -> None:
        button = dict(
            self.wait(
                lambda: self.read(
                    "const heading=[...document.querySelectorAll('main h3')]"
                    ".find(x=>x.textContent.trim()===arguments[0]);"
                    "return heading?[...heading.parentElement.querySelectorAll('button')]"
                    ".find(b=>b.textContent.trim()==='Review view selection'&&!b.disabled):null;",
                    label,
                ),
                "context selection button",
            )
        )
        self.click(button)
        self.review("select", label, context_id)
        self.selected(context_id)

    def selected(self, context_id: str) -> None:
        self.wait(
            lambda: self.read(
                "const selected=document.querySelector("
                "'section[aria-label=\"Context view\"] select');"
                "return selected&&!selected.disabled&&selected.value===arguments[0];",
                context_id,
            ),
            "persisted selected view",
        )

    def close(self) -> None:
        if sys.exception() is not None:
            with contextlib.suppress(OSError):
                self.diagnostics()
        try:
            if self.session is not None:
                with contextlib.suppress(OSError, ValueError, http.client.HTTPException):
                    self.command("DELETE", "")
        finally:
            self.http.close()
            # Only this fixture's own process group contains the driver and app.
            with contextlib.suppress(ProcessLookupError):
                os.killpg(self.process.pid, signal.SIGTERM)
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=10)
            self.log.close()

    def diagnostics(self) -> None:
        self.log.flush()
        with self.log_path.open("rb") as log:
            log.seek(0, os.SEEK_END)
            log.seek(max(0, log.tell() - 65536))
            tail = log.read().decode(errors="replace")
        # Only fixed marker booleans and the owned process's exit code leave
        # this fixture. Do not print request bodies, raw logs or DOM contents.
        print(
            json.dumps(
                {
                    "diagnostic": "installed_webdriver",
                    "stage": self.stage,
                    "driver_exit_code": self.process.poll(),
                    "markers": {
                        "proxy_connection_error": "Error serving connection:" in tail,
                        "canceled": "Canceled" in tail or "canceled" in tail,
                        "incomplete_message": "IncompleteMessage" in tail,
                        "connection_reset": "Connection reset" in tail,
                        "rust_panic": "panicked at" in tail,
                        "webkit_process_terminated": "WebProcess terminated" in tail,
                    },
                }
            ),
            flush=True,
        )


def native(binary: Path, environment: dict[str, str], arguments: list[str]) -> dict[str, Any]:
    result = subprocess.run(
        [str(binary), *arguments, "--json"],
        env=environment,
        capture_output=True,
        timeout=60,
        check=False,
    )
    require(result.returncode == 0 and not result.stderr, "installed native readback failed")
    envelope = json.loads(result.stdout)
    require(envelope["ok"] is True, "installed native returned an error")
    return dict(envelope["data"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--driver", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    require(
        os.environ.get("GITHUB_ACTIONS") == "true" and os.environ.get("RUNNER_OS") == "Linux",
        "only a disposable Linux CI runner is supported",
    )
    require(
        os.environ.get("AI_STP_TEST_SECRET_SERVICE") == "isolated", "private bus fixture required"
    )
    root = Path(os.environ["AI_STP_TEST_SECRET_SERVICE_ROOT"]).resolve(strict=True)
    require(
        root.is_relative_to(Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)), "foreign fixture"
    )
    home = root / "home"
    home.mkdir(mode=0o700)
    cache = root / "cache"
    cache.mkdir(mode=0o700)
    canary = home / "AGENTS.md"
    canary_bytes = b"# Owner instruction canary\nPreserve this unrelated file.\n"
    canary.write_bytes(canary_bytes)
    canary.chmod(0o640)
    environment = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "XDG_CACHE_HOME": str(cache),
        "TAURI_WEBVIEW_AUTOMATION": "true",
        **{
            name: os.environ[name]
            for name in (
                "DISPLAY",
                "XAUTHORITY",
                "DBUS_SESSION_BUS_ADDRESS",
                "XDG_RUNTIME_DIR",
                "XDG_CONFIG_HOME",
                "XDG_DATA_HOME",
            )
        },
    }
    installed = subprocess.check_output(["dpkg-query", "--listfiles", "ai-stp-desktop"], text=True)
    binaries = [
        Path(line) for line in installed.splitlines() if line.endswith("/cli/ai-stp-desktop-cli")
    ]
    require(len(binaries) == 1 and binaries[0].is_file(), "one actual installed CLI is required")
    binary = binaries[0].resolve(strict=True)
    version_response = native(binary, environment, ["version"])
    require(
        version_response["runtime"] == "rust" and version_response["wire_schema_version"] == 1,
        "installed CLI returned an unsupported version contract",
    )
    version = version_response["cli_version"]
    require(isinstance(version, str) and bool(version), "installed CLI version is absent")
    before = native(binary, environment, ["doctor"])
    require(
        any(
            c["name"] == "local_identity" and c["state"] == "needs_user_action"
            for c in before["checks"]
        ),
        "fixture already has an identity",
    )
    driver = Driver(args.driver.resolve(strict=True), environment, root / "first-driver.log")
    try:
        driver.start()
        driver.wait(
            lambda: driver.read(
                "return document.querySelector('main').textContent.includes(arguments[0]);",
                f"Rust {version}",
            ),
            "bundled Rust engine through actual IPC",
        )
        driver.navigate("settings")
        storage = dict(
            driver.wait(
                lambda: driver.read(
                    "const select=document.querySelector('main form select');"
                    "return select&&!select.disabled&&select.options.length?select:null;"
                ),
                "loaded credential store choices",
            )
        )
        require(
            driver.read("return arguments[0].value;", storage) == "os_keyring",
            "vault is not the default",
        )
        driver.click(driver.find('main form input[type="checkbox"]'))
        driver.click(driver.button("Initialize workspace"))
        driver.wait(
            lambda: driver.read(
                "return document.querySelector('main').textContent.includes('Initialized');"
            ),
            "UI native vault initialization",
        )
        identity = native(binary, environment, ["device", "show"])
        require(
            identity["credential_store"] == "os_keyring", "native key silently used file storage"
        )
        driver.navigate("profiles")
        first = driver.create_context("Installed personal one")
        second = driver.create_context("Installed personal two")
        require(first != second, "contexts share an identity")
        driver.select_context("Installed personal one", first)
        listed = native(binary, environment, ["context", "list"])
        require(
            listed["selected"]["context_id"] == first and len(listed["contexts"]) == 2,
            "installed CLI and UI differ",
        )
    finally:
        driver.close()
    driver = Driver(args.driver.resolve(strict=True), environment, root / "restarted-driver.log")
    try:
        driver.start()
        driver.selected(first)
        driver.navigate("profiles")
        driver.select_context("Installed personal two", second)
        listed = native(binary, environment, ["context", "list"])
        require(
            listed["selected"]["context_id"] == second and len(listed["contexts"]) == 2,
            "restart or switching lost native contexts",
        )
        require(
            native(binary, environment, ["device", "show"]) == identity,
            "restart replaced native identity",
        )
    finally:
        driver.close()
    require(
        canary.read_bytes() == canary_bytes and canary.stat().st_mode & 0o777 == 0o640,
        "context switching changed unowned home instructions",
    )
    args.out.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "evidence_type": "installed_linux_desktop",
                "consumer_commit": os.environ["GITHUB_SHA"],
                "native_version": version,
                "webdriver_transport": "persistent_http1",
                "installed_cli_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
                "actual_release_package": True,
                "actual_bundled_cli_ipc": True,
                "native_os_keyring": True,
                "two_offline_personal_contexts": True,
                "view_switching_and_restart_persistence": True,
                "independent_installed_cli_readback": True,
                "unowned_home_instructions_preserved": True,
                "corporate_enrollment_qualified": False,
                "harness_activation_qualified": False,
            },
            indent=2,
        )
        + "\n"
    )
    print("Installed release UI, bundled CLI, native vault and restart/context journey passed.")


if __name__ == "__main__":
    main()
