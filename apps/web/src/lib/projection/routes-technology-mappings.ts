import { getTranslations } from "next-intl/server";

import { readCorporateContext } from "@/lib/api/corporate";
import { ApiError } from "@/lib/api/errors";
import { readTechnologyMappingReview } from "@/lib/api/technology";
import { sessionCookieValue } from "@/lib/auth/require-session";
import { presentPage } from "@/lib/projection/presenters";
import type { MachineRoute } from "@/lib/projection/route-table";

export const TECHNOLOGY_MAPPING_ROUTES: MachineRoute[] = [
  {
    pattern: "corporate/technology-mappings",
    resolve: async () => {
      const t = await getTranslations("technology");
      const session = (await sessionCookieValue()) ?? "";
      const workspace = await readCorporateContext(session);
      const links = [[t("backToWorkspace"), "/corporate"]] as const;
      if (!workspace)
        return presentPage({ title: t("mappingTitle"), summary: t("notPermitted"), links });
      try {
        const review = await readTechnologyMappingReview(
          session,
          workspace.organization.organization_id,
        );
        if (!review)
          return presentPage({ title: t("mappingTitle"), summary: t("notPermitted"), links });
        const names = new Map(
          review.technologies.items.map((item) => [item.technology_id, item.name]),
        );
        return presentPage({
          title: t("mappingTitle"),
          summary: t("mappingDescription"),
          links,
          sections: [
            {
              heading: t("mappingQueue"),
              entries: review.unmapped.coordinates.map((entry) => ({
                title: `${entry.kind}: ${entry.coordinate}`,
                fields: [
                  [t("mappingState.open"), entry.state],
                  [
                    t("mappingCandidate"),
                    (entry.candidate_technology_id && names.get(entry.candidate_technology_id)) ??
                      "",
                  ],
                  [
                    t("mappingResolved"),
                    (entry.resolved_technology_id && names.get(entry.resolved_technology_id)) ?? "",
                  ],
                ],
              })),
            },
            {
              heading: t("mappingVersions"),
              entries: review.mappings.items.map((item) => ({
                title: item.version,
                href: `/corporate/technology-mappings?version=${encodeURIComponent(item.version)}`,
                fields: [["digest", item.digest]],
              })),
            },
          ],
          emptyMessage: t("mappingQueueEmpty"),
        });
      } catch (error) {
        if (error instanceof ApiError) {
          return presentPage({
            title: t("mappingTitle"),
            links,
            summary: error.status === 403 ? t("forbidden") : t("unavailable"),
          });
        }
        throw error;
      }
    },
  },
];
