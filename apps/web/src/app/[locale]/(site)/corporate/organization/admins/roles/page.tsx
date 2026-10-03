import { getTranslations, setRequestLocale } from "next-intl/server";
import { StatePanel } from "@/components/molecules/state-panel";
import { permissionDefinitions } from "@/lib/corporate-permission-ui";
import { CorporateRolesWorkspace } from "@/components/organisms/corporate-roles-workspace";
import { ApiError } from "@/lib/api/errors";
import { apiRequest } from "@/lib/api/http";
import { readCorporateWorkspace } from "@/lib/api/corporate";
import type { CorporatePermissionMatrix } from "@/lib/api/generated/types.gen";
import { canViewCorporateAdministration } from "@/lib/corporate-hub";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";

export default async function CorporateRolesPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/organization/admins/roles`);
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
    !canViewCorporateAdministration(workspace.context.capabilities) ||
    !workspace.context.capabilities.includes("role.list")
  )
    return <StatePanel kind="error" title={h("roles")} description={t("forbidden")} />;

  const definitions: CorporatePermissionMatrix["definitions"] =
    matrix?.definitions ??
    permissionDefinitions([
      ...workspace.context.capabilities,
      ...(workspace.roles?.items ?? []).flatMap((role) => role.permissions),
    ]);

  return (
    <div className="min-w-0 space-y-5">
      <header className="space-y-2">
        <p className="text-muted-foreground text-xs">
          {h("administration")} / {h("peopleAndAccess")} / {h("roles")}
        </p>
        <h1 className="text-3xl font-medium tracking-tight">{h("roles")}</h1>
        <p className="text-muted-foreground text-sm">{t("rolesBody")}</p>
      </header>
      <CorporateRolesWorkspace
        roles={workspace.roles?.items ?? []}
        bindings={workspace.bindings?.items ?? []}
        members={workspace.members?.items ?? []}
        definitions={definitions}
        context={workspace.context}
        csrfToken={(await readCsrfToken()) ?? ""}
      />
    </div>
  );
}
