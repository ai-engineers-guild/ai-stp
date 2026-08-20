import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";

import { Badge } from "@/components/atoms/badge";
import { EvidenceList } from "@/components/organisms/evidence-list";
import { StartPublicationForm } from "@/components/organisms/start-publication-form";
import { StatePanel } from "@/components/molecules/state-panel";
import { ApiError } from "@/lib/api/errors";
import { readOwnerVersion } from "@/lib/api/owner";
import { readCsrfToken } from "@/lib/auth/session";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { Link } from "@/lib/i18n/navigation";

type PageProps = {
  params: Promise<{ locale: string; kind: string; stableId: string; version: string }>;
};

export default async function OwnerVersionPage({ params }: PageProps) {
  const { locale, kind, stableId, version } = await params;
  setRequestLocale(locale);
  if (kind !== "component" && kind !== "setup") {
    notFound();
  }
  const session = await requireSession(
    locale,
    `/${locale}/objects/${kind}/${stableId}/versions/${version}`,
  );
  const t = await getTranslations("objects");
  const tc = await getTranslations("common");
  const token = await sessionCookieValue();
  const csrf = await readCsrfToken();

  let detail;
  try {
    detail = await readOwnerVersion(token ?? "", kind, stableId, version);
  } catch (error) {
    if (error instanceof ApiError && (error.status === 404 || error.status === 403)) {
      return <StatePanel kind="error" title={tc("notFound")} description={t("notFound")} />;
    }
    if (error instanceof ApiError && error.code === "AI_STP_UNAVAILABLE") {
      return <StatePanel kind="error" title={tc("error")} description={tc("apiUnavailable")} />;
    }
    throw error;
  }

  return (
    <div className="space-y-8">
      <div className="space-y-2">
        <p className="text-muted-foreground font-mono text-xs tracking-wide uppercase">
          {detail.object_kind} · {detail.version}
        </p>
        <h1 className="text-3xl font-medium tracking-tight">{detail.name}</h1>
        <p className="text-muted-foreground font-mono text-xs">{detail.stable_id}</p>
      </div>

      <dl className="bg-muted/40 border-border grid gap-3 rounded-lg border p-4 sm:grid-cols-2">
        <div>
          <dt className="text-muted-foreground font-mono text-xs">{t("lifecycle")}</dt>
          <dd className="font-mono text-sm">{detail.lifecycle_state}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground font-mono text-xs">{t("visibility")}</dt>
          <dd className="font-mono text-sm">{detail.visibility}</dd>
        </div>
        <div className="sm:col-span-2">
          <dt className="text-muted-foreground font-mono text-xs">{t("digest")}</dt>
          <dd className="font-mono text-xs break-all">{detail.content_digest ?? "—"}</dd>
        </div>
      </dl>

      <div className="flex flex-wrap gap-2">
        <Badge variant={detail.author_verified ? "default" : "outline"}>
          {t("authorVerified")}: {detail.author_verified ? tc("yes") : tc("no")}
        </Badge>
        <Badge variant={detail.component_verified ? "default" : "secondary"}>
          {t("componentVerified")}: {detail.component_verified ? tc("yes") : tc("no")}
        </Badge>
        <Badge variant={detail.install_eligible ? "default" : "secondary"}>
          {detail.install_eligible ? t("installEligible") : t("installBlocked")}
        </Badge>
      </div>

      <p className="text-muted-foreground max-w-2xl text-sm">{t("eligibilityNote")}</p>

      <EvidenceList
        items={detail.evidence}
        labels={{
          title: t("evidence"),
          empty: t("evidenceEmpty"),
          check: t("check"),
          result: t("result"),
          source: t("source"),
          expires: t("expires"),
        }}
      />

      {detail.open_publication_plan_id ? (
        <Link
          href={`/publications/${detail.open_publication_plan_id}`}
          className="text-primary text-sm font-medium underline-offset-4 hover:underline"
          prefetch={false}
        >
          {t("openPlan")}
        </Link>
      ) : null}

      {detail.can_start_publication && csrf && session.deviceId ? (
        <StartPublicationForm
          objectKind={detail.object_kind}
          stableId={detail.stable_id}
          version={detail.version}
          deviceId={session.deviceId}
          csrfToken={csrf}
          labels={{
            start: t("startPublication"),
            starting: t("startingPublication"),
          }}
        />
      ) : null}

      <Link
        href={`/reports?object_kind=${detail.object_kind}&stable_id=${detail.stable_id}&version=${detail.version}&digest=${encodeURIComponent(detail.content_digest ?? "")}`}
        className="text-muted-foreground text-sm underline-offset-4 hover:underline"
        prefetch={false}
      >
        {t("reportVersion")}
      </Link>
    </div>
  );
}
