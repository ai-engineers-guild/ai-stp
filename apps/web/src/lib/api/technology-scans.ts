import { privateApiRequest } from "@/lib/api/http";
import { readTechnologyCapabilities } from "./technology";

import type {
  AreaList,
  CategoryList,
  TechnologyList,
  TechnologyMappingList,
  TechnologyScanDetail,
  TechnologyScanList,
} from "./generated/types.gen";

export async function readTechnologyAreaDirectory(sessionToken: string, organizationId: string) {
  const permissions = await readTechnologyCapabilities(sessionToken, organizationId);
  if (!permissions.capabilities.includes("category.list")) return null;
  const areas = await privateApiRequest<AreaList>(
    `/v1/corporate/organizations/${organizationId}/technology-areas`,
    { sessionToken },
  );
  return { permissions, areas };
}

export async function readTechnologyScanJournal(
  sessionToken: string,
  organizationId: string,
  projectId?: string,
) {
  const permissions = await readTechnologyCapabilities(sessionToken, organizationId);
  if (!permissions.capabilities.includes("landscape.read")) return null;
  const scans = await privateApiRequest<TechnologyScanList>(
    `/v1/corporate/organizations/${organizationId}/technology-scans`,
    { sessionToken, ...(projectId ? { query: { project_id: projectId } } : {}) },
  );
  return { permissions, scans };
}

export async function readTechnologyScanDetail(
  sessionToken: string,
  organizationId: string,
  scanId: string,
) {
  const permissions = await readTechnologyCapabilities(sessionToken, organizationId);
  if (!permissions.capabilities.includes("landscape.read")) return null;
  const path = `/v1/corporate/organizations/${organizationId}`;
  const [scan, technologies, categories, mappings] = await Promise.all([
    privateApiRequest<TechnologyScanDetail>(`${path}/technology-scans/${scanId}`, {
      sessionToken,
    }),
    permissions.capabilities.includes("technology.list")
      ? privateApiRequest<TechnologyList>(`${path}/technologies`, {
          sessionToken,
          query: { limit: "256" },
        })
      : null,
    permissions.capabilities.includes("category.list") &&
    permissions.capabilities.includes("category.read")
      ? privateApiRequest<CategoryList>(`${path}/technology-categories`, { sessionToken })
      : null,
    privateApiRequest<TechnologyMappingList>(`${path}/technology-mappings`, { sessionToken }),
  ]);
  return { permissions, scan, technologies, categories, mappings };
}
