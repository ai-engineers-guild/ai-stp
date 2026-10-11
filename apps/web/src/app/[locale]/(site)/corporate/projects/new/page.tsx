import { CorporateCreatePage } from "@/components/screens/corporate-create-page";

export default async function NewCorporateProjectPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  return <CorporateCreatePage resource="projects" locale={(await params).locale} />;
}
