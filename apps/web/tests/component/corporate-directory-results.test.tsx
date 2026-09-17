import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
const { push } = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("@/lib/i18n/navigation", () => ({ Link: "a", useRouter: () => ({ push }) }));
vi.mock("next-intl", () => ({ useTranslations: () => (key: string) => key }));
import {
  CorporateDirectoryResults,
  matchesDirectoryFilters,
} from "@/components/organisms/corporate-directory-results";
describe("corporate directory filters", () => {
  beforeEach(() => {
    push.mockClear();
    window.history.replaceState(null, "", "/en/corporate/projects");
  });
  const item = {
    id: "project",
    name: "Project",
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
  it("applies filter drafts explicitly and discards them on Escape", () => {
    render(
      <CorporateDirectoryResults
        resource="members"
        items={[
          { id: "lead", name: "Lead employee", is_lead: true },
          { id: "staff", name: "Staff employee" },
        ]}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "filters" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "lead" }));
    expect(screen.getByRole("link", { name: "Staff employee" })).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.getByRole("link", { name: "Staff employee" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "filters" }));
    expect(screen.getByRole("checkbox", { name: "lead" })).not.toBeChecked();
    fireEvent.click(screen.getByRole("checkbox", { name: "lead" }));
    fireEvent.click(screen.getByRole("button", { name: "applyFilters" }));
    expect(screen.queryByRole("link", { name: "Staff employee" })).not.toBeInTheDocument();
  });
  it("renders clickable cards with owner and tags and switches to rows", () => {
    render(<CorporateDirectoryResults resource="projects" items={[item]} />);
    expect(screen.getByRole("link", { name: "Project" })).toHaveAttribute(
      "href",
      "/corporate/projects/project",
    );
    expect(screen.getByRole("link", { name: "Owner" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Technology" })).toBeVisible();
    expect(screen.queryByText("active")).not.toBeInTheDocument();
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
    expect(screen.getByRole("dialog")).toHaveAttribute("data-filter-surface", "drawer");
    expect(screen.getByRole("button", { name: "applyFilters" })).toBeVisible();
    expect(screen.getByRole("button", { name: "resetAll" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "applyFilters" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("writes corporate catalog facets to the URL and router", () => {
    window.history.replaceState(null, "", "/en/corporate/components?organization_id=org");
    render(
      <CorporateDirectoryResults
        resource="components"
        items={[]}
        catalogFacets={[
          {
            key: "team_ids",
            label: "catalogTeams",
            options: [{ value: "team_mobile", label: "Mobile" }],
          },
        ]}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "filters" }));
    fireEvent.click(screen.getByRole("button", { name: "catalogTeams" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Mobile" }));
    fireEvent.click(screen.getAllByRole("button", { name: "closeFilters" }).at(-1)!);
    fireEvent.click(screen.getByRole("button", { name: "applyFilters" }));
    expect(push).toHaveBeenCalledWith(
      "/en/corporate/components?organization_id=org&sort=name&team_ids=team_mobile",
    );
  });

  it("renders technology ownership and usage in the shared directory card", () => {
    render(
      <CorporateDirectoryResults
        resource="technologies"
        items={[
          {
            id: "claude-code",
            name: "Claude Code",
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
    expect(screen.queryByText("AI coding assistant")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "listView" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });
});
