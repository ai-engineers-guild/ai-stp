import { getTranslations, setRequestLocale } from "next-intl/server";
import { readCorporateContext } from "@/lib/api/corporate";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { Link } from "@/lib/i18n/navigation";
import { StatePanel } from "@/components/molecules/state-panel";

export default async function CorporateOverview({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate`);
  const t = await getTranslations("hub");
  const context = await readCorporateContext((await sessionCookieValue()) ?? "");
  if (!context)
    return <StatePanel kind="empty" title={t("organization")} description={t("empty")} />;
  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <h1 className="text-3xl font-medium tracking-tight">{context.organization.display_name}</h1>
        <p className="text-muted-foreground">{t("overviewBody")}</p>
      </header>
      <ul className="border-border divide-border divide-y rounded-lg border">
        {[
          { key: "organization", href: "/corporate/organization" },
          { key: "landscape", href: "/corporate/technology-landscape" },
        ].map((item) => (
          <li key={item.key}>
            <Link
              href={item.href}
              className="hover:bg-muted focus-visible:ring-ring flex min-h-16 items-center p-5 text-xl font-medium focus-visible:ring-2"
            >
              {t(item.key)}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
