import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";
import { CorporateDirectory } from "@/components/organisms/corporate-directory";
import { StatePanel } from "@/components/molecules/state-panel";
import { readCorporateDirectory } from "@/lib/api/corporate";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";

export default async function CorporateDirectoryPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string; resource: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { locale, resource } = await params;
  const filters = await searchParams;
  if (resource !== "projects" && resource !== "teams" && resource !== "members") notFound();
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/${resource}`);
  const t = await getTranslations("hub");
  const c = await getTranslations("common");
  let directory;
  try {
    directory = await readCorporateDirectory((await sessionCookieValue()) ?? "", resource);
  } catch {
    return (
      <StatePanel
        kind="error"
        title={t(resource === "members" ? "employees" : resource)}
        description={c("apiUnavailable")}
      />
    );
  }
  if (!directory)
    return <StatePanel kind="empty" title={t("organization")} description={t("empty")} />;
  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-medium tracking-tight">
        {t(resource === "members" ? "employees" : resource)}
      </h1>
      <CorporateDirectory
        resource={resource}
        items={directory.items}
        organizationId={directory.context.organization.organization_id}
        authorizationRevision={directory.context.organization.authorization_revision}
        csrfToken={(await readCsrfToken()) ?? ""}
        canCreate={directory.context.capabilities.includes(
          `${resource === "members" ? "member" : resource === "teams" ? "team" : "project"}.create`,
        )}
        roles={directory.roles?.items.map((role) => role.name) ?? []}
        initialQuery={typeof filters.query === "string" ? filters.query : ""}
        initialStatus={typeof filters.status === "string" ? filters.status : ""}
      />
    </div>
  );
}
