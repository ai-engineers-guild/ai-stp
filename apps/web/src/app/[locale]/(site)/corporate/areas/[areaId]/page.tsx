import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";
import { Badge } from "@/components/atoms/badge";
import { HistoryBackButton } from "@/components/molecules/history-back-button";
import { EntityDetailMenu } from "@/components/organisms/entity-detail-menu";
import { readCorporateContext } from "@/lib/api/corporate";
import { apiRequest } from "@/lib/api/http";
import type { AreaView, CategoryList } from "@/lib/api/generated/types.gen";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { Link } from "@/lib/i18n/navigation";
export default async function AreaDetailPage({
  params,
}: {
  params: Promise<{ locale: string; areaId: string }>;
}) {
  const { locale, areaId } = await params;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/areas/${areaId}`);
  const token = (await sessionCookieValue()) ?? "";
  const context = await readCorporateContext(token);
  if (!context) notFound();
  const org = context.organization.organization_id;
  const root = `/v1/corporate/organizations/${org}`;
  const [area, categories, h, w] = await Promise.all([
    apiRequest<AreaView>(`${root}/technology-areas/${areaId}`, { sessionToken: token }),
    context.capabilities.includes("category.list")
      ? apiRequest<CategoryList>(`${root}/technology-categories`, { sessionToken: token })
      : null,
    getTranslations("hub"),
    getTranslations("technology.workspace"),
  ]);
  return (
    <article className="space-y-6">
      <HistoryBackButton label={w("backLandscape")} fallback="/corporate/technology-landscape" />
      <header className="flex items-start justify-between gap-4">
        <div className="space-y-2">
          <h1 className="text-3xl font-medium">{area.name}</h1>
          <Badge variant="secondary">{area.state}</Badge>
          <p className="text-muted-foreground max-w-prose">{area.description}</p>
        </div>
        <EntityDetailMenu
          moreLabel={w("actions")}
          subject={{ kind: "area", id: areaId, organization_id: org }}
          choices={[]}
        />
      </header>
      <section className="space-y-3">
        <h2 className="text-xl font-medium">{h("categories")}</h2>
        <ul className="divide-border divide-y">
          {categories?.items
            .filter((category) => category.area_id === areaId)
            .map((category) => (
              <li key={category.category_id} className="py-3">
                <Link
                  href={`/corporate/categories/${category.category_id}`}
                  className="inline-flex min-h-11 items-center underline underline-offset-4"
                >
                  {category.name}
                </Link>
              </li>
            ))}
        </ul>
      </section>
    </article>
  );
}
