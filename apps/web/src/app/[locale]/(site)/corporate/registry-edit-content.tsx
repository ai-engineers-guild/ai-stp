import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";
import { loadEntityActionMenus } from "@/actions/entity-actions";
import { RouteDialog } from "@/components/molecules/route-dialog";
import { TechnologyRegistryCreate } from "@/components/organisms/technology-registry-create";
import { readCorporateContext } from "@/lib/api/corporate";
import { apiRequest } from "@/lib/api/http";
import type {
  AreaList,
  AreaView,
  CategoryList,
  CategoryView,
  TechnologyView,
} from "@/lib/api/generated/types.gen";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";

export async function RegistryEditContent({
  locale,
  kind,
  id,
}: {
  locale: string;
  kind: "area" | "category" | "technology";
  id: string;
}) {
  const resource = kind === "area" ? "areas" : kind === "category" ? "categories" : "technologies";
  await requireSession(locale, `/${locale}/corporate/${resource}/${id}/edit`);
  const token = (await sessionCookieValue()) ?? "";
  const context = await readCorporateContext(token);
  if (!context) notFound();
  const organizationId = context.organization.organization_id;
  const { menus } = await loadEntityActionMenus([{ kind, id, organization_id: organizationId }]);
  if (!menus.items[0]?.actions.some((action) => action.id === "edit")) notFound();
  const root = `/v1/corporate/organizations/${organizationId}`;
  const endpoint =
    kind === "technology"
      ? "technologies"
      : kind === "area"
        ? "technology-areas"
        : "technology-categories";
  const [record, categories, areas, corporate] = await Promise.all([
    apiRequest<TechnologyView | CategoryView | AreaView>(`${root}/${endpoint}/${id}`, {
      sessionToken: token,
    }),
    context.capabilities.includes("category.list")
      ? apiRequest<CategoryList>(`${root}/technology-categories`, { sessionToken: token })
      : null,
    context.capabilities.includes("area.list")
      ? apiRequest<AreaList>(`${root}/technology-areas`, { sessionToken: token })
      : null,
    getTranslations("corporate"),
  ]);
  return (
    <RouteDialog title={corporate("edit")} fallback={`/corporate/${resource}/${id}`}>
      <TechnologyRegistryCreate
        kind={kind}
        organizationId={organizationId}
        authorizationRevision={String(menus.items[0].authorization_revision)}
        csrfToken={(await readCsrfToken()) ?? ""}
        categories={categories?.items ?? null}
        areas={areas?.items ?? null}
        {...(kind === "technology"
          ? { initial: record as TechnologyView }
          : kind === "category"
            ? { initialCategory: record as CategoryView }
            : { initialArea: record as AreaView })}
        essential
        closeOnSave
      />
    </RouteDialog>
  );
}
