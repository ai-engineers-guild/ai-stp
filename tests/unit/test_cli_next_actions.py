"""Every `next_actions` string names a real command with real flags.

A `next_actions` entry is machine output an agent executes next. One that names
a command that does not exist, or a flag the named command does not take, sends
the caller into a refusal the original answer manufactured. Two such pointers
shipped and sat unnoticed — `registry version next` (a command that never
existed; the decision lives on `component version release --major`)
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


def _tokens(text: str) -> list[str]:
    """Shell-like tokens with a `<multi word hole>` kept as one placeholder.

    An ellipsis stands for "whatever else the call took" and is not a token.
    """
    tokens: list[str] = []
    open_hole: list[str] = []
    for word in text.split():
        if open_hole:
            open_hole.append(word)
            if ">" in word:
                tokens.append(" ".join(open_hole))
                open_hole = []
            continue
        if word == "...":
            continue
        if "<" in word and ">" not in word:
            open_hole = [word]
            continue
        tokens.append(word)
    return tokens + ([" ".join(open_hole)] if open_hole else [])


REQUIRED: dict[tuple[str, ...], frozenset[str]] = {
    tuple(item.path): frozenset(
        parameter.name for parameter in item.parameters if parameter.required
    )
    for item in DECLARATIONS
}


def _problems(text: str) -> list[str]:
    if text.startswith("..."):
        # The caller's own invocation with these options added: nothing to
        # resolve beyond the options being options.
        return (
            []
            if all(t.startswith("--") or _placeholder(t) for t in _tokens(text))
            else [f"a `...` pointer carries only options: {text!r}"]
        )
    tokens = _tokens(text)
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
        rest = tokens[_consumed(tokens, path) :]
        unknown = [
            token[2:]
            for token in rest
            if token.startswith("--") and not _placeholder(token) and token[2:] not in allowed
        ]
        # After the path only `--flag [value]` pairs may follow: a bare word
        # there is a subcommand that does not exist (`registry version next`).
        stray = [
            token
            for index, token in enumerate(rest)
            if not token.startswith("--")
            and not _placeholder(token)
            and (index == 0 or not rest[index - 1].startswith("--"))
        ]
        # A pointer that names its command whole must also carry what the
        # command refuses to run without; `...` defers that to the caller's call.
        given = {token[2:] for token in rest if token.startswith("--")}
        whole = not any(_placeholder(token) for token in tokens[: len(path)])
        lacking = sorted(REQUIRED[path] - given) if "..." not in text and given and whole else []
        if not unknown and not stray and not lacking:
            return []
        if unknown:
            failures.append(f"--{', --'.join(unknown)} not taken by `{' '.join(path)}`")
        if stray:
            failures.append(f"{', '.join(stray)} is not a subcommand of `{' '.join(path)}`")
        if lacking:
            failures.append(f"--{', --'.join(lacking)} required by `{' '.join(path)}` missing")
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


def _command_shaped(text: str) -> bool:
    tokens = text.split()
    return len(tokens) >= 2 and (tokens[0],) in GROUPS and any(t.startswith("--") for t in tokens)


GROUPS = {(path[0],) for path in PATHS}


def test_every_command_shaped_literal_is_a_command_this_build_declares() -> None:
    """Pointers held in tables and helpers, not only in `next_actions=` keywords.

    `CREATES_PASSPORT`, the cloud client's way back, the toolchain's actions and
    the recovery report's step table all hold commands a caller is told to run.
    A literal handed to a call positionally is a message, not a pointer, and is
    left alone.
    """
    issues: list[str] = []
    for source in sorted(SOURCE_ROOT.rglob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        messages = {
            id(part)
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            for argument in node.args
            for part in ast.walk(argument)
        }
        # A piece of an f-string is not a pointer; the whole f-string is.
        pieces = {
            id(part)
            for node in ast.walk(tree)
            if isinstance(node, ast.JoinedStr)
            for part in node.values
        }
        messages |= pieces
        for node in ast.walk(tree):
            if id(node) in messages or not isinstance(node, ast.Constant | ast.JoinedStr):
                continue
            text = _rendered(node)
            if text is None or "\n" in text or not _command_shaped(text):
                continue
            for problem in _problems(text):
                issues.append(f"{source.relative_to(SOURCE_ROOT)}:{node.lineno}: {problem}")
    assert issues == [], "\n".join(issues)
