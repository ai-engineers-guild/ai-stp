"""Exercise the installed Linux release through its UI, bundled CLI and real vault.

Run only in the disposable CI Secret Service fixture. JavaScript reads the DOM;
WebDriver sends actual clicks/keys. No IPC replacement or development server is used.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import hashlib
import http.client
import io
import json
import os
import re
import signal
import socket
import subprocess
import sys
import tarfile
import time
import urllib.request
from pathlib import Path
from typing import Any

ELEMENT = "element-6066-11e4-a52e-4f735466cecf"
REVIEW = 'section[aria-label="Review native profile plan"]'
_axe_tool: tuple[str, str] | None = None


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def driver_children(pid: int) -> dict[str, Any]:
    """Observe only the owned Linux driver's direct children, without private prose."""
    result: dict[str, Any] = {"observation": "unavailable"}
    try:
        task = Path(f"/proc/{pid}/task/{pid}/children")
        with task.open() as stream:
            content = stream.read(4097)
        children = content.split()
        if len(content) > 4096 or len(children) > 8 or any(not c.isdecimal() for c in children):
            return {"observation": "bounded"}
        running = 0
        exited: list[int] = []
        for child in children:
            with Path(f"/proc/{child}/stat").open() as stream:
                status = stream.read(4097)
            # The comm field may contain spaces and parentheses. Do not emit it.
            fields = status.rpartition(") ")[2].split()
            if (
                len(status) > 4096
                or len(fields) < 50
                or fields[0] not in {"R", "S", "D", "T", "t", "Z", "X", "x", "K", "W", "P", "I"}
                or int(fields[1]) != pid
            ):
                return result
            if fields[0] in {"Z", "X", "x"}:
                code = os.waitstatus_to_exitcode(int(fields[49]))
                if not -64 <= code <= 255:
                    return result
                exited.append(code)
            else:
                running += 1
        return {
            "observation": "read",
            "direct_children": len(children),
            "running": running,
            "exit_codes": sorted(exited),
        }
    except (OSError, ValueError, IndexError):
        return result


def owned_child_identities(pid: int) -> list[tuple[int, str]]:
    """Retain exact direct-child identities before stopping this fixture's driver."""
    with Path(f"/proc/{pid}/task/{pid}/children").open() as stream:
        content = stream.read(4097)
    children = content.split()
    require(len(content) <= 4096 and len(children) <= 8, "owned child inventory exceeds its bound")
    result: list[tuple[int, str]] = []
    for child in children:
        require(child.isdecimal(), "invalid owned child identity")
        try:
            with Path(f"/proc/{child}/stat").open() as stream:
                status = stream.read(4097)
        except (FileNotFoundError, ProcessLookupError):
            # An already-open procfs descriptor reports ESRCH after exit.
            continue
        fields = status.rpartition(") ")[2].split()
        require(
            len(status) <= 4096 and len(fields) >= 20 and fields[19].isdecimal(),
            "invalid owned child observation",
        )
        require(int(fields[1]) == pid, "native driver child ownership changed")
        result.append((int(child), fields[19]))
    return result


def wait_owned_children(children: list[tuple[int, str]]) -> None:
    """A proxy exit alone does not prove its native child released its listener."""
    deadline = time.monotonic() + 10
    while children:
        remaining: list[tuple[int, str]] = []
        for pid, started in children:
            try:
                with Path(f"/proc/{pid}/stat").open() as stream:
                    status = stream.read(4097)
            except (FileNotFoundError, ProcessLookupError):
                continue
            fields = status.rpartition(") ")[2].split()
            require(len(status) <= 4096 and len(fields) >= 20, "invalid owned child completion")
            if fields[19] == started and fields[0] not in {"Z", "X", "x"}:
                remaining.append((pid, started))
        if not remaining:
            return
        require(time.monotonic() < deadline, "owned native WebDriver did not finish during cleanup")
        children = remaining
        time.sleep(0.02)


