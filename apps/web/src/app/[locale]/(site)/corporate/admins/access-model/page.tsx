import { getTranslations, setRequestLocale } from "next-intl/server";
import { StatePanel } from "@/components/molecules/state-panel";
import { CorporateAccessModel } from "@/components/organisms/corporate-access-model";
import { ApiError } from "@/lib/api/errors";
import { apiRequest } from "@/lib/api/http";
import type { CorporatePermissionMatrix } from "@/lib/api/generated/types.gen";
import { readCorporateWorkspace } from "@/lib/api/corporate";
import { canViewCorporateAdministration } from "@/lib/corporate-hub";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { PeopleHeader } from "@/app/[locale]/(site)/corporate/admins/people-shared";

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
  await requireSession(locale, `/${locale}/corporate/admins/access-model`);
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
      <PeopleHeader
        section={h("peopleAndAccess")}
        current={h("accessModel")}
        description={t("accessBody")}
      />
      <CorporateAccessModel
        definitions={matrix.definitions}
        effective={matrix.effective}
        roles={workspace.roles?.items ?? []}
        capabilities={workspace.context.capabilities}
        view={filters.view === "matrix" || filters.view === "sections" ? "sections" : "entities"}
      />
    </div>
  );
}
