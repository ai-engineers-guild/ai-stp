import { RegistryEditContent } from "@/app/[locale]/(site)/corporate/registry-edit-content";
export default async function EditPage({
  params,
}: {
  params: Promise<{ locale: string; categoryId: string }>;
}) {
  const values = await params;
  return <RegistryEditContent locale={values.locale} kind="category" id={values.categoryId} />;
}
