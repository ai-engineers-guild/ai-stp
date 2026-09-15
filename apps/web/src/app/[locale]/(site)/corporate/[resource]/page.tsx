import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";
import { CorporateDirectory } from "@/components/organisms/corporate-directory";
import { StatePanel } from "@/components/molecules/state-panel";
import { readCorporateDirectory } from "@/lib/api/corporate";
import { ApiError } from "@/lib/api/errors";
import {
  isCorporateTeamProjectResource,
  readCorporateTeamProjectDirectory,
} from "@/lib/api/corporate-team-project";
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
  if (resource !== "members" && !isCorporateTeamProjectResource(resource)) notFound();
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/${resource}`);
  const t = await getTranslations("hub");
  const c = await getTranslations("common");
  let directory;
  try {
    const session = (await sessionCookieValue()) ?? "";
    directory = isCorporateTeamProjectResource(resource)
      ? await readCorporateTeamProjectDirectory(session, resource)
      : await readCorporateDirectory(session, resource);
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    return (
      <StatePanel
        kind="error"
        title={t(resource === "members" ? "employees" : resource)}
        description={
          error.status === 403 || error.status === 401 ? c("accessDenied") : c("apiUnavailable")
        }
      />
    );
  }
  if (!directory)
    return <StatePanel kind="empty" title={t("organization")} description={t("empty")} />;
  return (
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
    />
  );
}
