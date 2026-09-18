import { getTranslations, setRequestLocale } from "next-intl/server";
import { requireSession } from "@/lib/auth/require-session";

export default async function CorporateDashboard({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/dashboard`);
  const t = await getTranslations("hub");
  return <h1 className="text-3xl font-medium tracking-tight sm:text-4xl">{t("dashboard")}</h1>;
}
