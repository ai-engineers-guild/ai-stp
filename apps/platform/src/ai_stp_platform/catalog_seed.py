"""Idempotent first-party catalog seed loader (SPEC-021 REQ-2110, ADR-0034).

Corpus shape for browsable Sprint-1 catalog:
- three publishers (authors);
- per author: 1 mcp, 1 hook, 1 agent (subagent), 2 skills, 1 setup
  that pins mcp + hook + both skills;
- plus a first-party incident subagent and a setup that pins only that agent;
- plus #71 contract fixtures (fixture-component / fixture-setup).

Sprint-1 seed is entirely experimental (no validation pipeline → no
component_verified). Re-running is a pure upsert by (kind, stable_id, version).
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_foundation.digests import digest_bytes, digest_canonical
from ai_stp_foundation.timestamps import parse_timestamp
from ai_stp_passports.envelope import derive_revision_id, verify_revision_id
from ai_stp_passports.versions import (
    ComponentVersionPassport,
    SetupVersionPassport,
    seal_adaptation,
)
from ai_stp_platform.models import Account, CatalogMetadata, ComponentMedia
from ai_stp_platform.storage.object_store import ARTIFACT_DIGEST_DOMAIN, ImmutableObjectStore

PASSPORT_DIGEST_DOMAIN = "ai-stp:passport:v1"

ObjectKind = Literal["component", "setup"]

# --- Author accounts (stable, non-secret platform ids) ---
SEED_OWNER_ACCOUNT_ID = "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z"  # ai_stp First Party
SEED_AUTHOR_NORTHWIND_ID = "account_01JQZK7B8N4M6P2R9T5V0X3YA0"
SEED_AUTHOR_RIVER_ID = "account_01JQZK7B8N4M6P2R9T5V0X3YA1"

# Contract fixtures (#71 positive cases)
FIXTURE_COMPONENT_ID = "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z"
FIXTURE_SETUP_ID = "setup_01JQZK7B8N4M6P2R9T5V0X3Y7Z"

# Author 1 — First Party / claude-code
SEED_A1_SKILL_CORE_ID = "component_01JQZK7B8N4M6P2R9T5V0X3YB0"
SEED_A1_SKILL_PAIR_ID = "component_01JQZK7B8N4M6P2R9T5V0X3YB1"
SEED_A1_MCP_ID = "component_01JQZK7B8N4M6P2R9T5V0X3YB2"
SEED_A1_HOOK_ID = "component_01JQZK7B8N4M6P2R9T5V0X3YB3"
SEED_A1_AGENT_ID = "component_01JQZK7B8N4M6P2R9T5V0X3YB4"
SEED_A1_INCIDENT_AGENT_ID = "component_01JQZK7B8N4M6P2R9T5V0X3YBF"
SEED_A1_SETUP_ID = "setup_01JQZK7B8N4M6P2R9T5V0X3YC0"
SEED_A1_INCIDENT_SETUP_ID = "setup_01JQZK7B8N4M6P2R9T5V0X3YC3"

# Author 2 — Northwind Labs / codex
SEED_A2_SKILL_CORE_ID = "component_01JQZK7B8N4M6P2R9T5V0X3YB5"
SEED_A2_SKILL_PAIR_ID = "component_01JQZK7B8N4M6P2R9T5V0X3YB6"
SEED_A2_MCP_ID = "component_01JQZK7B8N4M6P2R9T5V0X3YB7"
SEED_A2_HOOK_ID = "component_01JQZK7B8N4M6P2R9T5V0X3YB8"
SEED_A2_AGENT_ID = "component_01JQZK7B8N4M6P2R9T5V0X3YB9"
SEED_A2_SETUP_ID = "setup_01JQZK7B8N4M6P2R9T5V0X3YC1"

# Author 3 — River Guild / pi
SEED_A3_SKILL_CORE_ID = "component_01JQZK7B8N4M6P2R9T5V0X3YBA"
SEED_A3_SKILL_PAIR_ID = "component_01JQZK7B8N4M6P2R9T5V0X3YBB"
SEED_A3_MCP_ID = "component_01JQZK7B8N4M6P2R9T5V0X3YBC"
SEED_A3_HOOK_ID = "component_01JQZK7B8N4M6P2R9T5V0X3YBD"
SEED_A3_AGENT_ID = "component_01JQZK7B8N4M6P2R9T5V0X3YBE"
SEED_A3_SETUP_ID = "setup_01JQZK7B8N4M6P2R9T5V0X3YC2"

# Backward-compatible aliases (older tests / docs that named single-harness seeds).
SEED_COMPONENT_CODEX_ID = SEED_A2_SKILL_CORE_ID
SEED_COMPONENT_PI_ID = SEED_A3_MCP_ID
SEED_COMPONENT_OPENCODE_ID = SEED_A1_HOOK_ID
SEED_SETUP_CODEX_ID = SEED_A2_SETUP_ID
SEED_SETUP_PI_ID = SEED_A3_SETUP_ID

FIXTURE_PUBLISHED_AT = "2026-08-05T00:00:00.000Z"
SEED_PUBLISHED_AT_V2 = "2026-08-06T00:00:00.000Z"
SEED_PUBLISHED_AT_INCIDENT = "2026-08-13T00:00:00.000Z"
ZERO_DIGEST = "sha256:" + ("0" * 64)

INCIDENT_SUBAGENT_NAME = "firstparty-incident-subagent"
INCIDENT_SETUP_NAME = "firstparty-incident-workspace"
INCIDENT_SUBAGENT_ARTIFACT = """# Incident triage

