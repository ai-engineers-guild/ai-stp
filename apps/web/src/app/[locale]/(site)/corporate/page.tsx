import { getTranslations, setRequestLocale } from "next-intl/server";
import { readCorporateOverview, readCorporateDirectoryPages } from "@/lib/api/corporate";
import { ApiError } from "@/lib/api/errors";
import { CorporateOverviewTree } from "@/components/organisms/corporate-overview-tree";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { Link } from "@/lib/i18n/navigation";
import { StatePanel } from "@/components/molecules/state-panel";
import { Icon, type IconName } from "@/theme";
import { overviewUsage, nodeTechnologies } from "@/lib/corporate-overview";
import { readCorporateCatalogOwnershipSummary } from "@/lib/api/corporate-catalog-ownership";
import { searchComponents, searchSetups } from "@/lib/api/catalog";
import { asComponentId, asSetupId, asVersionId } from "@/lib/brands";

export async function CorporateOverview({
  params,
  returnTo,
}: {
  params: Promise<{ locale: string }>;
  returnTo?: string;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  await requireSession(locale, returnTo ?? `/${locale}/corporate`);
  const t = await getTranslations("hub");
  const common = await getTranslations("common");
  let graph: Awaited<ReturnType<typeof readCorporateOverview>>;
  try {
    graph = await readCorporateOverview((await sessionCookieValue()) ?? "");
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    return (
      <StatePanel
        kind="error"
        title={common("error")}
        description={t(
          error.status === 403 || error.status === 401 ? "overviewDenied" : "overviewFailed",
        )}
      />
    );
  }
  if (!graph) return <StatePanel kind="empty" title={t("organization")} description={t("empty")} />;
  const token = (await sessionCookieValue()) ?? "";
  try {
    graph = await enrichOverview(graph, token);
  } catch (error) {
    // The graph is the required read. Descriptions and ownership are optional
    // enrichments, so a transient catalog/rate-limit error must not blank the
    // whole Overview.
    if (!(error instanceof ApiError)) throw error;
  }
  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <h1 className="text-3xl font-medium tracking-tight sm:text-4xl">
          {graph.organization.display_name}
        </h1>
        <p className="text-muted-foreground">{t("overviewBody")}</p>
      </header>
      <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[
          {
            key: "teams",
            href: "/corporate/teams",
            icon: "team",
            count: graph.nodes.filter((node) => node.kind === "team").length,
            caption: t("teamsSummary"),
          },
          {
            key: "projects",
            href: "/corporate/projects",
            icon: "component",
            count: graph.nodes.filter((node) => node.kind === "project").length,
            caption: t("projectsSummary"),
          },
          {
            key: "employees",
            href: "/corporate/employees",
            icon: "user",
            count: graph.nodes.filter((node) => node.kind === "employee").length,
            caption: t("acrossTeams"),
          },
          {
            key: "technologies",
            href: "/corporate/technologies",
            icon: "technology",
            count: new Set(
              graph.nodes.flatMap((node) => nodeTechnologies(node).map((item) => item.id)),
            ).size,
            caption: t("acrossProjects"),
          },
        ].map((item) => (
          <li key={item.key}>
            <Link
              href={item.href}
              className="border-border bg-card hover:bg-muted focus-visible:ring-ring flex min-h-28 items-center gap-4 rounded-lg border p-5 font-medium focus-visible:ring-2"
            >
              <span className="bg-muted grid size-12 shrink-0 place-items-center rounded-md">
                <Icon name={item.icon as IconName} />
              </span>
              <span className="min-w-0 flex-1">
                <span className="text-muted-foreground block text-sm font-normal">
                  {t(item.key)}
                </span>
                <span className="mt-1 block text-3xl tabular-nums">{item.count}</span>
                <span className="text-muted-foreground mt-1 block text-xs font-normal">
                  {item.caption}
                </span>
              </span>
              <Icon name="chevronRight" size="sm" />
            </Link>
          </li>
        ))}
      </ul>
      <CorporateOverviewTree graph={graph} />
    </div>
  );
}

