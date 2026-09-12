import { getTranslations, setRequestLocale } from "next-intl/server";

import { Button } from "@/components/atoms/button";
import { StatePanel } from "@/components/molecules/state-panel";
import { TechnologyLandscapeFilters } from "@/components/organisms/technology-landscape-filters";
import { readCorporateWorkspace } from "@/lib/api/corporate";
import { ApiError } from "@/lib/api/errors";
import { landscapeFilters, readTechnologyLandscape } from "@/lib/api/technology";
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
  const workspace = await readCorporateWorkspace(session);
  if (!workspace) return <StatePanel kind="empty" title={t("title")} description={t("empty")} />;
  const filters = landscapeFilters(await searchParams);
  let landscape;
  let failure: string | null = null;
  try {
    landscape = await readTechnologyLandscape(
      session,
      workspace.organization.organization_id,
      filters,
    );
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
        <Link href="/corporate" className="underline underline-offset-4">
          {t("back")}
        </Link>
        <h1 className="text-3xl font-medium tracking-tight sm:text-4xl">{t("title")}</h1>
        <p className="text-muted-foreground max-w-prose">{t("description")}</p>
      </header>
      <TechnologyLandscapeFilters filters={filters} context={workspace.context} />
      {failure && <StatePanel kind="error" title={t("title")} description={failure} />}
      {landscape && (
        <>
          {landscape.total === 0 ? (
            <StatePanel kind="empty" title={t("title")} description={t("empty")} />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <caption className="sr-only">{t("description")}</caption>
                <thead className="border-border border-b">
                  <tr>
                    <th scope="col" className="p-3 font-medium">
                      {t("technology")}
                    </th>
                    <th scope="col" className="p-3 font-medium">
                      {t("projects")}
                    </th>
                    <th scope="col" className="p-3 font-medium">
                      {t("proposed")}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {landscape.items.map((row) => (
                    <tr
                      key={row.technology.technology_id}
                      className="border-border border-b align-top"
                    >
                      <th scope="row" className="p-3 font-medium">
                        {row.technology.name}
                      </th>
                      <td className="p-3">
                        <span className="tabular-nums">{row.project_count}</span>
                        <ul className="mt-2 space-y-1">
                          {row.projects.map((project) => (
                            <li key={project.project_id}>
                              <Link
                                className="inline-flex min-h-11 items-center underline underline-offset-4"
                        href={`/corporate/projects/${project.project_id}?${new URLSearchParams(filters)}`}
                              >
                                {project.name}
                              </Link>
                            </li>
                          ))}
                        </ul>
                      </td>
                      <td className="p-3 tabular-nums">{row.proposed_project_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
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
  filters: Record<string, string>;
  offset: number;
  label: string;
}) {
  const query = new URLSearchParams({ ...filters, offset: String(offset) });
  return (
    <Button asChild variant="outline" size="lg">
      <Link href={`/corporate/technology-landscape?${query}`}>{label}</Link>
    </Button>
  );
}