def axe_source() -> tuple[str, str]:
    """Use the existing web lock's immutable tool, only in disposable CI/RAM."""
    global _axe_tool
    if _axe_tool is not None:
        return _axe_tool
    require(
        os.environ.get("GITHUB_ACTIONS") == "true" and os.environ.get("RUNNER_OS") == "Linux",
        "accessibility tooling is CI-only",
    )
    lock = Path(__file__).resolve().parents[2] / "apps/web/bun.lock"
    metadata = subprocess.run(
        [
            "bun",
            "-e",
            "const lock=Bun.JSONC.parse(await Bun.file("
            + json.dumps(str(lock))
            + ").text());const entry=lock.packages['axe-core'];"
            "if(!Array.isArray(entry)||!entry[0].startsWith('axe-core@'))"
            "throw new Error('Missing canonical accessibility tool');"
            "console.log(JSON.stringify({version:entry[0].slice(9),integrity:entry[3]}));",
        ],
        capture_output=True,
        timeout=15,
        check=False,
    )
    require(
        metadata.returncode == 0 and not metadata.stderr and len(metadata.stdout) <= 1024,
        "cannot read the canonical web accessibility lock using the pinned CI Bun",
    )
    pin = json.loads(metadata.stdout)
    version, integrity = pin["version"], pin["integrity"]
    require(
        isinstance(version, str)
        and re.fullmatch(r"[0-9]{1,5}\.[0-9]{1,5}\.[0-9]{1,5}", version) is not None
        and isinstance(integrity, str)
        and integrity.startswith("sha512-"),
        "canonical accessibility pin is not an exact stable registry artifact",
    )
    expected_digest = base64.b64decode(integrity[7:], validate=True)
    require(len(expected_digest) == 64, "canonical accessibility digest is malformed")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    url = f"https://registry.npmjs.org/axe-core/-/axe-core-{version}.tgz"
    with opener.open(url, timeout=30) as response:
        require(response.url == url, "accessibility tool redirected")
        archive_bytes = response.read(4 * 1024 * 1024 + 1)
    require(len(archive_bytes) <= 4 * 1024 * 1024, "accessibility tool exceeds download bound")
    require(
        hashlib.sha512(archive_bytes).digest() == expected_digest,
        "accessibility tool integrity differs from the pinned registry artifact",
    )
    source = None
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
        expanded = 0
        for count, member in enumerate(archive, 1):
            expanded += member.size
            require(
                count <= 100
                and expanded <= 16 * 1024 * 1024
                and (member.isfile() or member.isdir()),
                "accessibility tool inventory exceeds its bound",
            )
            if member.name == "package/axe.min.js":
                require(source is None and member.isfile(), "ambiguous accessibility executable")
                require(member.size <= 2 * 1024 * 1024, "accessibility executable exceeds bound")
                stream = archive.extractfile(member)
                require(stream is not None, "accessibility executable is absent")
                with stream:
                    source = stream.read(2 * 1024 * 1024 + 1).decode("utf-8")
    if source is None or not source:
        raise ValueError("accessibility executable is absent")
    _axe_tool = source, version
    return _axe_tool


