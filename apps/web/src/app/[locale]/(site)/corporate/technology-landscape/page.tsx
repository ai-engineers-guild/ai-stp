import { getTranslations, setRequestLocale } from "next-intl/server";
import { StatePanel } from "@/components/molecules/state-panel";
import { TechnologyLandscapeResults } from "@/components/organisms/technology-landscape-results";
import { TechnologyLandscapeFilters } from "@/components/organisms/technology-landscape-filters";
import { TechnologyScanLaunch } from "@/components/organisms/technology-scan-launch";
import { readCorporateContext } from "@/lib/api/corporate";
import { ApiError } from "@/lib/api/errors";
import { privateApiRequest } from "@/lib/api/http";
import {
  landscapeFilters,
  readTechnologyCapabilities,
  readTechnologyLandscape,
} from "@/lib/api/technology";
import { readTechnologyScanJournal } from "@/lib/api/technology-scans";
import type {
  AreaList,
  CategoryList,
  CategoryView,
  TechnologyLandscapeView,
  TechnologyScanListEntry,
} from "@/lib/api/generated/types.gen";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";
import { Icon, type IconName } from "@/theme";

export default async function TechnologyLandscapePage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/technology-landscape`);
  const session = (await sessionCookieValue()) ?? "",
    t = await getTranslations("technology"),
    w = await getTranslations("technology.workspace");
  const filters: Record<string, string | string[]> = {
    view: "grouped",
    include_proposed: "true",
    ...landscapeFilters(await searchParams),
    limit: "256",
  };
  let context;
  let organizationId = "";
  let permissions;
  let categories: CategoryList | null = null;
  let areas;
  let landscape;
  let journal;
  try {
    context = await readCorporateContext(session);

    if (context) {
      organizationId = context.organization.organization_id;
      permissions = await readTechnologyCapabilities(session, organizationId);
      const canRead =
        permissions.capabilities.includes("category.list") &&
        permissions.capabilities.includes("category.read");
      [categories, areas, landscape, journal] = await Promise.all([
        canRead
          ? privateApiRequest<CategoryList>(
              `/v1/corporate/organizations/${organizationId}/technology-categories`,
              { sessionToken: session },
            )
          : null,
        canRead
          ? privateApiRequest<AreaList>(
              `/v1/corporate/organizations/${organizationId}/technology-areas`,
              { sessionToken: session },
            )
          : null,
        readTechnologyLandscape(session, organizationId, filters),
        readTechnologyScanJournal(session, organizationId),
      ]);
      while (landscape.items.length < landscape.total) {
        const next = await readTechnologyLandscape(session, organizationId, {
          ...filters,
          offset: String(landscape.items.length),
        });
        if (!next.items.length) break;
        landscape.items.push(...next.items);
      }
    }
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    return (
      <StatePanel
        kind="error"
        title={w("mapTitle")}
        description={error.status === 403 ? t("forbidden") : t("unavailable")}
      />
    );
  }
  if (!context) return <StatePanel kind="empty" title={w("mapTitle")} description={t("empty")} />;
  if (!landscape || !permissions)
    return <StatePanel kind="empty" title={w("mapTitle")} description={t("empty")} />;
  const categoryItems = categories?.items ?? [];
  const metrics = landscapeMetrics(
    landscape,
    categoryItems,
    journal?.scans.items ?? [],
    filters,
    locale,
    w,
    areas?.items.filter((area) => area.state !== "archived").length,
  );
  return (
    <div className="technology-workspace technology-map-page space-y-2.5">
      <header className="space-y-1">
        <h1>{w("mapTitle")}</h1>
        <p className="text-muted-foreground text-sm">{w("mapDescription")}</p>
      </header>
      <TechnologyLandscapeFilters
        filters={filters}
        context={context}
        categories={categoryItems}
        launch={
          permissions.capabilities.includes("technology.scan_publish") ? (
            <TechnologyScanLaunch
              key="landscape-launch"
              organizationId={organizationId}
              authorizationRevision={permissions.authorization_revision}
              csrfToken={(await readCsrfToken()) ?? ""}
              projects={context.projects}
            />
          ) : undefined
        }
      />
      <div className="technology-metrics">
        {metrics.map((metric) => (
          <div key={metric.label} data-last-scan={metric.icon === "clock" || undefined}>
            <Icon name={metric.icon} size="lg" />
            <dl>
              <dt>{metric.label}</dt>
              <dd>{metric.value}</dd>
            </dl>
          </div>
        ))}
      </div>
      <TechnologyLandscapeResults
        landscape={landscape}
        filters={filters}
        categories={categoryItems}
        areas={areas?.items ?? null}
      />
    </div>
  );
}

function landscapeMetrics(
  landscape: TechnologyLandscapeView,
  categories: CategoryView[],
  journal: TechnologyScanListEntry[],
  filters: Record<string, string | string[]>,
  locale: string,
  w: (key: string) => string,
  areaCount?: number,
) {
  const selected = [filters.project_ids ?? filters.project_id ?? []].flat();
  const scans = journal.filter((item) => !selected.length || selected.includes(item.project_id));
  const latest = new Map<string, (typeof scans)[number]>();
  for (const scan of scans) {
    const key = `${scan.project_id}:${scan.scope ?? scan.repository ?? ""}`;
    if (!latest.has(key)) latest.set(key, scan);
  }
  const metrics: { icon: IconName; value: string | number; label: string }[] = [
    { icon: "technology", value: landscape.total, label: w("technologiesCount") },
    {
      icon: "cards",
      value:
        areaCount ??
        new Set(
          landscape.items.flatMap((row) =>
            row.technology.category_ids
              .map((id) => categories.find((c) => c.category_id === id)?.area_id)
              .filter(Boolean),
          ),
        ).size,
      label: w("areasCount"),
    },
    {
      icon: "folder",
      value: new Set(scans.filter((s) => s.status === "succeeded").map((s) => s.project_id)).size,
      label: w("scannedProjects"),
    },
    {
      icon: "alert",
      value: [...latest.values()].reduce((count, s) => count + s.pending, 0),
      label: w("needsReview"),
    },
    {
      icon: "clock",
      value: scans[0]
        ? new Date(scans[0].created_at).toLocaleString(locale, {
            day: "numeric",
            month: "short",
            hour: "2-digit",
            minute: "2-digit",
          })
        : w("neverScanned"),
      label: w("lastScan"),
    },
  ];
  return metrics;
}
