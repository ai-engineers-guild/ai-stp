"""Deterministic JSON Schema export (SPEC-015 REQ-1508/REQ-1509).

``schemas/v1`` holds the generated JSON Schema files; this module is their
only generator. CI regenerates and compares byte for byte, so drift between
models and committed schemas fails the gate instead of shipping.

Usage:
    python -m ai_stp_foundation.schemas schemas/v1
    python -m ai_stp_foundation.schemas --check schemas/v1
"""

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Final

from pydantic import BaseModel

from ai_stp_foundation.envelope import CliError, ErrorEnvelope, SuccessEnvelope
from ai_stp_foundation.errors import error_code_schema
from ai_stp_foundation.refs import ComponentRef, SetupRef

type ExportedSchema = type[BaseModel] | dict[str, object]

EXPORTED_MODELS: Final[dict[str, ExportedSchema]] = {
    "cli-envelope-error": ErrorEnvelope,
    "cli-envelope-success": SuccessEnvelope,
    "cli-error": CliError,
    "component-ref": ComponentRef,
    "error-code": error_code_schema(),
    "setup-ref": SetupRef,
}


SCHEMA_DIALECT: Final[str] = "https://json-schema.org/draft/2020-12/schema"


def schema_id(name: str) -> str:
    """Return the stable ``$id`` of one exported schema."""
    return f"urn:ai-stp:schema:v1:{name}"


def render(models: Mapping[str, ExportedSchema] = EXPORTED_MODELS) -> dict[str, str]:
    """Render every exported schema as deterministic file content."""
    rendered: dict[str, str] = {}
    for name, model in models.items():
        schema = dict(model) if isinstance(model, dict) else model.model_json_schema()
        schema["$schema"] = SCHEMA_DIALECT
        schema["$id"] = schema_id(name)
        text = json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True)
        rendered[f"{name}.schema.json"] = text + "\n"
    return rendered


def write(target: Path, models: Mapping[str, ExportedSchema] = EXPORTED_MODELS) -> list[Path]:
    """Write rendered schemas into ``target``; return written paths."""
    target.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for filename, content in render(models).items():
        path = target / filename
        # ``Path.write_text`` rejects an explicit newline translation on
        # Windows; the content already carries its final LF deterministically.
        path.write_text(content, encoding="utf-8")
        written.append(path)
    return written


def check(target: Path, models: Mapping[str, ExportedSchema] = EXPORTED_MODELS) -> list[str]:
    """Compare rendered schemas against ``target``; return drift messages."""
    problems: list[str] = []
    rendered = render(models)
    for filename, content in rendered.items():
        path = target / filename
        if not path.exists():
            problems.append(f"missing generated schema: {path}")
        elif path.read_text(encoding="utf-8") != content:
            problems.append(f"schema drifted from its models: {path}")
    for path in sorted(target.glob("*.schema.json")):
        if path.name not in rendered:
            problems.append(f"unexpected schema without a generator: {path}")
    return problems


def main(
    argv: list[str] | None = None,
    models: Mapping[str, ExportedSchema] = EXPORTED_MODELS,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path, help="schemas output directory")
    parser.add_argument("--check", action="store_true", help="compare instead of writing")
    arguments = parser.parse_args(argv)
    if arguments.check:
        problems = check(arguments.target, models)
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1 if problems else 0
    for path in write(arguments.target, models):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
