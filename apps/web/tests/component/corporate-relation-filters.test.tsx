import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { CorporateRelationSection } from "@/components/organisms/corporate-relation-section";

vi.mock("@/components/organisms/corporate-directory-card", () => ({
  CorporateDirectoryCard: ({ item }: { item: { name: string } }) => <div>{item.name}</div>,
}));

const labels = {
  filters: "Filters",
  filterTitle: "Refine",
  filterHint: "Hint",
  reset: "Reset",
  close: "Close",
  search: "Search",
  apply: "Apply",
  previous: "Previous",
  next: "Next",
  page: "Page",
  noMatches: "No matches",
  moreActions: "Actions",
  owner: "Owner",
  operationalOwner: "Operational owner",
  teams: "Teams",
  projects: "Projects",
  technologies: "Technologies",
  categories: "Categories",
  areas: "Areas",
  job_titles: "Job titles",
  teamLeads: "Team leads",
  team: "Team",
  employee: "Employee",
  author: "Author",
  type: "Type",
  lead: "Lead",
  unknownEmployee: "Unknown",
  notAvailable: "Unavailable",
};
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("applies the selected area to the project technology request and changes cards", async () => {
  const requests: URL[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((input: string) => {
      const url = new URL(input, "http://localhost");
      requests.push(url);
      const filtered = url.searchParams.get("area_ids") === "area_backend";
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            items: filtered
              ? [{ id: "tech_backend", name: "Backend" }]
              : [
                  { id: "tech_backend", name: "Backend" },
                  { id: "tech_frontend", name: "Frontend" },
                ],
            total: filtered ? 1 : 2,
            facets: { areas: [{ id: "area_backend", name: "Backend area" }] },
          }),
      });
    }),
  );
  render(
    <CorporateRelationSection
      title="Technologies"
      resource="technologies"
      references={[
        { id: "tech_backend", name: "Backend" },
        { id: "tech_frontend", name: "Frontend" },
      ]}
      api={{ resource: "technologies", filters: { project_ids: ["project_1"] } }}
      labels={labels}
    />,
  );
  expect(await screen.findByText("Frontend")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Filters" }));
  expect(screen.getAllByText("Areas").length).toBeGreaterThan(0);
  fireEvent.click(screen.getByRole("button", { name: "Areas" }));
  fireEvent.click(screen.getByRole("checkbox", { name: "Backend area" }));
  fireEvent.click(screen.getByRole("button", { name: "Apply" }));
  await waitFor(() => {
    expect(screen.queryByText("Frontend")).toBeNull();
  });
  expect(requests.at(-1)?.searchParams.getAll("project_ids")).toEqual(["project_1"]);
  expect(requests.at(-1)?.searchParams.getAll("area_ids")).toEqual(["area_backend"]);
});
