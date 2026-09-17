import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";
import { TechnologyRegistryCreate } from "@/components/organisms/technology-registry-create";
import { CategoryLifecycleControls } from "@/components/organisms/corporate-governance-controls";
import { HistoryBackButton } from "@/components/molecules/history-back-button";
import { readCorporateContext } from "@/lib/api/corporate";
import { readCategoryDetail } from "@/lib/api/technology";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";
import { Link } from "@/lib/i18n/navigation";

export default async function CategoryDetailPage({
  params,
}: {
  params: Promise<{ locale: string; categoryId: string }>;
}) {
  const { locale, categoryId } = await params;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/categories/${categoryId}`);
  const session = (await sessionCookieValue()) ?? "";
  const context = await readCorporateContext(session);
  if (!context) notFound();
  const detail = await readCategoryDetail(
    session,
    context.organization.organization_id,
    categoryId,
  );
  if (!detail) notFound();
  const h = await getTranslations("hub");
  const t = await getTranslations("technology");
  const mutation = {
    organizationId: context.organization.organization_id,
    authorizationRevision: detail.permissions.authorization_revision,
    csrfToken: (await readCsrfToken()) ?? "",
  };
  return (
    <article className="space-y-6">
      <HistoryBackButton label={h("backToCategories")} fallback="/corporate/categories" />
      <header className="space-y-2">
        <h1 className="text-3xl font-medium">{detail.category.name}</h1>
        <p className="text-muted-foreground max-w-prose">{detail.category.description}</p>
      </header>
      {detail.permissions.capabilities.includes("category.update") && (
        <details>
          <summary className="min-h-11 cursor-pointer py-3 text-sm underline underline-offset-4">
            {t("editCategory")}
          </summary>
          <TechnologyRegistryCreate
            kind="category"
            initialCategory={detail.category}
            categories={null}
            {...mutation}
          />
        </details>
      )}
      {detail.technologies && (
        <section className="space-y-3">
          <h2 className="text-xl font-medium">{h("technologies")}</h2>
          <ul className="divide-border divide-y">
            {detail.technologies.items.map((item) => (
              <li key={item.technology_id} className="py-3">
                <Link
                  href={`/corporate/technologies/${item.technology_id}`}
                  className="inline-flex min-h-11 items-center underline underline-offset-4"
                >
                  {item.name}
                </Link>
              </li>
            ))}
          </ul>
          {!detail.technologies.items.length && (
            <p className="text-muted-foreground text-sm">{h("empty")}</p>
          )}
        </section>
      )}
      <CategoryLifecycleControls
        category={detail.category}
        {...mutation}
        canRemove={detail.permissions.capabilities.includes("category.delete")}
        canRestore={detail.permissions.capabilities.includes("category.update")}
      />
    </article>
  );
}
