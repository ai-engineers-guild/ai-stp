import { getTranslations, setRequestLocale } from "next-intl/server";
import { readCorporateContext } from "@/lib/api/corporate";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { Link } from "@/lib/i18n/navigation";
import { StatePanel } from "@/components/molecules/state-panel";
import { canViewCorporateSection } from "@/lib/corporate-hub";

export default async function OrganizationPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/organization`);
  const t = await getTranslations("hub");
  const context = await readCorporateContext((await sessionCookieValue()) ?? "");
  if (!context)
    return <StatePanel kind="empty" title={t("organization")} description={t("empty")} />;
  const sections = [
    { key: "employees", href: "/corporate/employees" },
    { key: "projects", href: "/corporate/projects" },
    { key: "teams", href: "/corporate/teams" },
    { key: "technologies", href: "/corporate/technologies" },
  ];
  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <h1 className="text-3xl font-medium tracking-tight">{context.organization.display_name}</h1>
        <p className="text-muted-foreground">{t("organizationBody")}</p>
      </header>
      <ul className="border-border divide-border divide-y rounded-lg border">
        {sections
          .filter((item) => canViewCorporateSection(item.key, context.capabilities))
          .map((item) => (
            <li key={item.key}>
              <Link
                href={item.href}
                className="hover:bg-muted focus-visible:ring-ring flex min-h-14 items-center p-4 font-medium focus-visible:ring-2"
              >
                {t(item.key)}
              </Link>
            </li>
          ))}
      </ul>
    </div>
  );
}
