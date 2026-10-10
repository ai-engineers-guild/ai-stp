import { redirect } from "next/navigation";
import { setRequestLocale } from "next-intl/server";

export default async function CategoryDetailRedirect({
  params,
}: {
  params: Promise<{ locale: string; categoryId: string }>;
}) {
  const { locale, categoryId } = await params;
  setRequestLocale(locale);
  redirect(`/${locale}/corporate/organization/admins/technology-categories/${categoryId}`);
}
