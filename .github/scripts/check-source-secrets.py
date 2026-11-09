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
EXAMPLES = {
    ".github/scripts/check-source-secrets.py": "generic-password",
    ".env.dev.example": "generic-password",
    ".env.prod.example": "generic-password",
    ".github/workflows/source.yml": "generic-password",
    "deploy/compose.dev.yml": "generic-password",
    "apps/cli/tests/sources.rs": "generic-credential-uri",
    "apps/cli/tests/adoption.rs": "generic-credential-uri",
    "apps/cli/tests/projects/technology.rs": "generic-credential-uri",
    "apps/cli/src/sources/package/pypi.rs": "generic-credential-uri",
    ".repo-safety/templates/.env.example": "generic-credential-uri",
}


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
            "--config=" + str(ROOT / ".betterleaks.toml"),
            "--validation=false",
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
            # Default detectors can recognize public fixture values as non-secrets.
            # A credential-shaped addition must still be found at another path.
            (root / outside).write_bytes(original + ('\napi_key = "' + CONTROL + '"\n').encode())
            try:
                findings = scan(scanner, root, ["dir", "."])
                require(
                    any(
                        item.rule == "generic-api-key" and item.path == outside.as_posix()
                        for item in findings
                    ),
                    "An outside-path fixture credential was hidden: " + relative,
                )
            finally:
                (root / outside).unlink()
    print(
        "Secret controls: benign/finding, four exact fixtures, "
        "four changed-line and four outside-path refusals"
    )
    with tempfile.TemporaryDirectory(prefix="ai-stp-lock-controls-", dir=temporary) as directory:
        root = Path(directory)
        for relative in (
            "bun.lock",
            "apps/web/bun.lock",
            "docs_scripts/bun.lock",
            "tests/secret-control.py",
            "schemas/v1/openapi.json",
            "packages/contracts/src/ai_stp_contracts/fixtures/v1/secret-control.json",
            ".serena/memories/quality-gates-and-commands.md",
            ".serena/memories/current-work.md",
        ):
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('api_key = "' + CONTROL + '"\n')
            findings = scan(scanner, root, ["dir", "."])
            require(
                any(item.rule == "generic-api-key" and item.path == relative for item in findings),
                "A source-root credential was hidden by scanner policy: " + relative,
            )
    print("Secret controls: Bun locks, root tests, generated contracts and documentation findings")
    example_controls(scanner, temporary)


def example_controls(scanner: Path, temporary: Path) -> None:
    for relative, rule in EXAMPLES.items():
        original = (ROOT / relative).read_text()
        with tempfile.TemporaryDirectory(
            prefix="ai-stp-example-controls-", dir=temporary
        ) as directory:
            root = Path(directory)
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(original)
            require(
                not scan(scanner, root, ["dir", "."]),
                "Reviewed source example was rejected: " + relative,
            )
            target.unlink()
            outside = Path("outside") / target.name
            (root / outside).parent.mkdir(exist_ok=True)
            (root / outside).write_text(original)
            findings = [
                item
                for item in scan(scanner, root, ["dir", "."])
                if item.rule == rule and item.path == outside.as_posix()
            ]
            require(
                bool(findings), "A source example exemption escaped its exact path: " + relative
            )
            (root / outside).unlink()
            for finding in findings:
                lines = original.splitlines(keepends=True)
                credential = (
                    'password = "' + CONTROL + '"\n'
                    if rule == "generic-password"
                    else 'url = "postgresql://user:' + CONTROL + '@example.invalid/db"\n'
                )
                lines[finding.line - 1] = credential
                target.write_text("".join(lines))
                require(
                    any(
                        item.rule == rule and item.path == relative
                        for item in scan(scanner, root, ["dir", "."])
                    ),
                    "A changed source example credential was hidden: " + relative,
                )
    print("Secret controls: ten exact source examples and their path/credential refusals")


def main() -> int:
    require(
        os.environ.get("GITHUB_ACTIONS") == "true" and os.environ.get("RUNNER_OS") == "Linux",
        "Secret fixture execution requires disposable Linux CI",
    )
    require(Path(os.environ["GITHUB_WORKSPACE"]).resolve() == ROOT, "Unexpected source checkout")
    temporary = Path(os.environ["RUNNER_TEMP"])
    require(temporary.is_dir(), "CI temporary directory is missing")
    scanner = Path(os.environ["SOURCE_SECRET_SCANNER"])
    pin = os.environ["SOURCE_SECRET_SCANNER_VERSION"]
    require(re.fullmatch(r"\d+\.\d+\.\d+", pin) is not None, "Secret scanner pin is invalid")
    version = subprocess.check_output([str(scanner), "version"], text=True, timeout=10).strip()
    require(version == pin, "Secret scanner differs from the declared pin")
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
