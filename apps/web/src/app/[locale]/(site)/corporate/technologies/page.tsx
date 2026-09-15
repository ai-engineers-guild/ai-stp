import { getTranslations, setRequestLocale } from "next-intl/server";

import { StatePanel } from "@/components/molecules/state-panel";
import { CorporateDirectory } from "@/components/organisms/corporate-directory";
import { TechnologyRegistryCreate } from "@/components/organisms/technology-registry-create";
import { ApiError } from "@/lib/api/errors";
import { readTechnologyDirectory } from "@/lib/api/technology";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";

export default async function TechnologyRegistryPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/technologies`);
  const session = (await sessionCookieValue()) ?? "";
  const t = await getTranslations("technology");
  const h = await getTranslations("hub");
  const common = await getTranslations("common");
  const filters = await searchParams;
  const search = filters.query;
  const query = typeof search === "string" ? search : undefined;
  let registry;
  try {
    registry = await readTechnologyDirectory(session);
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    return (
      <StatePanel
        kind="error"
        title={h("technologies")}
        description={
          error.status === 401 || error.status === 403
            ? common("accessDenied")
            : t("registryUnavailable")
        }
      />
    );
  }
  if (!registry)
    return <StatePanel kind="empty" title={h("organization")} description={h("empty")} />;
  const { organization, permissions, directory, categories } = registry;
  if (!directory)
    return <StatePanel kind="empty" title={h("technologies")} description={t("notPermitted")} />;
  const mutation = {
    organizationId: organization.organization_id,
    authorizationRevision: permissions.authorization_revision,
    csrfToken: (await readCsrfToken()) ?? "",
    categories: categories?.items ?? null,
  };
  const canCreate = permissions.capabilities.includes("technology.create");
  return (
    <CorporateDirectory
      resource="technologies"
      items={directory.items}
      organizationId={directory.organization.organization_id}
      authorizationRevision={directory.organization.authorization_revision}
      csrfToken={mutation.csrfToken}
      canCreate={canCreate}
      roles={[]}
      initialQuery={query ?? ""}
      customCreate={
        canCreate ? <TechnologyRegistryCreate kind="technology" {...mutation} /> : undefined
      }
    />
  );
}
