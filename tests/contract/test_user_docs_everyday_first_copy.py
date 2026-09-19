"""Everyday user-facing pages must not lead a weak model with expert leaves.

First ```bash``` copy is the draining start. Later expert recovery stays
readable as ```text``` so a Haiku-class agent does not copy `install plan`.
Command-table argv for those leaves is plain text, not a copyable `ai-stp …`
cell.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ai_stp_cli.agy_qualify import FORBIDDEN_LEAVES

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs-user-facing"

INSTALL = "ai-stp task start --intent install --idempotency-key install-session-01 --json"
AUTHOR = "ai-stp task start --intent author --idempotency-key author-session-01 --json"
PUBLISH = "ai-stp task start --intent publish --idempotency-key publish-session-01 --json"
INITIALIZE = "ai-stp task start --intent initialize --idempotency-key initialize-session-01 --json"
CHANGE = "ai-stp task start --intent change --idempotency-key change-session-01 --json"
ACCOUNT = "ai-stp task start --intent account --idempotency-key account-session-01 --json"
SWITCH = "ai-stp task start --intent switch --idempotency-key switch-session-01 --json"
INTENTS = "ai-stp task intents --json"

KINDS = (
    "skill",
    "mcp",
    "hook",
    "command",
    "plugin",
    "instruction",
    "setting",
    "agent",
    "cli",
)

#: `--help` matches too many human sentences. Tables stay expert recovery.
DOCS_FORBIDDEN = (
    *(leaf for leaf in FORBIDDEN_LEAVES if leaf != "--help"),
    "select propose",
    "select confirm",
    "config init",
    "component publish",
)

FENCE = re.compile(r"```(?:bash|shell|sh|zsh|console)\n(.*?)```", re.S)


def _first_bash(relative: str) -> str:
    path = DOCS / relative
    match = re.search(r"```bash\n(.*?)```", path.read_text(encoding="utf-8"), re.S)
    assert match is not None, f"{relative} has no bash fence"
    return match.group(1).strip()


def _cases() -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = [
        ("docs/en/catalog/index.md", INSTALL),
        ("docs/ru/catalog/index.md", INSTALL),
        ("docs/en/web/catalog.md", INSTALL),
        ("docs/ru/web/catalog.md", INSTALL),
        ("docs/en/web/catalog-setup.md", INSTALL),
        ("docs/ru/web/catalog-setup.md", INSTALL),
        ("docs/en/web/catalog-component.md", INSTALL),
        ("docs/ru/web/catalog-component.md", INSTALL),
        ("docs/en/cli/install.md", INSTALL),
        ("docs/ru/cli/install.md", INSTALL),
        ("docs/en/cli/select.md", INSTALL),
        ("docs/ru/cli/select.md", INSTALL),
        ("docs/en/cli/registry.md", INSTALL),
        ("docs/ru/cli/registry.md", INSTALL),
        ("docs/en/cli/config.md", INITIALIZE),
        ("docs/ru/cli/config.md", INITIALIZE),
        ("docs/en/cli/publication.md", PUBLISH),
        ("docs/ru/cli/publication.md", PUBLISH),
        ("docs/en/cli/component-publish.md", PUBLISH),
        ("docs/ru/cli/component-publish.md", PUBLISH),
        ("docs/en/cli/setup.md", CHANGE),
        ("docs/ru/cli/setup.md", CHANGE),
        ("docs/en/cli/auth.md", ACCOUNT),
        ("docs/ru/cli/auth.md", ACCOUNT),
        ("docs/en/cli/sync.md", ACCOUNT),
        ("docs/ru/cli/sync.md", ACCOUNT),
        ("docs/en/cli/target.md", SWITCH),
        ("docs/ru/cli/target.md", SWITCH),
        ("docs/en/cli/component-discover.md", AUTHOR),
        ("docs/ru/cli/component-discover.md", AUTHOR),
        ("docs/en/cli/index.md", INTENTS),
        ("docs/ru/cli/index.md", INTENTS),
        ("docs/en/cli/observe.md", INTENTS),
        ("docs/ru/cli/observe.md", INTENTS),
        ("docs/en/cli/commands.md", INTENTS),
        ("docs/ru/cli/commands.md", INTENTS),
        ("docs/en/quickstart/agent.md", INTENTS),
        ("docs/ru/quickstart/agent.md", INTENTS),
        ("docs/en/troubleshooting/index.md", INTENTS),
        ("docs/ru/troubleshooting/index.md", INTENTS),
        ("docs/en/publishing/index.md", PUBLISH),
        ("docs/ru/publishing/index.md", PUBLISH),
        ("docs/en/web/login.md", ACCOUNT),
        ("docs/ru/web/login.md", ACCOUNT),
        ("docs/en/web/devices.md", ACCOUNT),
        ("docs/ru/web/devices.md", ACCOUNT),
        ("docs/en/web/home.md", INITIALIZE),
        ("docs/ru/web/home.md", INITIALIZE),
        ("docs/en/setups/index.md", CHANGE),
        ("docs/ru/setups/index.md", CHANGE),
        ("docs/en/components/index.md", AUTHOR),
        ("docs/ru/components/index.md", AUTHOR),
    ]
    for kind in KINDS:
        rows.append((f"docs/en/components/{kind}.md", AUTHOR))
        rows.append((f"docs/ru/components/{kind}.md", AUTHOR))
        if kind == "cli":
            continue
        rows.append((f"content/en/article-kind-{kind}.md", AUTHOR))
        rows.append((f"content/ru/article-kind-{kind}.md", AUTHOR))
    return rows


@pytest.mark.parametrize(("relative", "needle"), _cases())
def test_everyday_page_first_bash_is_the_draining_start(relative: str, needle: str) -> None:
    held = _first_bash(relative)
    assert needle in held, f"{relative} first bash is {held!r}"
    for leaf in DOCS_FORBIDDEN:
        assert leaf not in held, f"{relative} first bash teaches {leaf}"


def test_no_user_facing_bash_fence_teaches_a_forbidden_leaf() -> None:
    leaked: list[str] = []
    for path in sorted(DOCS.rglob("*.md")):
        relative = path.relative_to(DOCS).as_posix()
        for index, body in enumerate(FENCE.findall(path.read_text(encoding="utf-8")), 1):
            hits = [leaf for leaf in DOCS_FORBIDDEN if leaf in body]
            if hits:
                leaked.append(f"{relative} fence {index}: {hits}")
    assert not leaked, "copyable bash still teaches expert leaves:\n" + "\n".join(leaked)


_TABLE_ARGV = re.compile(r"^\|\s*`ai-stp ([^`]+)`\s*\|", re.M)


def test_no_user_facing_table_cell_is_copyable_forbidden_argv() -> None:
    leaked: list[str] = []
    for path in sorted(DOCS.rglob("*.md")):
        relative = path.relative_to(DOCS).as_posix()
        text = path.read_text(encoding="utf-8")
        for match in _TABLE_ARGV.finditer(text):
            body = match.group(1)
            hits = [leaf for leaf in DOCS_FORBIDDEN if leaf in body]
            if hits:
                leaked.append(f"{relative}: ai-stp {body} ({hits})")
    assert not leaked, "table cells still copy expert argv:\n" + "\n".join(leaked)
