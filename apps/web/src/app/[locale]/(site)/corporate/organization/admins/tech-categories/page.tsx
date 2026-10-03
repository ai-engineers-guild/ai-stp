import { getTranslations, setRequestLocale } from "next-intl/server";

import { StatePanel } from "@/components/molecules/state-panel";
import { CorporateTechCategories } from "@/components/organisms/corporate-tech-categories";
import { readCorporateContext } from "@/lib/api/corporate";
import { readTechnologyRegistry } from "@/lib/api/technology";
import { privateApiRequest } from "@/lib/api/http";
import type { TechnologyList, TechnologyView } from "@/lib/api/generated/types.gen";
import { ApiError } from "@/lib/api/errors";
import { canViewCorporateAdministration } from "@/lib/corporate-hub";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";
import { Link } from "@/lib/i18n/navigation";

export default async function TechCategoriesPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/organization/admins/tech-categories`);
  const t = await getTranslations("technologyCategories");
  const people = await getTranslations("people");
  const common = await getTranslations("common");
  const session = (await sessionCookieValue()) ?? "";
  let context;
  try {
    context = await readCorporateContext(session);
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    return <StatePanel kind="error" title={t("title")} description={common("apiUnavailable")} />;
  }
  if (!context)
    return <StatePanel kind="empty" title={t("title")} description={t("noOrganization")} />;
  const capabilities = context.capabilities;
  const allowed =
    canViewCorporateAdministration(capabilities) &&
    capabilities.includes("category.list") &&
    capabilities.includes("category.read");
  if (!allowed)
    return <StatePanel kind="empty" title={t("title")} description={common("accessDenied")} />;
  const organizationId = context.organization.organization_id;
  let registry;
  let technologies: TechnologyView[] | null = null;
  try {
    registry = await readTechnologyRegistry(session, organizationId);
    if (capabilities.includes("technology.list")) {
      const items: TechnologyView[] = [];
      let total = 0;
      do {
        const page = await privateApiRequest<TechnologyList>(
          `/v1/corporate/organizations/${organizationId}/technologies`,
          { sessionToken: session, query: { offset: String(items.length), limit: "256" } },
        );
        items.push(...page.items);
        total = page.total;
        if (!page.items.length) break;
      } while (items.length < total);
      technologies = items;
    }
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    return <StatePanel kind="error" title={t("title")} description={common("apiUnavailable")} />;
  }
  return (
    <div className="min-w-0 space-y-5">
      <header className="space-y-3">
        <nav
          aria-label={people("breadcrumbs")}
          className="text-muted-foreground flex flex-wrap items-center gap-2 text-xs sm:text-sm"
        >
          <Link href="/corporate/overview" className="hover:text-foreground">
            {people("corporate")}
          </Link>
          <span aria-hidden>/</span>
          <span>{people("administration")}</span>
          <span aria-hidden>/</span>
          <span>{people("referenceData")}</span>
          <span aria-hidden>/</span>
          <span aria-current="page" className="text-foreground">
            {t("title")}
          </span>
        </nav>
        <div className="space-y-1">
          <h1 className="text-3xl leading-tight font-medium tracking-tight">{t("title")}</h1>
          <p className="text-muted-foreground text-sm sm:text-base">{t("body")}</p>
        </div>
      </header>
      <CorporateTechCategories
        csrfToken={(await readCsrfToken()) ?? ""}
        organizationId={organizationId}
        authorizationRevision={context.organization.authorization_revision}
        capabilities={capabilities}
        categories={registry.categories?.items ?? []}
        technologies={technologies}
      />
    </div>
  );
}
