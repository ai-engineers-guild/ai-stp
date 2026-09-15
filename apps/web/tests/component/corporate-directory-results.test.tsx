import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
vi.mock("@/lib/i18n/navigation", () => ({ Link: "a" }));
vi.mock("next-intl", () => ({ useTranslations: () => (key: string) => key }));
import {
  CorporateDirectoryResults,
  matchesDirectoryFilters,
} from "@/components/organisms/corporate-directory-results";
describe("corporate directory filters", () => {
  beforeEach(() => {
    window.history.replaceState(null, "", "/en/corporate/projects");
  });
  const item = {
    id: "project",
    name: "Project",
    state: "active",
    owner_team: { id: "owner", name: "Owner" },
    technologies: [{ id: "tech", name: "Technology" }],
  };
  it("includes owner teams, ORs values and ANDs facets", () => {
    expect(
      matchesDirectoryFilters(item, { teams: ["other", "owner"], technologies: ["tech"] }),
    ).toBe(true);
    expect(matchesDirectoryFilters(item, { teams: ["owner"], technologies: ["other"] })).toBe(
      false,
    );
    expect(matchesDirectoryFilters(item, { leads: ["missing"] })).toBe(false);
    expect(matchesDirectoryFilters(item, { teams: [] })).toBe(true);
  });
  it("renders clickable cards with owner and tags and switches to rows", () => {
    render(<CorporateDirectoryResults resource="projects" items={[item]} />);
    expect(screen.getByRole("link", { name: "Project" })).toHaveAttribute(
      "href",
      "/corporate/projects/project",
    );
    expect(screen.getByRole("link", { name: "Owner" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Technology" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "listView" }));
    expect(screen.getByRole("button", { name: "listView" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("renders catalog component metadata and the shared filter dialog", () => {
    render(
      <CorporateDirectoryResults
        resource="components"
        items={[
          {
            id: "agent-gateway",
            name: "Agent Gateway",
            state: "active",
            description: "Gateway",
            component_type: "skill",
            author_name: "Ada Lovelace",
            owner_name: "Grace Hopper",
            tags: ["LLM"],
            version: "1.0.0",
          },
        ]}
      />,
    );
    expect(screen.getByRole("link", { name: "Agent Gateway" })).toHaveAttribute(
      "href",
      "/catalog/components/agent-gateway?return_to=%2Fcorporate%2Fcomponents",
    );
    expect(screen.getByText("skill")).toBeVisible();
    expect(screen.getByText("Ada Lovelace")).toBeVisible();
    expect(screen.getByText("Grace Hopper")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "filters" }));
    expect(screen.getByRole("dialog")).toBeVisible();
  });

  it("renders technology ownership and usage in the shared directory card", () => {
    render(
      <CorporateDirectoryResults
        resource="technologies"
        items={[
          {
            id: "claude-code",
            name: "Claude Code",
            state: "active",
            description: "AI coding assistant",
            owner: { id: "elena", name: "Elena Smirnova", kind: "employee" },
            projects: [{ id: "growth", name: "Growth Experiments", kind: "project" }],
            teams: [{ id: "product", name: "Product & Engineering", kind: "team" }],
          },
        ]}
      />,
    );
    expect(screen.getByRole("link", { name: "Elena Smirnova" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Growth Experiments" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Product & Engineering" })).toBeVisible();
    expect(screen.getByRole("button", { name: "listView" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });
});
