import { RegistryEditContent } from "@/app/[locale]/(site)/corporate/registry-edit-content";
import DetailPage from "@/app/[locale]/(site)/corporate/categories/[categoryId]/page";
export default async function EditPage({
  params,
}: {
  params: Promise<{ locale: string; categoryId: string }>;
}) {
  const values = await params;
  return (
    <>
      <DetailPage params={params} />
      <RegistryEditContent locale={values.locale} kind="category" id={values.categoryId} />
    </>
  );
}
