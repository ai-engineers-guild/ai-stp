import { afterEach, describe, expect, it, vi } from "vitest";

import { asComponentId } from "@/lib/brands";
import {
  ALL_COMPONENT_SUMMARIES,
  FIXTURE_COMPONENT_ID,
  SEED_A1_INCIDENT_AGENT_ID,
  SEED_COMPONENT_CODEX_ID,
  SEED_COMPONENT_PI_ID,
} from "@/mocks/fixtures";

describe("mock catalog reads", () => {
  afterEach(() => {
    vi.resetModules();
    vi.unstubAllEnvs();
  });

  function stubEnv() {
    vi.stubEnv("NEXT_PUBLIC_APP_URL", "http://localhost:3000");
    vi.stubEnv("AI_STP_API_BASE_URL", "http://localhost:8000");
    vi.stubEnv("AI_STP_SESSION_SECRET", "dev-only-change-me-to-a-long-random-string");
    vi.stubEnv("AI_STP_USE_MOCKS", "true");
  }

  it("returns experimental component detail from fixtures", async () => {
    stubEnv();
    const { readComponent, searchComponents } = await import("@/lib/api/catalog");
    const list = await searchComponents({ q: "pytest", include_experimental: true });
    expect(list.items).toEqual([]);
    expect(list.experimental[0]?.stable_id).toBe(FIXTURE_COMPONENT_ID);
    const detail = await readComponent(asComponentId(FIXTURE_COMPONENT_ID));
    expect(detail.summary.latest_name).toBe("pytest-guard-skill");
    expect(detail.versions.map((v) => v.version)).toEqual(["1.0", "1.2"]);
  });

  it("lists multi-harness seed corpus when experimental is consented", async () => {
    stubEnv();
    const { searchComponents } = await import("@/lib/api/catalog");
    const list = await searchComponents({ include_experimental: true });
    expect(list.items).toEqual([]);
    const ids = list.experimental.map((item) => item.stable_id);
    expect(ids).toContain(FIXTURE_COMPONENT_ID);
    expect(ids).toContain(SEED_COMPONENT_CODEX_ID);
    expect(ids).toContain(SEED_COMPONENT_PI_ID);
  });

  it("filters by tag and rejects unknown query keys", async () => {
    stubEnv();
    const { searchComponents } = await import("@/lib/api/catalog");
    const { mockFetch } = await import("@/lib/api/mock-transport");
    const tagged = await searchComponents({
      include_experimental: true,
      tags: ["documentation"],
    });
    const ids = tagged.experimental.map((item) => item.stable_id);
    expect(ids.length).toBeGreaterThanOrEqual(1);
    expect(ids).toContain(SEED_COMPONENT_PI_ID);

    const byType = await searchComponents({
      include_experimental: true,
      component_type: "agent",
    });
    expect(byType.experimental.every((item) => item.latest_component_type === "agent")).toBe(true);
    expect(byType.experimental.map((item) => item.stable_id)).toContain(SEED_A1_INCIDENT_AGENT_ID);
    expect(byType.experimental.length).toBe(
      ALL_COMPONENT_SUMMARIES.filter((item) => item.latest_component_type === "agent").length,
    );

    const rejected = mockFetch("GET", "/v1/catalog/components", {
      query: new URLSearchParams({ include_experimental: "true", bogus: "1" }),
    });
    expect(rejected.status).toBe(400);
  });

  it("filters mock catalog by support tier and state", async () => {
    stubEnv();
    const { searchComponents } = await import("@/lib/api/catalog");
    const beta = await searchComponents({
      include_experimental: true,
      support_tier: "beta",
      support_state: "missing",
    });
    expect(beta.items).toEqual([]);
    expect(beta.experimental.length).toBeGreaterThan(0);
    expect(
      beta.experimental.every(
        (item) => item.latest_support.tier === "beta" && item.latest_support.state === "missing",
      ),
    ).toBe(true);
  });

  it("updates mock catalog reactions", async () => {
    const { mockFetch } = await import("@/lib/api/mock-transport");
    const path = "/v1/account/catalog-reactions/component/component_01JQZK7B8N4M6P2R9T5V0X3YBE";
    expect(mockFetch("PUT", path).body).toEqual({ schema_version: 1, liked: true, likes_count: 1 });
    expect(mockFetch("DELETE", path).body).toEqual({
      schema_version: 1,
      liked: false,
      likes_count: 0,
    });
  });
});