class Driver:
    def __init__(self, executable: Path, environment: dict[str, str], log: Path):
        # urllib forces Connection: close, which the intermediary forwards to
        # its pooled WebKit connection. Keep this owned HTTP/1.1 transport alive;
        # never replay a failed command, including clicks or session creation.
        # Choose both currently free endpoints under simultaneous reservations.
        # Stale listeners from another session cannot own either selected port.
        with socket.socket() as proxy, socket.socket() as native:
            proxy.bind(("127.0.0.1", 0))
            native.bind(("127.0.0.1", 0))
            self.port, self.native_port = proxy.getsockname()[1], native.getsockname()[1]
        self.http = http.client.HTTPConnection("127.0.0.1", self.port, timeout=90)
        self.session: str | None = None
        self.log_path = log
        self.stage = "starting"
        self.last_response_ok = False
        self.app_started = 0.0
        self.startup_ms = 0.0
        self.accessibility: list[dict[str, Any]] = []
        self.readiness_observations = {
            "connection_refused": 0,
            "connection_reset": 0,
            "disconnected": 0,
            "timeout": 0,
            "other_transport": 0,
            "not_ready": 0,
        }
        self.log = log.open("wb")
        self.process = subprocess.Popen(
            [
                str(executable),
                "--port",
                str(self.port),
                "--native-port",
                str(self.native_port),
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
        self.last_response_ok = False
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
        self.last_response_ok = True
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
            children = driver_children(self.process.pid)
            require(
                not (
                    children.get("observation") == "read"
                    and children.get("exit_codes")
                    and children.get("running") == 0
                ),
                "owned native WebDriver exited before readiness",
            )
            try:
                status = self.request("GET", "/status")
                require(
                    isinstance(status, dict) and isinstance(status.get("ready"), bool),
                    "WebDriver returned an invalid readiness observation",
                )
                if not status["ready"]:
                    self.readiness_observations["not_ready"] += 1
                return status["ready"]
            except (OSError, http.client.HTTPException) as error:
                # Readiness is an observation before any application session.
                category = (
                    "connection_refused"
                    if isinstance(error, ConnectionRefusedError)
                    else "connection_reset"
                    if isinstance(error, ConnectionResetError)
                    else "timeout"
                    if isinstance(error, TimeoutError)
                    else "disconnected"
                    if isinstance(error, http.client.RemoteDisconnected)
                    else "other_transport"
                )
                self.readiness_observations[category] += 1
                self.http.close()
                return False

        self.wait(ready, "WebDriver readiness")
        self.app_started = time.monotonic()
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
        self.startup_ms = round((time.monotonic() - self.app_started) * 1000, 2)

    def theme(self, dark: bool) -> None:
        if self.read("return document.documentElement.classList.contains('dark');") != dark:
            label = "Use dark theme" if dark else "Use light theme"
            self.click(self.find(f'button[aria-label="{label}"]'))
        self.wait(
            lambda: (
                self.read("return document.documentElement.classList.contains('dark');") == dark
            ),
            "actual theme control",
        )
        self.wait(
            lambda: self.read(
                "return document.getAnimations().every(a=>a.playState!=='running'||"
                "a.effect?.getComputedTiming().iterations===Infinity);"
            ),
            "completed finite theme transitions",
        )

    def audit_accessibility(self, surface: str) -> None:
        require(not self.read("return document.querySelector('iframe');"), "uninspected frame")
        source, version = axe_source()
        require(self.read(source + "\nreturn axe.version;") == version, "wrong axe engine")
        self.command("POST", "/timeouts", {"script": 30000})
        report = self.command(
            "POST",
            "/execute/async",
            {
                "script": "const done=arguments[arguments.length-1];"
                "const summarize=v=>{const out={id:v.id,impact:v.impact,count:v.nodes.length};"
                "if(v.id==='color-contrast')out.contrast=v.nodes.slice(0,16).flatMap(n=>"
                "n.any.filter(c=>c.id==='color-contrast').slice(0,1).map(c=>{"
                "const d=c.data||{},number=x=>Number.isFinite(parseFloat(x))?parseFloat(x):null,"
                "color=x=>typeof x==='string'&&/^#[0-9a-f]{3,8}$/i.test(x)?x:null;"
                "return {foreground:color(d.fgColor),background:color(d.bgColor),"
                "ratio:number(d.contrastRatio),expected:number(d.expectedContrastRatio)};}));"
                "return out;};"
                "axe.run(document,{runOnly:{type:'tag',values:"
                "['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa','best-practice']},"
                "resultTypes:['violations','incomplete','passes']}).then(r=>done({"
                "engine:r.testEngine.version,passes:r.passes.length,"
                "violations:r.violations.map(summarize),"
                "incomplete:r.incomplete.map(v=>({id:v.id,impact:v.impact,count:v.nodes.length}))"
                "})).catch(()=>done({failed:true}));",
                "args": [],
            },
        )
        require(
            isinstance(report, dict)
            and report.get("engine") == version
            and isinstance(report.get("passes"), int)
            and report["passes"] > 0
            and isinstance(report.get("violations"), list)
            and isinstance(report.get("incomplete"), list),
            "accessibility engine did not execute its real document checks",
        )
        # Retain fixed rule IDs/counts and bounded numeric/hex contrast operands.
        # No HTML, selectors, text, accounts, screenshots or raw DOM leave it.
        require(
            not report["violations"],
            "Installed accessibility violations: " + json.dumps(report["violations"]),
        )
        self.accessibility.append({"surface": surface, **report})

    def observe_reduced_motion(self) -> None:
        require(
            self.read("return matchMedia('(prefers-reduced-motion: reduce)').matches;"),
            "installed webview did not inherit its owned GTK reduced-motion preference",
        )
        self.read(
            "window.__installedMotion=[];"
            "window.__installedMotionObserver=new MutationObserver(()=>{"
            "for(const spinner of document.querySelectorAll('[role=status] .animate-spin')){"
            "if(window.__installedMotion.length<16)"
            "window.__installedMotion.push(getComputedStyle(spinner).animationName);}});"
            "window.__installedMotionObserver.observe(document,{childList:true,subtree:true});"
        )

    def reduced_motion_observed(self) -> int:
        observations = self.read(
            "window.__installedMotionObserver.disconnect();return window.__installedMotion;"
        )
        require(
            isinstance(observations, list)
            and bool(observations)
            and all(value == "none" for value in observations),
            "actual native-loading status animations ignored reduced motion",
        )
        return len(observations)

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

    def navigate(self, route: str, *, keyboard: bool = False) -> None:
        link = self.find(f'nav[aria-label="Main navigation"] a[href="#/{route}"]')
        if keyboard:
            # Exercise actual accessible link activation, including when a
            # retained company identity changes the scrollable sidebar height.
            self.command("POST", f"/element/{link[ELEMENT]}/value", {"text": "\ue007"})
            self.wait(
                lambda: self.read("return location.hash===arguments[0];", "#/" + route),
                "keyboard navigation",
            )
        else:
            self.click(link)

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
        if sys.exception() is not None and not self.log.closed:
            with contextlib.suppress(OSError, ValueError):
                self.diagnostics()
        children: list[tuple[int, str]] = []
        try:
            if self.process.poll() is None:
                children = owned_child_identities(self.process.pid)
            if self.session is not None:
                with contextlib.suppress(OSError, ValueError, http.client.HTTPException):
                    self.command("DELETE", "")
        finally:
            self.http.close()
            # Only this fixture's own process group contains the driver and app.
            try:
                if self.process.poll() is None:
                    with contextlib.suppress(ProcessLookupError):
                        os.killpg(self.process.pid, signal.SIGTERM)
                try:
                    self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    with contextlib.suppress(ProcessLookupError):
                        os.killpg(self.process.pid, signal.SIGKILL)
                    self.process.wait(timeout=10)
                wait_owned_children(children)
            finally:
                self.log.close()

    def diagnostics(self) -> None:
        self.log.flush()
        with self.log_path.open("rb") as log:
            log.seek(0, os.SEEK_END)
            log.seek(max(0, log.tell() - 65536))
            tail = log.read().decode(errors="replace")
        # The rendered CLI already provides safe credential-stage categories.
        # Observe that original refusal only after a successful driver command;
        # never reuse a transport whose previous command did not complete.
        stage = self.stage
        driver_exit_code = self.process.poll()
        children = (
            driver_children(self.process.pid)
            if driver_exit_code is None
            else {"observation": "driver_exited"}
        )
        public_failures: list[dict[str, str]] = []
        public_failure_observation = "not_read"
        allowed = {
            "credential_stage": {
                "session_address",
                "session_transport",
                "connect",
                "proxy",
                "service_collections",
                "service_collections_shape",
                "search_items",
                "search_locked_or_ambiguous",
                "open_session",
                "open_session_shape",
                "close_session",
                "get_secret",
                "get_secret_shape",
                "set_secret",
                "read_default_alias",
                "default_collection_absent",
                "read_collection_lock",
                "collection_locked",
                "create_item",
                "create_item_prompt",
                "delete_item",
                "delete_item_prompt",
            },
            "credential_error_kind": {
                "no_reply",
                "timeout",
                "service_absent",
                "unknown_object",
                "unknown_method",
                "remote_failure",
                "invalid_arguments",
                "access_denied",
                "disconnected",
                "resource_limit",
                "standard_remote_error",
                "secret_locked",
                "secret_session_absent",
                "secret_object_absent",
                "remote_error",
                "transport",
                "invalid_reply",
                "wire_type",
                "handshake",
                "other",
            },
        }
        if self.session is not None and self.last_response_ok:
            try:
                observed = self.read(
                    "return [...document.querySelectorAll('main [role=alert] pre')]"
                    ".slice(0,4).flatMap(node=>{"
                    "const text=node.textContent;if(text.length>8192)return [];"
                    "try{const detail=JSON.parse(text);"
                    "if(!detail||typeof detail!=='object')return [];"
                    "const selected=Object.fromEntries(Object.entries(arguments[0])"
                    ".filter(([key,values])=>values.includes(detail[key]))"
                    ".map(([key])=>[key,detail[key]]));"
                    "return Object.keys(selected).length?[selected]:[];"
                    "}catch{return [];}});",
                    {key: sorted(values) for key, values in allowed.items()},
                )
                if isinstance(observed, list):
                    for item in observed[:4]:
                        if isinstance(item, dict):
                            selected = {
                                key: value
                                for key, value in item.items()
                                if key in allowed
                                and isinstance(value, str)
                                and value in allowed[key]
                            }
                            if selected:
                                public_failures.append(selected)
                    public_failure_observation = "read"
            except (OSError, ValueError, KeyError, TypeError, http.client.HTTPException):
                public_failure_observation = "unavailable"
            finally:
                self.stage = stage
        # Only fixed categories, marker booleans and the owned process's exit
        # code leave the fixture. No raw DOM, detail values or error prose.
        print(
            json.dumps(
                {
                    "diagnostic": "installed_webdriver",
                    "stage": stage,
                    "public_failure_observation": public_failure_observation,
                    "public_credential_failures": public_failures,
                    "driver_exit_code": driver_exit_code,
                    "readiness_observations": self.readiness_observations,
                    "driver_children": children,
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


def inspect_personal_task(driver: Driver, task_id: str, ownership: dict[str, Any]) -> None:
    """Open a real journal row through Activity, without substituting IPC."""
    require(bool(re.fullmatch(r"task_[0-7][0-9A-HJKMNP-TV-Z]{25}", task_id)), "invalid task")
    driver.navigate("tasks")
    driver.click(driver.find(f'main a[href="#/install?task={task_id}"]'))
    driver.wait(
        lambda: driver.read(
            "const text=document.querySelector('main').textContent;"
            "return text.includes(arguments[0])&&text.includes(arguments[1]);",
            task_id,
            "Personal task · retained local owner",
        ),
        "native personal task ownership in the installed workspace",
    )
    summary = dict(
        driver.wait(
            lambda: driver.read(
                "return [...document.querySelectorAll('main summary')]"
                ".find(x=>x.textContent==='Original task identity')??null;"
            ),
            "original task identity disclosure",
        )
    )
    driver.click(summary)
    require(
        driver.read(
            "const values=[...document.querySelectorAll('main dd')].map(x=>x.textContent);"
            "return values.includes(arguments[0])&&values.includes(arguments[1]);",
            ownership["native_account_id"],
            ownership["native_device_id"],
        ),
        "installed task workspace changed the original native owner",
    )


def inspect_task_trace(
    driver: Driver, commands: tuple[str, ...], forbidden: tuple[str, ...]
) -> None:
    """Inspect actual diagnostic rows after native task effects and readbacks."""
    driver.navigate("debug")
    for name in commands:
        entry = driver.wait(
            lambda command_name=name: driver.read(
                "return [...document.querySelectorAll('main li button')]"
                ".find(b=>b.querySelector('span.w-40')?.textContent===arguments[0])??null;",
                command_name,
            ),
            "actual private task trace entry",
        )
        driver.click(entry)
        text = driver.read("return arguments[0].closest('li').textContent;", entry)
        require(
            "[private content omitted]" in text and all(value not in text for value in forbidden),
            "shared diagnostics retained private task content",
        )


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
    version_started = time.monotonic()
    version_response = native(binary, environment, ["version"])
    native_version_read_ms = round((time.monotonic() - version_started) * 1000, 2)
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
        native_contract_ready_ms = round((time.monotonic() - driver.app_started) * 1000, 2)
        first_start_ms = driver.startup_ms
        driver.theme(False)
        driver.audit_accessibility("offline-overview-light")
        driver.theme(True)
        driver.audit_accessibility("offline-overview-dark")
        driver.theme(False)
        skip = driver.find("a.skip-link")
        original_route = driver.read("return location.hash;")
        driver.command("POST", f"/element/{skip[ELEMENT]}/value", {"text": "\ue007"})
        require(
            driver.read("return document.activeElement?.id;") == "main-content"
            and driver.read("return location.hash;") == original_route,
            "keyboard skip link did not focus content without retargeting the route",
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
        driver.navigate("debug")
        driver.wait(
            lambda: driver.read(
                "return document.querySelector('main h1')?.textContent==='Diagnostics';"
            ),
            "diagnostic page committed after leaving workspace settings",
        )
        trace_toggle = driver.find('main input[type="checkbox"]')
        require(
            not driver.read("return arguments[0].checked;", trace_toggle), "trace is not opt-in"
        )
        driver.click(trace_toggle)
        require(driver.read("return arguments[0].checked;", trace_toggle), "trace was not enabled")
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
        driver.audit_accessibility("retained-personal-profiles")
        accessibility = list(driver.accessibility)
        local = next(
            item["context"]["local_identity"]
            for item in listed["contexts"]
            if item["context"]["context_id"] == first
        )
        task_ownership = {
            "kind": "personal",
            "native_account_id": local["account_id"],
            "native_device_id": local["device_id"],
        }
        driver.navigate("install")
        driver.click(driver.button("Create from files"))
        driver.click(driver.find('main fieldset input[type="checkbox"]'))
        driver.click(driver.button("Start authoring"))
        task_id = driver.wait(
            lambda: driver.read(
                "return new URLSearchParams(location.hash.split('?')[1]??'').get('task');"
            ),
            "UI task start opened its original native receipt",
        )
        require(
            isinstance(task_id, str)
            and bool(re.fullmatch(r"task_[0-7][0-9A-HJKMNP-TV-Z]{25}", task_id)),
            "installed UI returned an invalid task identity",
        )
        task = native(binary, environment, ["task", "status", "--task", task_id])
        require(
            task["task_id"] == task_id
            and task["state"] == "blocked"
            and task["ownership"] == task_ownership
            and task["child_operation_ids"] == [],
            "native personal task admission differs",
        )
        inspect_personal_task(driver, task_id, task_ownership)
        inspect_task_trace(
            driver,
            ("task_start", "task_status", "task_list"),
            (task_id, local["account_id"], local["device_id"]),
        )
    finally:
        driver.close()
    # Only this disposable fixture's GTK configuration is changed. A fresh real
    # app process must inherit the preference; do not emulate matchMedia or IPC.
    gtk = Path(environment["XDG_CONFIG_HOME"]) / "gtk-3.0"
    gtk.mkdir(exist_ok=True)
    with (gtk / "settings.ini").open("x") as settings:
        settings.write("[Settings]\ngtk-enable-animations=false\n")
    driver = Driver(args.driver.resolve(strict=True), environment, root / "restarted-driver.log")
    try:
        driver.start()
        restart_start_ms = driver.startup_ms
        driver.selected(first)
        driver.observe_reduced_motion()
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
        reduced_motion_observations = driver.reduced_motion_observed()
        driver.audit_accessibility("restarted-personal-profiles-reduced-motion")
        accessibility.extend(driver.accessibility)
        inspect_personal_task(driver, task_id, task_ownership)
        require(
            native(binary, environment, ["task", "status", "--task", task_id]) == task,
            "restart or view switching retargeted the original task",
        )
        driver.click(driver.button("Cancel task"))
        driver.button("Start another flow")
        cancelled = native(binary, environment, ["task", "status", "--task", task_id])
        require(
            cancelled["state"] == "cancelled"
            and cancelled["ownership"] == task_ownership
            and cancelled["child_operation_ids"] == [],
            "installed task cancellation changed its original owner or created child effects",
        )
        inspect_task_trace(
            driver,
            ("task_cancel", "task_status", "task_list"),
            (task_id, local["account_id"], local["device_id"]),
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
                "personal_task_started_through_ui": True,
                "personal_task_ownership_after_restart": True,
                "personal_task_original_owner_after_view_switch": True,
                "personal_task_cancelled_original_receipt": True,
                "installed_personal_task_trace_privacy": True,
                "independent_installed_cli_readback": True,
                "unowned_home_instructions_preserved": True,
                "keyboard_skip_link_focuses_content": True,
                "reduced_motion_actual_loading_observations": reduced_motion_observations,
                "accessibility_checks": accessibility,
                "performance_observations_ms": {
                    "first_app_session_to_main": first_start_ms,
                    "first_app_session_to_native_contract": native_contract_ready_ms,
                    "restarted_app_session_to_main": restart_start_ms,
                    "installed_cli_version_read": native_version_read_ms,
                },
                "performance_budget_qualified": False,
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
