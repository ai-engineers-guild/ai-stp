import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import { Button } from "@/components/atoms/button";
import { StatePanel } from "@/components/molecules/state-panel";
import { TechnologyRegistryCreate } from "@/components/organisms/technology-registry-create";
import { readCorporateContext } from "@/lib/api/corporate";
import { readCategoryDirectory } from "@/lib/api/technology";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";
import { Link } from "@/lib/i18n/navigation";

export default async function CategoryDirectoryPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/categories`);
  const session = (await sessionCookieValue()) ?? "";
  const context = await readCorporateContext(session);
  if (!context) notFound();
  const h = await getTranslations("hub");
  const t = await getTranslations("technology");
  const result = await readCategoryDirectory(session, context.organization.organization_id);
  if (!result)
    return <StatePanel kind="empty" title={h("categories")} description={t("notPermitted")} />;
  const raw = (await searchParams).query;
  const query = typeof raw === "string" ? raw : "";
  const items = result.categories.items.filter((item) =>
    item.name.toLocaleLowerCase().includes(query.toLocaleLowerCase()),
  );
  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-medium">{h("categories")}</h1>
      <form method="get" className="flex max-w-xl flex-wrap items-end gap-3">
        <div className="flex-1 space-y-2">
          <Label htmlFor="category-query">{h("search")}</Label>
          <Input id="category-query" name="query" defaultValue={query} />
        </div>
        <Button type="submit">{t("apply")}</Button>
      </form>
      {result.permissions.capabilities.includes("category.create") && (
        <details>
          <summary className="min-h-11 cursor-pointer py-3 text-sm underline underline-offset-4">
            {h("create")}
          </summary>
          <TechnologyRegistryCreate
            kind="category"
            organizationId={context.organization.organization_id}
            authorizationRevision={result.permissions.authorization_revision}
            csrfToken={(await readCsrfToken()) ?? ""}
            categories={null}
          />
        </details>
      )}
      {items.length ? (
        <ul className="divide-border divide-y">
          {items.map((item) => (
            <li key={item.category_id} className="space-y-1 py-4">
              <Link
                href={`/corporate/categories/${item.category_id}`}
                className="inline-flex min-h-11 items-center font-medium underline underline-offset-4"
              >
                {item.name}
              </Link>
              <p className="text-muted-foreground max-w-prose text-sm">{item.description}</p>
            </li>
          ))}
        </ul>
      ) : (
        <StatePanel
          kind="empty"
          title={h("categories")}
          description={h(query ? "noMatches" : "empty")}
        />
      )}
    </div>
  );
}
