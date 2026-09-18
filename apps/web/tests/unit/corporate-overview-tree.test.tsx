import type { ReactNode } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { CorporateOverview, CorporateOverviewNode } from "@/lib/api/generated/types.gen";
import { overviewAssignmentHref, overviewForest, overviewUsage } from "@/lib/corporate-overview";

vi.mock("next-intl", () => ({ useTranslations: () => (key: string) => key }));
vi.mock("@/lib/i18n/navigation", () => ({
  Link: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));
import { CorporateOverviewTree } from "@/components/organisms/corporate-overview-tree";
import { ComponentUsageView } from "@/components/organisms/corporate-overview-usage";

afterEach(cleanup);
const node = (
  kind: CorporateOverviewNode["kind"],
  id: string,
  name: string,
): CorporateOverviewNode => ({
  kind,
  id,
  name,
  assignments: [],
  assignments_readable: true,
  lead_account_ids: [],
});
const graph: CorporateOverview = {
  schema_version: 1,
  organization: {
    schema_version: 1,
    organization_id: "organization_test",
    display_name: "Acme",
    state: "active",
    authorization_revision: 1,
  },
  nodes: [
    node("project", "p1", "Mobile"),
    node("project", "p2", "Web"),
    node("team", "t1", "Platform"),
    node("team", "t2", "Design"),
    node("employee", "e1", "Alice"),
    node("employee", "e2", "Bob"),
    node("employee", "e3", "Unassigned"),
  ],
  edges: [
    { parent_id: "p1", child_id: "t1", kind: "project_team", role: "owner" },
    { parent_id: "p2", child_id: "t1", kind: "project_team", role: "contributor" },
    { parent_id: "p2", child_id: "t2", kind: "project_team", role: "owner" },
    { parent_id: "t1", child_id: "e1", kind: "team_employee", role: "lead" },
    { parent_id: "t2", child_id: "e2", kind: "team_employee", role: "staff" },
  ],
};
const empty = () => ({ project: [], team: [], employee: [] });

it("links overview assignments to their exact catalog versions", () => {
  expect(
    overviewAssignmentHref({
      assignment_id: "assignment_1",
      object_kind: "component",
      organization_id: "organization_test",
      revision: 1,
      schema_version: 1,
      stable_id: "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
      state: "current",
      subject_id: "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
      subject_kind: "employee",
      version: "1.2",
      display_name: "Worker",
      source_team_id: null,
      source_team_name: null,
    }),
  ).toBe("/catalog/components/component_01JQZK7B8N4M6P2R9T5V0X3Y7Z/versions/1.2");
});

it("preserves shared branches without changing graph identities", () => {
  const forest = overviewForest(graph, empty());
  expect(forest.map((branch) => branch.node.name)).toEqual(["Mobile", "Web", "Unassigned"]);
  expect(forest[0]?.children[0]?.node.id).toBe(forest[1]?.children[0]?.node.id);
  expect(graph.nodes).toHaveLength(7);
});

it("uses OR within multiselect and AND across a branch", () => {
  const forest = overviewForest(graph, { project: ["p1", "p2"], team: ["t1"], employee: ["e1"] });
  expect(forest).toHaveLength(2);
  expect(
    forest.every((branch) => branch.children.length === 1 && branch.children[0]?.node.id === "t1"),
  ).toBe(true);
  expect(overviewForest(graph, { project: ["p1"], team: ["t2"], employee: [] })).toEqual([]);
  expect(overviewForest(graph, empty(), "Alice").map((branch) => branch.node.name)).toEqual([
    "Mobile",
    "Web",
  ]);
});

it("changes depth, filters employees, and restores the full graph", () => {
  const { container } = render(<CorporateOverviewTree graph={graph} />);
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "0" } });
  expect(container.querySelector('[data-ui="corporate-overview-tree"] details[open]')).toBeNull();
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "3" } });
  expect(
    container.querySelectorAll('[data-ui="corporate-overview-tree"] details[open]').length,
  ).toBeGreaterThan(3);
  fireEvent.click(screen.getByRole("checkbox", { name: "Alice" }));
  expect(screen.queryByRole("link", { name: "Bob" })).not.toBeInTheDocument();
  expect(screen.getAllByRole("link", { name: "Alice" })).toHaveLength(2);
  fireEvent.click(screen.getByRole("button", { name: "clearFilters" }));
  expect(screen.getByRole("link", { name: "Bob" })).toHaveAttribute(
    "href",
    "/corporate/employees/e2",
  );
});

