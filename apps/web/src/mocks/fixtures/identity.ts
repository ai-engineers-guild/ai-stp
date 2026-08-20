export const FIXTURE_ACCOUNT_ID = "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z";
export const SEED_AUTHOR_NORTHWIND_ID = "account_01JQZK7B8N4M6P2R9T5V0X3YA0";
export const SEED_AUTHOR_RIVER_ID = "account_01JQZK7B8N4M6P2R9T5V0X3YA1";
export const FIXTURE_TIMESTAMP = "2026-08-05T00:00:00.000Z";
export const SEED_TIMESTAMP_V2 = "2026-08-06T00:00:00.000Z";

export const seedPublicProfiles = {
  [FIXTURE_ACCOUNT_ID]: {
    schema_version: 1 as const,
    kind: "public_profile" as const,
    account_id: FIXTURE_ACCOUNT_ID,
    author_verified: true,
    display_name: "ai_stp First Party",
    bio: "Platform first-party publisher for launch corpus and fixture parity.",
    links: [
      { label: "GitHub", url: "https://github.com/ai-stp" },
      { label: "Docs", url: "https://github.com/ai-stp/docs" },
    ],
  },
  [SEED_AUTHOR_NORTHWIND_ID]: {
    schema_version: 1 as const,
    kind: "public_profile" as const,
    account_id: SEED_AUTHOR_NORTHWIND_ID,
    author_verified: true,
    display_name: "Northwind Labs",
    bio: "Codex-focused tooling publisher: review skills, MCP bridges, session hooks.",
    links: [{ label: "GitHub", url: "https://github.com/northwind-labs" }],
  },
  [SEED_AUTHOR_RIVER_ID]: {
    schema_version: 1 as const,
    kind: "public_profile" as const,
    account_id: SEED_AUTHOR_RIVER_ID,
    author_verified: false,
    display_name: "River Guild",
    bio: "Pi harness publisher for documentation workflows and planning agents.",
    links: [{ label: "Site", url: "https://github.com/river-guild" }],
  },
} as const;

export const seedPublicProfile = seedPublicProfiles[FIXTURE_ACCOUNT_ID];

export const accountProfile = {
  schema_version: 1 as const,
  account_id: FIXTURE_ACCOUNT_ID,
  created_at: FIXTURE_TIMESTAMP,
  show_profile_publicly: true,
  allow_publisher_listing: true,
  identities: [
    {
      provider: "github" as const,
      linked_at: FIXTURE_TIMESTAMP,
      avatar_url: "https://avatars.githubusercontent.com/u/1?v=4",
      display_name: "fixture-github",
    },
  ],
};
