import { getTranslations, setRequestLocale } from "next-intl/server";
import { CorporateReportCard } from "@/components/organisms/corporate-report-card";
import { StatePanel } from "@/components/molecules/state-panel";
import { readCorporateContext } from "@/lib/api/corporate";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";

export default async function CorporateReportsPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/reports`);
  const t = await getTranslations("corporateReports");
  const token = await sessionCookieValue();
  const context = token ? await readCorporateContext(token) : null;
  if (!context?.capabilities.includes("telemetry.read"))
    return <StatePanel kind="empty" title={t("title")} />;

  const rows = [
    [t("device"), t("employee"), t("status"), t("lastSeen")],
    ["MacBook", "A. Smith", "●", "—"],
    ["ThinkPad", "I. Brown", "●", "—"],
    ["Desktop", "M. Lee", "●", "—"],
  ];
  const heartbeatPreview = (
    <table className="w-full text-left text-[10px]">
      <tbody>
        {rows.map((row, index) => (
          <tr key={index} className="border-border border-b last:border-0">
            {row.map((cell, column) => (
              <td
                key={column}
                className={`py-2 pr-2 ${index === 0 ? "text-muted-foreground" : ""}`}
              >
                {cell}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
  const bars = (widths: number[]) => (
    <div className="flex h-full min-h-36 items-end gap-2">
      {widths.map((width, index) => (
        <span
          key={index}
          className="bg-muted block flex-1 rounded-t-sm"
          style={{ height: `${width}%` }}
        />
      ))}
    </div>
  );
  const usagePreview = (
    <div className="flex h-full flex-col">
      {bars([36, 48, 44, 63, 56, 74, 67, 85])}
      <div className="text-muted-foreground mt-2 flex justify-between">
        <span>{t("team")} 8</span>
        <span>{t("employee")} 36</span>
      </div>
    </div>
  );
  const providerPreview = (
    <table className="w-full text-left text-[10px]">
      <tbody>
        {[
          [t("providerName"), t("status"), t("lastSeen"), t("issues")],
          ["Codex", t("active"), "12m", "—"],
          ["Claude", t("active"), "28m", "—"],
          ["Gemini", t("stale"), "2h", "1"],
        ].map((row, index) => (
          <tr key={index} className="border-border border-b last:border-0">
            {row.map((cell, column) => (
              <td key={column} className="py-2 pr-2">
                {cell}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
  const coveragePreview = (
    <div className="flex h-full flex-col justify-center gap-4">
      {[74, 58, 82, 42, 65].map((width, index) => (
        <span
          key={index}
          className="bg-muted block h-2 rounded-sm"
          style={{ width: `${width}%` }}
        />
      ))}
    </div>
  );
  const cards = [
    {
      key: "heartbeat",
      description: "heartbeatDescription",
      href: "/corporate/reports/heartbeat",
      preview: heartbeatPreview,
    },
    {
      key: "usage",
      description: "usageDescription",
      href: "/corporate/reports/usage",
      preview: usagePreview,
    },
    {
      key: "coverage",
      description: "coverageDescription",
      href: "/corporate/reports/coverage",
      preview: coveragePreview,
    },
    {
      key: "provider",
      description: "providerDescription",
      href: "/corporate/reports/provider",
      preview: providerPreview,
    },
  ] as const;
  return (
    <main className="mx-auto w-full max-w-6xl space-y-7 px-4 py-8 sm:px-6">
      <div>
        <h1 className="text-3xl font-medium tracking-tight">{t("title")}</h1>
        <p className="text-muted-foreground mt-2">{t("subtitle")}</p>
      </div>
      <div className="grid gap-5 lg:grid-cols-2">
        {cards.map(({ key, description, href, preview }) => (
          <CorporateReportCard
            key={key}
            title={t(key)}
            description={t(description)}
            href={href}
            openLabel={t("open")}
            preview={preview}
          />
        ))}
      </div>
    </main>
  );
}
