import { CorporateCreatePage } from "@/components/screens/corporate-create-page";

export default async function NewCorporateTeamPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  return <CorporateCreatePage resource="teams" locale={(await params).locale} />;
}
