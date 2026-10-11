import { redirect } from "next/navigation";
export default async function EmployeeAccess({
  params,
}: {
  params: Promise<{ locale: string; resourceId: string }>;
}) {
  const { locale, resourceId } = await params;
  redirect(`/${locale}/corporate/admin/employee-access?employee=${encodeURIComponent(resourceId)}`);
}
