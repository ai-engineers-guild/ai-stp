"""Compare exact installed packages on one disposable worker with fresh app profiles."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def distribution(values: list[float], *, allow_zero: bool = False) -> dict[str, float | int]:
    if not values or any(
        not math.isfinite(value) or value < 0 or (value == 0 and not allow_zero) for value in values
    ):
        raise ValueError("Performance samples must be finite observations in their declared range")
    ordered = sorted(values)
    return {
        "count": len(values),
        "min_ms": min(values),
        "p50_ms": round(statistics.median(values), 2),
        "p95_ms": ordered[math.ceil(len(values) * 0.95) - 1],
        "max_ms": max(values),
    }


def ready(driver: Any, route: str, title: str) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if driver.read(
            "return (location.hash===arguments[0]||"
            "(arguments[0]==='#/'&&location.hash===''))&&"
            "document.querySelector('main h1')?.textContent===arguments[1]&&"
            "!document.querySelector('section[aria-label=\"Context view\"] select')?.disabled;",
            "#/" + route,
            title,
        ):
            driver.read(
                "return document.fonts.ready.then(()=>new Promise(resolve=>"
                "requestAnimationFrame(()=>requestAnimationFrame(()=>resolve(true)))));"
            )
            return
        time.sleep(0.005)
    raise ValueError("Installed navigation did not reach its usable surface")


def navigate(driver: Any, route: str, title: str) -> dict[str, float]:
    observer = Path(__file__).with_name("desktop-navigation-timing.js").read_text()
    driver.read("return (" + observer + ")(...arguments);", route, title)
    started = time.monotonic()
    driver.navigate(route)
    ready(driver, route, title)
    observation = driver.read("return window.__aiStpNavigationTiming.promise;")
    end_to_end = (time.monotonic() - started) * 1000
    if (
        not isinstance(observation, dict)
        or observation.get("route") != route
        or observation.get("trusted") is not True
        or type(observation.get("renderer_ms")) not in {int, float}
    ):
        raise ValueError("Renderer timing did not observe the intended actual navigation")
    renderer = float(observation["renderer_ms"])
    overhead = end_to_end - renderer
    if not math.isfinite(renderer) or renderer <= 0 or not math.isfinite(overhead) or overhead < 0:
        raise ValueError("Renderer and end-to-end observation clocks are inconsistent")
    return {
        "end_to_end_ms": round(end_to_end, 2),
        "renderer_ms": round(renderer, 2),
        "automation_and_control_ms": round(overhead, 2),
    }


def sample(module: Any, driver_path: Path, root: Path) -> dict[str, Any]:
    root.mkdir(mode=0o700)
    environment = {
        "PATH": "/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "TAURI_WEBVIEW_AUTOMATION": "true",
        **{
            name: os.environ[name]
            for name in (
                "DISPLAY",
                "XAUTHORITY",
                "DBUS_SESSION_BUS_ADDRESS",
                "XDG_RUNTIME_DIR",
            )
        },
    }
    for key, directory in (
        ("HOME", "home"),
        ("XDG_CONFIG_HOME", "config"),
        ("XDG_DATA_HOME", "data"),
        ("XDG_CACHE_HOME", "cache"),
    ):
        path = root / directory
        path.mkdir(mode=0o700)
        environment[key] = str(path)
    files = subprocess.check_output(
        ["dpkg-query", "--listfiles", "ai-stp-desktop"],
        text=True,
    ).splitlines()
    binaries = [Path(path) for path in files if path.endswith("/cli/ai-stp-desktop-cli")]
    module.require(len(binaries) == 1, "one installed bundled CLI is required")
    binary = binaries[0].resolve(strict=True)
    version = module.native(binary, environment, ["version"])
    module.require(version["runtime"] == "rust", "installed engine is not native")
    module.native(binary, environment, ["init", "--credential-store", "os_keyring"])
    driver = module.Driver(driver_path, environment, root / "driver.log")
    try:
        driver.start()
        driver.wait(
            lambda: driver.read(
                "return document.querySelector('main').textContent"
                ".includes('Create your workspace');"
            ),
            "initialized Overview with its native context observation",
        )
        ready(driver, "", "Your workspace")
        webview_usable_ms = float(driver.read("return performance.now();"))
        usable_start_ms = round((time.monotonic() - driver.app_started) * 1000, 2)
        dark = driver.read("return document.documentElement.classList.contains('dark');")
        driver.navigate("profiles")
        context = driver.create_context("Performance personal")
        driver.select_context("Performance personal", context)
        first_settings = navigate(driver, "settings", "Settings")
        driver.navigate("")
        ready(driver, "", "Your workspace")
        navigation: dict[str, list[float]] = {"profiles": [], "settings": [], "overview": []}
        renderer_navigation: dict[str, list[float]] = {key: [] for key in navigation}
        automation_navigation: dict[str, list[float]] = {key: [] for key in navigation}
        for _round in range(6):
            for route, title in (
                ("profiles", "Connections and contexts"),
                ("settings", "Settings"),
                ("", "Your workspace"),
            ):
                observed = navigate(driver, route, title)
                key = route or "overview"
                navigation[key].append(observed["end_to_end_ms"])
                renderer_navigation[key].append(observed["renderer_ms"])
                automation_navigation[key].append(observed["automation_and_control_ms"])
        driver.selected(context)
        return {
            "first_main_ms": driver.startup_ms,
            "usable_start_ms": usable_start_ms,
            "first_settings_ms": first_settings["end_to_end_ms"],
            "first_settings_renderer_ms": first_settings["renderer_ms"],
            "first_settings_automation_and_control_ms": first_settings["automation_and_control_ms"],
            "webview_usable_ms": round(webview_usable_ms, 2),
            "navigation_ms": navigation,
            "renderer_navigation_ms": renderer_navigation,
            "automation_navigation_ms": automation_navigation,
            "cli_version": version["cli_version"],
            "dark_theme": dark,
        }
    finally:
        driver.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-directory", type=Path, required=True)
    parser.add_argument("--current-package", type=Path, required=True)
    parser.add_argument("--driver", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if not (
        os.environ.get("GITHUB_ACTIONS") == "true"
        and os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted"
        and os.environ.get("RUNNER_OS") == "Linux"
        and os.environ.get("AI_STP_TEST_SECRET_SERVICE") == "isolated"
    ):
        raise ValueError("Only the disposable hosted Linux vault fixture is supported")
    fixture = Path(os.environ["AI_STP_TEST_SECRET_SERVICE_ROOT"]).resolve(strict=True)
    temporary = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
    if not fixture.is_relative_to(temporary):
        raise ValueError("Performance fixture is outside this job")
    manifest = json.loads((ROOT / ".github/desktop-performance-baseline.json").read_text())
    asset = manifest["assets"][0]
    baseline = args.baseline_directory.resolve(strict=True) / asset["file"]
    current = args.current_package.resolve(strict=True)
    if not baseline.is_relative_to(temporary) or not current.is_relative_to(ROOT):
        raise ValueError("Performance packages must belong to the admitted job")
    if baseline.stat().st_size != asset["size"] or sha256(baseline) != asset["sha256"]:
        raise ValueError("Baseline package differs from its exact admitted bytes")
    current_digest = sha256(current)
    current_version = json.loads((ROOT / "apps/desktop/package.json").read_text())["version"]
    specification = importlib.util.spec_from_file_location(
        "installed_desktop_performance_driver",
        Path(__file__).with_name("qualify-installed-desktop.py"),
    )
    if specification is None or specification.loader is None:
        raise ValueError("Installed application driver is absent")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    packages = {"baseline": baseline, "current": current}
    samples: list[dict[str, Any]] = []
    try:
        for phase, source in enumerate(("baseline", "current", "current", "baseline")):
            subprocess.run(
                ["sudo", "dpkg", "--install", str(packages[source])], check=True, timeout=60
            )
            installed = subprocess.check_output(
                ["dpkg-query", "--show", "ai-stp-desktop"], text=True
            ).split()
            expected = manifest["version"] if source == "baseline" else current_version
            if installed != ["ai-stp-desktop", expected]:
                raise ValueError("Installed package version differs from its measured source")
            for trial in range(3):
                observation = sample(
                    module, args.driver.resolve(strict=True), fixture / f"profile-{phase}-{trial}"
                )
                samples.append({"source": source, "phase": phase, "trial": trial, **observation})
    finally:
        # Leave the new package installed for subsequent acceptance and artifact sealing.
        subprocess.run(["sudo", "dpkg", "--install", str(current)], check=True, timeout=60)
    if sha256(current) != current_digest:
        raise ValueError("Current installer changed during performance acceptance")
    if len({row["dark_theme"] for row in samples}) != 1:
        raise ValueError("Measured profiles selected different visual themes")
    summaries = {}
    for source in packages:
        selected = [row for row in samples if row["source"] == source]
        summaries[source] = {
            **{
                key: distribution([row[key] for row in selected])
                for key in (
                    "first_main_ms",
                    "usable_start_ms",
                    "first_settings_ms",
                    "first_settings_renderer_ms",
                    "webview_usable_ms",
                )
            },
            "navigation": {
                route: distribution(
                    [value for row in selected for value in row["navigation_ms"][route]]
                )
                for route in ("profiles", "settings", "overview")
            },
            "renderer_navigation": {
                route: distribution(
                    [value for row in selected for value in row["renderer_navigation_ms"][route]]
                )
                for route in ("profiles", "settings", "overview")
            },
            "automation_and_control_navigation": {
                route: distribution(
                    [value for row in selected for value in row["automation_navigation_ms"][route]],
                    allow_zero=True,
                )
                for route in ("profiles", "settings", "overview")
            },
            "first_settings_automation_and_control_ms": distribution(
                [row["first_settings_automation_and_control_ms"] for row in selected],
                allow_zero=True,
            ),
        }
    proof = {
        "schema_version": 2,
        "source_commit": os.environ["GITHUB_SHA"],
        "baseline_source_commit": manifest["source_commit"],
        "baseline_version": manifest["version"],
        "current_version": current_version,
        "baseline_installer_sha256": asset["sha256"],
        "current_installer_sha256": current_digest,
        "order": ["baseline", "current", "current", "baseline"],
        "profiles_per_phase": 3,
        "navigation_rounds_per_profile": 6,
        "poll_interval_ms": 5,
        "measurement": (
            "Real session creation or pointer click through usable content, loaded fonts "
            "and two paint frames; includes automation transport and timing observation retrieval."
        ),
        "renderer_measurement": (
            "Trusted navigation click to usable content, loaded fonts and two paint frames, "
            "observed entirely inside the WebView. Automation/control is the nonnegative "
            "end-to-end residual. WebView startup is relative to its own performance time origin."
        ),
        "observer_sha256": sha256(Path(__file__).with_name("desktop-navigation-timing.js")),
        "cache_condition": (
            "Fresh application profiles on one worker; shared OS caches are not flushed."
        ),
        "runner_os": os.environ["RUNNER_OS"],
        "image_version": os.environ.get("ImageVersion"),  # noqa: SIM112 - GitHub runner variable
        "samples": samples,
        "summary": summaries,
    }
    args.out.write_text(json.dumps(proof, indent=2) + "\n")
    print(json.dumps({"installed_desktop_performance": summaries}), flush=True)


if __name__ == "__main__":
    main()
