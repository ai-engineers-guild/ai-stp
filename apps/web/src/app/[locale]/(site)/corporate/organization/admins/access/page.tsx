import { getTranslations, setRequestLocale } from "next-intl/server";
import { StatePanel } from "@/components/molecules/state-panel";
import { CorporateAccessModel } from "@/components/organisms/corporate-access-model";
import { ApiError } from "@/lib/api/errors";
import { apiRequest } from "@/lib/api/http";
import type { CorporatePermissionMatrix } from "@/lib/api/generated/types.gen";
import { readCorporateWorkspace } from "@/lib/api/corporate";
import { canViewCorporateAdministration } from "@/lib/corporate-hub";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";

export default async function CorporateAccessModelPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { locale } = await params;
  const filters = await searchParams;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/organization/admins/access`);
  const h = await getTranslations("hub");
  const t = await getTranslations("accessUi");
  const common = await getTranslations("common");
  const session = (await sessionCookieValue()) ?? "";
  let workspace: Awaited<ReturnType<typeof readCorporateWorkspace>>;
  let matrix: CorporatePermissionMatrix | null;
  try {
    workspace = await readCorporateWorkspace(session, false);
    matrix = workspace?.context.capabilities.includes("role.read")
      ? await apiRequest<CorporatePermissionMatrix>(
          `/v1/corporate/organizations/${workspace.organization.organization_id}/permissions/matrix`,
          { sessionToken: session },
        )
      : null;
  } catch (error) {
    if (error instanceof ApiError && error.code === "AI_STP_UNAVAILABLE")
      return (
        <StatePanel kind="error" title={common("error")} description={common("apiUnavailable")} />
      );
    throw error;
  }

  if (
    !workspace ||
    !matrix ||
    !canViewCorporateAdministration(workspace.context.capabilities) ||
    !workspace.context.capabilities.includes("role.read")
  ) {
    return <StatePanel kind="error" title={h("accessModel")} description={t("forbidden")} />;
  }

  return (
    <div className="min-w-0 space-y-5">
      <header className="space-y-2">
        <p className="text-muted-foreground text-xs">
          {h("administration")} / {h("peopleAndAccess")} / {h("accessModel")}
        </p>
        <h1 className="text-3xl font-medium tracking-tight">{h("accessModel")}</h1>
        <p className="text-muted-foreground text-sm">{t("accessBody")}</p>
      </header>
      <CorporateAccessModel
        definitions={matrix.definitions}
        effective={matrix.effective}
        roles={workspace.roles?.items ?? []}
        capabilities={workspace.context.capabilities}
        view={
          filters.view === "roles"
            ? "roles"
            : filters.view === "matrix" || filters.view === "sections"
              ? "sections"
              : "entities"
        }
      />
    </div>
  );
}
