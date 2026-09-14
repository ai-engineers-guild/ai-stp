import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
vi.mock("@/lib/i18n/navigation", () => ({ Link: "a" }));
vi.mock("next-intl", () => ({ useTranslations: () => (key: string) => key }));
import {
  CorporateDirectoryResults,
  matchesDirectoryFilters,
} from "@/components/organisms/corporate-directory-results";
describe("corporate directory filters", () => {
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
    expect(screen.getByRole("link")).toHaveAttribute("href", "/corporate/projects/project");
    expect(within(screen.getByRole("link")).getByText("Owner")).toBeVisible();
    expect(within(screen.getByRole("link")).getByText("Technology")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "listView" }));
    expect(screen.getByRole("button", { name: "listView" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });
});
