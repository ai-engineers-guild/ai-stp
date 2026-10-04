import { getTranslations, setRequestLocale } from "next-intl/server";

import { StatePanel } from "@/components/molecules/state-panel";
import { CorporateInvitationsPanel } from "@/components/organisms/corporate-invitations-panel";
import { isOutstandingInvitation } from "@/lib/corporate-invitation-state";
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
};

export default async function CorporateInvitationsPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/admins/invitations`);
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
        title={h("invitations")}
        description={data.status === "empty" ? t("noOrganization") : t("forbidden")}
      />
    );
  if (!data.workspace.context.capabilities.includes("member.invite"))
    return <StatePanel kind="error" title={h("invitations")} description={t("forbidden")} />;
  const csrfToken = (await readCsrfToken()) ?? "";
  return <InvitationsContent data={data} csrfToken={csrfToken} />;
}

async function InvitationsContent({ data, csrfToken }: { data: AdminData; csrfToken: string }) {
  const t = await getTranslations("people");
  const h = await getTranslations("hub");
  const { workspace, invitations } = data;
  const { context, members, roles } = workspace;
  const now = new Date().toISOString();
  return (
    <div className="min-w-0 space-y-5" data-ui="invitations-page">
      <PeopleHeader
        section={t("peopleAndAccess")}
        current={h("invitations")}
        description={t("invitationsBody")}
      />
      <PeopleStats
        items={[
          {
            label: t("pendingInvitations"),
            count:
              invitations?.items.filter((invitation) =>
                isOutstandingInvitation(invitation, Date.parse(now)),
              ).length ?? null,
            icon: "mail",
          },
          { label: t("totalMembers"), count: members?.items.length ?? null, icon: "team" },
          { label: t("teams"), count: context.teams.length, icon: "team" },
          { label: t("roles"), count: roles?.items.length ?? null, icon: "access" },
        ]}
      />
      <CorporateInvitationsPanel
        csrfToken={csrfToken}
        context={context}
        roles={roles?.items ?? []}
        members={members?.items ?? []}
        invitations={invitations?.items ?? []}
        grantableRoles={data.grantableRoles}
        now={now}
        unavailable={invitations === null}
      />
    </div>
  );
}
