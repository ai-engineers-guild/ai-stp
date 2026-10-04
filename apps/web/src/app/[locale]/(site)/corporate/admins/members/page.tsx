import { getTranslations, setRequestLocale } from "next-intl/server";
import { redirect } from "next/navigation";

import { StatePanel } from "@/components/molecules/state-panel";
import { isOutstandingInvitation } from "@/lib/corporate-invitation-state";
import { CorporateMembersDirectory } from "@/components/organisms/corporate-members-directory";
import { ApiError } from "@/lib/api/errors";
import { requireSession } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";
import {
  loadAdminData,
  PeopleHeader,
  PeopleStats,
  type AdminData,
} from "@/app/[locale]/(site)/corporate/admins/people-shared";

type PageProps = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export default async function CorporateMembersPage({ params, searchParams }: PageProps) {
  const { locale } = await params;
  const filters = await searchParams;
  // The invitations tab became its own route; carry the remaining filters over.
  if (filters.tab === "invitations") {
    const rest = new URLSearchParams();
    for (const [key, value] of Object.entries(filters)) {
      if (key === "tab" || value === undefined) continue;
      for (const item of Array.isArray(value) ? value : [value]) rest.append(key, item);
    }
    const suffix = rest.size ? `?${rest.toString()}` : "";
    redirect(`/${locale}/corporate/admins/invitations${suffix}`);
  }
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/admins/members`);
  const t = await getTranslations("people");
  const h = await getTranslations("hub");
  const common = await getTranslations("common");
  let data: Awaited<ReturnType<typeof loadAdminData>>;
  try {
    data = await loadAdminData();
  } catch (error) {
    if (error instanceof ApiError && error.code === "AI_STP_UNAVAILABLE")
      return (
        <StatePanel kind="error" title={common("error")} description={common("apiUnavailable")} />
      );
    throw error;
  }
  if (data.status !== "ok")
    return (
      <StatePanel
        kind={data.status === "empty" ? "empty" : "error"}
        title={h("members")}
        description={data.status === "empty" ? t("noOrganization") : t("forbidden")}
      />
    );
  const csrfToken = (await readCsrfToken()) ?? "";
  return <MembersContent data={data} csrfToken={csrfToken} />;
}

async function MembersContent({ data, csrfToken }: { data: AdminData; csrfToken: string }) {
  const t = await getTranslations("people");
  const h = await getTranslations("hub");
  const { workspace, invitations } = data;
  const { context, members, roles, jobTitles } = workspace;
  const now = new Date().toISOString();
  return (
    <div className="min-w-0 space-y-5" data-ui="members-page">
      <PeopleHeader
        section={t("peopleAndAccess")}
        current={h("members")}
        description={t("pageBody")}
      />
      <PeopleStats
        items={[
          { label: t("totalMembers"), count: members?.items.length ?? null, icon: "team" },
          {
            label: t("pendingInvitations"),
            count:
              invitations?.items.filter((invitation) =>
                isOutstandingInvitation(invitation, Date.parse(now)),
              ).length ?? null,
            icon: "mail",
          },
          { label: t("teams"), count: context.teams.length, icon: "team" },
          { label: t("roles"), count: roles?.items.length ?? null, icon: "access" },
        ]}
      />
      <CorporateMembersDirectory
        members={members?.items ?? []}
        context={context}
        roles={roles?.items ?? []}
        jobTitles={jobTitles?.items ?? []}
        csrfToken={csrfToken}
        now={now}
      />
    </div>
  );
}
