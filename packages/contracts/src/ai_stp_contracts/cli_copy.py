"""Native CLI commands and agent handoffs, projected to the web from one owner."""

from __future__ import annotations

import re
from typing import Final, Literal

from ai_stp_contracts.auth import OAuthProvider

type ObjectKind = Literal["component", "setup"]

REGISTRY_SHOW: Final = "ai-stp registry show --kind {kind} --id {stable_id}"
REGISTRY_VERSION: Final = (
    "ai-stp registry version --kind {kind} --id {stable_id} --version {version}"
)
SELECT_IMPACT: Final = "ai-stp select impact --setup-id {stable_id} --setup-version {version}"
COMPONENT_NEXT_STEP: Final = (
    "ai-stp task start --intent author --idempotency-key author-session-01 --json"
)
SETUP_NEXT_STEP: Final = COMPONENT_NEXT_STEP
INSTALL_TASK_START: Final = (
    "Use ai-stp to configure my installed harness with {stable_id}{version_label}. "
    "Start with `ai-stp task intents --json`, inspect the exact object and gather "
    "the local target, source and provider facts required by the install input schema. "
    "Keep harness installation and updates under its own management."
)
INSTALL_SETUP_START: Final = INSTALL_TASK_START
LOGIN: Final = "ai-stp account plan --action start --provider {provider} --json"
CLI_RELEASES_URL: Final = "https://github.com/ai-engineers-guild/ai-stp/releases/tag/cli-v0.1.0"
INTENTS_BOOTSTRAP: Final = "ai-stp task intents --json"
INITIALIZE_START: Final = "ai-stp init --credential-store os_keyring --json"
INITIALIZE_PROMPT: Final = (
    "After installing the native CLI, initialize a new local identity with: "
    + INITIALIZE_START
    + ". Existing Python state requires explicit `ai-stp state migrate plan` and apply."
)
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
    """Everyday first step for an owner with no components yet."""
    return COMPONENT_NEXT_STEP


def owner_setup_next_step() -> str:
    """Everyday first step for an owner with no setups yet."""
    return SETUP_NEXT_STEP


def install_start() -> str:
    """First read-only step for an agent preparing an installation."""
    return INTENTS_BOOTSTRAP


def install_task_start(stable_id: str, version: str | None = None) -> str:
    """Agent handoff: the browser cannot know local installation facts."""
    if re.fullmatch(r"[A-Za-z0-9_]+", stable_id) is None:
        raise ValueError("invalid catalog object identifier")
    return INSTALL_TASK_START.format(
        stable_id=stable_id, version_label=f" version {version}" if version else ""
    )


def install_setup_start(stable_id: str, version: str) -> str:
    """An exact object pin in an agent prompt, never an incomplete install argv."""
    return install_task_start(stable_id, version)


def login(provider: OAuthProvider) -> str:
    """Public plan only; the agent applies its exact digest and polls the session."""
    return LOGIN.format(provider=provider)
