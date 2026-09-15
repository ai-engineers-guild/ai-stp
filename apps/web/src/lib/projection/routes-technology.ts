import { getTranslations } from "next-intl/server";
import { canViewCorporateSection } from "@/lib/corporate-hub";

import {
  readCorporateContext,
  readCorporateAudit,
  readCorporateMemberAccess,
} from "@/lib/api/corporate";
import { ApiError } from "@/lib/api/errors";
import {
  landscapeFilters,
  readTechnologyRegistry,
  readTechnologyDetail,
  readTechnologyLandscape,
  readCategoryDirectory,
  readCategoryDetail,
  readTechnologyCapabilities,
  readTechnologyLandscapePolicy,
} from "@/lib/api/technology";
import { sessionCookieValue } from "@/lib/auth/require-session";
import { presentPage } from "@/lib/projection/presenters";
import type { MachineRoute } from "@/lib/projection/route-table";

export const TECHNOLOGY_ROUTES: MachineRoute[] = [
  {
    pattern: "corporate/organization",
    resolve: async () => {
      const t = await getTranslations("hub");
      const context = await readCorporateContext((await sessionCookieValue()) ?? "");
      if (!context) return presentPage({ title: t("organization"), summary: t("empty") });
      return presentPage({
        title: context.organization.display_name,
        summary: t("organizationBody"),
        links: [
          { key: "employees", href: "/corporate/members" },
          { key: "projects", href: "/corporate/projects" },
          { key: "teams", href: "/corporate/teams" },
          { key: "admins", href: "/corporate/organization/admins" },
        ]
          .filter((item) => canViewCorporateSection(item.key, context.capabilities))
          .map((item): [string, string] => [t(item.key), item.href]),
      });
    },
  },
  {
    pattern: "corporate/organization/admins/members/:accountId",
    resolve: async ({ segments }) => {
      const accountId = segments.at(-1);
      if (!accountId) return null;
      const t = await getTranslations("corporate");
      const technology = await getTranslations("technology");
      const result = await readCorporateMemberAccess((await sessionCookieValue()) ?? "", accountId);
      if (
        !result?.member ||
        !result.context.capabilities.some((capability) =>
          ["member.update", "member.delete"].includes(capability),
        )
      )
        return presentPage({ title: t("accessAdministration"), summary: technology("forbidden") });
      return presentPage({
        title: t("accessAdministration"),
        fields: [
          [t("member"), result.member.display_name ?? t("member")],
          [t("organizationRole"), result.member.role],
          [t("state"), result.member.state],
        ],
        links: [[t("member"), `/corporate/members/${accountId}`]],
      });
    },
  },
  {
    pattern: "corporate/organization/admins/audit",
    resolve: async ({ searchParams }) => {
      const t = await getTranslations("corporate");
      const result = await readCorporateAudit((await sessionCookieValue()) ?? "", searchParams);
      return presentPage({
        title: t("auditJournal"),
        links: [[t("backToWorkspace"), "/corporate/organization/admins"]],
        sections: [
          {
            heading: t("auditJournal"),
            entries:
              result?.audit.items.map((item) => ({
                title:
                  item.action === "member.profile.update"
                    ? t("auditUi.profileUpdated")
                    : t("auditUi.otherEvent"),
                fields: [
                  [t("state"), t(`auditUi.outcomes.${item.outcome}`)],
                  [
                    t("member"),
                    result.members?.items.find(
                      (member) => member.account_id === item.actor_account_id,
                    )?.display_name ?? t(`auditUi.actors.${item.actor_type}`),
                  ],
                ],
              })) ?? [],
          },
        ],
        emptyMessage: t("noAudit"),
      });
    },
  },
  {
    pattern: "corporate/organization/admins/settings",
    resolve: async () => {
      const t = await getTranslations("technology");
      const session = (await sessionCookieValue()) ?? "";
      const context = await readCorporateContext(session);
      if (!context) return presentPage({ title: t("activityPolicy"), summary: t("empty") });
      const organizationId = context.organization.organization_id;
      const permissions = await readTechnologyCapabilities(session, organizationId);
      if (
        !permissions.capabilities.includes("landscape.manage") ||
        !permissions.capabilities.includes("landscape.read")
      )
        return presentPage({ title: t("activityPolicy"), summary: t("forbidden") });
      try {
        const policy = await readTechnologyLandscapePolicy(session, organizationId);
        return presentPage({
          title: t("activityPolicy"),
          fields: [[t("inactivityMonths"), String(policy.inactivity_months)]],
        });
      } catch {
        return presentPage({ title: t("activityPolicy"), summary: t("unavailable") });
      }
    },
  },
  {
    pattern: "corporate/categories",
    resolve: async ({ searchParams }) => {
      const h = await getTranslations("hub");
      const session = (await sessionCookieValue()) ?? "";
      const context = await readCorporateContext(session);
      const result = context
        ? await readCategoryDirectory(session, context.organization.organization_id)
        : null;
      const query =
        typeof searchParams.query === "string" ? searchParams.query.toLocaleLowerCase() : "";
      return presentPage({
        title: h("categories"),
        sections: [
          {
            heading: h("categories"),
            entries:
              result?.categories.items
                .filter((item) => item.name.toLocaleLowerCase().includes(query))
                .map((item) => ({
                  title: item.name,
                  href: `/corporate/categories/${item.category_id}`,
                  fields: [[h("organization"), item.description]],
                })) ?? [],
          },
        ],
        emptyMessage: h("empty"),
      });
    },
  },
  {
    pattern: "corporate/categories/:categoryId",
    resolve: async ({ segments }) => {
      const h = await getTranslations("hub");
      const session = (await sessionCookieValue()) ?? "";
      const context = await readCorporateContext(session);
      const detail = context
        ? await readCategoryDetail(session, context.organization.organization_id, segments[2] ?? "")
        : null;
      return presentPage({
        title: detail?.category.name ?? h("categories"),
        summary: detail?.category.description ?? "",
        links: [[h("backToCategories"), "/corporate/categories"]],
        sections: [
          {
            heading: h("technologies"),
            entries:
              detail?.technologies?.items.map((item) => ({
                title: item.name,
                href: `/corporate/technologies/${item.technology_id}`,
              })) ?? [],
          },
        ],
        emptyMessage: h("empty"),
      });
    },
  },
  {
    pattern: "corporate/technologies",
    resolve: async ({ searchParams }) => {
      const t = await getTranslations("technology");
      const session = (await sessionCookieValue()) ?? "";
      const workspace = await readCorporateContext(session);
      const links = [[t("backToWorkspace"), "/corporate"]] as const;
      if (!workspace)
        return presentPage({ title: t("registry"), summary: t("registryEmpty"), links });
      try {
        const registry = await readTechnologyRegistry(
          session,
          workspace.organization.organization_id,
          typeof searchParams.query === "string" ? searchParams.query : undefined,
        );
        return presentPage({
          title: t("registry"),
          summary: t("registryDescription"),
          links,
          sections: [
            {
              heading: t("registry"),
              entries:
                registry.technologies?.items.map((technology) => ({
                  title: technology.name,
                  href: `/corporate/technologies/${technology.technology_id}`,
                  fields: [
                    [t("lifecycle"), t(`values.${technology.lifecycle}`)],
                    [t("details"), technology.description],
                    [t("aliases"), technology.aliases.join(", ")],
                  ],
                })) ?? [],
            },
            {
              heading: t("categories"),
              entries:
                registry.categories?.items.map((category) => ({
                  title: category.name,
                  fields: [[t("details"), category.description]],
                })) ?? [],
            },
          ],
          emptyMessage: t("registryEmpty"),
        });
      } catch {
        return presentPage({ title: t("registry"), summary: t("registryUnavailable"), links });
      }
    },
  },
  {
    pattern: "corporate/technologies/:technologyId",
    resolve: async ({ segments }) => {
      const t = await getTranslations("technology");
      const session = (await sessionCookieValue()) ?? "";
      const workspace = await readCorporateContext(session);
      const links = [[t("backToTechnologies"), "/corporate/technologies"]] as const;
      const technologyId = segments[2];
      if (!workspace || !technologyId || !/^technology_[0-9A-HJKMNP-TV-Z]{26}$/.test(technologyId))
        return presentPage({ title: t("registry"), summary: t("notPermitted"), links });
      try {
        const detail = await readTechnologyDetail(
          session,
          workspace.organization.organization_id,
          technologyId,
        );
        if (!detail)
          return presentPage({ title: t("registry"), summary: t("notPermitted"), links });
        return presentPage({
          title: detail.technology.name,
          summary: detail.technology.description,
          links,
          fields: [
            [t("lifecycle"), t(`values.${detail.technology.lifecycle}`)],
            [t("aliases"), detail.technology.aliases.join(", ")],
            [
              t("categories"),
              detail.technology.category_ids
                .map(
                  (id) =>
                    detail.categories?.items.find((category) => category.category_id === id)
                      ?.name ?? "",
                )
                .join(", "),
            ],
            [t("officialUrls"), detail.technology.official_urls.join(", ")],
            [t("iconUrl"), detail.technology.icon_url ?? ""],
          ],
          sections: [
            ...(detail.projects?.status === "data"
              ? [
                  {
                    heading: (await getTranslations("hub"))("projects"),
                    entries: detail.projects.data.projects.map((project) => ({
                      title: project.name,
                      href: `/corporate/projects/${project.project_id}`,
                    })),
                  },
                ]
              : []),
            ...(detail.technology.redirect_id
              ? [
                  {
                    heading: t("mergedIdentity"),
                    entries: [
                      {
                        title: t("mergedIdentity"),
                        href: `/corporate/technologies/${detail.technology.redirect_id}`,
                      },
                    ],
                  },
                ]
              : []),
          ],
        });
      } catch {
        return presentPage({ title: t("registry"), summary: t("registryUnavailable"), links });
      }
    },
  },
  {
    pattern: "corporate/technology-landscape",
    resolve: async ({ searchParams }) => {
      const t = await getTranslations("technology");
      const session = (await sessionCookieValue()) ?? "";
      const workspace = await readCorporateContext(session);
      const links = [[t("backToWorkspace"), "/corporate"]] as const;
      if (!workspace) return presentPage({ title: t("title"), summary: t("empty"), links });
      const filters = landscapeFilters(searchParams);
      try {
        const landscape = await readTechnologyLandscape(
          session,
          workspace.organization.organization_id,
          filters,
        );
        return presentPage({
          title: t("title"),
          summary: t("description"),
          links,
          fields: Object.entries(filters),
          sections: landscape.items.map((row) => ({
            heading: row.technology.name,
            text: `${t("projects")}: ${row.project_count}; ${t("proposed")}: ${row.proposed_project_count}`,
            entries: row.projects.map((project) => ({
              title: project.name,
              href: `/corporate/projects/${project.project_id}?${new URLSearchParams(filters)}`,
              fields: [
                [t("activity"), project.activity],
                [t("source_availability"), project.source_availability ?? "unknown"],
                ["relation_id", project.usage.relation_id],
                [t("details"), JSON.stringify(project.usage.facts)],
              ],
            })),
          })),
          emptyMessage: t("empty"),
        });
      } catch (error) {
        return presentPage({
          title: t("title"),
          links,
          summary:
            error instanceof ApiError && error.code === "AI_STP_FORBIDDEN"
              ? t("forbidden")
              : t("unavailable"),
        });
      }
    },
  },
];
