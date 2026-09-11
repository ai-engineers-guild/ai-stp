import { getTranslations } from "next-intl/server";

import { ProjectionDockView } from "@/components/molecules/projection-dock-view";
import { readCanonicalPathname, readSearch } from "@/lib/projection/mode";
import { projectionSwitchHrefs } from "@/lib/projection/paths";

export async function ProjectionDock({
  locale,
  projection,
}: {
  locale: string;
  projection: "human" | "machine";
}) {
  const t = await getTranslations("theme");
  const pathname = (await readCanonicalPathname()) ?? `/${locale}`;
  const { humanHref, machineHref } = projectionSwitchHrefs(pathname, locale, await readSearch());

  return (
    <ProjectionDockView
      projection={projection}
      humanHref={humanHref}
      machineHref={machineHref}
      labels={{
        group: t("projectionLabel"),
        human: t("human"),
        machine: t("machine"),
      }}
    />
  );
}
