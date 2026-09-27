import { getTranslations, setRequestLocale } from "next-intl/server";

import { AcceptInvitation } from "@/components/organisms/accept-invitation";
import { requireSession } from "@/lib/auth/require-session";

type PageProps = {
  params: Promise<{ locale: string; invitationId: string }>;
};

export default async function AcceptCorporateInvitationPage({ params }: PageProps) {
  const { locale, invitationId } = await params;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate-invitations/${invitationId}`);
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
