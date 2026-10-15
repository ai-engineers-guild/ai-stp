import { getTranslations } from "next-intl/server";
import { RouteDialog } from "@/components/molecules/route-dialog";
import { CorporateCreatePage } from "@/components/screens/corporate-create-page";
export default async function CreateModal({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  const t = await getTranslations("hub");
  return (
    <RouteDialog title={t("addProject")}>
      <CorporateCreatePage embedded resource="projects" locale={locale} />
    </RouteDialog>
  );
}