it("toggles the global tree action between expand and collapse", () => {
  render(<CorporateOverviewTree graph={graph} />);
  const toggle = screen.getByRole("button", { name: "expandAll" });
  fireEvent.click(toggle);
  expect(screen.getByRole("button", { name: "collapseAll" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "collapseAll" }));
  expect(screen.getByRole("button", { name: "expandAll" })).toBeInTheDocument();
});

it("toggles every usage row from the shared global action", () => {
  const assignment = {
    assignment_id: "usage-1",
    display_name: "Gateway",
    object_kind: "component" as const,
    organization_id: "organization_test",
    revision: 1,
    schema_version: 1 as const,
    source_team_id: null,
    stable_id: "component_gateway",
    state: "current" as const,
    subject_id: "t1",
    subject_kind: "team" as const,
    version: "1.0",
  };
  const team = graph.nodes.find((item) => item.id === "t1");
  if (!team) throw new Error("Missing team fixture");
  const { container } = render(
    <CorporateOverviewTree
      graph={{ ...graph, nodes: [{ ...team, assignments: [assignment] }], edges: [] }}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "byComponents" }));
  const row = screen.getByRole("link", { name: "Gateway" }).closest("details");
  expect(row).not.toHaveAttribute("open");
  fireEvent.click(screen.getByRole("button", { name: "expandAll" }));
  expect(screen.getByRole("link", { name: "Gateway" }).closest("details")).toHaveAttribute("open");
  fireEvent.click(screen.getByRole("button", { name: "collapseAll" }));
  expect(container.querySelector("details[open]")).toBeNull();
});

it("does not describe unreadable assignments as empty", () => {
  render(
    <CorporateOverviewTree
      graph={{
        ...graph,
        nodes: [{ ...node("employee", "e1", "Alice"), assignments_readable: false }],
        edges: [],
      }}
    />,
  );
  expect(screen.getByText("assignmentsRestricted")).toBeInTheDocument();
  expect(screen.queryByText("noAssignments")).not.toBeInTheDocument();
});

it("opens the owning team first regardless of relationship ID order", () => {
  render(
    <CorporateOverviewTree
      graph={{
        ...graph,
        nodes: [
          node("project", "p1", "Growth"),
          node("team", "t1", "Data"),
          node("team", "t2", "Product"),
        ],
        edges: [
          { parent_id: "p1", child_id: "t1", kind: "project_team", role: "contributor" },
          { parent_id: "p1", child_id: "t2", kind: "project_team", role: "owner" },
        ],
      }}
    />,
  );
  expect(screen.getByRole("link", { name: "Product" }).closest("details")).toHaveAttribute("open");
  expect(screen.getByRole("link", { name: "Data" }).closest("details")).not.toHaveAttribute("open");
});

it("previews three employees and expands the remainder without losing identity", () => {
  const employees = ["Anna", "Ivan", "Maria", "Pavel"].map((name, index) =>
    node("employee", `preview-${index}`, name),
  );
  render(
    <CorporateOverviewTree
      graph={{
        ...graph,
        nodes: [node("project", "p1", "Growth"), node("team", "t1", "Product"), ...employees],
        edges: [
          { parent_id: "p1", child_id: "t1", kind: "project_team", role: "owner" },
          ...employees.map((employee) => ({
            parent_id: "t1",
            child_id: employee.id,
            kind: "team_employee" as const,
            role: "staff" as const,
          })),
        ],
      }}
    />,
  );
  expect(screen.queryByRole("link", { name: "Pavel" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "+1 employees" }));
  expect(screen.getByRole("link", { name: "Pavel" })).toHaveAttribute(
    "href",
    "/corporate/employees/preview-3",
  );
  fireEvent.click(screen.getByRole("button", { name: "showLess" }));
  expect(screen.queryByRole("link", { name: "Pavel" })).not.toBeInTheDocument();
});

