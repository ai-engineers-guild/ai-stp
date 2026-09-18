import { CorporateCreatePage } from "@/components/organisms/corporate-create-page";

export default async function NewCorporateTeamPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  return <CorporateCreatePage resource="teams" locale={(await params).locale} />;
}
