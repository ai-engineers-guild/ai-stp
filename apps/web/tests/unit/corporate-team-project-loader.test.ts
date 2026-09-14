import { beforeEach, expect, it, vi } from "vitest";

const { readDirectory, readTeam, readProject } = vi.hoisted(() => ({
  readDirectory: vi.fn(),
  readTeam: vi.fn(),
  readProject: vi.fn(),
}));

vi.mock("@/lib/api/corporate", () => ({ readCorporateDirectory: readDirectory }));
vi.mock("@/lib/api/technology", () => ({
  readTeamProjects: readTeam,
  readProjectTechnologyDetail: readProject,
}));

import {
  isCorporateTeamProjectResource,
  readCorporateProjectRelations,
  readCorporateTeamProjectDirectory,
  readCorporateTeamRelations,
} from "@/lib/api/corporate-team-project";

beforeEach(() => vi.clearAllMocks());

it.each([
  ["teams", true],
  ["projects", true],
  ["members", false],
  ["technologies", false],
])("recognizes %s as a team/project resource: %s", (resource, expected) => {
  expect(isCorporateTeamProjectResource(resource)).toBe(expected);
});

it.each(["teams", "projects"] as const)(
  "routes %s directory reads through the shared directory loader",
  async (resource) => {
    const directory = { resource };
    readDirectory.mockResolvedValue(directory);

    await expect(readCorporateTeamProjectDirectory("session", resource)).resolves.toBe(directory);
    expect(readDirectory).toHaveBeenCalledWith("session", resource);
  },
);

it("keeps team and project relationship reads on their canonical loaders", async () => {
  const teamRelations = { relations: { items: [] } };
  const projectRelations = { project: { project_id: "remote_project_fixture" } };
  readTeam.mockResolvedValue(teamRelations);
  readProject.mockResolvedValue(projectRelations);

  await expect(
    readCorporateTeamRelations("session", "organization_fixture", "operation_fixture"),
  ).resolves.toBe(teamRelations);
  await expect(
    readCorporateProjectRelations("session", "organization_fixture", "remote_project_fixture"),
  ).resolves.toBe(projectRelations);
  expect(readTeam).toHaveBeenCalledWith("session", "organization_fixture", "operation_fixture");
  expect(readProject).toHaveBeenCalledWith(
    "session",
    "organization_fixture",
    "remote_project_fixture",
  );
});
