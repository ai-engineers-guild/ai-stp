import { getTranslations, setRequestLocale } from "next-intl/server";

import { Button } from "@/components/atoms/button";
import { CopyValue } from "@/components/molecules/copy-value";
import { IdentityList } from "@/components/organisms/identity-list";
import { StatePanel } from "@/components/molecules/state-panel";
import { readAccount } from "@/lib/api/account";
import { ApiError } from "@/lib/api/errors";
import { readCsrfToken } from "@/lib/auth/session";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { Link } from "@/lib/i18n/navigation";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export default async function AccountPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/account`);
  const t = await getTranslations("account");
  const tc = await getTranslations("common");
  const tn = await getTranslations("nav");
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

  return (
    <div className="min-w-0 space-y-6">
      <h1 className="text-2xl font-medium tracking-tight sm:text-3xl">{t("title")}</h1>
      <dl className="grid gap-3">
        <div>
          <dt className="text-muted-foreground text-sm">{t("accountId")}</dt>
          <dd className="mt-1">
            <CopyValue
              value={profile.account_id}
              label={t("copyAccountId")}
              copied={tc("copied")}
            />
          </dd>
        </div>
      </dl>

      <section className="border-border bg-card space-y-3 rounded-lg border p-5 shadow-sm">
        <div className="space-y-1">
          <h2 className="text-xl font-medium tracking-tight">{t("profile")}</h2>
          <p className="text-muted-foreground text-sm">{t("profileAccountHint")}</p>
        </div>
        <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap">
          <Button asChild className="min-h-11 w-full sm:w-auto">
            <Link href="/account/profile">{t("editProfile")}</Link>
          </Button>
          <Button asChild variant="outline" className="min-h-11 w-full sm:w-auto">
            <Link href={`/publishers/${profile.account_id}`}>{t("viewPublicProfile")}</Link>
          </Button>
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-medium tracking-tight">{t("signInMethods")}</h2>
        <IdentityList
          identities={profile.identities}
          csrfToken={csrfToken}
          returnTo={`/${locale}/account`}
        />
      </section>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <Button asChild variant="outline" className="min-h-11 w-full shrink-0 sm:w-auto">
          <Link href="/account/privacy">{t("editPrivacy")}</Link>
        </Button>
        <p className="text-muted-foreground text-sm">{t("privacySubtitle")}</p>
      </div>
      <form action={`/api/auth/logout?locale=${locale}`} method="post">
        <Button type="submit" variant="destructive" className="min-h-11 w-full sm:w-auto">
          {tn("logout")}
        </Button>
      </form>
    </div>
  );
}
