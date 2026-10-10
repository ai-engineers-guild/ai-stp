import { redirect } from "next/navigation";
import { setRequestLocale } from "next-intl/server";

export default async function CategoryDirectoryRedirect({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const raw = (await searchParams).query;
  const query =
    typeof raw === "string" && raw ? `?query=${encodeURIComponent(raw)}` : "";
  redirect(`/${locale}/corporate/organization/admins/technology-categories${query}`);
}
