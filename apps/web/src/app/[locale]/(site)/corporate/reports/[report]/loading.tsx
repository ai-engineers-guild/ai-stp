import { getTranslations } from "next-intl/server";

import { RouteLoading } from "@/components/molecules/route-loading";

export default async function CorporateReportLoading() {
  const t = await getTranslations("corporateReports");
  return <RouteLoading label={t("loadingReport")} />;
}
