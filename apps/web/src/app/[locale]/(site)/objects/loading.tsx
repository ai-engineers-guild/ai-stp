import { getTranslations } from "next-intl/server";

import { RouteLoading } from "@/components/molecules/route-loading";

export default async function ObjectsLoading() {
  const t = await getTranslations("common");
  return <RouteLoading label={t("loading")} />;
}
