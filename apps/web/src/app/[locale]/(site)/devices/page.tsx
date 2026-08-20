import { getTranslations, setRequestLocale } from "next-intl/server";
import { redirect } from "next/navigation";

import { approveDeviceCodeAction } from "@/actions/device-login";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import { DeviceList } from "@/components/organisms/device-list";
import { StatePanel } from "@/components/molecules/state-panel";
import { listDevices } from "@/lib/api/devices";
import { ApiError } from "@/lib/api/errors";
import { readCsrfToken } from "@/lib/auth/session";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";

type PageProps = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ status?: string; user_code?: string }>;
};

export default async function DevicesPage({ params, searchParams }: PageProps) {
  const { locale } = await params;
  const sp = await searchParams;
  setRequestLocale(locale);
  const session = await requireSession(locale, `/${locale}/devices`);
  const t = await getTranslations("devices");
  const tc = await getTranslations("common");
  const td = await getTranslations("deviceLogin");
  const token = await sessionCookieValue();

  const csrf = await readCsrfToken();
  if (!csrf) {
    // Session without a CSRF cookie is an incomplete session; re-establish it
    // via the logout route handler (cookies cannot be set during render).
    const params = new URLSearchParams({
      locale,
      returnTo: `/${locale}/devices`,
      reason: "session_expired",
    });
    redirect(`/api/auth/logout?${params.toString()}`);
  }

  let devices;
  try {
    devices = await listDevices(token ?? "");
  } catch (error) {
    if (error instanceof ApiError && error.code === "AI_STP_UNAVAILABLE") {
      return <StatePanel kind="error" title={tc("error")} description={tc("apiUnavailable")} />;
    }
    throw error;
  }

  return (
    <div className="space-y-10">
      <header className="space-y-2">
        <h1 className="text-3xl font-medium tracking-tight">{t("title")}</h1>
        <p className="text-muted-foreground max-w-2xl">{t("subtitle")}</p>
      </header>

      <DeviceList devices={devices.items} currentDeviceId={session.deviceId} csrfToken={csrf} />

      <section
        aria-labelledby="authorize-device-heading"
        className="border-border bg-card text-card-foreground space-y-5 rounded-lg border p-6 shadow-sm"
      >
        <div className="space-y-2">
          <h2 id="authorize-device-heading" className="text-lg font-medium tracking-tight">
            {t("authorizeTitle")}
          </h2>
          <p className="text-muted-foreground max-w-3xl text-sm">
            {t.rich("authorizeHint", {
              command: (chunks) => <code className="font-mono text-xs">{chunks}</code>,
            })}
          </p>
        </div>

        {sp.status === "ok" ? (
          <StatePanel kind="empty" title={td("approved")} description={td("approvedHint")} />
        ) : null}
        {sp.status === "error" ? (
          <StatePanel kind="error" title={td("error")} description={t("codeErrorHint")} />
        ) : null}

        <form
          action={async (formData) => {
            "use server";
            const rawCode = formData.get("user_code");
            const rawCsrf = formData.get("csrf");
            await approveDeviceCodeAction({
              userCode: typeof rawCode === "string" ? rawCode : "",
              csrfToken: typeof rawCsrf === "string" ? rawCsrf : "",
              locale,
              destination: "devices",
            });
          }}
          className="space-y-4"
        >
          <input type="hidden" name="csrf" value={csrf} />
          <div className="space-y-2">
            <Label htmlFor="user_code">{t("deviceCode")}</Label>
            <Input
              id="user_code"
              name="user_code"
              defaultValue={(sp.user_code ?? "").trim().toUpperCase()}
              required
              autoComplete="one-time-code"
              placeholder="ABCD-EFGH"
              className="font-mono tracking-[0.12em]"
            />
          </div>
          <Button type="submit" className="w-full">
            {t("confirmDevice")}
          </Button>
        </form>
      </section>
    </div>
  );
}