You are a first-party incident-response subagent for Claude Code.

## When to load
Load only when the user reports an outage, a failed release, or a production
error that needs a bounded next step.

## Work
1. Classify severity as se1, se2, or se3 from observed impact.
2. Collect the smallest evidence set: failing command, timestamp, and last
   change.
3. Propose one next action. Do not restart services or change production.
4. Stop after the proposal. Do not open a wide investigation.

## Limits
Do not request credentials. Do not invent logs. If evidence is missing, say so
and ask for one specific artifact.
""".replace("\r\n", "\n").encode("utf-8")

#: Closed tag facet set used by the seed corpus (UI dropdown source of truth
#: on the web is the same id list in apps/web/src/lib/tag-vocabulary.ts).
SEED_TAG_VOCABULARY: tuple[str, ...] = (
    "python",
    "tests",
    "code-review",
    "documentation",
    "devops",
    "security",
    "refactor",
    "github",
    "planning",
    "release",
)

SEED_PUBLIC_PROFILE: dict[str, Any] = {
    "schema_version": 1,
    "kind": "public_profile",
    "account_id": SEED_OWNER_ACCOUNT_ID,
    "display_name": "ai_stp First Party",
    "bio": "Platform first-party publisher for launch corpus and fixture parity.",
    "links": [
        {"label": "GitHub", "url": "https://github.com/ai-stp"},
        {"label": "Docs", "url": "https://github.com/ai-stp/docs"},
    ],
}

SEED_PUBLIC_PROFILES: dict[str, dict[str, Any]] = {
    SEED_OWNER_ACCOUNT_ID: SEED_PUBLIC_PROFILE,
    SEED_AUTHOR_NORTHWIND_ID: {
        "schema_version": 1,
        "kind": "public_profile",
        "account_id": SEED_AUTHOR_NORTHWIND_ID,
        "display_name": "Northwind Labs",
        "bio": "Codex-focused tooling publisher: review skills, MCP bridges, session hooks.",
        "links": [{"label": "GitHub", "url": "https://github.com/northwind-labs"}],
    },
    SEED_AUTHOR_RIVER_ID: {
        "schema_version": 1,
        "kind": "public_profile",
        "account_id": SEED_AUTHOR_RIVER_ID,
        "display_name": "River Guild",
        "bio": "Pi harness publisher for documentation workflows and planning agents.",
        "links": [{"label": "Site", "url": "https://github.com/river-guild"}],
    },
}

SEED_ACCOUNT_IDS: tuple[str, ...] = (
    SEED_OWNER_ACCOUNT_ID,
    SEED_AUTHOR_NORTHWIND_ID,
    SEED_AUTHOR_RIVER_ID,
)


@dataclass(frozen=True)
class SeedResult:
    """Counts for one seed run (created vs already present)."""

    created_accounts: int
    created_versions: int
    reused_versions: int
    artifacts_written: int


def _empty_conflicts() -> dict[str, list[str]]:
    return {
        "paths": [],
        "commands": [],
        "hooks": [],
        "mcp": [],
        "agents": [],
        "plugins": [],
    }


def _component_ref(stable_id: str, version: str = "1.0") -> dict[str, Any]:
    return {
        "stable_id": stable_id,
        "variant_id": None,
        "version": version,
        "passport_digest": ZERO_DIGEST,
    }


def _component_body(
    *,
    stable_id: str,
    name: str,
    description: str,
    version: str,
    tags: list[str],
    harness_id: str,
    component_type: str,
    owner_id: str = SEED_OWNER_ACCOUNT_ID,
    projection_kind: str = "native_files",
    published_at: str = FIXTURE_PUBLISHED_AT,
) -> dict[str, Any]:
    adaptation = seal_adaptation(
        {
            "harness_id": harness_id,
            "implementation_mode": "native",
            "source_artifact": None,
            "transform": None,
            "logical_component_type": component_type,
            "scope_adaptations": [
                {
                    "scope": "global",
                    "projection_format": "ai-stp-adaptation-projection/1",
                    "projection_artifact": {"digest": ZERO_DIGEST, "size_bytes": 1024},
                    "provider_component_kind": component_type,
                    "projection_kind": projection_kind,
                    "required_surface": {
                        "profile_id": f"{harness_id}/fixture/1",
                        "profile_digest": ZERO_DIGEST,
                        "bundle_format": "ai-stp-bundle/1",
                    },
                    "members": [
                        {
                            "path": f"fixtures/{stable_id}",
                            "object_type": "file",
                            "mode": 420,
                            "content_artifact": {"digest": ZERO_DIGEST, "size_bytes": 1024},
                            "native_ids": [stable_id],
                            "content_format": "application/octet-stream",
                            "ownership": "whole",
                            "write_semantics": "replace",
                            "withdrawal_semantics": "remove_path",
                        }
                    ],
                    "technical_support": "experimental",
                    "technical_support_reason": "synthetic catalog seed",
                }
            ],
        }
    )
    return {
        "schema_version": 1,
        "kind": "component",
        "stable_id": stable_id,
        "revision_id": "revision_" + ("0" * 64),
        "parent_revision_ids": [],
        "owner_id": owner_id,
        "created_at": published_at,
        "visibility": "public",
        "facts": {},
        "name": name,
        "description": description,
        "version": version,
        "tags": tags,
        "source": None,
        "artifact": {"digest": ZERO_DIGEST, "size_bytes": 1024},
        "required_env": [],
        "requires_credentials": False,
        "requires_authorization": "none",
        "permissions": {"filesystem": [], "network": [], "process": []},
        "external_endpoints": [],
        "license": {"spdx_id": "AGPL-3.0-or-later", "redistribution_allowed": True},
        "compatibility_evidence_refs": [],
        "component_type": component_type,
        "origin_harness_id": harness_id,
        "adaptations": [adaptation.model_dump(mode="json")],
        "provides_capabilities": [],
        "requires_components": [],
        "requires_capabilities": [],
        "conflicts": _empty_conflicts(),
    }


def _setup_body(
    *,
    stable_id: str,
    name: str,
    description: str,
    version: str,
    tags: list[str],
    harness_id: str,
    purpose: str,
    target_role: str,
    components: list[dict[str, Any]],
    posture: str | None = None,
    owner_id: str = SEED_OWNER_ACCOUNT_ID,
    published_at: str = FIXTURE_PUBLISHED_AT,
    supported_tasks: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "setup",
        "stable_id": stable_id,
        "revision_id": "revision_" + ("0" * 64),
        "parent_revision_ids": [],
        "owner_id": owner_id,
        "created_at": published_at,
        "visibility": "public",
        "facts": {},
        "name": name,
        "description": description,
        "version": version,
        "tags": tags,
        "source": None,
        "artifact": {"digest": ZERO_DIGEST, "size_bytes": 2048},
        "harness_id": harness_id,
        "required_env": [],
        "requires_credentials": False,
        "requires_authorization": "none",
        "permissions": {"filesystem": [], "network": [], "process": []},
        "external_endpoints": [],
        "license": {"spdx_id": "AGPL-3.0-or-later", "redistribution_allowed": True},
        "compatibility_evidence_refs": [],
        "purpose": purpose,
        "target_role": target_role,
        # Spelled out although optional. `seal_envelope` derives the id over the
        # *validated dump*, so a field left to its default hashes one document
        # while the sealed envelope is another — see its docstring.
        "posture": posture,
        "supported_tasks": supported_tasks or ["development"],
        "components": components,
        "ported_from": None,
        "related_setup_ids": [],
        "execution_profile": "full-auto",
        "supported_harness_versions": ["2.1.0"],
        "supported_os": ["linux"],
        "supported_arch": ["x86_64"],
        "composition_report_ref": None,
        "conversion_report_ref": None,
        "install_evidence_ref": None,
        "launch_evidence_ref": None,
    }


# Exact bodies from ai_stp_contracts.fixtures (catalog.json / setups.json).
_COMPONENT_V12: dict[str, Any] = _component_body(
    stable_id=FIXTURE_COMPONENT_ID,
    name="fixture-component",
    description="fixture-component-description",
    version="1.2",
    tags=["python", "tests"],
    harness_id="claude-code",
    component_type="skill",
)
_COMPONENT_V12["revision_id"] = (
    "revision_96370e726c35370359c21a99c5aff141f4fc69a9a536699ff91370fb1403263a"
)

_COMPONENT_V10: dict[str, Any] = {**_COMPONENT_V12, "version": "1.0"}

_SETUP_V10: dict[str, Any] = _setup_body(
    stable_id=FIXTURE_SETUP_ID,
    name="fixture-setup",
    description="fixture-setup-description",
    version="1.0",
    tags=["python"],
    harness_id="claude-code",
    purpose="fixture-purpose",
    target_role="fixture-role",
    # A real value rather than `None`, because this seed backs the published
    # contract example for `readSetup`: a field that is always null in the one
    # example a client reads teaches nothing about its shape.
    posture="baseline",
    components=[_component_ref(FIXTURE_COMPONENT_ID, "1.2")],
    supported_tasks=["fixture-task"],
)
# Pinned rather than derived because this passport backs a published contract
# example, and an example whose id moves on every edit is not a fixed point a
# client can test against. Pinned means it must be **recomputed** when the body
# changes: adding `posture` moved it, and nothing caught that — the seed digest
# test recomputes from the body and so heals itself, while `revision_id` was
# checked by nothing. `test_every_seed_passport_id_derives_from_its_own_body`
# is that missing check.
_SETUP_V10["revision_id"] = (
    "revision_b4a9fa7b0fc3932a01407ce00ee801bd3fa0422d37fa2fb6a3438c031528845c"
)
_SETUP_V10["target_role"] = "fixture-role"


def _seal_component(body: dict[str, Any]) -> dict[str, Any]:
    sealed = dict(body)
    if sealed.get("revision_id", "").startswith("revision_0") or (
        sealed.get("version") == "1.0" and sealed.get("stable_id") == FIXTURE_COMPONENT_ID
    ):
        sealed.pop("revision_id", None)
        sealed["revision_id"] = derive_revision_id(sealed)
    passport = ComponentVersionPassport.model_validate(sealed)
    if not verify_revision_id(passport):
        re_sealed = dict(sealed)
        re_sealed.pop("revision_id", None)
        re_sealed["revision_id"] = derive_revision_id(re_sealed)
        passport = ComponentVersionPassport.model_validate(re_sealed)
        if not verify_revision_id(passport):
            raise RuntimeError("seed component passport failed revision seal")
    return passport.model_dump(mode="json")


def _seal_setup(body: dict[str, Any]) -> dict[str, Any]:
    sealed = dict(body)
    if sealed.get("revision_id", "").startswith("revision_0"):
        sealed.pop("revision_id", None)
        sealed["revision_id"] = derive_revision_id(sealed)
    passport = SetupVersionPassport.model_validate(sealed)
    if not verify_revision_id(passport):
        re_sealed = dict(sealed)
        re_sealed.pop("revision_id", None)
        re_sealed["revision_id"] = derive_revision_id(re_sealed)
        passport = SetupVersionPassport.model_validate(re_sealed)
        if not verify_revision_id(passport):
            raise RuntimeError("seed setup passport failed revision seal")
    return passport.model_dump(mode="json")


def _passport_digest(passport: dict[str, Any]) -> str:
    """Integrity digest for a sealed passport body (matches #71 fixture corpus)."""
    return digest_canonical(PASSPORT_DIGEST_DOMAIN, passport)  # type: ignore[arg-type]


def _seed_entry(
    kind: ObjectKind,
    passport: dict[str, Any],
    published_at: str,
) -> tuple[ObjectKind, dict[str, Any], str, str]:
    return (kind, passport, published_at, _passport_digest(passport))


def incident_subagent_artifact_digest() -> str:
    """Content digest for the first-party incident subagent artifact."""
    return digest_bytes(ARTIFACT_DIGEST_DOMAIN, INCIDENT_SUBAGENT_ARTIFACT)


def _incident_entries() -> list[tuple[ObjectKind, dict[str, Any], str, str]]:
    """Published first-party incident subagent and the setup that pins it."""
    agent = _component_body(
        stable_id=SEED_A1_INCIDENT_AGENT_ID,
        name=INCIDENT_SUBAGENT_NAME,
        description=(
            "Incident-response subagent for Claude Code: classifies severity, "
            "gathers evidence, and proposes a bounded next step."
        ),
        version="1.0",
        tags=["security", "planning"],
        harness_id="claude-code",
        component_type="agent",
        published_at=SEED_PUBLISHED_AT_INCIDENT,
    )
    agent["artifact"] = {
        "digest": incident_subagent_artifact_digest(),
        "size_bytes": len(INCIDENT_SUBAGENT_ARTIFACT),
    }
    sealed_agent = _seal_component(agent)
    setup = _setup_body(
        stable_id=SEED_A1_INCIDENT_SETUP_ID,
        name=INCIDENT_SETUP_NAME,
        description=(
            "Claude Code workspace that pins the first-party incident subagent "
            "as conditionally loaded context."
        ),
        version="1.0",
        tags=["security", "planning"],
        harness_id="claude-code",
        purpose="incident-response",
        target_role="on-call-engineer",
        components=[
            {
                "stable_id": SEED_A1_INCIDENT_AGENT_ID,
                "variant_id": None,
                "version": "1.0",
                "passport_digest": _passport_digest(sealed_agent),
            }
        ],
        supported_tasks=["incident-response", "triage"],
        published_at=SEED_PUBLISHED_AT_INCIDENT,
    )
    return [
        _seed_entry("component", sealed_agent, SEED_PUBLISHED_AT_INCIDENT),
        _seed_entry("setup", _seal_setup(setup), SEED_PUBLISHED_AT_INCIDENT),
    ]


async def _write_seed_artifact(
    store: ImmutableObjectStore,
    payload: bytes,
) -> bool:
    stored = await store.put_immutable(
        payload,
        expected_digest=digest_bytes(ARTIFACT_DIGEST_DOMAIN, payload),
        expected_size=len(payload),
    )
    return stored.created


def _author_suite(
    *,
    owner_id: str,
    harness_id: str,
    skill_core_id: str,
    skill_pair_id: str,
    mcp_id: str,
    hook_id: str,
    agent_id: str,
    setup_id: str,
    brand: str,
    skill_core_name: str,
    skill_core_desc: str,
    skill_core_tags: list[str],
    skill_pair_name: str,
    skill_pair_desc: str,
    skill_pair_tags: list[str],
    mcp_name: str,
    mcp_desc: str,
    mcp_tags: list[str],
    hook_name: str,
    hook_desc: str,
    hook_tags: list[str],
    agent_name: str,
    agent_desc: str,
    agent_tags: list[str],
    setup_name: str,
    setup_desc: str,
    setup_tags: list[str],
    purpose: str,
    target_role: str,
    supported_tasks: list[str],
    published_at: str = FIXTURE_PUBLISHED_AT,
) -> list[tuple[ObjectKind, dict[str, Any], str, str]]:
    """One publisher suite: 2 skills + mcp + hook + agent + composed setup."""
    del brand  # naming only; kept for call-site readability
    skill_core = _component_body(
        stable_id=skill_core_id,
        name=skill_core_name,
        description=skill_core_desc,
        version="1.0",
        tags=skill_core_tags,
        harness_id=harness_id,
        component_type="skill",
        owner_id=owner_id,
        published_at=published_at,
    )
    skill_pair = _component_body(
        stable_id=skill_pair_id,
        name=skill_pair_name,
        description=skill_pair_desc,
        version="1.0",
        tags=skill_pair_tags,
        harness_id=harness_id,
        component_type="skill",
        owner_id=owner_id,
        published_at=published_at,
    )
    mcp = _component_body(
        stable_id=mcp_id,
        name=mcp_name,
        description=mcp_desc,
        version="1.0",
        tags=mcp_tags,
        harness_id=harness_id,
        component_type="mcp",
        projection_kind="package",
        owner_id=owner_id,
        published_at=published_at,
    )
    hook = _component_body(
        stable_id=hook_id,
        name=hook_name,
        description=hook_desc,
        version="1.0",
        tags=hook_tags,
        harness_id=harness_id,
        component_type="hook",
        owner_id=owner_id,
        published_at=published_at,
    )
    agent = _component_body(
        stable_id=agent_id,
        name=agent_name,
        description=agent_desc,
        version="1.0",
        tags=agent_tags,
        harness_id=harness_id,
        component_type="agent",
        owner_id=owner_id,
        published_at=published_at,
    )
    setup = _setup_body(
        stable_id=setup_id,
        name=setup_name,
        description=setup_desc,
        version="1.0",
        tags=setup_tags,
        harness_id=harness_id,
        purpose=purpose,
        target_role=target_role,
        owner_id=owner_id,
        components=[
            _component_ref(mcp_id),
            _component_ref(hook_id),
            _component_ref(skill_core_id),
            _component_ref(skill_pair_id),
        ],
        supported_tasks=supported_tasks,
        published_at=published_at,
    )
    return [
        _seed_entry("component", _seal_component(skill_core), published_at),
        _seed_entry("component", _seal_component(skill_pair), published_at),
        _seed_entry("component", _seal_component(mcp), published_at),
        _seed_entry("component", _seal_component(hook), published_at),
        _seed_entry("component", _seal_component(agent), published_at),
        _seed_entry("setup", _seal_setup(setup), published_at),
    ]


def seed_corpus() -> list[tuple[ObjectKind, dict[str, Any], str, str]]:
    """(kind, passport, published_at wire, passport_digest) for first-party seed."""
    corpus: list[tuple[ObjectKind, dict[str, Any], str, str]] = [
        # Contract fixture corpus (REQ-2212 parity with #71).
        _seed_entry("component", _seal_component(_COMPONENT_V10), FIXTURE_PUBLISHED_AT),
        _seed_entry("component", _seal_component(_COMPONENT_V12), FIXTURE_PUBLISHED_AT),
        _seed_entry("setup", _seal_setup(_SETUP_V10), FIXTURE_PUBLISHED_AT),
    ]

    # Three multi-author suites (mcp + hook + pair of skills in each setup;
    # hooks/mcps/agents/skills also listed as standalone catalog components).
    corpus.extend(
        _author_suite(
            owner_id=SEED_OWNER_ACCOUNT_ID,
            harness_id="claude-code",
            skill_core_id=SEED_A1_SKILL_CORE_ID,
            skill_pair_id=SEED_A1_SKILL_PAIR_ID,
            mcp_id=SEED_A1_MCP_ID,
            hook_id=SEED_A1_HOOK_ID,
            agent_id=SEED_A1_AGENT_ID,
            setup_id=SEED_A1_SETUP_ID,
            brand="first-party",
            skill_core_name="firstparty-security-skill",
            skill_core_desc="Security review skill for Claude Code workspaces.",
            skill_core_tags=["security", "code-review"],
            skill_pair_name="firstparty-release-skill",
            skill_pair_desc="Release checklist skill for Claude Code workspaces.",
            skill_pair_tags=["release", "devops"],
            mcp_name="firstparty-metrics-mcp",
            mcp_desc="Metrics MCP server for Claude Code observability tasks.",
            mcp_tags=["devops", "documentation"],
            hook_name="firstparty-audit-hook",
            hook_desc="Audit lifecycle hook for Claude Code sessions.",
            hook_tags=["security", "devops"],
            agent_name="firstparty-triage-agent",
            agent_desc="Triage subagent for Claude Code incident workflows.",
            agent_tags=["planning", "security"],
            setup_name="firstparty-ops-workspace",
            setup_desc=(
                "Claude Code ops workspace: metrics MCP, audit hook, security and release skills."
            ),
            setup_tags=["devops", "security"],
            purpose="operations",
            target_role="platform-engineer",
            supported_tasks=["ops", "security-review", "release"],
            published_at=FIXTURE_PUBLISHED_AT,
        )
    )
    corpus.extend(
        _author_suite(
            owner_id=SEED_AUTHOR_NORTHWIND_ID,
            harness_id="codex",
            skill_core_id=SEED_A2_SKILL_CORE_ID,
            skill_pair_id=SEED_A2_SKILL_PAIR_ID,
            mcp_id=SEED_A2_MCP_ID,
            hook_id=SEED_A2_HOOK_ID,
            agent_id=SEED_A2_AGENT_ID,
            setup_id=SEED_A2_SETUP_ID,
            brand="northwind",
            skill_core_name="northwind-refactor-skill",
            skill_core_desc="Python refactor skill for Codex harness.",
            skill_core_tags=["python", "refactor"],
            skill_pair_name="northwind-test-skill",
            skill_pair_desc="Test-writing skill for Codex harness.",
            skill_pair_tags=["python", "tests"],
            mcp_name="northwind-github-mcp",
            mcp_desc="GitHub MCP bridge for Codex pull-request workflows.",
            mcp_tags=["github", "code-review"],
            hook_name="northwind-precommit-hook",
            hook_desc="Pre-commit lifecycle hook for Codex sessions.",
            hook_tags=["devops", "tests"],
            agent_name="northwind-review-agent",
            agent_desc="Code-review subagent for Codex pull requests.",
            agent_tags=["code-review", "python"],
            setup_name="northwind-python-workspace",
            setup_desc="Codex workspace: GitHub MCP, precommit hook, refactor and test skills.",
            setup_tags=["python", "code-review"],
            purpose="python-development",
            target_role="developer",
            supported_tasks=["code-review", "refactor", "tests"],
            published_at=SEED_PUBLISHED_AT_V2,
        )
    )
    corpus.extend(
        _author_suite(
            owner_id=SEED_AUTHOR_RIVER_ID,
            harness_id="pi",
            skill_core_id=SEED_A3_SKILL_CORE_ID,
            skill_pair_id=SEED_A3_SKILL_PAIR_ID,
            mcp_id=SEED_A3_MCP_ID,
            hook_id=SEED_A3_HOOK_ID,
            agent_id=SEED_A3_AGENT_ID,
            setup_id=SEED_A3_SETUP_ID,
            brand="river",
            skill_core_name="river-docs-skill",
            skill_core_desc="Documentation writing skill for the Pi harness.",
            skill_core_tags=["documentation"],
            skill_pair_name="river-research-skill",
            skill_pair_desc="Research synthesis skill for the Pi harness.",
            skill_pair_tags=["documentation", "planning"],
            mcp_name="river-docs-mcp",
            mcp_desc="Documentation MCP server for the Pi harness.",
            mcp_tags=["documentation"],
            hook_name="river-session-hook",
            hook_desc="Session lifecycle hook for Pi documentation runs.",
            hook_tags=["documentation", "devops"],
            agent_name="river-planner-agent",
            agent_desc="Planning subagent for Pi documentation projects.",
            agent_tags=["planning", "documentation"],
            setup_name="river-docs-workspace",
            setup_desc="Pi workspace: docs MCP, session hook, docs and research skills.",
            setup_tags=["documentation", "planning"],
            purpose="documentation",
            target_role="technical-writer",
            supported_tasks=["docs", "research"],
            published_at=FIXTURE_PUBLISHED_AT,
        )
    )
    river_agent_source = deepcopy(
        next(
            passport
            for kind, passport, _published, _digest in corpus
            if kind == "component" and passport["stable_id"] == SEED_A3_AGENT_ID
        )
    )
    river_agent_source.update(
        {
            "version": "1.1",
            "created_at": SEED_PUBLISHED_AT_V2,
            "source": {
                "repository": "https://github.com/ai-engineers-guild/ai-stp",
                "commit": "3d58d4f470461456f10b236d7017dcba7a74332a",
                "path": "apps/platform/src/ai_stp_platform/catalog_seed.py",
            },
        }
    )
    corpus.append(
        _seed_entry(
            "component",
            _seal_component(river_agent_source),
            SEED_PUBLISHED_AT_V2,
        )
    )
    corpus.extend(_incident_entries())
    return corpus


async def upsert_seed_version(
    session: AsyncSession,
    *,
    object_kind: ObjectKind,
    passport: dict[str, Any],
    published_at_wire: str,
    passport_digest: str,
    store: ImmutableObjectStore | None = None,
) -> tuple[CatalogMetadata, bool]:
    """Upsert one published experimental version by (kind, stable_id, version).

    Returns (row, created). Sprint-1 seed is entirely experimental (REQ-2110).
    """
    del store  # artifact byte put is optional; fixture digests are placeholders
    stable_id = str(passport["stable_id"])
    version = str(passport["version"])
    owner_id = str(passport.get("owner_id") or SEED_OWNER_ACCOUNT_ID)
    existing = await session.scalar(
        select(CatalogMetadata).where(
            CatalogMetadata.object_kind == object_kind,
            CatalogMetadata.stable_id == stable_id,
            CatalogMetadata.version == version,
        )
    )
    if existing is not None:
        return existing, False

    row = CatalogMetadata(
        owner_account_id=owner_id,
        object_kind=object_kind,
        stable_id=stable_id,
        version=version,
        current_revision_id=str(passport["revision_id"]),
        visibility="public",
        lifecycle_state="active",
        name=str(passport.get("name") or ""),
        published_at=parse_timestamp(published_at_wire),
        # The seed is frozen contract evidence.  Its object update timestamp is
        # the publication event, not the wall clock when a test database happens
        # to be migrated, otherwise conformance responses change every run.
        updated_at=parse_timestamp(published_at_wire),
        trust_lane="experimental",
        author_verified=False,
        component_verified=False,
        passport_digest=passport_digest,
        passport_document=passport,
    )
    session.add(row)
    await session.flush()
    return row, True


async def load_first_party_seed(
    session: AsyncSession,
    *,
    store: ImmutableObjectStore | None = None,
) -> SeedResult:
    """Idempotent environment-scoped seed of public experimental first-party objects."""
    created_accounts = 0
    for account_id in SEED_ACCOUNT_IDS:
        owner = await session.get(Account, account_id)
        if owner is None:
            session.add(Account(id=account_id))
            created_accounts += 1
    if created_accounts:
        await session.flush()

    created = 0
    reused = 0
    artifacts_written = 0
    for kind, passport, published_wire, digest in seed_corpus():
        _, was_created = await upsert_seed_version(
            session,
            object_kind=kind,
            passport=passport,
            published_at_wire=published_wire,
            passport_digest=digest,
            store=store,
        )
        if was_created:
            created += 1
        else:
            reused += 1
        if (
            store is not None
            and kind == "component"
            and passport.get("stable_id") == SEED_A1_INCIDENT_AGENT_ID
            and await _write_seed_artifact(store, INCIDENT_SUBAGENT_ARTIFACT)
        ):
            artifacts_written += 1
    preview_id = "media_seed_river_planner_preview"
    if await session.get(ComponentMedia, preview_id) is None:
        session.add(
            ComponentMedia(
                id=preview_id,
                stable_id=SEED_A3_AGENT_ID,
                owner_account_id=SEED_AUTHOR_RIVER_ID,
                position=0,
                kind="youtube",
                source_type="youtube",
                state="ready",
                youtube_video_id="aqz-KE-bpKQ",
                alt="River planner agent workflow preview",
                caption="Planning workflow preview",
            )
        )
        await session.flush()
    return SeedResult(
        created_accounts=created_accounts,
        created_versions=created,
        reused_versions=reused,
        artifacts_written=artifacts_written,
    )
