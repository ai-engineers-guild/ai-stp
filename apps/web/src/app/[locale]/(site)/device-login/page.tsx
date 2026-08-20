import { getTranslations, setRequestLocale } from "next-intl/server";

import { approveDeviceCodeAction } from "@/actions/device-login";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import { StatePanel } from "@/components/molecules/state-panel";
import { readCsrfToken } from "@/lib/auth/session";
import { getOptionalSession } from "@/lib/auth/require-session";
import { Link } from "@/lib/i18n/navigation";

type PageProps = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ user_code?: string; status?: string }>;
};

export default async function DeviceLoginPage({ params, searchParams }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const sp = await searchParams;
  const t = await getTranslations("deviceLogin");

  const tc = await getTranslations("common");
  const session = await getOptionalSession();
  const csrf = (await readCsrfToken()) ?? "";
  const userCode = (sp.user_code ?? "").trim().toUpperCase();

  if (sp.status === "ok") {
    return (
      <div className="mx-auto max-w-md space-y-4">
        <h1 className="text-3xl font-medium tracking-tight">{t("title")}</h1>
        <StatePanel kind="empty" title={t("approved")} description={t("approvedHint")} />
      </div>
    );
  }

  if (!session) {
    const returnTo = `/${locale}/device-login${userCode ? `?user_code=${encodeURIComponent(userCode)}` : ""}`;
    return (
      <div className="mx-auto max-w-md space-y-4">
        <h1 className="text-3xl font-medium tracking-tight">{t("title")}</h1>
        <p className="text-muted-foreground">{t("needSignIn")}</p>
        <Button asChild>
          <Link href={`/login?returnTo=${encodeURIComponent(returnTo)}`}>{tc("login")}</Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-md space-y-6">
      <h1 className="text-3xl font-medium tracking-tight">{t("title")}</h1>
      <p className="text-muted-foreground">{t("subtitle")}</p>
      {sp.status === "error" ? (
        <StatePanel kind="error" title={t("error")} description={sp.status} />
      ) : null}
      <form
        action={async (formData) => {
          "use server";
          const rawCode = formData.get("user_code");
          const rawCsrf = formData.get("csrf");
          const code = typeof rawCode === "string" ? rawCode : "";
          const csrfToken = typeof rawCsrf === "string" ? rawCsrf : "";
          await approveDeviceCodeAction({
            userCode: code,
            csrfToken,
            locale,
          });
        }}
        className="space-y-4"
      >
        <input type="hidden" name="csrf" value={csrf} />
        <div className="space-y-1">
          <Label htmlFor="user_code">{t("userCode")}</Label>
          <Input
            id="user_code"
            name="user_code"
            defaultValue={userCode}
            required
            className="font-mono tracking-widest"
            autoComplete="one-time-code"
          />
        </div>
        <Button type="submit" className="w-full">
          {t("approve")}
        </Button>
      </form>
    </div>
  );
}
