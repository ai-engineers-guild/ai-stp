import { getTranslations } from "next-intl/server";

import { Button } from "@/components/atoms/button";
import { StatePanel } from "@/components/molecules/state-panel";
import { getEnv } from "@/lib/env";
import { Link } from "@/lib/i18n/navigation";

export default async function NotFound() {
  const t = await getTranslations("errors");
  const docsHref = getEnv().AI_STP_USER_DOCS_URL;
  return (
    <div className="space-y-6">
      <StatePanel kind="empty" title={t("notFoundTitle")} description={t("notFoundBody")} />
      <div className="flex flex-wrap gap-3">
        <Button asChild>
          <Link href="/catalog">{t("toCatalog")}</Link>
        </Button>
        <Button asChild variant="outline">
          <Link href="/">{t("toHome")}</Link>
        </Button>
        <Button asChild variant="outline">
          <a href={docsHref}>{t("toDocs")}</a>
        </Button>
      </div>
    </div>
  );
}