it("separates and collapses technology and catalog assignment groups", () => {
  const assignment = {
    assignment_id: "grouped-1",
    display_name: "Agent Gateway",
    object_kind: "component" as const,
    organization_id: "organization_test",
    revision: 1,
    schema_version: 1 as const,
    source_team_id: null,
    stable_id: "component_gateway",
    state: "current" as const,
    subject_id: "grouped-team",
    subject_kind: "team" as const,
    version: "1.0",
  };
  render(
    <CorporateOverviewTree
      graph={{
        ...graph,
        nodes: [
          node("project", "grouped-project", "Growth"),
          {
            ...node("team", "grouped-team", "Platform"),
            technologies: [{ id: "postgres", kind: "technology" as const, name: "PostgreSQL" }],
            assignments: [assignment],
          },
        ],
        edges: [
          {
            parent_id: "grouped-project",
            child_id: "grouped-team",
            kind: "project_team",
            role: "owner",
          },
        ],
      }}
    />,
  );
  expect(screen.getByRole("link", { name: "PostgreSQL" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Agent Gateway" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /technologies/ }));
  expect(screen.queryByRole("link", { name: "PostgreSQL" })).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Agent Gateway" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /technologies/ }));
  expect(screen.getByRole("link", { name: "PostgreSQL" })).toBeInTheDocument();
});

it("groups a shared object once and deduplicates usage anchors", () => {
  const assignment = {
    assignment_id: "a1",
    display_name: "Gateway",
    object_kind: "component" as const,
    organization_id: "organization_test",
    revision: 1,
    schema_version: 1 as const,
    source_team_id: null,
    stable_id: "component_test",
    state: "current" as const,
    subject_id: "t1",
    subject_kind: "team" as const,
    version: "1.0",
  };
  const shared = {
    ...graph,
    nodes: graph.nodes.map((item) => ({
      ...item,
      assignments:
        item.kind === "team"
          ? [assignment, { ...assignment, assignment_id: "a2", version: "1.1" }]
          : [],
    })),
  };
  expect(overviewUsage(shared)).toHaveLength(1);
  expect(overviewUsage(shared)[0]?.nodes).toHaveLength(2);
  render(<CorporateOverviewTree graph={shared} />);
  fireEvent.click(screen.getByRole("button", { name: "byComponents" }));
  expect(screen.getAllByRole("link", { name: "Gateway" })).toHaveLength(1);
  expect(screen.queryByRole("button", { name: "setups" })).not.toBeInTheDocument();
});

it("renders one unified usage list with catalog type, author, and owner", () => {
  const teamFixture = graph.nodes.find((item) => item.id === "t1");
  if (!teamFixture) throw new Error("Missing team fixture");
  const assignment = {
    assignment_id: "component-1",
    display_name: "Gateway",
    object_kind: "component" as const,
    organization_id: "organization_test",
    revision: 1,
    schema_version: 1 as const,
    source_team_id: null,
    stable_id: "component_gateway",
    state: "current" as const,
    subject_id: "t1",
    subject_kind: "team" as const,
    version: "1.0",
    author_name: "Alex Kim",
    owner_name: "Elena Smirnova",
    owner_id: "e1",
    owner_readable: true,
    catalog_type: "skill",
  };
  const setup = {
    ...assignment,
    assignment_id: "setup-1",
    display_name: "Production",
    object_kind: "setup" as const,
    stable_id: "setup_production",
    catalog_type: "setup",
  };
  render(
    <ComponentUsageView
      graph={{ ...graph, nodes: [{ ...teamFixture, assignments: [assignment, setup] }] }}
      query=""
      teams={[]}
      sort="name"
      owners={[]}
    />,
  );
  expect(screen.getByRole("link", { name: "Gateway" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Production" })).toBeInTheDocument();
  expect(screen.getAllByText(/Alex Kim/)).toHaveLength(2);
  expect(screen.getByText("skill")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "setups" })).not.toBeInTheDocument();
});
