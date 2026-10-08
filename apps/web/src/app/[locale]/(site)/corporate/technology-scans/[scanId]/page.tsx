import { getTranslations, setRequestLocale } from "next-intl/server";

import { Badge } from "@/components/atoms/badge";
import { HistoryBackButton } from "@/components/molecules/history-back-button";
import { StatePanel } from "@/components/molecules/state-panel";
import { TechnologyScanFindings } from "@/components/organisms/technology-scan-findings";
import { readCorporateContext } from "@/lib/api/corporate";
import { ApiError } from "@/lib/api/errors";
import { privateApiRequest } from "@/lib/api/http";
import { readTechnologyScanDetail } from "@/lib/api/technology-scans";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";
import { Link } from "@/lib/i18n/navigation";
import type { AreaList, TechnologyScanDetail } from "@/lib/api/generated/types.gen";

type Props = {
  params: Promise<{ locale: string; scanId: string }>;
};

export default async function TechnologyScanPage({ params }: Props) {
  const { locale, scanId } = await params;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/technology-scans/${scanId}`);
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
  let detail;
  try {
    detail = await readTechnologyScanDetail(session, organizationId, scanId);
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
  if (!detail)
    return <StatePanel kind="empty" title={scans("title")} description={t("notPermitted")} />;
  const areas =
    detail.permissions.capabilities.includes("category.list") &&
    detail.permissions.capabilities.includes("category.read")
      ? await privateApiRequest<AreaList>(
          `/v1/corporate/organizations/${organizationId}/technology-areas`,
          { sessionToken: session },
        ).catch(() => null)
      : null;
  const { scan } = detail;
  return (
    <div className="min-w-0 space-y-8">
      <ScanHeader scan={scan} locale={locale} />
      {scan.findings.length ? (
        <TechnologyScanFindings
          organizationId={organizationId}
          authorizationRevision={detail.permissions.authorization_revision}
          csrfToken={(await readCsrfToken()) ?? ""}
          findings={scan.findings}
          technologies={detail.technologies?.items ?? []}
          categories={detail.categories?.items ?? null}
          areas={areas?.items ?? null}
          baseVersion={detail.mappings.items.at(-1)?.version ?? null}
          canUpdate={detail.permissions.capabilities.includes("technology.update")}
        />
      ) : (
        <StatePanel kind="empty" title={scans("findings")} description={scans("empty")} />
      )}
    </div>
  );
}

async function ScanHeader({ scan, locale }: { scan: TechnologyScanDetail; locale: string }) {
  const scans = await getTranslations("technology.scans");
  const columns = await getTranslations("technology.scans.columns");
  const meta = [
    ["repository", scan.repository],
    ["branch", scan.branch],
    ["commit", scan.commit?.slice(0, 12) ?? null],
  ] as const;
  return (
    <header className="space-y-3">
      <HistoryBackButton label={scans("title")} fallback="/corporate/technology-scans" />
      <h1 className="font-mono text-2xl font-medium tracking-tight break-all sm:text-3xl">
        {scan.scan_id}
      </h1>
      <dl className="text-muted-foreground flex max-w-prose flex-wrap gap-x-6 gap-y-1 text-sm">
        <div className="flex gap-2">
          <dt>{columns("project")}</dt>
          <dd>
            <Link
              href={`/corporate/projects/${scan.project_id}`}
              className="text-foreground underline underline-offset-4"
            >
              {scan.project_name ?? scan.project_id}
            </Link>
          </dd>
        </div>
        <div className="flex gap-2">
          <dt>{columns("source")}</dt>
          <dd>{scans(`source.${scan.source}`)}</dd>
        </div>
        {meta.map(([key, value]) =>
          value === null ? null : (
            <div key={key} className="flex gap-2">
              <dt>{columns(key)}</dt>
              <dd className="font-mono text-xs break-all">{value}</dd>
            </div>
          ),
        )}
        <div className="flex gap-2">
          <dt>{columns("date")}</dt>
          <dd className="tabular-nums">{new Date(scan.created_at).toLocaleString(locale)}</dd>
        </div>
      </dl>
      <div className="flex flex-wrap gap-2">
        <Badge variant={scan.status === "failed" ? "warning" : "secondary"}>
          {scans(`status.${scan.status}`)}
        </Badge>
        <Badge variant="outline">{scans("foundCount", { count: scan.found })}</Badge>
        <Badge variant="outline">{scans("pendingCount", { count: scan.pending })}</Badge>
        {scan.detector_version && (
          <Badge variant="outline">
            {scans("detectorVersion", { version: scan.detector_version })}
          </Badge>
        )}
        {scan.mapping_version && (
          <Badge variant="outline">
            {scans("mappingVersion", { version: scan.mapping_version })}
          </Badge>
        )}
      </div>
      {scan.pending > 0 && (
        <p className="text-sm">
          <Link
            href={`/corporate/technology-mappings?scan_id=${scan.scan_id}`}
            className="inline-flex min-h-11 items-center underline underline-offset-4"
          >
            {scans("openInMapping", { count: scan.pending })}
          </Link>
        </p>
      )}
    </header>
  );
}
