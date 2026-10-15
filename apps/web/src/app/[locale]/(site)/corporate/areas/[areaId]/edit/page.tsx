import { RegistryEditContent } from "@/app/[locale]/(site)/corporate/registry-edit-content";
import DetailPage from "@/app/[locale]/(site)/corporate/areas/[areaId]/page";
export default async function EditPage({
  params,
}: {
  params: Promise<{ locale: string; areaId: string }>;
}) {
  const values = await params;
  return (
    <>
      <DetailPage params={params} />
      <RegistryEditContent locale={values.locale} kind="area" id={values.areaId} />
    </>
  );
}
