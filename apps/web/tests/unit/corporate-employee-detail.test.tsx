import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { ApiError } from "@/lib/api/errors";

const { profile, components, setups, assignments, registry } = vi.hoisted(() => ({
  profile: vi.fn(),
  components: vi.fn(),
  setups: vi.fn(),
  assignments: vi.fn(),
  registry: vi.fn(),
}));
vi.mock("@/lib/api/public-profile", () => ({ readPublisherProfile: profile }));
vi.mock("@/lib/api/catalog", () => ({ searchComponents: components, searchSetups: setups }));
vi.mock("@/lib/api/corporate", () => ({ readEmployeeTechnologies: assignments }));
vi.mock("@/lib/api/technology", () => ({ readTechnologyRegistry: registry }));
vi.mock("next-intl", () => ({ useTranslations: () => (key: string) => key }));
vi.mock("@/lib/i18n/navigation", () => ({
  Link: ({ href, children, ...props }: { href: string; children: ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

import { CorporateEmployeeDetail } from "@/components/organisms/corporate-employee-detail";
import {
  applyCorporateEmployeePresentation,
  assembleCorporateEmployeePresentation,
  readCorporateEmployeeContent,
} from "@/lib/api/corporate-employee";
import type { CorporatePresentation } from "@/lib/corporate-detail";

const accountId = "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z";
const labels = {
  profile: "Public profile",
  profileEmpty: "No public profile",
  profileUnavailable: "Profile unavailable",
  noAccess: "Not available",
  authoredSetups: "Authored setups",
  noSetups: "No setups",
  setupsUnavailable: "Setups unavailable",
  authoredComponents: "Authored components",
  noComponents: "No components",
  componentsUnavailable: "Components unavailable",
  version: "Version",
  technologies: "Technologies",
  noTechnologies: "No technologies",
  technologiesUnavailable: "Technologies unavailable",
  leadStatus: "Lead status",
  notLead: "Not a lead",
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

it("keeps public profile, authored catalog, and tenant technologies as separate read states", async () => {
  profile.mockResolvedValue({
    account_id: accountId,
    display_name: "Alice",
    bio: "Bio",
    links: [],
    avatar_url: null,
  });
  components.mockResolvedValue({ items: [], experimental: [], page: { next_cursor: null } });
  setups.mockRejectedValue(
    new ApiError({ code: "AI_STP_UNAVAILABLE", status: 503, message: "down" }),
  );
  assignments.mockResolvedValue({
    items: [{ technology_id: "technology_1", state: "current" }],
    total: 1,
  });
  registry.mockResolvedValue({
    technologies: { items: [{ technology_id: "technology_1", name: "TypeScript" }] },
  });
  const result = await readCorporateEmployeeContent({
    sessionToken: "session",
    organizationId: "organization_1",
    accountId,
    canReadTechnologies: true,
  });
  expect(result.publicProfile.status).toBe("data");
  expect(result.components.status).toBe("empty");
  expect(result.setups.status).toBe("error");
  expect(result.technologies).toEqual({
    status: "data",
    data: [{ id: "technology_1", name: "TypeScript" }],
  });
  const merged = await assembleCorporateEmployeePresentation({
    presentation: {
      name: "Tenant Alice",
      description: "Tenant bio",
      avatar_url: null,
      links: [],
      teams: [],
      projects: [],
      technologies: [],
      leads: [],
      components: [],
    } as unknown as CorporatePresentation,
    sessionToken: "session",
    organizationId: "organization_1",
    member: { account_id: accountId, display_name: "Tenant Alice" },
    teams: [],
    projects: [],
    content: result,
    unknownName: "Unknown employee",
  });
  expect(merged).toMatchObject({ name: "Alice", description: "Bio" });
});

it("derives team-owned relations without using an account id as a display label", () => {
  const presentation = {
    teams: [],
    projects: [],
    technologies: [],
    leads: [],
    components: [],
  } as unknown as CorporatePresentation;
  const result = applyCorporateEmployeePresentation(presentation, {
    member: { account_id: accountId, display_name: null },
    teams: [
      {
        team_id: "team_1",
        name: "Mobile",
        lead_account_ids: ["account_lead"],
        members: [
          { account_id: accountId },
          { account_id: "account_lead", display_name: "Team Lead" },
        ],
      } as never,
      {
        team_id: "team_2",
        name: "Other",
        lead_account_ids: [],
        members: [],
      } as never,
    ],
    projects: [{ project_id: "project_1", name: "App" }],
    technologies: [{ id: "technology_1", name: "TypeScript" }],
    authoredComponents: [{ kind: "component", id: "component_1", name: "Lint", version: "1" }],
    unknownName: "Unknown employee",
  });
  expect(result.teams).toEqual([{ kind: "team", id: "team_1", name: "Mobile" }]);
  expect(result.projects).toEqual([{ kind: "project", id: "project_1", name: "App" }]);
  expect(result.leads).toEqual([{ kind: "employee", id: "account_lead", name: "Team Lead" }]);
  expect(result.technologies).toEqual([
    { kind: "technology", id: "technology_1", name: "TypeScript" },
  ]);
  expect(result.components).toEqual([{ kind: "component", id: "component_1", name: "Lint" }]);
  expect(result.author).toEqual({ kind: "employee", id: accountId, name: "Unknown employee" });
});

it("renders authored setups as catalog links and does not expose a fallback account label", () => {
  render(
    <CorporateEmployeeDetail
      content={{
        publicProfile: { status: "empty", data: null },
        components: { status: "data", data: [] },
        technologies: { status: "data", data: [] },
        setups: {
          status: "data",
          data: [{ kind: "setup", id: "setup_1", name: "Frontend", version: "1.0" }],
        },
      }}
      labels={labels}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Authored setups" }));
  expect(screen.getByRole("link", { name: /Frontend/ })).toHaveAttribute(
    "href",
    "/catalog/setups/setup_1",
  );
  expect(screen.queryByText(accountId)).not.toBeInTheDocument();
});

it("shows no-access and empty relation states without duplicating successful lists", () => {
  render(
    <CorporateEmployeeDetail
      content={{
        publicProfile: { status: "empty", data: null },
        components: { status: "empty", data: null },
        technologies: { status: "noaccess", data: null },
        setups: { status: "empty", data: null },
      }}
      labels={labels}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Technologies" }));
  fireEvent.click(screen.getByRole("button", { name: "Authored components" }));
  expect(screen.getByText("Not available")).toHaveAttribute("data-state", "noaccess");
  expect(screen.getByText("No components")).toHaveAttribute("data-state", "empty");
});
