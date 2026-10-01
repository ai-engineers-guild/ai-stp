import { getTranslations } from "next-intl/server";

import { searchComponents } from "@/lib/api/catalog";
import { corporateNavPage } from "@/lib/corporate-navigation";
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
    pattern: "corporate/reports",
    resolve: async () => {
      const t = await getTranslations("corporateReports");
      return presentPage({ title: t("title"), summary: t("subtitle") });
    },
  },
  {
    pattern: "corporate/reports/heartbeat",
    resolve: async () => {
      const t = await getTranslations("corporateReports");
      return presentPage({ title: t("heartbeat"), summary: t("currentDescription") });
    },
  },
  {
    pattern: "corporate/reports/:report",
    resolve: async () => {
      const t = await getTranslations("corporateReports");
      return presentPage({ title: t("title") });
    },
  },
  ...(["corporate/installations", "corporate/usage"] as const).map((pattern): MachineRoute => ({
    pattern,
    resolve: async () => {
      const t = await getTranslations("corporateReports");
      return presentPage({ title: t("title"), links: [[t("title"), "/corporate/reports"]] });
    },
  })),
  // ADR-0219: the machine inventory names the same destinations the rail owns.
  ...(
    [
      ["corporate/organization", "/corporate"],
      ["corporate/technology-landscape", "/corporate"],
      ["corporate/categories", "/corporate/technology-landscape"],
      ["corporate/technology-mappings", "/corporate/technology-landscape"],
      ["corporate/organization/admins/access", "/corporate/organization/admins"],
      ["corporate/organization/admins/audit", "/corporate/organization/admins"],
      ["corporate/organization/admins/job-titles", "/corporate/organization/admins"],
      ["corporate/organization/admins/settings", "/corporate/organization/admins"],
      ["corporate/organization/admins/security", "/corporate/organization/admins"],
      ["corporate/organization/admins/employees", "/corporate/organization/admins"],
      ["corporate/organization/admins/employees/:accountId", "/corporate/organization/admins"],
    ] as const
  ).map(([pattern, back]): MachineRoute => {
    const page = corporateNavPage(`/${pattern.replace(/\/:.*$/, "")}`);
    const backPage = corporateNavPage(back);
    return {
      pattern,
      resolve: async () => {
        const t = await getTranslations("hub");
        return presentPage({
          title: t(page?.label ?? "navigation"),
          links: [[t(backPage?.rootLabel ?? backPage?.label ?? "navigation"), back]],
        });
      },
    };
  }),
];
