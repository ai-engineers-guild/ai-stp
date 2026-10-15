import CorporateResourcePage from "@/app/[locale]/(site)/corporate/[resource]/[resourceId]/page";
import GrantModal from "@/app/[locale]/(site)/@modal/(.)corporate/employees/[resourceId]/access/page";
export default async function EmployeeAccess({
  params,
}: {
  params: Promise<{ locale: string; resourceId: string }>;
}) {
  const values = await params;
  return (
    <>
      <CorporateResourcePage
        params={Promise.resolve({ ...values, resource: "employees" })}
        searchParams={Promise.resolve({})}
      />
      <GrantModal params={params} />
    </>
  );
}
