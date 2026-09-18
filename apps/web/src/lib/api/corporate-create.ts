import type { CorporateDirectoryReference } from "./generated/types.gen";
import { readCorporateContext, readCorporateDirectoryPage } from "./corporate";

export async function readCorporateCreateOptions(sessionToken: string) {
  const context = await readCorporateContext(sessionToken);
  if (!context) return null;
  const [members, technologies] = await Promise.all([
    context.capabilities.includes("member.list")
      ? readCorporateDirectoryPage(sessionToken, "members", { page: 1, pageSize: 256 })
      : Promise.resolve(null),
    context.capabilities.includes("technology.list")
      ? readCorporateDirectoryPage(sessionToken, "technologies", { page: 1, pageSize: 256 })
      : Promise.resolve(null),
  ]);
  return {
    context,
    employees: members?.items ?? [],
    teams: context.teams,
    projects: context.projects,
    technologies: technologies?.items ?? [],
    jobTitles: members?.facets.job_titles ?? [],
    roles: members?.roles?.items ?? [],
  };
}

export type CorporateCreateOption = Pick<CorporateDirectoryReference, "id" | "name">;
