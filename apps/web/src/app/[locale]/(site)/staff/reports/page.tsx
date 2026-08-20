import { getTranslations, setRequestLocale } from "next-intl/server";

import { Badge } from "@/components/atoms/badge";
import { StatePanel } from "@/components/molecules/state-panel";
import { ApiError } from "@/lib/api/errors";
import { listStaffReports } from "@/lib/api/reports";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { Link } from "@/lib/i18n/navigation";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export default async function StaffReportsPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/staff/reports`);
  const t = await getTranslations("staff");
  const tc = await getTranslations("common");
  const token = await sessionCookieValue();

  let list;
  try {
    list = await listStaffReports(token ?? "");
  } catch (error) {
    if (error instanceof ApiError && (error.status === 403 || error.code === "AI_STP_FORBIDDEN")) {
      return <StatePanel kind="error" title={t("forbidden")} description={t("subtitle")} />;
    }
    if (error instanceof ApiError && error.code === "AI_STP_UNAVAILABLE") {
      return <StatePanel kind="error" title={tc("error")} description={tc("apiUnavailable")} />;
    }
    throw error;
  }

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="text-3xl font-medium tracking-tight">{t("title")}</h1>
        <p className="text-muted-foreground max-w-2xl text-sm">{t("subtitle")}</p>
      </div>

      {list.items.length === 0 ? (
        <StatePanel kind="empty" title={tc("empty")} description={t("empty")} />
      ) : (
        <ul className="divide-border border-border divide-y rounded-lg border">
          {list.items.map((item) => (
            <li key={item.case_id}>
              <Link
                href={`/staff/reports/${item.case_id}`}
                className="hover:bg-muted/40 flex flex-col gap-2 px-4 py-3 transition-colors sm:flex-row sm:items-center sm:justify-between"
                prefetch={false}
              >
                <div className="min-w-0 space-y-1">
                  <p className="font-mono text-xs">{item.case_id}</p>
                  <p className="text-muted-foreground font-mono text-xs">
                    {item.object_kind} / {item.stable_id} / {item.version}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Badge variant="outline" className="font-mono text-xs">
                    {item.state}
                  </Badge>
                  {item.vulnerability ? (
                    <Badge variant="warning" className="font-mono text-xs">
                      {t("vulnerability")}
                    </Badge>
                  ) : null}
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
