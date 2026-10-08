import { getTranslations, setRequestLocale } from "next-intl/server";

import { Button } from "@/components/atoms/button";
import { HistoryBackButton } from "@/components/molecules/history-back-button";
import { StatePanel } from "@/components/molecules/state-panel";
import { TechnologyLandscapeResults } from "@/components/organisms/technology-landscape-results";
import { TechnologyLandscapeFilters } from "@/components/organisms/technology-landscape-filters";
import { readCorporateContext } from "@/lib/api/corporate";
import { ApiError } from "@/lib/api/errors";
import { privateApiRequest } from "@/lib/api/http";
import {
  landscapeFilters,
  landscapeSearchParams,
  readTechnologyCapabilities,
  readTechnologyLandscape,
} from "@/lib/api/technology";
import type { AreaList, CategoryList } from "@/lib/api/generated/types.gen";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { Link } from "@/lib/i18n/navigation";

type Props = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export default async function TechnologyLandscapePage({ params, searchParams }: Props) {
  const { locale } = await params;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/technology-landscape`);
  const session = (await sessionCookieValue()) ?? "";
  const t = await getTranslations("technology");
  const workspace = await readCorporateContext(session);
  if (!workspace) return <StatePanel kind="empty" title={t("title")} description={t("empty")} />;
  const filters = landscapeFilters(await searchParams);
  const organizationId = workspace.organization.organization_id;
  const permissions = await readTechnologyCapabilities(session, organizationId).catch(() => null);
  const canReadDirectories = Boolean(
    permissions?.capabilities.includes("category.list") &&
    permissions.capabilities.includes("category.read"),
  );
  const [categories, areas] = await Promise.all([
    canReadDirectories
      ? privateApiRequest<CategoryList>(
          `/v1/corporate/organizations/${organizationId}/technology-categories`,
          { sessionToken: session },
        ).catch(() => null)
      : null,
    canReadDirectories
      ? privateApiRequest<AreaList>(
          `/v1/corporate/organizations/${organizationId}/technology-areas`,
          { sessionToken: session },
        ).catch(() => null)
      : null,
  ]);
  let landscape;
  let failure: string | null = null;
  try {
    landscape = await readTechnologyLandscape(session, organizationId, filters);
  } catch (error) {
    failure =
      error instanceof ApiError && error.code === "AI_STP_FORBIDDEN"
        ? t("forbidden")
        : t("unavailable");
  }
  const offset = landscape?.filters.offset ?? 0;
  const limit = landscape?.filters.limit ?? 128;
  return (
    <div className="min-w-0 space-y-8">
      <header className="space-y-3">
        <HistoryBackButton label={t("backToWorkspace")} fallback="/corporate/overview" />
        <h1 className="text-3xl font-medium tracking-tight sm:text-4xl">{t("title")}</h1>
        <p className="text-muted-foreground max-w-prose">{t("description")}</p>
      </header>
      <TechnologyLandscapeFilters filters={filters} context={workspace} />
      {failure && <StatePanel kind="error" title={t("title")} description={failure} />}
      {landscape && (
        <>
          {landscape.total === 0 ? (
            <StatePanel kind="empty" title={t("title")} description={t("empty")} />
          ) : (
            <TechnologyLandscapeResults
              landscape={landscape}
              filters={filters}
              categories={categories?.items ?? null}
              areas={areas?.items ?? null}
            />
          )}
          <nav aria-label={t("title")} className="flex flex-wrap gap-3">
            {offset > 0 && (
              <PageLink
                filters={filters}
                offset={Math.max(0, offset - limit)}
                label={t("previous")}
              />
            )}
            {offset + limit < landscape.total && (
              <PageLink filters={filters} offset={offset + limit} label={t("next")} />
            )}
          </nav>
        </>
      )}
    </div>
  );
}

function PageLink({
  filters,
  offset,
  label,
}: {
  filters: Record<string, string | string[]>;
  offset: number;
  label: string;
}) {
  const query = new URLSearchParams(landscapeSearchParams(filters));
  query.set("offset", String(offset));
  return (
    <Button asChild variant="outline" size="lg">
      <Link href={`/corporate/technology-landscape?${query}`}>{label}</Link>
    </Button>
  );
}
