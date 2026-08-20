import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";

import { Badge } from "@/components/atoms/badge";
import { Button } from "@/components/atoms/button";
import { StatePanel } from "@/components/molecules/state-panel";
import { HistoryBackButton } from "@/components/molecules/history-back-button";
import { ExternalProductManager } from "@/components/organisms/external-product-manager";
import { listExternalProducts, type ExternalProduct } from "@/lib/api/catalog";
import { ApiError } from "@/lib/api/errors";
import { readOwnerExternalProducts, readOwnerObject } from "@/lib/api/owner";
import { readCsrfToken } from "@/lib/auth/session";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { Link } from "@/lib/i18n/navigation";
import { Icon } from "@/theme";

type PageProps = {
  params: Promise<{ locale: string; kind: string; stableId: string }>;
};

export default async function OwnerObjectDetailPage({ params }: PageProps) {
  const { locale, kind, stableId } = await params;
  setRequestLocale(locale);
  if (kind !== "component" && kind !== "setup") {
    notFound();
  }
  await requireSession(locale, `/${locale}/objects/${kind}/${stableId}`);
  const t = await getTranslations("objects");
  const tc = await getTranslations("common");
  const token = await sessionCookieValue();

  let detail;
  let allProducts: { schema_version: 1; items: ExternalProduct[] } = {
    schema_version: 1,
    items: [],
  };
  let attachedProducts: { schema_version: 1; items: ExternalProduct[] } = {
    schema_version: 1,
    items: [],
  };
  try {
    detail = await readOwnerObject(token ?? "", kind, stableId);
    if (process.env.NEXT_PUBLIC_EXTERNAL_CATALOG_ENABLED !== "false") {
      [allProducts, attachedProducts] = await Promise.all([
        listExternalProducts(),
        readOwnerExternalProducts(token ?? "", kind, stableId),
      ]);
    }
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
    <div className="space-y-6">
      <HistoryBackButton label={t("backToObjects")} fallback="/objects" />
      <div className="space-y-2">
        <p className="text-muted-foreground font-mono text-xs tracking-wide uppercase">
          {detail.object_kind}
        </p>
        <h1 className="text-3xl font-medium tracking-tight">{detail.name}</h1>
        <p className="text-muted-foreground font-mono text-xs">{detail.stable_id}</p>
        <div className="mt-3 flex flex-wrap gap-2">
          <Button asChild variant="outline">
            <Link
              href={`/catalog/${kind === "component" ? "components" : "setups"}/${stableId}`}
              prefetch={false}
            >
              <Icon name="eye" size="sm" /> {t("viewPublic")}
            </Link>
          </Button>
          {kind === "component" ? (
            <Button asChild>
              <Link href={`/objects/component/${stableId}/edit`} prefetch={false}>
                <Icon name="edit" size="sm" /> {t("editPresentation")}
              </Link>
            </Button>
          ) : null}
        </div>
      </div>

      {process.env.NEXT_PUBLIC_EXTERNAL_CATALOG_ENABLED !== "false" ? (
        <ExternalProductManager
          locale={locale}
          objectKind={kind}
          stableId={stableId}
          csrfToken={(await readCsrfToken()) ?? ""}
          initialProducts={allProducts.items}
          selectedDomains={attachedProducts.items.map((item) => item.canonical_domain)}
        />
      ) : null}

      <section className="space-y-3" aria-labelledby="versions-heading">
        <h2 id="versions-heading" className="text-lg font-medium tracking-tight">
          {t("versions")}
        </h2>
        {detail.versions.length === 0 ? (
          <StatePanel kind="empty" title={tc("empty")} description={t("noVersions")} />
        ) : (
          <ul className="divide-border border-border divide-y rounded-lg border">
            {detail.versions.map((version) => (
              <li key={version.version}>
                <Link
                  href={`/objects/${detail.object_kind}/${detail.stable_id}/versions/${version.version}`}
                  className="hover:bg-muted/40 flex flex-col gap-2 px-4 py-3 transition-colors sm:flex-row sm:items-center sm:justify-between"
                  prefetch={false}
                >
                  <div className="space-y-1">
                    <p className="font-mono text-sm font-medium">{version.version}</p>
                    {version.content_digest ? (
                      <p className="text-muted-foreground max-w-xl truncate font-mono text-xs">
                        {version.content_digest}
                      </p>
                    ) : null}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Badge variant="outline" className="font-mono text-xs">
                      {version.lifecycle_state}
                    </Badge>
                    {version.install_eligible ? (
                      <Badge>{t("installEligible")}</Badge>
                    ) : (
                      <Badge variant="secondary">{t("installBlocked")}</Badge>
                    )}
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
