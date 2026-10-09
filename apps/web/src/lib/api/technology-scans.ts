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
  if (
    !permissions.capabilities.includes("area.list") ||
    !permissions.capabilities.includes("area.read")
  )
    return null;
  const areas = await privateApiRequest<AreaList>(
    `/v1/corporate/organizations/${organizationId}/technology-areas`,
    { sessionToken },
  );
  return { permissions, areas };
}

export async function readTechnologyScanJournal(
  sessionToken: string,
  organizationId: string,
  filters: {
    projectId?: string | undefined;
    createdFrom?: string | undefined;
    createdTo?: string | undefined;
  } = {},
) {
  const permissions = await readTechnologyCapabilities(sessionToken, organizationId);
  if (!permissions.capabilities.includes("landscape.read")) return null;
  const scans = await privateApiRequest<TechnologyScanList>(
    `/v1/corporate/organizations/${organizationId}/technology-scans`,
    {
      sessionToken,
      query: {
        ...(filters.projectId ? { project_id: filters.projectId } : {}),
        ...(filters.createdFrom ? { created_from: filters.createdFrom } : {}),
        ...(filters.createdTo ? { created_to: filters.createdTo } : {}),
      },
    },
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
          query: { limit: "256", include_archived: "true" },
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

export async function readTechnologyReviewWorkspace(
  sessionToken: string,
  organizationId: string,
  scanId?: string,
  scanFilters: { createdFrom?: string; createdTo?: string } = {},
) {
  const journal = await readTechnologyScanJournal(sessionToken, organizationId, {
    createdFrom: scanFilters.createdFrom,
    createdTo: scanFilters.createdTo,
  });
  if (!journal) return null;
  const path = `/v1/corporate/organizations/${organizationId}`;
  const canReadCategories =
    journal.permissions.capabilities.includes("category.list") &&
    journal.permissions.capabilities.includes("category.read");
  const canReadAreas =
    journal.permissions.capabilities.includes("area.list") &&
    journal.permissions.capabilities.includes("area.read");
  const [technologies, categories, areas, scans] = await Promise.all([
    journal.permissions.capabilities.includes("technology.list")
      ? privateApiRequest<TechnologyList>(`${path}/technologies`, {
          sessionToken,
          query: { limit: "256", include_archived: "true" },
        })
      : null,
    canReadCategories
      ? privateApiRequest<CategoryList>(`${path}/technology-categories`, { sessionToken })
      : null,
    canReadAreas ? privateApiRequest<AreaList>(`${path}/technology-areas`, { sessionToken }) : null,
    Promise.all(
      (scanId ? [{ scan_id: scanId }] : journal.scans.items).map((item) =>
        privateApiRequest<TechnologyScanDetail>(`${path}/technology-scans/${item.scan_id}`, {
          sessionToken,
        }),
      ),
    ),
  ]);
  if (technologies) {
    while (technologies.items.length < technologies.total) {
      const page = await privateApiRequest<TechnologyList>(`${path}/technologies`, {
        sessionToken,
        query: {
          offset: String(technologies.items.length),
          limit: "256",
          include_archived: "true",
        },
      });
      if (!page.items.length) break;
      technologies.items.push(...page.items);
    }
  }
  return { permissions: journal.permissions, technologies, categories, areas, scans };
}
