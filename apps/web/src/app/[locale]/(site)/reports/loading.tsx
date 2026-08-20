import { getTranslations } from "next-intl/server";

import { RouteLoading } from "@/components/molecules/route-loading";

export default async function ReportsLoading() {
  const t = await getTranslations("common");
  return <RouteLoading label={t("loading")} />;
}
