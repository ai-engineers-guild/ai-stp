import { readCorporateDirectory } from "@/lib/api/corporate";
import { readProjectTechnologyDetail, readTeamProjects } from "@/lib/api/technology";

export const corporateTeamProjectResources = ["teams", "projects"] as const;
export type CorporateTeamProjectResource = (typeof corporateTeamProjectResources)[number];

export function isCorporateTeamProjectResource(
  resource: string,
): resource is CorporateTeamProjectResource {
  return (corporateTeamProjectResources as readonly string[]).includes(resource);
}

export function readCorporateTeamProjectDirectory(
  sessionToken: string,
  resource: CorporateTeamProjectResource,
) {
  return readCorporateDirectory(sessionToken, resource);
}

export function readCorporateTeamRelations(
  sessionToken: string,
  organizationId: string,
  teamId: string,
) {
  return readTeamProjects(sessionToken, organizationId, teamId);
}

export function readCorporateProjectRelations(
  sessionToken: string,
  organizationId: string,
  projectId: string,
) {
  return readProjectTechnologyDetail(sessionToken, organizationId, projectId);
}
