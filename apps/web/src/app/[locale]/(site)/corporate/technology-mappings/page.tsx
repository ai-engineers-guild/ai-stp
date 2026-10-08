import { getTranslations, setRequestLocale } from "next-intl/server";

import { Badge } from "@/components/atoms/badge";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import { HistoryBackButton } from "@/components/molecules/history-back-button";
import { StatePanel } from "@/components/molecules/state-panel";
import { TechnologyMappingReview } from "@/components/organisms/technology-mapping-review";
import { readCorporateContext } from "@/lib/api/corporate";
import { ApiError } from "@/lib/api/errors";
import { readTechnologyMappingReview, readTechnologyMappingVersion } from "@/lib/api/technology";
import { readTechnologyScanJournal } from "@/lib/api/technology-scans";
import type { TechnologyMappingList, TechnologyMappingView } from "@/lib/api/generated/types.gen";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";
import { Link } from "@/lib/i18n/navigation";

type Props = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export default async function TechnologyMappingsPage({ params, searchParams }: Props) {
  const { locale } = await params;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/technology-mappings`);
  const session = (await sessionCookieValue()) ?? "";
  const t = await getTranslations("technology");
  const h = await getTranslations("hub");
  const workspace = await readCorporateContext(session);
  if (!workspace)
    return <StatePanel kind="empty" title={t("mappingTitle")} description={h("empty")} />;
  const organizationId = workspace.organization.organization_id;
  const search = await searchParams;
  const query = search.query;
  const filterProject = typeof search.project_id === "string" ? search.project_id : "";
  const filterScan = typeof search.scan_id === "string" ? search.scan_id : "";
  let review;
  try {
    review = await readTechnologyMappingReview(session, organizationId, {
      ...(filterProject ? { project_id: filterProject } : {}),
      ...(filterScan ? { scan_id: filterScan } : {}),
    });
  } catch (error) {
    if (error instanceof ApiError) {
      return (
        <StatePanel
          kind="error"
          title={t("mappingTitle")}
          description={error.status === 403 ? t("forbidden") : t("unavailable")}
        />
      );
    }
    throw error;
  }
  if (!review)
    return <StatePanel kind="empty" title={t("mappingTitle")} description={t("notPermitted")} />;
  const scans = review.permissions.capabilities.includes("landscape.read")
    ? await readTechnologyScanJournal(session, organizationId).catch(() => null)
    : null;
  const rawVersion = search.version;
  const requestedVersion = typeof rawVersion === "string" ? rawVersion : "";
  const filter = typeof query === "string" ? query.toLocaleLowerCase() : "";
  const entries = review.unmapped.coordinates.filter(
    (entry) =>
      !filter ||
      entry.coordinate.toLocaleLowerCase().includes(filter) ||
      entry.kind.includes(filter),
  );
  const selected = requestedVersion
    ? await readTechnologyMappingVersion(session, organizationId, requestedVersion)
    : null;
  const technologyNames = new Map(
    review.technologies.items.map((item) => [item.technology_id, item.name]),
  );
  return (
    <div className="min-w-0 space-y-8">
      <header className="space-y-3">
        <HistoryBackButton label={t("backToWorkspace")} fallback="/corporate/overview" />
        <h1 className="text-3xl font-medium tracking-tight sm:text-4xl">{t("mappingTitle")}</h1>
        <p className="text-muted-foreground max-w-prose">{t("mappingDescription")}</p>
      </header>
      <form method="get" className="flex max-w-4xl flex-wrap items-end gap-3">
        <div className="min-w-56 flex-1 space-y-2">
          <Label htmlFor="mapping-query">{t("mappingSearch")}</Label>
          <Input
            id="mapping-query"
            name="query"
            defaultValue={typeof query === "string" ? query : ""}
          />
        </div>
        <div className="min-w-56 space-y-2">
          <Label htmlFor="mapping-project">{t("project")}</Label>
          <select
            id="mapping-project"
            name="project_id"
            defaultValue={filterProject}
            className="border-input bg-background text-foreground focus-visible:ring-ring h-11 w-full rounded-sm border px-3 text-sm focus-visible:ring-2"
          >
            <option value="">{t("all")}</option>
            {workspace.projects.map((project) => (
              <option key={project.project_id} value={project.project_id}>
                {project.name}
              </option>
            ))}
          </select>
        </div>
        {scans && (
          <div className="min-w-56 space-y-2">
            <Label htmlFor="mapping-scan">{t("scans.title")}</Label>
            <select
              id="mapping-scan"
              name="scan_id"
              defaultValue={filterScan}
              className="border-input bg-background text-foreground focus-visible:ring-ring h-11 w-full rounded-sm border px-3 text-sm focus-visible:ring-2"
            >
              <option value="">{t("all")}</option>
              {scans.scans.items.map((scan) => (
                <option key={scan.scan_id} value={scan.scan_id}>
                  {scan.scan_id}
                  {scan.project_name ? ` — ${scan.project_name}` : ""}
                </option>
              ))}
            </select>
          </div>
        )}
        <Button type="submit">{t("apply")}</Button>
      </form>
      <TechnologyMappingReview
        organizationId={organizationId}
        authorizationRevision={review.permissions.authorization_revision}
        csrfToken={(await readCsrfToken()) ?? ""}
        entries={entries}
        technologies={review.technologies.items}
        categories={review.categories?.items ?? null}
        baseVersion={review.mappings.items.at(-1)?.version ?? null}
        canUpdate={review.permissions.capabilities.includes("technology.update")}
      />
      <MappingVersions
        mappings={review.mappings.items}
        selected={selected}
        requestedVersion={requestedVersion}
        technologyNames={technologyNames}
      />
    </div>
  );
}

async function MappingVersions({
  mappings,
  selected,
  requestedVersion,
  technologyNames,
}: {
  mappings: TechnologyMappingList["items"];
  selected: TechnologyMappingView | null;
  requestedVersion: string;
  technologyNames: Map<string, string>;
}) {
  const t = await getTranslations("technology");
  return (
    <section className="space-y-3">
      <h2 className="text-xl font-medium">{t("mappingVersions")}</h2>
      <p className="text-muted-foreground max-w-prose text-sm">{t("mappingVersionsDescription")}</p>
      {mappings.length ? (
        <ul className="divide-border divide-y">
          {mappings.map((item) => (
            <li key={item.version} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 py-3">
              <Link
                href={`/corporate/technology-mappings?version=${encodeURIComponent(item.version)}`}
                className="inline-flex min-h-11 items-center font-medium underline underline-offset-4"
              >
                {item.version}
              </Link>
              <span className="text-muted-foreground font-mono text-xs">
                {item.digest.slice(0, 19)}
              </span>
              <Badge variant="outline">{t("mappingEntries", { count: item.entries })}</Badge>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-muted-foreground text-sm">{t("mappingVersionsEmpty")}</p>
      )}
      {requestedVersion !== "" && (
        <section className="border-border space-y-3 border-t pt-4">
          <h3 className="text-lg font-medium">
            {t("mappingSnapshot", { version: requestedVersion })}
          </h3>
          {selected ? (
            <ul className="divide-border divide-y">
              {selected.entries.map((entry) => (
                <li
                  key={`${entry.kind}:${entry.coordinate}`}
                  className="flex flex-wrap items-baseline gap-x-3 gap-y-1 py-2 text-sm"
                >
                  <Badge variant="outline">{entry.kind}</Badge>
                  <code className="font-mono break-all">{entry.coordinate}</code>
                  <span aria-hidden="true">→</span>
                  <Link
                    href={`/corporate/technologies/${entry.technology_id}`}
                    className="underline underline-offset-4"
                  >
                    {technologyNames.get(entry.technology_id) ?? entry.technology_id}
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-muted-foreground text-sm">{t("mappingSnapshotMissing")}</p>
          )}
        </section>
      )}
    </section>
  );
}
