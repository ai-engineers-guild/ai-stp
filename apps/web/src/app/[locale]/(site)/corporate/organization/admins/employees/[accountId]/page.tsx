import { setRequestLocale } from "next-intl/server";

import { requireSession } from "@/lib/auth/require-session";

import { EmployeeAccessView } from "../employee-access-view";

export default async function EmployeeAccessPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string; accountId: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { locale, accountId } = await params;
  const filters = await searchParams;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/organization/admins/employees/${accountId}`);
  return (
    <EmployeeAccessView
      accountId={accountId}
      filters={filters}
      embedded={filters.embedded === "1"}
    />
  );
}
