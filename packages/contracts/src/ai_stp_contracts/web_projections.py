"""Generated web projections of Python-owned contracts (SPEC-047 REQ-4701).

CLI copy templates and the deep-link corpus have one owner:
``ai_stp_contracts``. Web consumes a generated TypeScript artifact. A
hand-written second copy is a contract defect.
"""

from __future__ import annotations

import argparse
import json
import sys
from importlib.resources import files
from pathlib import Path
from typing import Final

from ai_stp_contracts import cli_copy

WEB_LIB = Path("apps") / "web" / "src" / "lib" / "generated"
CLI_COPY_NAME: Final[str] = "cli-copy.ts"
DEEP_LINK_CORPUS_NAME: Final[str] = "deep-link-corpus.ts"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _ts_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def render_cli_copy() -> str:
    """Render the TypeScript projection of ``cli_copy``."""
    lines = [
        "/* Generated from ai_stp_contracts.cli_copy. Do not edit. */",
        "",
        'export type ObjectKind = "component" | "setup";',
        'export type LoginProvider = "google" | "github";',
        "",
        f"export const DISTRIBUTION = {_ts_string(cli_copy.DISTRIBUTION)} as const;",
        f"export const INSTALL_CLI = {_ts_string(cli_copy.INSTALL_CLI)} as const;",
        f"export const REGISTRY_SHOW = {_ts_string(cli_copy.REGISTRY_SHOW)} as const;",
        "export const REGISTRY_VERSION =",
        f"  {_ts_string(cli_copy.REGISTRY_VERSION)} as const;",
        "export const SELECT_IMPACT =",
        f"  {_ts_string(cli_copy.SELECT_IMPACT)} as const;",
        f"export const COMPONENT_NEXT_STEP = {_ts_string(cli_copy.COMPONENT_NEXT_STEP)} as const;",
        f"export const SETUP_NEXT_STEP = {_ts_string(cli_copy.SETUP_NEXT_STEP)} as const;",
        f"export const LOGIN = {_ts_string(cli_copy.LOGIN)} as const;",
        "",
        "export function registryShow(kind: ObjectKind, stableId: string): string {",
        '  return REGISTRY_SHOW.replaceAll("{kind}", kind).replaceAll("{stable_id}", stableId);',
        "}",
        "",
        (
            "export function registryVersion(kind: ObjectKind, "
            "stableId: string, version: string): string {"
        ),
        '  return REGISTRY_VERSION.replaceAll("{kind}", kind)',
        '    .replaceAll("{stable_id}", stableId)',
        '    .replaceAll("{version}", version);',
        "}",
        "",
        "export function selectImpact(stableId: string, version: string): string {",
        '  return SELECT_IMPACT.replaceAll("{stable_id}", stableId)',
        '    .replaceAll("{version}", version);',
        "}",
        "",
        "export function ownerComponentNextStep(): string {",
        "  return COMPONENT_NEXT_STEP;",
        "}",
        "",
        "export function ownerSetupNextStep(): string {",
        "  return SETUP_NEXT_STEP;",
        "}",
        "",
        "export function login(provider: LoginProvider): string {",
        '  return LOGIN.replaceAll("{provider}", provider);',
        "}",
        "",
        "export function objectKindFromId(stableId: string): ObjectKind {",
        '  if (stableId.startsWith("setup_")) {',
        '    return "setup";',
        "  }",
        '  return "component";',
        "}",
        "",
        "export function registryCommand(stableId: string, version?: string): string {",
        "  const kind = objectKindFromId(stableId);",
        "  if (version) {",
        "    return registryVersion(kind, stableId, version);",
        "  }",
        "  return registryShow(kind, stableId);",
        "}",
        "",
    ]
    return "\n".join(lines)


def render_deep_link_corpus() -> str:
    """Render the packaged deep-link corpus as a TypeScript constant."""
    source = files("ai_stp_contracts").joinpath("fixtures/deep-links/v1.json")
    payload = json.loads(source.read_text(encoding="utf-8"))
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    return (
        "/* Generated from ai_stp_contracts fixtures/deep-links/v1.json. Do not edit. */\n"
        "\n"
        f"export const DEEP_LINK_CORPUS = {body} as const;\n"
        "\n"
        "export type DeepLinkCorpus = typeof DEEP_LINK_CORPUS;\n"
    )


def render_all() -> dict[str, str]:
    return {
        CLI_COPY_NAME: render_cli_copy(),
        DEEP_LINK_CORPUS_NAME: render_deep_link_corpus(),
    }


def write(target: Path | None = None) -> list[Path]:
    """Write generated TypeScript projections. Return written paths."""
    root = target or (_repo_root() / WEB_LIB)
    root.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, content in render_all().items():
        path = root / name
        path.write_text(content, encoding="utf-8", newline="\n")
        written.append(path)
    return written


def check(target: Path | None = None) -> list[str]:
    """Compare generated TypeScript against the committed files."""
    root = target or (_repo_root() / WEB_LIB)
    problems: list[str] = []
    rendered = render_all()
    for name, content in rendered.items():
        path = root / name
        if not path.exists():
            problems.append(f"missing generated web projection: {path}")
        elif path.read_text(encoding="utf-8") != content:
            problems.append(f"web projection drifted from its contract source: {path}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="compare instead of writing")
    parser.add_argument("target", nargs="?", type=Path, help="output directory")
    arguments = parser.parse_args(argv)
    if arguments.check:
        problems = check(arguments.target)
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1 if problems else 0
    for path in write(arguments.target):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
