import { getTranslations, setRequestLocale } from "next-intl/server";

import { StatePanel } from "@/components/molecules/state-panel";
import { CorporateDirectory } from "@/components/organisms/corporate-directory";
import { readCorporateContext } from "@/lib/api/corporate";
import { ApiError } from "@/lib/api/errors";
import { listCatalogAuthors, searchComponents } from "@/lib/api/catalog";
import type { ComponentType } from "@/lib/api/generated/types.gen";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";

export default async function CorporateComponentsPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/components`);
  const t = await getTranslations("hub");
  const common = await getTranslations("common");
  const catalog = await getTranslations("catalog");
  const token = (await sessionCookieValue()) ?? "";
  const context = await readCorporateContext(token);
  if (!context) return <StatePanel kind="empty" title={t("components")} description={t("empty")} />;
  const raw = await searchParams;
  const query = typeof raw.query === "string" ? raw.query : undefined;
  let rows: Array<{
    id: string;
    name: string;
    description?: string;
    component_type?: ComponentType;
    author_name?: string;
    owner_name?: string | null;
    tags?: readonly string[];
    version?: string;
  }> = [];
  try {
    const [result, authors] = await Promise.all([
      searchComponents({
        ...(query ? { q: query } : {}),
        page_size: 100,
        include_experimental: true,
      }),
      listCatalogAuthors().catch(() => ({ items: [] })),
    ]);
    const authorNames = new Map(
      authors.items.map((author) => [
        author.account_id,
        author.display_name || [author.first_name, author.last_name].filter(Boolean).join(" "),
      ]),
    );
    rows = [...result.items, ...result.experimental].map((item) => ({
      id: item.stable_id,
      name: item.latest_name,
      description: item.latest_description,
      component_type: item.latest_component_type,
      author_name: authorNames.get(item.publisher_id) || item.owner_handle || catalog("author"),
      owner_name: authorNames.get(item.owner_account_id) || item.owner_handle || null,
      tags: item.latest_tags,
      version: item.latest_version,
    }));
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    return (
      <StatePanel kind="error" title={t("components")} description={common("apiUnavailable")} />
    );
  }
  return (
    <CorporateDirectory
      resource="components"
      items={rows}
      organizationId={context.organization.organization_id}
      authorizationRevision={context.organization.authorization_revision}
      csrfToken={(await readCsrfToken()) ?? ""}
      canCreate={false}
      roles={[]}
      initialQuery={query ?? ""}
    />
  );
}
