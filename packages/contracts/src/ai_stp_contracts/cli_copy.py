"""Canonical CLI copy templates for web surfaces (docs/contracts/cli-copy-templates.md).

`SPEC-037` `REQ-3706` asks for *exact* commands from *one* canonical source. Both
halves had failed: a second copy lived in the web as TypeScript, and every
template here rendered a command the parser refuses.

`ai-stp registry show component_01ABC` has no flags, and `registry show` declares
`--kind` and `--id` as required; `@{version}` was never a syntax the CLI parsed —
an exact version is a separate command with its own `--version`. `component sync`,
`setup sync` and `login` are not commands at all; the verbs are `component
discover`, `setup import inspect` and `auth login --provider`.

So a copy button handed the user something that could only fail. The templates
below are checked by rendering them and putting them through the real parser, not
by comparing two lists — see `tests/contract/test_cli_copy_templates.py`.

An owner next step is deliberately the read-only entry point of its flow rather
than the mutating command it leads to. `component discover` and `toolchain
harnesses` take no arguments, so the copied line is complete and safe; the step
that needs a root, a harness or a confirmation cannot be rendered without
substituting something this contract forbids putting in a UI command.
"""

from __future__ import annotations

from typing import Final, Literal

type ObjectKind = Literal["component", "setup"]

REGISTRY_SHOW: Final = "ai-stp registry show --kind {kind} --id {stable_id}"
REGISTRY_VERSION: Final = (
    "ai-stp registry version --kind {kind} --id {stable_id} --version {version}"
)
SELECT_IMPACT: Final = "ai-stp select impact --setup-id {stable_id} --setup-version {version}"
COMPONENT_NEXT_STEP: Final = "ai-stp component discover"
SETUP_NEXT_STEP: Final = "ai-stp toolchain harnesses"
LOGIN: Final = "ai-stp auth login --provider {provider}"
INSTALL_CLI: Final = "uv tool install ai-stp-cli"

#: The distribution `uv` installs. `ai-stp` is the console script, not the
#: package, and installing that name fetches something this project does not
#: publish.
DISTRIBUTION: Final = "ai-stp-cli"


def registry_show(kind: ObjectKind, stable_id: str) -> str:
    """Public object copy command."""
    return REGISTRY_SHOW.format(kind=kind, stable_id=stable_id)


def registry_version(kind: ObjectKind, stable_id: str, version: str) -> str:
    """Public exact-version copy command."""
    return REGISTRY_VERSION.format(kind=kind, stable_id=stable_id, version=version)


def select_impact(stable_id: str, version: str) -> str:
    """Local CLI command for the full selection-impact report."""
    return SELECT_IMPACT.format(stable_id=stable_id, version=version)


def owner_component_next_step() -> str:
    """Safe first step for an owner with no components yet."""
    return COMPONENT_NEXT_STEP


def owner_setup_next_step() -> str:
    """Safe first step for an owner with no setups yet."""
    return SETUP_NEXT_STEP


def login(provider: Literal["google", "github"]) -> str:
    """Device sign-in. `--provider` is required and closed to these two values."""
    return LOGIN.format(provider=provider)
