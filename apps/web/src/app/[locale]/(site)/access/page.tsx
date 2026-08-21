import { getTranslations, setRequestLocale } from "next-intl/server";

import { AccessWorkspace } from "@/components/organisms/access-workspace";
import { StatePanel } from "@/components/molecules/state-panel";
import { ApiError } from "@/lib/api/errors";
import { listGrants } from "@/lib/api/grants";
import { readCsrfToken } from "@/lib/auth/session";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export default async function AccessPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/access`);
  const t = await getTranslations("access");
  const tc = await getTranslations("common");
  const token = await sessionCookieValue();
  const csrf = await readCsrfToken();

  let grants;
  try {
    grants = await listGrants(token ?? "");
  } catch (error) {
    if (error instanceof ApiError && error.code === "AI_STP_UNAVAILABLE") {
      return <StatePanel kind="error" title={tc("error")} description={tc("apiUnavailable")} />;
    }
    throw error;
  }

  if (!csrf) {
    return <StatePanel kind="error" title={tc("sessionExpired")} description={tc("login")} />;
  }

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="text-3xl font-medium tracking-tight">{t("title")}</h1>
        <p className="text-muted-foreground max-w-2xl text-sm">{t("subtitle")}</p>
      </div>
      <AccessWorkspace
        invitations={grants.invitations}
        grants={grants.grants}
        csrfToken={csrf}
        labels={{
          invitations: t("invitations"),
          grants: t("grants"),
          emptyInvitations: t("emptyInvitations"),
          emptyGrants: t("emptyGrants"),
          create: t("createInvitation"),
          email: t("email"),
          major: t("major"),
          stableId: t("stableId"),
          kind: t("kind"),
          recipientKind: t("recipientKind"),
          githubUsername: t("githubUsername"),
          userId: t("userId"),
          kindComponent: t("kindComponent"),
          kindSetup: t("kindSetup"),
          revoke: t("revoke"),
          revokeWarning: t("revokeWarning"),
          reason: t("reason"),
          confirm: tc("confirm"),
          cancel: tc("cancel"),
          referenceId: tc("referenceId"),
        }}
      />
    </div>
  );
}
