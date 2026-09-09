import { setRequestLocale } from "next-intl/server";
import { GithubConnector } from "@/components/organisms/github-connector";
import { readCsrfToken } from "@/lib/auth/session";
import { requireSession } from "@/lib/auth/require-session";

export default async function GithubPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const session = await requireSession(locale, `/${locale}/account/github`);
  return (
    <GithubConnector
      csrfToken={(await readCsrfToken()) ?? ""}
      deviceId={session.deviceId}
      locale={locale === "ru" ? "ru" : "en"}
    />
  );
}
