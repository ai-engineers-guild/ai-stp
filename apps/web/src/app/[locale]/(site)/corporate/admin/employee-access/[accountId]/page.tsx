import { redirect } from "next/navigation";

/** The standalone employee page was folded into the directory drawer (`?employee=`). */
export default async function EmployeeAccessRedirect({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string; accountId: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { locale, accountId } = await params;
  const filters = await searchParams;
  const query = new URLSearchParams();
  query.set("employee", accountId);
  if (typeof filters.scope === "string") query.set("scope", filters.scope);
  redirect(`/${locale}/corporate/admin/employee-access?${query.toString()}`);
}
