import { getTranslations, setRequestLocale } from "next-intl/server";

import { AcceptInvitation } from "@/components/organisms/accept-invitation";
import { corporateHref } from "@/lib/features/corporate-path";

type PageProps = {
  params: Promise<{ locale: string; invitationId: string }>;
};

/**
 * Public confirm page for claimed invitations (#201). Same fragment-token
 * contract as the accept page: no server session gate, the POST enforces
 * auth and sends a 401 to login with the fragment inside `returnTo`.
 */
export default async function ConfirmCorporateInvitationPage({ params }: PageProps) {
  const { locale, invitationId } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("invitations");
  const tc = await getTranslations("common");

  return (
    <div className="mx-auto max-w-lg space-y-6">
      <div className="space-y-2">
        <h1 className="text-3xl font-medium tracking-tight">{t("confirmTitle")}</h1>
        <p className="text-muted-foreground text-sm">{t("confirmSubtitle")}</p>
        <p className="text-muted-foreground font-mono text-xs">{invitationId}</p>
      </div>
      <AcceptInvitation
        invitationId={invitationId}
        endpoint={`/api/corporate/invitations/${encodeURIComponent(invitationId)}/confirm`}
        holdEndpoint={`/api/corporate/invitations/${encodeURIComponent(invitationId)}/hold`}
        holdVariant="confirm"
        signInHref={corporateHref(`/${locale}/login`)}
        onboardingHref={corporateHref(`/${locale}/onboarding`)}
        labels={{
          accept: t("confirm"),
          accepting: t("confirming"),
          missingToken: t("missingToken"),
          success: t("confirmSuccess"),
          error: t("error"),
          referenceId: tc("referenceId"),
        }}
      />
    </div>
  );
}
