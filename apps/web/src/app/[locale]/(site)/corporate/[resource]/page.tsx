import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound, permanentRedirect } from "next/navigation";
import { CorporateDirectory } from "@/components/organisms/corporate-directory";
import { StatePanel } from "@/components/molecules/state-panel";
import {
  readCorporateDirectoryPage,
  type CorporateDirectoryPageOptions,
} from "@/lib/api/corporate";
import { ApiError } from "@/lib/api/errors";
import { isCorporateTeamProjectResource } from "@/lib/api/corporate-team-project";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";
import { safeCorporateQuery } from "@/lib/corporate-routes";

export default async function CorporateDirectoryPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string; resource: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { locale, resource } = await params;
  const filters = await searchParams;
  if (resource === "members") {
    permanentRedirect(`/${locale}/corporate/employees${safeCorporateQuery(filters)}`);
  }
  const apiResource = resource === "employees" ? "members" : resource;
  if (apiResource !== "members" && !isCorporateTeamProjectResource(apiResource)) notFound();
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/${resource}`);
  const t = await getTranslations("hub");
  const c = await getTranslations("common");
  let directory;
  try {
    const session = (await sessionCookieValue()) ?? "";
    const list = (key: string) => {
      const value = filters[key];
      return (Array.isArray(value) ? value : value ? [value] : [])
        .flatMap((item) => item.split(","))
        .map((item) => item.trim())
        .filter(Boolean);
    };
    const number = (key: string, fallback: number) => {
      const value = Number(filters[key]);
      return Number.isInteger(value) && value > 0 ? value : fallback;
    };
    const directoryFilters: CorporateDirectoryPageOptions = {
      include_archived: false,
      ...(typeof filters.query === "string" ? { query: filters.query } : {}),
      lead_ids: list("lead_ids"),
      team_ids: list("team_ids"),
      technology_ids: list("technology_ids"),
      project_ids: list("project_ids"),
      category_ids: list("category_ids"),
      job_title_ids: list("job_title_ids"),
      ...(filters.is_lead === "true" ? { is_lead: true } : {}),
      sort: filters.sort === "name_desc" ? "name_desc" : "name",
      page: number("page", 1),
      pageSize: Math.min(64, number("page_size", 10)),
    };
    directory = await readCorporateDirectoryPage(session, apiResource, directoryFilters);
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    return (
      <StatePanel
        kind="error"
        title={t(apiResource === "members" ? "employees" : apiResource)}
        description={
          error.status === 403 || error.status === 401 ? c("accessDenied") : c("apiUnavailable")
        }
      />
    );
  }
  if (!directory)
    return <StatePanel kind="empty" title={t("organization")} description={t("empty")} />;
  return (
    <CorporateDirectory
      resource={apiResource}
      items={directory.items}
      organizationId={directory.context.organization.organization_id}
      authorizationRevision={directory.context.organization.authorization_revision}
      csrfToken={(await readCsrfToken()) ?? ""}
      canCreate={directory.context.capabilities.includes(
        `${apiResource === "members" ? "member" : apiResource === "teams" ? "team" : "project"}.create`,
      )}
      createHref={`/corporate/${apiResource === "members" ? "employees" : apiResource}/new`}
      roles={directory.roles?.items.map((role) => role.name) ?? []}
      initialQuery={typeof filters.query === "string" ? filters.query : ""}
      filters={safeCorporateQuery(filters).slice(1)}
      serverPaginated
      pageNumber={directory.page}
      pageSize={directory.pageSize}
      total={directory.total}
      facets={directory.facets}
      paginationLabel={t("pagination")}
    />
  );
}
