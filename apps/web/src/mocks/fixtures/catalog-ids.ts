export const FIXTURE_COMPONENT_ID = "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z";
export const FIXTURE_SETUP_ID = "setup_01JQZK7B8N4M6P2R9T5V0X3Y7Z";

// Author 1 — First Party / claude-code
export const SEED_A1_SKILL_CORE_ID = "component_01JQZK7B8N4M6P2R9T5V0X3YB0";
export const SEED_A1_SKILL_PAIR_ID = "component_01JQZK7B8N4M6P2R9T5V0X3YB1";
export const SEED_A1_MCP_ID = "component_01JQZK7B8N4M6P2R9T5V0X3YB2";
export const SEED_A1_HOOK_ID = "component_01JQZK7B8N4M6P2R9T5V0X3YB3";
export const SEED_A1_AGENT_ID = "component_01JQZK7B8N4M6P2R9T5V0X3YB4";
export const SEED_A1_INCIDENT_AGENT_ID = "component_01JQZK7B8N4M6P2R9T5V0X3YBF";
export const SEED_A1_SETUP_ID = "setup_01JQZK7B8N4M6P2R9T5V0X3YC0";
export const SEED_A1_INCIDENT_SETUP_ID = "setup_01JQZK7B8N4M6P2R9T5V0X3YC3";

// Author 2 — Northwind / codex
export const SEED_A2_SKILL_CORE_ID = "component_01JQZK7B8N4M6P2R9T5V0X3YB5";
export const SEED_A2_SKILL_PAIR_ID = "component_01JQZK7B8N4M6P2R9T5V0X3YB6";
export const SEED_A2_MCP_ID = "component_01JQZK7B8N4M6P2R9T5V0X3YB7";
export const SEED_A2_HOOK_ID = "component_01JQZK7B8N4M6P2R9T5V0X3YB8";
export const SEED_A2_AGENT_ID = "component_01JQZK7B8N4M6P2R9T5V0X3YB9";
export const SEED_A2_SETUP_ID = "setup_01JQZK7B8N4M6P2R9T5V0X3YC1";

// Author 3 — River Guild / pi
export const SEED_A3_SKILL_CORE_ID = "component_01JQZK7B8N4M6P2R9T5V0X3YBA";
export const SEED_A3_SKILL_PAIR_ID = "component_01JQZK7B8N4M6P2R9T5V0X3YBB";
export const SEED_A3_MCP_ID = "component_01JQZK7B8N4M6P2R9T5V0X3YBC";
export const SEED_A3_HOOK_ID = "component_01JQZK7B8N4M6P2R9T5V0X3YBD";
export const SEED_A3_AGENT_ID = "component_01JQZK7B8N4M6P2R9T5V0X3YBE";
export const SEED_A3_SETUP_ID = "setup_01JQZK7B8N4M6P2R9T5V0X3YC2";

// Backward-compatible aliases used by older tests.
export const SEED_COMPONENT_CODEX_ID = SEED_A2_SKILL_CORE_ID;
export const SEED_COMPONENT_PI_ID = SEED_A3_MCP_ID;
export const SEED_COMPONENT_OPENCODE_ID = SEED_A1_HOOK_ID;
export const SEED_SETUP_CODEX_ID = SEED_A2_SETUP_ID;
export const SEED_SETUP_PI_ID = SEED_A3_SETUP_ID;

export const ZERO_DIGEST = "sha256:" + "0".repeat(64);

export const experimentalTrust = {
  trust_lane: "experimental" as const,
  author_verified: false,
  component_verified: false,
};
