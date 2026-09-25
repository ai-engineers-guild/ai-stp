import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";
import { Link } from "@/lib/i18n/navigation";
import { requireSession } from "@/lib/auth/require-session";

export default async function FutureCorporateReport({
  params,
}: {
  params: Promise<{ locale: string; report: string }>;
}) {
  const { locale, report } = await params;
  if (report !== "usage" && report !== "coverage" && report !== "provider") notFound();
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/reports/${report}`);
  const t = await getTranslations("corporateReports");
  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-8 sm:px-6">
      <Link href="/corporate/reports" className="text-muted-foreground underline">
        {t("title")}
      </Link>
      <h1 className="mt-6 text-3xl font-medium">{t(report)}</h1>
      <p className="text-muted-foreground mt-2">{t("later")}</p>
    </main>
  );
}
