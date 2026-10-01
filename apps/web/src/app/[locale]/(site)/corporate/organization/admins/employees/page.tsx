import { getTranslations, setRequestLocale } from "next-intl/server";
import { StatePanel } from "@/components/molecules/state-panel";
import { CorporateMembersDirectory } from "@/components/organisms/corporate-members-directory";
import { readCorporateWorkspace } from "@/lib/api/corporate";
import { ApiError } from "@/lib/api/errors";
import { canViewCorporateAdministration } from "@/lib/corporate-hub";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";
import EmployeeAccessDetail from "./[accountId]/page";

export default async function EmployeeAccessPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { locale } = await params;
  const filters = await searchParams;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/organization/admins/employees`);
  const h = await getTranslations("hub");
  const t = await getTranslations("accessUi");
  const common = await getTranslations("common");
  let workspace: Awaited<ReturnType<typeof readCorporateWorkspace>>;
  try {
    workspace = await readCorporateWorkspace((await sessionCookieValue()) ?? "", false);
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
    !workspace.context.capabilities.includes("member.list")
  )
    return <StatePanel kind="error" title={h("employeeAccess")} description={t("forbidden")} />;
  const members = workspace.members?.items ?? [];
  const employee = members.find((member) => member.account_id === filters.employee);
  return (
    <div className="min-w-0 space-y-5">
      <header className="space-y-2">
        <p className="text-muted-foreground text-xs">
          {h("administration")} / {h("peopleAndAccess")} / {h("employeeAccess")}
        </p>
        <h1 className="text-3xl font-medium tracking-tight">{h("employeeAccess")}</h1>
        <p className="text-muted-foreground text-sm">{t("employeeBody")}</p>
      </header>
      <CorporateMembersDirectory
        accessView
        members={members}
        context={workspace.context}
        roles={workspace.roles?.items ?? []}
        jobTitles={workspace.jobTitles?.items ?? []}
        bindings={workspace.bindings?.items ?? []}
        csrfToken={(await readCsrfToken()) ?? ""}
        now={new Date().toISOString()}
        accessPanel={
          employee ? (
            <EmployeeAccessDetail
              params={Promise.resolve({ locale, accountId: employee.account_id })}
              searchParams={Promise.resolve({ ...filters, embedded: "1" })}
            />
          ) : null
        }
      />
    </div>
  );
}
