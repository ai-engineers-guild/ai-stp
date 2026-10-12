import CorporateDirectoryPage from "@/app/[locale]/(site)/corporate/[resource]/page";
import { RouteDialog } from "@/components/molecules/route-dialog";
import { getTranslations } from "next-intl/server";
import { CorporateCreatePage } from "@/components/screens/corporate-create-page";

export default async function NewCorporateTeamPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const locale = (await params).locale;
  const h = await getTranslations("hub");
  return (
    <>
      <CorporateDirectoryPage
        params={Promise.resolve({ locale, resource: "teams" })}
        searchParams={Promise.resolve({})}
      />
      <RouteDialog title={h("addTeam")} fallback="/corporate/teams">
        <CorporateCreatePage embedded resource="teams" locale={locale} />
      </RouteDialog>
    </>
  );
}
