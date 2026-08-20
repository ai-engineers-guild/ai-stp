import { getTranslations, setRequestLocale } from "next-intl/server";

import { Button } from "@/components/atoms/button";
import { ProfilePreview } from "@/components/organisms/profile-preview";
import { StatePanel } from "@/components/molecules/state-panel";
import { ApiError } from "@/lib/api/errors";
import { previewOwnerPublicProfile } from "@/lib/api/public-profile";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { Link } from "@/lib/i18n/navigation";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export default async function AccountProfilePreviewPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/account/profile/preview`);
  const t = await getTranslations("account");
  const tc = await getTranslations("common");
  const token = (await sessionCookieValue()) ?? "";

  let preview;
  try {
    preview = await previewOwnerPublicProfile(token);
  } catch (error) {
    if (error instanceof ApiError && error.code === "AI_STP_UNAVAILABLE") {
      return <StatePanel kind="error" title={tc("error")} description={tc("apiUnavailable")} />;
    }
    if (error instanceof ApiError && error.code === "AI_STP_NOT_FOUND") {
      return (
        <StatePanel kind="empty" title={t("profile")} description={t("profilePreviewEmpty")} />
      );
    }
    throw error;
  }

  const p = preview.projection;
  return (
    <article className="space-y-6">
      <div className="border-border bg-muted flex flex-wrap items-center justify-between gap-3 rounded-md border px-3 py-2 text-sm">
        <span>{t("profilePreviewBanner")}</span>
        <Button asChild variant="outline" size="sm">
          <Link href="/account/profile">{t("profileEdit")}</Link>
        </Button>
      </div>
      <ProfilePreview projection={p} copyLabel={tc("copy")} copiedLabel={tc("copied")} />
    </article>
  );
}
