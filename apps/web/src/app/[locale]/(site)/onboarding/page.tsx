import { getTranslations, setRequestLocale } from "next-intl/server";

import { completeLegalOnboardingAction } from "@/actions/legal-onboarding";
import { Button } from "@/components/atoms/button";
import { Link } from "@/lib/i18n/navigation";
import { readLegalOnboarding } from "@/lib/api/legal";
import { requireOnboardingSession } from "@/lib/auth/require-session";

type PageProps = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ returnTo?: string; reason?: string }>;
};

export default async function LegalOnboardingPage({ params, searchParams }: PageProps) {
  const { locale } = await params;
  const { returnTo: requestedReturnTo, reason } = await searchParams;
  setRequestLocale(locale);
  const t = await getTranslations("onboarding");
  const fallback = `/${locale}/account`;
  const returnTo = requestedReturnTo?.startsWith(`/${locale}/`) ? requestedReturnTo : fallback;
  await requireOnboardingSession(locale, returnTo);
  const legal = await readLegalOnboarding(locale);
  const action = completeLegalOnboardingAction.bind(
    null,
    locale,
    returnTo,
    legal.service_rules_revision_id,
    legal.personal_data_consent_revision_id,
  );
  const termsHref = `/legal/service-rules?revision=${encodeURIComponent(legal.service_rules_revision_id)}`;
  const consentHref = `/legal/personal-data-consent?revision=${encodeURIComponent(legal.personal_data_consent_revision_id)}`;

  return (
    <main className="mx-auto w-full max-w-xl space-y-6 py-8 sm:py-14">
      <header className="space-y-3">
        <h1 className="text-3xl font-medium tracking-tight">{t("title")}</h1>
        <p className="text-muted-foreground leading-relaxed">{t("body")}</p>
      </header>
      {reason === "required" ? (
        <p className="border-destructive text-destructive rounded-sm border p-3 text-sm">
          {t("required")}
        </p>
      ) : null}
      <form action={action} className="space-y-5 border-y py-6">
        <label className="flex items-start gap-3 text-sm leading-relaxed">
          <input name="service-rules" type="checkbox" value="accepted" required className="mt-1" />
          <span>
            {t("rulesPrefix")}{" "}
            <Link className="underline" href={termsHref}>
              {t("serviceRules")}
            </Link>
            {t("rulesSuffix")}
          </span>
        </label>
        <label className="flex items-start gap-3 text-sm leading-relaxed">
          <input name="personal-data" type="checkbox" value="accepted" required className="mt-1" />
          <span>
            {t("consentPrefix")}{" "}
            <Link className="underline" href={consentHref}>
              {t("personalData")}
            </Link>
            {t("consentSuffix")}
          </span>
        </label>
        <Button type="submit" size="lg">
          {t("continue")}
        </Button>
      </form>
      <p className="text-muted-foreground text-xs">{t("evidence")}</p>
    </main>
  );
}
