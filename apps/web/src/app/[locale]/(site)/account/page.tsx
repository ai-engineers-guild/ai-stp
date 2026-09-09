import { getTranslations, setRequestLocale } from "next-intl/server";

import { AvatarImage } from "@/components/atoms/avatar-image";
import { Badge } from "@/components/atoms/badge";
import { Button } from "@/components/atoms/button";
import { CopyValue } from "@/components/molecules/copy-value";
import { GitHubConnectionLink } from "@/components/molecules/github-connection-link";
import { StatePanel } from "@/components/molecules/state-panel";
import { IdentityList } from "@/components/organisms/identity-list";
import { readAccount } from "@/lib/api/account";
import { ApiError } from "@/lib/api/errors";
import { readCsrfToken } from "@/lib/auth/session";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { Link } from "@/lib/i18n/navigation";
import { Icon } from "@/theme";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export default async function AccountPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/account`);
  const t = await getTranslations("account");
  const tc = await getTranslations("common");
  const tg = await getTranslations("githubConnector");
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

  const primaryIdentity = profile.identities[0];
  const displayName = profile.display_name || primaryIdentity?.display_name || profile.account_id;
  const avatarUrl = primaryIdentity?.avatar_url ?? null;
  const profileVisibility = profile.show_profile_publicly ? tc("public") : tc("private");

  return (
    <div className="min-w-0 space-y-8">
      <nav aria-label={t("settingsBreadcrumb")} className="flex items-center gap-2 text-sm">
        <span className="text-muted-foreground">{t("settingsBreadcrumb")}</span>
        <Icon name="chevronRight" size="sm" className="text-muted-foreground" />
        <span aria-current="page" className="font-medium">
          {t("title")}
        </span>
      </nav>

      <header className="space-y-2">
        <h1 className="text-3xl font-medium tracking-tight sm:text-4xl">{t("title")}</h1>
        <p className="text-muted-foreground text-base">{t("subtitle")}</p>
      </header>

      <div className="grid items-stretch gap-5 lg:grid-cols-[1.12fr_0.88fr]">
        <section className="border-border bg-card flex min-w-0 flex-col gap-7 rounded-lg border p-5 shadow-sm sm:p-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="space-y-1">
              <h2 className="text-2xl font-medium tracking-tight">{t("profile")}</h2>
              <p className="text-muted-foreground text-sm">{t("profileAccountHint")}</p>
            </div>
            <Badge variant={profile.show_profile_publicly ? "success" : "secondary"}>
              <Icon name="globe" size="sm" />
              {profileVisibility}
            </Badge>
          </div>

          <div className="flex flex-col gap-5 sm:flex-row sm:items-center">
            <AvatarImage
              src={avatarUrl}
              width={96}
              height={96}
              className="border-primary bg-muted ring-primary/10 size-24 rounded-full border-2 object-cover ring-4"
              fallback={
                <span className="border-primary bg-muted text-foreground ring-primary/10 grid size-24 place-items-center rounded-full border-2 text-xl font-medium uppercase ring-4">
                  {displayName.slice(0, 2)}
                </span>
              }
            />
            <div className="min-w-0 space-y-1">
              <h3 className="text-2xl font-medium tracking-tight break-words">{displayName}</h3>
              <p className="text-muted-foreground">{t("publisherOn")}</p>
            </div>
          </div>

          <div className="border-border border-t pt-5">
            <div className="space-y-2">
              <p className="text-muted-foreground text-sm">{t("accountId")}</p>
              <div className="border-input bg-background min-w-0 rounded-sm border px-3 py-1.5 [&>div]:w-full [&>div]:justify-between">
                <CopyValue
                  value={profile.account_id}
                  label={t("copyAccountId")}
                  copied={tc("copied")}
                />
              </div>
              <p className="text-muted-foreground text-xs">{t("accountIdHint")}</p>
            </div>
          </div>

          <div className="flex flex-col gap-3 pt-1 sm:flex-row sm:flex-wrap">
            <Button asChild className="min-h-11 w-full sm:w-auto">
              <Link href="/account/profile">{t("editProfile")}</Link>
            </Button>
            <Button asChild variant="outline" className="min-h-11 w-full sm:w-auto">
              <Link href={`/publishers/${profile.account_id}`}>{t("viewPublicProfile")}</Link>
            </Button>
          </div>
        </section>

        <div className="flex min-w-0 flex-col gap-5">
          <section className="border-border bg-card min-w-0 rounded-lg border p-5 shadow-sm sm:p-6">
            <div className="space-y-1">
              <h2 className="text-2xl font-medium tracking-tight">{t("signInMethods")}</h2>
              <p className="text-muted-foreground text-sm">{t("signInMethodsHint")}</p>
            </div>
            <div className="mt-5">
              <IdentityList
                identities={profile.identities}
                csrfToken={csrfToken}
                returnTo={`/${locale}/account`}
              />
            </div>
            <div className="border-border mt-6 space-y-3 border-t pt-5">
              <div className="space-y-1">
                <h3 className="font-medium">{tg("title")}</h3>
                <p className="text-muted-foreground text-xs">{tg("accountHint")}</p>
              </div>
              <GitHubConnectionLink csrfToken={csrfToken} compact />
            </div>
          </section>

          <section className="border-border bg-card min-w-0 rounded-lg border p-5 shadow-sm sm:p-6">
            <div className="space-y-1">
              <h2 className="text-2xl font-medium tracking-tight">{t("privacy")}</h2>
              <p className="text-muted-foreground text-sm">{t("privacySubtitle")}</p>
            </div>
            <div className="border-border mt-5 flex min-w-0 items-center gap-3 rounded-lg border p-3">
              <span className="bg-muted text-muted-foreground grid size-10 shrink-0 place-items-center rounded-full">
                <Icon name="lock" size="md" />
              </span>
              <p className="min-w-0 flex-1 text-sm font-medium">{t("editPrivacy")}</p>
              <Button asChild variant="outline" className="min-h-11 shrink-0">
                <Link href="/account/privacy">{t("editPrivacy")}</Link>
              </Button>
            </div>
          </section>
        </div>
      </div>

      <section className="border-border bg-card flex flex-col gap-4 rounded-lg border p-5 shadow-sm sm:flex-row sm:items-center sm:justify-between sm:p-6">
        <div className="space-y-1">
          <h2 className="text-xl font-medium tracking-tight">{t("dangerZone")}</h2>
          <p className="text-muted-foreground text-sm">{t("signOutHint")}</p>
        </div>
        <form action={`/api/auth/logout?locale=${locale}`} method="post">
          <Button type="submit" variant="destructive" className="min-h-11 w-full sm:w-auto">
            {tn("logout")}
          </Button>
        </form>
      </section>
    </div>
  );
}
