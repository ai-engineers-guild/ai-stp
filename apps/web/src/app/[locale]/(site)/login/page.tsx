import { getTranslations, setRequestLocale } from "next-intl/server";

import { mockLoginCancelAction, mockLoginErrorAction, startLoginAction } from "@/actions/auth";
import { Button } from "@/components/atoms/button";
import { CliCopyBlock } from "@/components/molecules/cli-copy-block";
import { StatePanel } from "@/components/molecules/state-panel";
import { login } from "@/lib/cli-copy";
import { getEnv } from "@/lib/env";
import { Icon } from "@/theme";

type PageProps = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{
    returnTo?: string;
    status?: string;
    reason?: string;
    debug?: string;
  }>;
};

function oauthLoginHref(provider: "google" | "github", returnTo: string): string {
  const params = new URLSearchParams({
    client: "web",
    return_to: returnTo,
  });
  return `/v1/auth/${provider}/login?${params.toString()}`;
}

/**
 * Login UX (SPEC-023, ADR-0041). Provider buttons always render.
 * Real OAuth uses same-origin /v1/auth/... (Next rewrite to API in dev; Caddy
 * path split in staging/prod). Offline e2e keeps mock forms when
 * AI_STP_USE_MOCKS is true. OAuth status=error|cancel|conflict is driven by
 * the callback query. Mock error/cancel simulators stay behind a test-only
 * gate: AI_STP_USE_MOCKS and ?debug=1.
 */
export default async function LoginPage({ params, searchParams }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const sp = await searchParams;
  const t = await getTranslations("login");
  const tc = await getTranslations("common");
  const tCli = await getTranslations("cli");
  const env = getEnv();
  const showMockSimulators = env.AI_STP_USE_MOCKS && sp.debug === "1";
  const useMockLogin = env.AI_STP_USE_MOCKS;
  const defaultReturn = `/${locale}/account`;
  const returnTo = sp.returnTo && sp.returnTo.startsWith("/") ? sp.returnTo : defaultReturn;

  return (
    <div className="mx-auto w-full max-w-md min-w-0 space-y-6">
      <div className="space-y-2">
        <h1 className="text-2xl font-medium tracking-tight sm:text-3xl">{t("title")}</h1>
        <p className="text-muted-foreground text-sm leading-relaxed sm:text-base">
          {t("subtitle")}
        </p>
      </div>

      {sp.reason === "session_expired" ? (
        <StatePanel kind="error" title={tc("sessionExpired")} />
      ) : null}
      {sp.status === "error" ? <StatePanel kind="error" title={t("error")} /> : null}
      {sp.status === "cancel" ? <StatePanel kind="empty" title={t("cancel")} /> : null}
      {sp.status === "conflict" ? <StatePanel kind="error" title={t("conflict")} /> : null}

      <div className="flex flex-col gap-3">
        {useMockLogin ? (
          <>
            <form
              action={async () => {
                "use server";
                await startLoginAction("google", {
                  locale,
                  returnTo,
                });
              }}
            >
              <Button type="submit" className="min-h-11 w-full">
                <Icon name="google" size="sm" />
                {t("google")}
              </Button>
            </form>
            <form
              action={async () => {
                "use server";
                await startLoginAction("github", {
                  locale,
                  returnTo,
                });
              }}
            >
              <Button type="submit" variant="secondary" className="min-h-11 w-full">
                <Icon name="github" size="sm" />
                {t("github")}
              </Button>
            </form>
          </>
        ) : (
          <>
            <Button asChild className="min-h-11 w-full">
              <a href={oauthLoginHref("google", returnTo)}>
                <Icon name="google" size="sm" />
                {t("google")}
              </a>
            </Button>
            <Button asChild variant="secondary" className="min-h-11 w-full">
              <a href={oauthLoginHref("github", returnTo)}>
                <Icon name="github" size="sm" />
                {t("github")}
              </a>
            </Button>
          </>
        )}
        <CliCopyBlock
          command={login("github")}
          title={tCli("loginHint")}
          copyLabel={tCli("copy")}
          copiedLabel={tCli("copied")}
          errorLabel={tCli("copyError")}
          docsLabel={tCli("docs")}
        />
        {showMockSimulators ? (
          <>
            <form
              action={async () => {
                "use server";
                await mockLoginErrorAction(locale);
              }}
            >
              <Button
                type="submit"
                variant="ghost"
                className="w-full"
                name="simulate"
                value="error"
              >
                {t("error")}
              </Button>
            </form>
            <form
              action={async () => {
                "use server";
                await mockLoginCancelAction(locale);
              }}
            >
              <Button
                type="submit"
                variant="ghost"
                className="w-full"
                name="simulate"
                value="cancel"
              >
                {t("cancel")}
              </Button>
            </form>
          </>
        ) : null}
      </div>
    </div>
  );
}
