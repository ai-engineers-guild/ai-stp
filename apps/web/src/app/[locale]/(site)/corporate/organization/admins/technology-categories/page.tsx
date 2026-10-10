import { getTranslations, setRequestLocale } from "next-intl/server";

import { HistoryBackButton } from "@/components/molecules/history-back-button";
import { StatePanel } from "@/components/molecules/state-panel";
import { TaxonomyDirectory } from "@/components/organisms/taxonomy-directory";
import { readCorporateContext } from "@/lib/api/corporate";
import { ApiError } from "@/lib/api/errors";
import { readCategoryDirectory } from "@/lib/api/technology";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";

export default async function TechnologyCategoriesPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  await requireSession(
    locale,
    `/${locale}/corporate/organization/admins/technology-categories`,
  );
  const session = (await sessionCookieValue()) ?? "";
  const t = await getTranslations("technology");
  const h = await getTranslations("hub");
  const c = await getTranslations("corporate");
  const common = await getTranslations("common");
  let context;
  try {
    context = await readCorporateContext(session);
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    return (
      <StatePanel kind="error" title={h("categories")} description={common("apiUnavailable")} />
    );
  }
  if (!context)
    return <StatePanel kind="empty" title={h("categories")} description={c("noOrganization")} />;
  let result;
  try {
    result = await readCategoryDirectory(session, context.organization.organization_id);
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    return (
      <StatePanel
        kind="error"
        title={h("categories")}
        description={error.status === 403 ? t("forbidden") : t("unavailable")}
      />
    );
  }
  if (!result)
    return <StatePanel kind="empty" title={h("categories")} description={t("notPermitted")} />;
  const capabilities = result.permissions.capabilities;
  return (
    <div className="min-w-0 space-y-6">
      <header className="space-y-3">
        <HistoryBackButton label={h("referenceData")} fallback="/corporate/organization/admins" />
        <h1 className="text-3xl font-medium tracking-tight sm:text-4xl">{h("categories")}</h1>
        <p className="text-muted-foreground max-w-prose">{t("categoriesDescription")}</p>
      </header>
      <TaxonomyDirectory
        kind="category"
        items={result.categories.items}
        areas={result.areas?.items ?? []}
        authority={{
          organizationId: context.organization.organization_id,
          authorizationRevision: result.permissions.authorization_revision,
          csrfToken: (await readCsrfToken()) ?? "",
        }}
        canCreate={capabilities.includes("category.create")}
        canUpdate={capabilities.includes("category.update")}
        canRemove={capabilities.includes("category.delete")}
        detailBase="/corporate/organization/admins/technology-categories"
      />
    </div>
  );
}
