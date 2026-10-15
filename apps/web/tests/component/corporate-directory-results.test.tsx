import { entityMenuResult, publicActions } from "../entity-menu-fixture";
import type { EntityActionSubject } from "@/lib/api/generated/types.gen";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
const { push } = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("@/lib/i18n/navigation", () => ({
  Link: "a",
  useRouter: () => ({ push }),
  usePathname: () => window.location.pathname.replace(/^\/en/, "") || "/",
}));
vi.mock("next-intl", () => ({
  useLocale: () => "en",
  useTranslations: () => (key: string) => key,
}));
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
  it.each(["projects", "teams"] as const)(
    "limits %s technology chips to five and keeps overflow reachable",
    async (resource) => {
      const user = userEvent.setup();
      const technologies = Array.from({ length: 7 }, (_, index) => ({
        id: `tech_${index}`,
        name: `Technology ${index}`,
        kind: "technology" as const,
      }));
      render(
        <CorporateDirectoryResults
          resource={resource}
          items={[{ id: "entity", name: "Entity", technologies }]}
        />,
      );
      for (let index = 0; index < 5; index++)
        expect(screen.getByRole("link", { name: `Technology ${index}` })).toBeVisible();
      expect(screen.queryByRole("link", { name: "Technology 5" })).not.toBeInTheDocument();
      await user.click(screen.getByRole("button", { name: /^technologies:/ }));
      expect(await screen.findByRole("menuitem", { name: "Technology 5" })).toHaveAttribute(
        "href",
        expect.stringContaining("tech_5"),
      );
    },
  );
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

  it("uses the server action projection for card actions", async () => {
    const user = userEvent.setup();
    render(
      <CorporateDirectoryResults
        resource="projects"
        items={[
          {
            ...item,
            available_actions: ["project.update", "entity_profile.update"],
          },
        ]}
      />,
    );
    await user.click(screen.getByRole("button", { name: "moreActions" }));
    expect(screen.getByRole("menuitem", { name: "openDetails" })).toHaveAttribute(
      "href",
      "/corporate/projects/project",
    );
    expect(screen.getByRole("menuitem", { name: "edit" })).toHaveAttribute(
      "href",
      "/corporate/projects/project/edit",
    );
    expect(screen.getByRole("menuitem", { name: "editPresentation" })).toHaveAttribute(
      "href",
      "/corporate/projects/project/presentation/edit",
    );
  });

  it("does not invent privileged actions when the server projection is empty", async () => {
    const user = userEvent.setup();
    render(<CorporateDirectoryResults resource="teams" items={[{ id: "team", name: "Team" }]} />);
    await user.click(screen.getByRole("button", { name: "moreActions" }));
    expect(screen.queryByRole("menuitem", { name: "edit" })).not.toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "editPresentation" })).not.toBeInTheDocument();
  });

  it("renders a normal create link when a dedicated create route is provided", () => {
    render(
      <CorporateDirectoryResults
        resource="teams"
        items={[]}
        addLabel="addTeam"
        addHref="/corporate/teams/new"
      />,
    );
    expect(screen.getByRole("link", { name: "addTeam" })).toHaveAttribute(
      "href",
      "/corporate/teams/new",
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
      "/catalog/components/agent-gateway?return_to=%2Fcorporate%2Fcatalog",
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

  it("writes corporate catalog facets to the URL and router", async () => {
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
    const closeButton = screen.getAllByRole("button", { name: "closeFilters" }).at(-1);
    if (!closeButton) throw new Error("catalog facet close button is missing");
    fireEvent.click(closeButton);
    fireEvent.click(screen.getByRole("button", { name: "applyFilters" }));
    await vi.waitFor(() => {
      expect(push).toHaveBeenCalledWith(
        "/corporate/components?organization_id=org&sort=name&page=1&team_ids=team_mobile",
      );
    });
  });

  it("clears every facet param atomically on Reset all + Apply", async () => {
    window.history.replaceState(null, "", "/en/corporate/technologies?area_ids=area_1&page=2");
    render(
      <CorporateDirectoryResults
        resource="technologies"
        serverPaginated
        total={1}
        items={[{ id: "tech", name: "Tech", areas: [{ id: "area_1", name: "Area" }] }]}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /filters/ }));
    fireEvent.click(screen.getByRole("button", { name: "resetAll" }));
    fireEvent.click(screen.getByRole("button", { name: "applyFilters" }));
    await vi.waitFor(() => {
      expect(push).toHaveBeenCalled();
    });
    const url = push.mock.calls.at(-1)?.[0] as string;
    expect(url).not.toContain("area_ids");
    expect(url).toContain("page=1");
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
    expect(screen.queryByText("—")).not.toBeInTheDocument();
  });
});

vi.mock("@/lib/entity-action-query", () => ({
  queryEntityActionMenu: vi.fn((subject: EntityActionSubject) =>
    Promise.resolve(
      entityMenuResult(
        subject,
        subject.kind === "project"
          ? [...publicActions.slice(0, -1), "edit", "edit_presentation", "report"]
          : publicActions,
        `/corporate/${subject.kind === "project" ? "projects" : "teams"}/${subject.id}`,
      ),
    ),
  ),
}));
