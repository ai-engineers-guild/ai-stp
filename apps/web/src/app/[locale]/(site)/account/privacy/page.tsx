import { getTranslations, setRequestLocale } from "next-intl/server";

import { StatePanel } from "@/components/molecules/state-panel";
import { PrivacyPreferencesForm } from "@/components/organisms/privacy-preferences-form";
import { privacyFieldsFromAccount, readAccount } from "@/lib/api/account";
import { ApiError } from "@/lib/api/errors";
import { readCsrfToken } from "@/lib/auth/session";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { Link } from "@/lib/i18n/navigation";
import { Icon } from "@/theme";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export default async function AccountPrivacyPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/account/privacy`);
  const t = await getTranslations("account");
  const tc = await getTranslations("common");
  const token = await sessionCookieValue();
  const csrfToken = (await readCsrfToken()) ?? "";

  let profile;
  try {
    profile = await readAccount(token ?? "");
  } catch (error) {
    if (error instanceof ApiError && error.code === "AI_STP_UNAVAILABLE") {
      return <StatePanel kind="error" title={tc("error")} description={tc("apiUnavailable")} />;
    }
    throw error;
  }

  const privacy = privacyFieldsFromAccount(profile);

  return (
    <article className="mx-auto w-full max-w-3xl min-w-0 space-y-6">
      <Link
        href="/account"
        className="hover:bg-accent focus-visible:ring-ring inline-flex min-h-11 items-center gap-2 rounded-sm px-3 text-sm font-medium transition-colors focus-visible:ring-2 focus-visible:outline-none"
      >
        <Icon name="arrowLeft" className="h-4 w-4" />
        {t("title")}
      </Link>
      <header className="space-y-2">
        <h1 className="text-2xl font-medium tracking-tight sm:text-3xl">{t("privacy")}</h1>
        <p className="text-muted-foreground max-w-[70ch] text-sm">{t("privacySubtitle")}</p>
      </header>
      <PrivacyPreferencesForm
        csrfToken={csrfToken}
        initialShowProfilePublicly={privacy.showProfilePublicly}
        initialAllowPublisherListing={privacy.allowPublisherListing}
        labels={{
          showProfilePublicly: t("showProfilePublicly"),
          allowPublisherListing: t("allowPublisherListing"),
          save: t("savePreferences"),
          saving: t("savingPreferences"),
          saved: t("preferencesSaved"),
          failed: t("preferencesSaveFailed"),
        }}
      />
    </article>
  );
}
