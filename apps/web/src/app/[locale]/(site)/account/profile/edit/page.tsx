import { getTranslations, setRequestLocale } from "next-intl/server";

import { HistoryBackButton } from "@/components/molecules/history-back-button";
import { StatePanel } from "@/components/molecules/state-panel";
import { ProfileForm } from "@/components/organisms/profile-form";
import { ApiError } from "@/lib/api/errors";
import { readOwnerPublicProfile } from "@/lib/api/public-profile";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";

export default async function AccountProfileEditPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/account/profile/edit`);
  const t = await getTranslations("account");
  const common = await getTranslations("common");
  const token = (await sessionCookieValue()) ?? "";
  let initial;
  try {
    initial = await readOwnerPublicProfile(token);
  } catch (error) {
    if (error instanceof ApiError && error.code === "AI_STP_UNAVAILABLE")
      return (
        <StatePanel kind="error" title={common("error")} description={common("apiUnavailable")} />
      );
    throw error;
  }
  return (
    <article className="mx-auto w-full max-w-3xl min-w-0 space-y-6">
      <HistoryBackButton label={t("backToAccount")} fallback="/account" />
      <ProfileForm initial={initial} csrfToken={(await readCsrfToken()) ?? ""} />
    </article>
  );
}
