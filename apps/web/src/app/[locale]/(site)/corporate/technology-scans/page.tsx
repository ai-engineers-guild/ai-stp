import { getTranslations, setRequestLocale } from "next-intl/server";

import { Badge } from "@/components/atoms/badge";
import { Button } from "@/components/atoms/button";
import { Label } from "@/components/atoms/label";
import { HistoryBackButton } from "@/components/molecules/history-back-button";
import { StatePanel } from "@/components/molecules/state-panel";
import { TechnologyScanLaunch } from "@/components/organisms/technology-scan-launch";
import { readCorporateContext } from "@/lib/api/corporate";
import { ApiError } from "@/lib/api/errors";
import { readTechnologyScanJournal } from "@/lib/api/technology-scans";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";
import { Link } from "@/lib/i18n/navigation";
import type { TechnologyScanList } from "@/lib/api/generated/types.gen";

type Props = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export default async function TechnologyScansPage({ params, searchParams }: Props) {
  const { locale } = await params;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/technology-scans`);
  const session = (await sessionCookieValue()) ?? "";
  const t = await getTranslations("technology");
  const scans = await getTranslations("technology.scans");
  const c = await getTranslations("corporate");
  const common = await getTranslations("common");
  let context;
  try {
    context = await readCorporateContext(session);
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    return (
      <StatePanel kind="error" title={scans("title")} description={common("apiUnavailable")} />
    );
  }
  if (!context)
    return <StatePanel kind="empty" title={scans("title")} description={c("noOrganization")} />;
  const organizationId = context.organization.organization_id;
  const search = await searchParams;
  const projectId = typeof search.project_id === "string" ? search.project_id : undefined;
  let journal;
  try {
    journal = await readTechnologyScanJournal(session, organizationId, projectId);
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    return (
      <StatePanel
        kind="error"
        title={scans("title")}
        description={error.status === 403 ? t("forbidden") : t("unavailable")}
      />
    );
  }
  if (!journal)
    return <StatePanel kind="empty" title={scans("title")} description={t("notPermitted")} />;
  const canLaunch = journal.permissions.capabilities.includes("technology.scan_publish");
  const projectNames = new Map(context.projects.map((project) => [project.project_id, project]));
  return (
    <div className="min-w-0 space-y-8">
      <header className="space-y-3">
        <HistoryBackButton label={t("backToWorkspace")} fallback="/corporate/overview" />
        <div className="flex flex-wrap items-center gap-4">
          <h1 className="text-3xl font-medium tracking-tight sm:text-4xl">{scans("title")}</h1>
          {canLaunch && (
            <TechnologyScanLaunch
              organizationId={organizationId}
              authorizationRevision={journal.permissions.authorization_revision}
              csrfToken={(await readCsrfToken()) ?? ""}
              projects={context.projects}
            />
          )}
        </div>
        <p className="text-muted-foreground max-w-prose">{scans("description")}</p>
      </header>
      <form method="get" className="flex max-w-xl flex-wrap items-end gap-3">
        <div className="min-w-56 flex-1 space-y-2">
          <Label htmlFor="scans-project">{t("project")}</Label>
          <select
            id="scans-project"
            name="project_id"
            defaultValue={projectId ?? ""}
            className="border-input bg-background text-foreground focus-visible:ring-ring h-11 w-full rounded-sm border px-3 text-sm focus-visible:ring-2"
          >
            <option value="">{t("all")}</option>
            {context.projects.map((project) => (
              <option key={project.project_id} value={project.project_id}>
                {project.name}
              </option>
            ))}
          </select>
        </div>
        <Button type="submit">{t("apply")}</Button>
      </form>
      {journal.scans.items.length ? (
        <ScanJournalTable items={journal.scans.items} locale={locale} projectNames={projectNames} />
      ) : (
        <StatePanel kind="empty" title={scans("title")} description={scans("empty")} />
      )}
    </div>
  );
}

async function ScanJournalTable({
  items,
  locale,
  projectNames,
}: {
  items: TechnologyScanList["items"];
  locale: string;
  projectNames: Map<string, { name: string }>;
}) {
  const scans = await getTranslations("technology.scans");
  const columns = await getTranslations("technology.scans.columns");
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <caption className="sr-only">{scans("title")}</caption>
        <thead className="border-border border-b">
          <tr>
            <th scope="col" className="p-3 font-medium">
              {columns("id")}
            </th>
            <th scope="col" className="p-3 font-medium">
              {columns("project")}
            </th>
            <th scope="col" className="p-3 font-medium">
              {columns("repository")}
            </th>
            <th scope="col" className="p-3 font-medium">
              {columns("source")}
            </th>
            <th scope="col" className="p-3 font-medium">
              {columns("date")}
            </th>
            <th scope="col" className="p-3 font-medium">
              {columns("status")}
            </th>
            <th scope="col" className="p-3 font-medium">
              {columns("found")}
            </th>
            <th scope="col" className="p-3 font-medium">
              {columns("pending")}
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((scan) => (
            <tr key={scan.scan_id} className="border-border border-b align-top">
              <th scope="row" className="p-3 font-medium">
                <Link
                  href={`/corporate/technology-scans/${scan.scan_id}`}
                  className="inline-flex min-h-11 items-center font-mono text-xs underline underline-offset-4"
                >
                  {scan.scan_id}
                </Link>
              </th>
              <td className="p-3">
                <Link
                  href={`/corporate/projects/${scan.project_id}`}
                  className="underline underline-offset-4"
                >
                  {scan.project_name ?? projectNames.get(scan.project_id)?.name ?? scan.project_id}
                </Link>
              </td>
              <td className="max-w-64 p-3">
                <span className="font-mono text-xs break-all">{scan.repository ?? "—"}</span>
              </td>
              <td className="p-3">
                <Badge variant="outline">{scans(`source.${scan.source}`)}</Badge>
              </td>
              <td className="p-3 whitespace-nowrap tabular-nums">
                {scan.created_at ? new Date(scan.created_at).toLocaleString(locale) : "—"}
              </td>
              <td className="p-3">
                <Badge
                  variant={
                    scan.status === "failed"
                      ? "warning"
                      : scan.status === "succeeded"
                        ? "secondary"
                        : "outline"
                  }
                >
                  {scans(`status.${scan.status}`)}
                </Badge>
              </td>
              <td className="p-3 tabular-nums">{scan.found}</td>
              <td className="p-3 tabular-nums">{scan.pending}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
