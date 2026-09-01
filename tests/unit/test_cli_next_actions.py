"""Every `next_actions` string names a real command with real flags.

A `next_actions` entry is machine output an agent executes next. One that names
a command that does not exist, or a flag the named command does not take, sends
the caller into a refusal the original answer manufactured. Two such pointers
shipped and sat unnoticed — `registry version next` (a command that never
existed; the decision lives on `component version release --major --confirm`)
and `toolchain install --harness` (that command takes `--tool`; installing a
harness program is `harness install`) — because nothing read these strings the
way their audience does. This test is that reader.

Templates are allowed exactly one placeholder shape: `<word>`. A placeholder
segment matches any single argv token; a placeholder flag value is not a flag.
A whole-command placeholder (an f-string interpolating the verb itself, e.g.
`provider {operation} plan`) is validated against every command it can expand
to by trying each declared path.
"""

from __future__ import annotations

import ast
from pathlib import Path

from ai_stp_cli.registry import DECLARATIONS

SOURCE_ROOT = Path(__file__).resolve().parents[2] / "apps" / "cli" / "src"

COMMANDS: dict[tuple[str, ...], frozenset[str]] = {
    tuple(item.path): frozenset(parameter.name for parameter in item.parameters)
    for item in DECLARATIONS
}
PATHS = sorted(COMMANDS, key=len, reverse=True)


def _rendered(element: ast.expr) -> str | None:
    """A literal string, or an f-string with `<x>` standing for each hole."""
    if isinstance(element, ast.Constant) and isinstance(element.value, str):
        return element.value
    if isinstance(element, ast.JoinedStr):
        return "".join(
            str(value.value) if isinstance(value, ast.Constant) else "<x>"
            for value in element.values
        )
    return None


def _placeholder(token: str) -> bool:
    return token.startswith("<") or "<" in token


def _matches(tokens: list[str], path: tuple[str, ...]) -> bool:
    if len(tokens) < len(path):
        return False
    return all(
        given == expected or _placeholder(given)
        for given, expected in zip(tokens[: len(path)], path, strict=False)
    )


def _consumed(tokens: list[str], path: tuple[str, ...]) -> int:
    """How many leading tokens the command path accounts for.

    A leading placeholder may hold a whole phrase (`f"{action} --confirm"`
    where `action` is `grant invite`), so it accounts for the full path in one
    token; otherwise segments pair one-to-one.
    """
    if tokens and _placeholder(tokens[0]) and not _matches(tokens, path):
        return 1
    return len(path)


def _problems(text: str) -> list[str]:
    tokens = text.split()
    candidates = [path for path in PATHS if _matches(tokens, path)]
    if tokens and _placeholder(tokens[0]):
        candidates = list(PATHS)
    if not candidates:
        return [f"names no declared command: {text!r}"]
    # A placeholder verb can expand to several commands; the string is honest
    # if at least one expansion takes every literal flag it carries.
    failures: list[str] = []
    for path in candidates:
        allowed = COMMANDS[path] | {"json"}
        unknown = [
            token[2:]
            for token in tokens[_consumed(tokens, path) :]
            if token.startswith("--") and not _placeholder(token) and token[2:] not in allowed
        ]
        if not unknown:
            return []
        failures.append(f"--{', --'.join(unknown)} not taken by `{' '.join(path)}`")
    concise = failures if len(failures) <= 3 else [*failures[:3], f"... {len(failures) - 3} more"]
    return [f"{'; '.join(concise)}: {text!r}"]


def test_every_next_action_is_a_command_this_build_declares() -> None:
    issues: list[str] = []
    for source in sorted(SOURCE_ROOT.rglob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.keyword) and node.arg == "next_actions"):
                continue
            value = node.value
            elements = value.elts if isinstance(value, ast.List | ast.Tuple) else [value]
            for element in elements:
                text = _rendered(element)
                if text is None:
                    continue
                for problem in _problems(text):
                    issues.append(f"{source.relative_to(SOURCE_ROOT)}:{element.lineno}: {problem}")
    assert issues == [], "\n".join(issues)
