import { RegistryEditContent } from "@/app/[locale]/(site)/corporate/registry-edit-content";
import DetailPage from "@/app/[locale]/(site)/corporate/technologies/[technologyId]/page";
export default async function EditPage({
  params,
}: {
  params: Promise<{ locale: string; technologyId: string }>;
}) {
  const values = await params;
  return (
    <>
      <DetailPage params={params} />
      <RegistryEditContent locale={values.locale} kind="technology" id={values.technologyId} />
    </>
  );
}
