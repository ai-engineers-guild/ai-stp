import { getTranslations, setRequestLocale } from "next-intl/server";

import { AcceptInvitation } from "@/components/organisms/accept-invitation";
import { corporateHref } from "@/lib/features/corporate-path";

type PageProps = {
  params: Promise<{ locale: string; invitationId: string }>;
};

/**
 * No server session gate on purpose: the invitation token lives in the URL
 * fragment, which the server never sees. Gating here would 307 to login and
 * drop `#token=…` before the client could read it. The accept POST enforces
 * auth; a 401 sends the client to login with the fragment carried inside
 * `returnTo`.
 */
export default async function AcceptCorporateInvitationPage({ params }: PageProps) {
  const { locale, invitationId } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("invitations");
  const tc = await getTranslations("common");

  return (
    <div className="mx-auto max-w-lg space-y-6">
      <div className="space-y-2">
        <h1 className="text-3xl font-medium tracking-tight">{t("corporateTitle")}</h1>
        <p className="text-muted-foreground text-sm">{t("corporateSubtitle")}</p>
        <p className="text-muted-foreground font-mono text-xs">{invitationId}</p>
      </div>
      <AcceptInvitation
        invitationId={invitationId}
        endpoint={`/api/corporate/invitations/${encodeURIComponent(invitationId)}/accept`}
        signInHref={corporateHref(`/${locale}/login`)}
        onboardingHref={corporateHref(`/${locale}/onboarding`)}
        labels={{
          accept: t("accept"),
          accepting: t("accepting"),
          missingToken: t("missingToken"),
          success: t("corporateSuccess"),
          error: t("error"),
          referenceId: tc("referenceId"),
        }}
      />
    </div>
  );
}
