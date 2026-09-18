import { CorporateCreatePage } from "@/components/organisms/corporate-create-page";

export default async function NewCorporateEmployeePage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  return <CorporateCreatePage resource="members" locale={(await params).locale} />;
}
