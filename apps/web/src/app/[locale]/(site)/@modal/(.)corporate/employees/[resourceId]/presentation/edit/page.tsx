import { RouteDialog } from "@/components/molecules/route-dialog";
import CorporatePresentationEditPage from "@/app/[locale]/(site)/corporate/[resource]/[resourceId]/presentation/edit-content";
import { getTranslations } from "next-intl/server";
export default async function EmployeePresentationModal({
  params,
}: {
  params: Promise<{ locale: string; resourceId: string }>;
}) {
  const data = await params;
  const t = await getTranslations("corporate");
  return (
    <RouteDialog title={t("edit")}>
      <CorporatePresentationEditPage
        embedded
        params={Promise.resolve({ ...data, resource: "employees" })}
      />
    </RouteDialog>
  );
}
