import { describe, expect, it, vi } from "vitest";

import type * as requireSessionModule from "@/lib/auth/require-session";
import type * as technologyApi from "@/lib/api/technology";

vi.mock("next-intl/server", () => ({
  getTranslations: () => Promise.resolve((key: string) => key),
}));

vi.mock("@/lib/auth/require-session", async (importOriginal) => {
  const actual = await importOriginal<typeof requireSessionModule>();
  return { ...actual, sessionCookieValue: () => Promise.resolve("session-fixture") };
});

vi.mock("@/lib/api/corporate", () => ({
  readCorporateContext: () =>
    Promise.resolve({ organization: { organization_id: "organization_A" } }),
  readCorporateMemberAccess: () => Promise.resolve(null),
  readCorporateWorkspace: () => Promise.resolve(null),
}));

vi.mock("@/lib/api/corporate-audit", () => ({ readCorporateAudit: vi.fn() }));

vi.mock("@/lib/api/technology", async (importOriginal) => {
  const actual = await importOriginal<typeof technologyApi>();
  return {
    ...actual,
    readTechnologyLandscape: () =>
      Promise.resolve({
        items: [
          {
            technology: { name: "FastAPI", technology_id: "technology_A" },
            project_count: 1,
            proposed_project_count: 0,
            projects: [
              {
                project_id: "project_A",
                name: "api",
                activity: "active",
                source_availability: "available",
                usage: { relation_id: "relation_A", facts: {} },
              },
            ],
          },
        ],
      }),
    readTechnologyRegistry: () => Promise.resolve(null),
    readTechnologyDetail: () => Promise.resolve(null),
    readTechnologyCapabilities: () => Promise.resolve({ capabilities: [] }),
    readTechnologyLandscapePolicy: () => Promise.resolve({ inactivity_months: 12 }),
    readCategoryDirectory: () => Promise.resolve(null),
    readCategoryDetail: () => Promise.resolve(null),
  };
});

const { resolveMachineDocument } = await import("@/lib/projection/registry");
const { machineDocumentToText } = await import("@/lib/projection/document-text");

describe("machine projection landscape filters", () => {
  it("repeats array filters in project links instead of comma-folding them", async () => {
    const document = await resolveMachineDocument({
      segments: ["corporate", "technology-landscape"],
      locale: "en",
      searchParams: { project_ids: ["project_A", "project_B"], review: "confirmed" },
    });
    if (document === null) throw new Error("no machine route for technology-landscape");
    const text = machineDocumentToText(document, "en");
    expect(text).toContain("project_ids=project_A&project_ids=project_B");
    expect(text).not.toContain("project_ids=project_A%2Cproject_B");
  });
});
