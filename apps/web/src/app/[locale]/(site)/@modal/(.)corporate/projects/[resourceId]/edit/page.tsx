import { CorporateEntityEditPage } from "@/app/[locale]/(site)/corporate/[resource]/[resourceId]/edit-content";
export default async function EditModal({
  params,
}: {
  params: Promise<{ locale: string; resourceId: string }>;
}) {
  return <CorporateEntityEditPage {...await params} resource="projects" />;
}
