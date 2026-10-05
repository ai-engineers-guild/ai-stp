import { getTranslations, setRequestLocale } from "next-intl/server";

import { StatePanel } from "@/components/molecules/state-panel";
import { GitLabConnector } from "@/components/organisms/gitlab-connector";
import { readAccount } from "@/lib/api/account";
import { readCorporateContext } from "@/lib/api/corporate";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";

export default async function CorporateGitLabPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const session = await requireSession(locale, `/${locale}/corporate/gitlab`);
  const token = (await sessionCookieValue()) ?? "";
  const t = await getTranslations("gitlabConnector");
  const context = await readCorporateContext(token);
  if (!context)
    return <StatePanel kind="empty" title={t("title")} description={t("unavailable")} />;
  const account = await readAccount(token);
  return (
    <GitLabConnector
      csrfToken={(await readCsrfToken()) ?? ""}
      organizationId={context.organization.organization_id}
      deviceId={session.deviceId}
      gitlabIdentityLinked={account.identities.some((identity) => identity.provider === "gitlab")}
      locale={locale === "ru" ? "ru" : "en"}
      capabilities={context.capabilities}
    />
  );
}
