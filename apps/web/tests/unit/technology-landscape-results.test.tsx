import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ComponentProps } from "react";
import type { TechnologyLandscapeView } from "@/lib/api/generated/types.gen";
vi.mock("next-intl/server", () => ({
  getTranslations: () => Promise.resolve((key: string) => key),
}));
vi.mock("@/lib/i18n/navigation", () => ({
  Link: ({ children, ...props }: ComponentProps<"a">) => <a {...props}>{children}</a>,
}));
import { TechnologyLandscapeResults } from "@/components/organisms/technology-landscape-results";
const sample: TechnologyLandscapeView = {
  organization_id: "organization_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
  evaluated_at: "2026-09-12T00:00:00.000Z",
  inactivity_months: 9,
  filters: {
    category_id: null,
    query: null,
    technology_id: null,
    project_id: null,
    team_id: null,
    lifecycle: null,
    adoption: null,
    context: null,
    review: null,
    freshness: null,
    include_history: false,
    include_inactive: false,
    offset: 0,
    limit: 128,
    project_offset: 0,
    project_limit: 128,
    view: "table",
  },
  items: [
    {
      technology: {
        name: "Bun",
        category_ids: ["category_01JQZK7B8N4M6P2R9T5V0X3Y7Z"],
        aliases: ["Bun runtime"],
        description: "",
        icon_url: null,
        official_urls: [],
        schema_version: 1,
        organization_id: "organization_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
        technology_id: "technology_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
        owner_account_id: null,
        lifecycle: "active",
        restore_lifecycle: "draft",
        revision: 2,
        redirect_id: null,
        provenance: "manual",
      },
      project_count: 1,
      proposed_project_count: 0,
      projects: [
        {
          project_id: "remote_project_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
          name: "Known project",
          activity: "unknown",
          usage: {
            organization_id: "organization_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
            relation_id: "relation_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
            project_id: "remote_project_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
            technology_id: "technology_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
            state: "current",
            revision: 1,
            facts: [
              {
                context: "development",
                version: null,
                version_kind: "unknown",
                evidence: [],
                review: "confirmed",
                freshness: "current",
              },
            ],
          },
        },
      ],
      decision: null,
    },
  ],
  total: 1,
};
afterEach(cleanup);
describe("one authorized landscape projection", () => {
  it("repeats a multi-category row without inventing additive counts", async () => {
    const row = sample.items[0];
    if (!row) throw new Error("sample row is missing");
    const landscape: TechnologyLandscapeView = {
      ...sample,
      filters: { ...sample.filters, view: "grouped" },
      items: [
        {
          ...row,
          technology: {
            ...row.technology,
            category_ids: [...row.technology.category_ids, "category_00000000000000000000000002"],
          },
        },
      ],
    };
    render(await TechnologyLandscapeResults({ landscape, filters: { view: "grouped" } }));
    expect(screen.getByText("groupedNote")).toBeVisible();
    expect(screen.getAllByRole("table")).toHaveLength(2);
    expect(screen.getAllByRole("link", { name: "Known project" })).toHaveLength(2);
    expect(screen.getAllByText("1")).toHaveLength(2);
  });
  it("never derives adoption placement from an active technology lifecycle", async () => {
    render(
      await TechnologyLandscapeResults({
        landscape: { ...sample, filters: { ...sample.filters, view: "radar" } },
        filters: { view: "radar" },
      }),
    );
    expect(screen.getByRole("heading", { name: "decisionUnavailable" })).toBeVisible();
    expect(screen.queryByRole("heading", { name: "values.adopt" })).toBeNull();
  });
  it("keeps filters and the exact project ID in links and paginates drill-down independently", async () => {
    const row = sample.items[0];
    if (!row) throw new Error("sample row is missing");
    const landscape: TechnologyLandscapeView = {
      ...sample,
      filters: { ...sample.filters, view: "relationships", project_limit: 1 },
      items: [{ ...row, project_count: 2 }],
    };
    render(
      await TechnologyLandscapeResults({
        landscape,
        filters: { view: "relationships", context: "development", project_limit: "1" },
      }),
    );
    const project = screen.getByRole("link", { name: "Known project" });
    expect(project.getAttribute("href")).toContain(row.projects[0]?.project_id);
    expect(project.getAttribute("href")).toContain("context=development");
    const next = screen.getByRole("link", { name: "next" }).getAttribute("href") ?? "";
    expect(next).toContain("project_offset=1");
    expect(next).toContain("technology_id=" + row.technology.technology_id);
    expect(next).toContain("view=relationships");
  });
});
