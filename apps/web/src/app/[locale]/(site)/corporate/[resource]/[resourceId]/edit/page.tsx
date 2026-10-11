import { CorporateEntityEditPage } from "@/app/[locale]/(site)/corporate/[resource]/[resourceId]/edit-content";
export default async function EditPage({
  params,
}: {
  params: Promise<{ locale: string; resource: string; resourceId: string }>;
}) {
  return <CorporateEntityEditPage {...await params} />;
}
