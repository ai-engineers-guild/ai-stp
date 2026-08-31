#!/usr/bin/env python3
"""Check active-spec structure, identifiers, and traceability."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC_DIR = Path("specs/active")
SPEC_FILE_RE = re.compile(r"^(SPEC-\d{3})-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
REQ_LINE_RE = re.compile(r"^- `(?P<id>REQ-\d{3,4})`: (?P<text>\S.*)$", re.M)
REQ_REF_RE = re.compile(r"`(REQ-\d{3,4})`")
FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.S)
REQUIRED_HEADINGS = (
    "## Purpose",
    "## Scope",
    "## Terms",
    "## Requirements",
    "## States and errors",
    "## Security and privacy",
    "## Compatibility and migration",
    "## Acceptance criteria",
)


@dataclass
class Issue:
    path: Path
    code: str
    message: str


class SpecLinter:
    def __init__(self, root: Path = ROOT) -> None:
        self.root = root.resolve()
        self.issues: list[Issue] = []
        self.seen_requirements: dict[str, Path] = {}
        self.spec_count = 0

    def error(self, path: Path, code: str, message: str) -> None:
        self.issues.append(Issue(path, code, message))

    @staticmethod
    def section(text: str, heading: str) -> str:
        match = re.search(
            rf"^{re.escape(heading)}\n+(.*?)(?=^##\s|\Z)",
            text,
            re.M | re.S,
        )
        return match.group(1).strip() if match else ""

    def run(self) -> None:
        directory = self.root / SPEC_DIR
        if not directory.is_dir():
            self.error(directory, "SP01", "нет specs/active")
            return
        files = sorted(path for path in directory.glob("SPEC-*.md") if path.is_file())
        if not files:
            self.error(directory, "SP01", "нет active specs")
            return
        self.spec_count = len(files)
        for path in files:
            self.check_spec(path)

    def check_spec(self, path: Path) -> None:
        match = SPEC_FILE_RE.match(path.name)
        if not match:
            self.error(path, "SP02", "имя не по форме SPEC-NNN-краткое-название.md")
            return
        spec_id = match.group(1)
        text = path.read_text(encoding="utf-8")
        if not FRONTMATTER_RE.match(text):
            self.error(path, "SP03", "нет корректного frontmatter")
        if "{{" in text:
            self.error(path, "SP04", "остался незаполненный placeholder")
        if not re.search(rf"^# {re.escape(spec_id)}:\s+\S", text, re.M):
            self.error(path, "SP05", f"H1 не начинается с {spec_id}")

        for heading in REQUIRED_HEADINGS:
            section = self.section(text, heading)
            if not section:
                self.error(path, "SP06", f"нет непустого раздела {heading}")

        requirements_section = self.section(text, "## Requirements")
        requirements = list(REQ_LINE_RE.finditer(requirements_section))
        if not requirements:
            self.error(path, "SP07", "нет требований формата `REQ-NNN`")
            return

        ids: list[str] = []
        for requirement in requirements:
            req_id = requirement.group("id")
            ids.append(req_id)
            previous = self.seen_requirements.get(req_id)
            if previous:
                self.error(
                    path, "SP08", f"{req_id} уже объявлен в {previous.relative_to(self.root)}"
                )
            else:
                self.seen_requirements[req_id] = path

        acceptance = self.section(text, "## Acceptance criteria")
        accepted_ids = set(REQ_REF_RE.findall(acceptance))
        for req_id in ids:
            if req_id not in accepted_ids:
                self.error(path, "SP09", f"для {req_id} нет acceptance oracle")
        unknown = accepted_ids - set(ids)
        if unknown:
            self.error(
                path,
                "SP10",
                f"acceptance ссылается на чужие требования: {', '.join(sorted(unknown))}",
            )

    def report(self, fmt: str) -> int:
        if fmt == "github":
            for issue in self.issues:
                relative = issue.path.relative_to(self.root)
                print(f"::error file={relative},title={issue.code}::{issue.message}")
        else:
            for issue in sorted(self.issues, key=lambda item: (str(item.path), item.code)):
                relative = issue.path.relative_to(self.root)
                print(f"ОШИБКА {relative} [{issue.code}] {issue.message}")
            print(
                f"Спецификаций: {self.spec_count}, требований: {len(self.seen_requirements)}, "
                f"ошибок: {len(self.issues)}"
            )
        return 1 if self.issues else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("text", "github"), default="text")
    args = parser.parse_args()
    linter = SpecLinter()
    linter.run()
    return linter.report(args.format)


if __name__ == "__main__":
    raise SystemExit(main())
