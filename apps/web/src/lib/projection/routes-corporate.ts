import { getTranslations } from "next-intl/server";

import { searchComponents } from "@/lib/api/catalog";
import { presentPage } from "@/lib/projection/presenters";
import type { MachineRoute } from "@/lib/projection/route-table";

export const CORPORATE_ROUTES: MachineRoute[] = [
  {
    pattern: "corporate/catalog",
    resolve: async () => {
      const t = await getTranslations("hub");
      const result = await searchComponents({ page_size: 100, include_experimental: true }).catch(
        () => null,
      );
      return presentPage({
        title: t("components"),
        links:
          result === null
            ? []
            : [...result.items, ...result.experimental].map((item) => [
                item.latest_name,
                `/catalog/components/${encodeURIComponent(item.stable_id)}`,
              ]),
      });
    },
  },
  ...(
    [
      ["corporate/employees/new", "addEmployee"],
      ["corporate/teams/new", "addTeam"],
      ["corporate/projects/new", "addProject"],
    ] as const
  ).map(([pattern, titleKey]): MachineRoute => ({
    pattern,
    resolve: async () => {
      const t = await getTranslations("hub");
      return presentPage({ title: t(titleKey), links: [[t("organization"), "/corporate"]] });
    },
  })),
  {
    pattern: "corporate/components",
    resolve: async () => {
      const t = await getTranslations("hub");
      return presentPage({
        title: t("components"),
        links: [[t("components"), "/corporate/catalog"]],
      });
    },
  },
  {
    pattern: "corporate/installations",
    resolve: async () => {
      const t = await getTranslations("installations");
      return presentPage({ title: t("title"), summary: t("unavailable") });
    },
  },
  {
    pattern: "corporate/usage",
    resolve: async () => {
      const t = await getTranslations("hub");
      return presentPage({ title: t("usage"), summary: t("usageViewBody") });
    },
  },
];
