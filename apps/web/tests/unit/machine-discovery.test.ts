import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GET as agents } from "@/app/agents.md/route";
import { GET as llmsFull } from "@/app/llms-full.txt/route";
import { GET as llms } from "@/app/llms.txt/route";

describe("machine discovery surfaces", () => {
  beforeEach(() => {
    vi.stubEnv("NEXT_PUBLIC_APP_URL", "http://localhost:3000");
    vi.stubEnv("AI_STP_API_BASE_URL", "http://localhost:8000");
    vi.stubEnv("AI_STP_SESSION_SECRET", "dev-only-change-me-to-a-long-random-string");
    vi.stubEnv("AI_STP_USER_DOCS_URL", "http://localhost:8011");
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("publishes a concise LLM index and extended context", async () => {
    const concise = await llms().text();
    const extended = await llmsFull().text();
    expect(concise).toContain("author_verified is not proof");
    expect(concise).toContain("/agents.md");
    expect(extended).toContain("local_owner_or_pinned");
  });

  it("keeps agent onboarding safety-first", async () => {
    const body = await agents().text();
    expect(body).toContain("ai-stp doctor --json");
    expect(body).toContain("Ask before experimental selection");
  });
});
