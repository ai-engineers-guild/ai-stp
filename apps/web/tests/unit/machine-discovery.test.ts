import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GET as agents } from "@/app/agents.md/route";
import { GET as catalog } from "@/app/llms/catalog.ndjson/route";
import { GET as llmsFull } from "@/app/llms-full.txt/route";
import { GET as llms } from "@/app/llms.txt/route";
import { resetEnvCache } from "@/lib/env";

describe("machine discovery surfaces", () => {
  beforeEach(() => {
    vi.stubEnv("NEXT_PUBLIC_APP_URL", "http://localhost:3000");
    vi.stubEnv("AI_STP_API_BASE_URL", "http://localhost:8000");
    vi.stubEnv("AI_STP_SESSION_SECRET", "dev-only-change-me-to-a-long-random-string");
    vi.stubEnv("AI_STP_USER_DOCS_URL", "http://localhost:8011");
    vi.stubEnv("AI_STP_USE_MOCKS", "true");
    resetEnvCache();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("publishes a concise LLM index and extended context", async () => {
    const concise = await llms().text();
    const extended = await (await llmsFull()).text();
    expect(concise).toContain("author_verified is not proof");
    expect(concise).toContain("/agents.md");
    expect(concise).toContain("/llms/catalog.ndjson");
    expect(extended).toContain("local_owner_or_pinned");
    expect(
      extended.includes("/llms/catalog.ndjson") || concise.includes("/llms/catalog.ndjson"),
    ).toBe(true);
  });

  it("keeps agent onboarding safety-first", async () => {
    const body = await agents().text();
    expect(body).toContain("ai-stp doctor --json");
    expect(body).toContain("Ask before experimental selection");
  });

  it("serves a paginated catalog manifest instead of one giant document", async () => {
    const response = await catalog(new Request("http://localhost:3000/llms/catalog.ndjson"));
    expect(response.headers.get("content-type")).toContain("ndjson");
    const body = await response.text();
    expect(body.split("\n").filter(Boolean).length).toBeLessThan(200);
  });
});
