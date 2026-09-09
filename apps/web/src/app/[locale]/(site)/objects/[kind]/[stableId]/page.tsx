import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound, redirect } from "next/navigation";

import { Badge } from "@/components/atoms/badge";
import { VisibilityLabel } from "@/components/molecules/visibility-label";
import { StatePanel } from "@/components/molecules/state-panel";
import { HistoryBackButton } from "@/components/molecules/history-back-button";
import { ExternalProductManager } from "@/components/organisms/external-product-manager";
import { listExternalProducts, type ExternalProduct } from "@/lib/api/catalog";
import { ApiError } from "@/lib/api/errors";
import { readOwnerExternalProducts, readOwnerObject } from "@/lib/api/owner";
import { readCsrfToken } from "@/lib/auth/session";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { Link } from "@/lib/i18n/navigation";

type PageProps = {
  params: Promise<{ locale: string; kind: string; stableId: string }>;
};

export default async function OwnerObjectDetailPage({ params }: PageProps) {
  const { locale, kind, stableId } = await params;
  setRequestLocale(locale);
  if (kind !== "component" && kind !== "setup") {
    notFound();
  }
  if (kind === "component") {
    redirect(`/${locale}/catalog/components/${stableId}?return_to=%2Fobjects`);
  }
  await requireSession(locale, `/${locale}/objects/${kind}/${stableId}`);
  const t = await getTranslations("objects");
  const tc = await getTranslations("common");
  const tCatalog = await getTranslations("catalog");
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

  if (detail.versions[0]?.visibility === "public") {
    redirect(`/catalog/setups/${stableId}`);
  }

  return (
    <div className="space-y-6">
      <HistoryBackButton label={t("backToObjects")} fallback="/objects" />
      <div className="relative space-y-2 pr-24">
        <VisibilityLabel
          className="absolute top-0 right-0"
          visibility={detail.versions[0]?.visibility ?? "private"}
          publicLabel={tCatalog("public")}
          privateLabel={tCatalog("private")}
        />
        <p className="text-muted-foreground font-mono text-xs tracking-wide uppercase">
          {detail.object_kind}
        </p>
        <h1 className="text-3xl font-medium tracking-tight">{detail.name}</h1>
        <p className="text-muted-foreground font-mono text-xs">{detail.stable_id}</p>
      </div>

      {process.env.NEXT_PUBLIC_EXTERNAL_CATALOG_ENABLED !== "false" ? (
        <details className="border-border rounded-lg border">
          <summary className="hover:bg-muted/30 cursor-pointer px-4 py-4 text-lg font-medium transition-colors">
            {t("integrations")}
          </summary>
          <div className="border-border border-t p-4">
            <ExternalProductManager
              locale={locale}
              objectKind={kind}
              stableId={stableId}
              csrfToken={(await readCsrfToken()) ?? ""}
              initialProducts={allProducts.items}
              selectedDomains={attachedProducts.items.map((item) => item.canonical_domain)}
            />
          </div>
        </details>
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
