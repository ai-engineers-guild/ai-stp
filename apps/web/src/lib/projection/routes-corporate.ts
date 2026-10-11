import { getTranslations } from "next-intl/server";

import { searchComponents } from "@/lib/api/catalog";
import { readCorporateContext } from "@/lib/api/corporate";
import { apiRequest } from "@/lib/api/http";
import type { CorporateTelemetryPolicyView } from "@/lib/api/generated/types.gen";
import { sessionCookieValue } from "@/lib/auth/require-session";
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
  {
    pattern: "corporate/admin/telemetry",
    resolve: async () => {
      const t = await getTranslations("technology");
      const hub = await getTranslations("hub");
      const session = (await sessionCookieValue()) ?? "";
      const context = await readCorporateContext(session);
      const title = hub("telemetry");
      if (!context) return presentPage({ title, summary: t("empty") });
      if (!context.capabilities.includes("telemetry.read"))
        return presentPage({ title, summary: t("forbidden") });
      const policy = await apiRequest<CorporateTelemetryPolicyView>(
        `/v1/corporate/organizations/${context.organization.organization_id}/telemetry/policy`,
        { sessionToken: session },
      ).catch(() => null);
      if (!policy) return presentPage({ title, summary: t("telemetryUnavailable") });
      const on = (v: boolean) => t(v ? "policyEnabled" : "policyDisabled");
      return presentPage({
        title,
        fields: [
          [t("heartbeatCardTitle"), on(policy.heartbeat_enabled)],
          [t("heartbeatInterval"), `${policy.heartbeat_interval_seconds}s`],
          [t("inventoryScanReporting"), on(policy.inventory_scan_enabled)],
          [t("usageCollectionReporting"), on(policy.usage_collection_enabled)],
          [t("telemetryRawRetention"), String(policy.raw_retention_days)],
          [t("telemetryAggregateRetention"), String(policy.aggregate_retention_days)],
          [t("reportTimezone"), policy.report_timezone],
        ],
      });
    },
  },
  // ADR-0219: the machine inventory names the same destinations the rail owns.
  ...(
    [
      ["corporate/organization", "/corporate"],
      ["corporate/technology-landscape", "/corporate"],
      ["corporate/technology-scans", "/corporate/technology-landscape"],
      ["corporate/technology-scans/:scanId", "/corporate/technology-scans"],
      ["corporate/categories", "/corporate/technology-landscape"],
      ["corporate/technology-mappings", "/corporate/technology-landscape"],
      ["corporate/admin/invitations", "/corporate/admin/members"],
      ["corporate/admin/access-model", "/corporate/admin/members"],
      ["corporate/admin/audit", "/corporate/admin/members"],
      ["corporate/admin/job-titles", "/corporate/admin/members"],
      ["corporate/admin/tech-categories", "/corporate/admin/members"],
      ["corporate/admin/technology-areas", "/corporate/admin/members"],
      ["corporate/admin/settings", "/corporate/admin/members"],
      ["corporate/admin/security", "/corporate/admin/members"],
      ["corporate/admin/telemetry", "/corporate/admin/members"],
      ["corporate/admin/employee-access", "/corporate/admin/members"],
      ["corporate/admin/employee-access/:accountId", "/corporate/admin/members"],
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
