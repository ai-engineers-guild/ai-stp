import CorporateDirectoryPage from "@/app/[locale]/(site)/corporate/[resource]/page";
import { RouteDialog } from "@/components/molecules/route-dialog";
import { getTranslations } from "next-intl/server";
import { CorporateCreatePage } from "@/components/screens/corporate-create-page";

export default async function NewCorporateEmployeePage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const locale = (await params).locale;
  const h = await getTranslations("hub");
  return (
    <>
      <CorporateDirectoryPage
        params={Promise.resolve({ locale, resource: "employees" })}
        searchParams={Promise.resolve({})}
      />
      <RouteDialog title={h("addEmployee")} fallback="/corporate/employees">
        <CorporateCreatePage embedded resource="members" locale={locale} />
      </RouteDialog>
    </>
  );
}