export default CorporateOverview;
async function enrichOverview(
  graph: NonNullable<Awaited<ReturnType<typeof readCorporateOverview>>>,
  token: string,
) {
  const organizationId = graph.organization.organization_id;
  const directories = await Promise.all(
    (["projects", "teams", "members"] as const).map(async (resource) => {
      try {
        return (await readCorporateDirectoryPages(token, organizationId, { resource })).items;
      } catch (error) {
        if (error instanceof ApiError && [401, 403].includes(error.status)) return [];
        throw error;
      }
    }),
  );
  const descriptions = new Map(directories.flat().map((item) => [item.id, item]));
  const directoryNames = new Map(
    directories
      .flat()
      .map((item) => [item.id, item.name] as const)
      .filter((item) => item[1]),
  );
  const directoryGraph = {
    ...graph,
    nodes: graph.nodes.map((node) => {
      const detail = descriptions.get(node.id);
      return detail
        ? {
            ...node,
            description: detail.description,
            technologies: detail.technologies,
            role: detail.role,
            lead_account_ids: node.lead_account_ids.length
              ? node.lead_account_ids
              : detail.leads.map((lead) => lead.id),
          }
        : node;
    }),
  };
  try {
    const usage = overviewUsage(directoryGraph);
    const [componentCatalog, componentCatalogSecondPage, setupCatalog] = await Promise.all([
      searchComponents({
        sessionToken: token,
        organization_id: organizationId,
        page_size: 100,
        include_experimental: true,
        page: 1,
      }),
      searchComponents({
        sessionToken: token,
        organization_id: organizationId,
        page_size: 100,
        include_experimental: true,
        page: 2,
      }),
      searchSetups({
        sessionToken: token,
        organization_id: organizationId,
        page_size: 100,
        include_experimental: true,
      }),
    ]);
    const catalogDetails = new Map(
      [
        ...componentCatalog.items,
        ...componentCatalog.experimental,
        ...componentCatalogSecondPage.items,
        ...componentCatalogSecondPage.experimental,
        ...setupCatalog.items,
        ...setupCatalog.experimental,
      ].map((item) => [
        `${"stable_id" in item ? item.stable_id : ""}:${"latest_version" in item ? item.latest_version : ""}`,
        item,
      ]),
    );
    const catalog = new Map(
      (
        await Promise.all(
          usage.map(async ({ assignment }) => {
            // A `latest` selector carries no stored version; the ownership
            // read below needs an exact coordinate, so those rows enrich nothing.
            if (assignment.version === null) return null;
            const version = asVersionId(assignment.version);
            const stableId =
              assignment.object_kind === "component"
                ? asComponentId(assignment.stable_id)
                : asSetupId(assignment.stable_id);
            const ownership = await readCorporateCatalogOwnershipSummary(
              token,
              organizationId,
              assignment.object_kind,
              stableId,
              version,
            ).catch((error: unknown) => {
              if (error instanceof ApiError && error.status >= 400) return null;
              throw error;
            });
            const detail = catalogDetails.get(`${assignment.stable_id}:${assignment.version}`);
            const publisherId =
              detail && "publisher_id" in detail && typeof detail.publisher_id === "string"
                ? detail.publisher_id
                : null;
            const authorName =
              (publisherId && directoryNames.get(publisherId)) ||
              (detail && "owner_handle" in detail && typeof detail.owner_handle === "string"
                ? detail.owner_handle || null
                : publisherId && !publisherId.startsWith("account_")
                  ? publisherId
                  : null);
            return [
              `${assignment.object_kind}:${assignment.stable_id}`,
              {
                owner_name: ownership?.owner_display_name ?? null,
                owner_id: ownership?.owner_display_name ? ownership.owner_account_id : null,
                owner_readable: ownership !== null,
                author_name: authorName,
                author_id: publisherId,
                catalog_type:
                  detail &&
                  "latest_component_type" in detail &&
                  typeof detail.latest_component_type === "string"
                    ? detail.latest_component_type
                    : assignment.object_kind,
                description:
                  detail &&
                  "latest_description" in detail &&
                  typeof detail.latest_description === "string"
                    ? detail.latest_description
                    : "",
              },
            ] as const;
          }),
        )
      ).filter((entry): entry is NonNullable<typeof entry> => entry !== null),
    );
    return {
      ...directoryGraph,
      nodes: directoryGraph.nodes.map((node) => ({
        ...node,
        assignments: node.assignments.map((assignment) => ({
          ...assignment,
          ...catalog.get(`${assignment.object_kind}:${assignment.stable_id}`),
        })),
      })),
    };
  } catch (error) {
    if (error instanceof ApiError) return directoryGraph;
    throw error;
  }
}
