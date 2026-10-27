"""Qualify secret scanning with scoped fixtures and emit finding coordinates only."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[2]
CONTROL = "AbcDef0123456789GhIjKlMnOpQrStUvWxYz"
FIXTURES = (
    "apps/cli/resources/packages/contracts/src/ai_stp_contracts/fixtures/v1/github_connector.json",
    "apps/cli/resources/packages/contracts/src/ai_stp_contracts/fixtures/v1/corporate.json",
    "apps/cli/tests/fixtures/legacy-state.json",
    "apps/web/tests/component/access-workspace.test.tsx",
)


@dataclass(frozen=True)
class Finding:
    rule: str
    path: str
    line: int


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def scan(scanner: Path, cwd: Path, arguments: list[str], data: str | None = None) -> list[Finding]:
    result = subprocess.run(
        [
            str(scanner),
            *arguments,
            "--config=" + str(ROOT / ".gitleaks.toml"),
            "--redact=100",
            "--no-banner",
            "--report-format=json",
            "--report-path=/dev/stdout",
        ],
        cwd=cwd,
        input=data,
        text=True,
        capture_output=True,
        timeout=90,
        check=False,
    )
    require(result.returncode in (0, 1), "Secret scanner failed to execute")
    decoded: object = json.loads(result.stdout)
    require(isinstance(decoded, list), "Secret scanner omitted its finding report")
    findings: list[Finding] = []
    for raw in cast(list[object], decoded):
        require(isinstance(raw, dict), "Invalid secret scanner finding")
        item = cast(dict[str, object], raw)
        rule, path, line = item.get("RuleID"), item.get("File"), item.get("StartLine")
        require(
            isinstance(rule, str) and isinstance(path, str) and type(line) is int,
            "Secret scanner omitted finding coordinates",
        )
        findings.append(Finding(cast(str, rule), cast(str, path), cast(int, line)))
    require(
        result.returncode == (1 if findings else 0),
        "Secret scanner status does not match its finding report",
    )
    return findings


def controls(scanner: Path, temporary: Path) -> None:
    require(
        not scan(scanner, ROOT, ["stdin"], "ordinary source\n"), "Benign scanner control failed"
    )
    known = scan(scanner, ROOT, ["stdin"], "ghp_" + CONTROL + "\n")
    require(any(item.rule == "github-pat" for item in known), "Finding scanner control failed")
    with tempfile.TemporaryDirectory(prefix="ai-stp-secret-controls-", dir=temporary) as directory:
        root = Path(directory)
        for relative in FIXTURES:
            source = ROOT / relative
            require(source.is_file() and not source.is_symlink(), "Secret fixture is missing")
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
        require(not scan(scanner, root, ["dir", "."]), "Reviewed fixture control failed")
        for relative in FIXTURES:
            target = root / relative
            original = target.read_bytes()
            try:
                target.write_bytes(original + ('\napi_key = "' + CONTROL + '"\n').encode())
                findings = scan(scanner, root, ["dir", "."])
                require(
                    any(
                        item.rule == "generic-api-key" and item.path == relative
                        for item in findings
                    ),
                    "A changed credential in a reviewed fixture was hidden",
                )
            finally:
                target.write_bytes(original)
            outside = Path("outside") / target.name
            (root / outside).parent.mkdir(exist_ok=True)
            (root / outside).write_bytes(original)
            try:
                findings = scan(scanner, root, ["dir", "."])
                require(
                    any(
                        item.rule == "generic-api-key" and item.path == outside.as_posix()
                        for item in findings
                    ),
                    "A fixture exemption escaped its exact source path",
                )
            finally:
                (root / outside).unlink()
    print(
        "Secret controls: benign/finding, four exact fixtures, "
        "four changed-line and four outside-path refusals"
    )


def main() -> int:
    require(
        os.environ.get("GITHUB_ACTIONS") == "true" and os.environ.get("RUNNER_OS") == "Linux",
        "Secret fixture execution requires disposable Linux CI",
    )
    require(Path(os.environ["GITHUB_WORKSPACE"]).resolve() == ROOT, "Unexpected source checkout")
    temporary = Path(os.environ["RUNNER_TEMP"])
    require(temporary.is_dir(), "CI temporary directory is missing")
    scanner = Path(os.environ["SAFETY_BIN_PREFIX"]) / "gitleaks"
    pin = [
        line.split("=", 1)[1]
        for line in (ROOT / "scripts/safety/versions.env").read_text().splitlines()
        if line.startswith("GITLEAKS_VERSION=")
    ]
    require(len(pin) == 1, "Secret scanner pin is ambiguous")
    version = subprocess.check_output([str(scanner), "version"], text=True, timeout=10).strip()
    require(version == pin[0], "Secret scanner differs from the declared pin")
    controls(scanner, temporary)
    event = os.environ["EVENT"]
    require(event in ("pull_request", "push", "workflow_dispatch"), "Unexpected source event")
    scopes: list[tuple[str, list[str]]] = [("source_tree", ["dir", "."])]
    if event == "pull_request":
        base, head = os.environ["BASE_SHA"], os.environ["HEAD_SHA"]
        require(
            re.fullmatch("[0-9a-f]{40}", base) is not None
            and re.fullmatch("[0-9a-f]{40}", head) is not None,
            "PR source coordinates are invalid",
        )
        for revision in (base, head):
            subprocess.run(
                ["git", "cat-file", "-e", revision + "^{commit}"],
                cwd=ROOT,
                capture_output=True,
                check=True,
            )
        scopes.append(("pr_commits", ["git", ".", "--log-opts=" + base + ".." + head]))
    failed = False
    for name, arguments in scopes:
        findings = scan(scanner, ROOT, arguments)
        print(json.dumps({"scope": name, "findings": [asdict(item) for item in findings]}))
        failed |= bool(findings)
    return int(failed)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        raise SystemExit("Secret qualification failed: " + str(error)) from None
