import CorporateResourcePage from "@/app/[locale]/(site)/corporate/[resource]/[resourceId]/page";
import { CorporateEntityEditPage } from "@/app/[locale]/(site)/corporate/[resource]/[resourceId]/edit-content";
export default async function EditPage({
  params,
}: {
  params: Promise<{ locale: string; resource: string; resourceId: string }>;
}) {
  return (
    <>
      <CorporateResourcePage params={params} searchParams={Promise.resolve({})} />
      <CorporateEntityEditPage {...await params} />
    </>
  );
}
