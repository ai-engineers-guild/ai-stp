"use client";

import { useTranslations } from "next-intl";
import { useSearchParams } from "next/navigation";

import { usePathname } from "@/lib/i18n/navigation";
import { isMachinePagePath, projectionSwitchHrefs } from "@/lib/projection/paths";
import { UI } from "@/lib/ui-selectors";

type ProjectionDockProps = {
  locale: string;
};

/**
 * Fixed projection switcher as plain links (REQ-3604). Path comes from the
 * live router, not from layout-time x-pathname: the shared (site) layout does
 * not re-render on catalog → component navigation, so a header-baked pair
 * would keep sending the switch to /catalog.
 */
export function ProjectionDock({ locale }: ProjectionDockProps) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const t = useTranslations("theme");
  const search = searchParams.toString();
  const { humanHref, machineHref } = projectionSwitchHrefs(
    pathname,
    locale,
    search ? `?${search}` : "",
  );
  const projection = isMachinePagePath(pathname) ? "machine" : "human";

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

function ProjectionDockView({
  projection,
  humanHref,
  machineHref,
  labels,
}: {
  projection: "human" | "machine";
  humanHref: string;
  machineHref: string;
  labels: { group: string; human: string; machine: string };
}) {
  const optionStyle = (active: boolean) => ({ opacity: active ? 1 : 0.9 });

  return (
    <aside
      data-ui={UI.projection.toggle}
      className="projection-dock inline-grid grid-cols-2 gap-2 rounded-sm px-2 py-1"
      aria-label={labels.group}
      // Placement is inline so a stale cached stylesheet can never drop the
      // dock into the document flow below the footer.
      style={{
        position: "fixed",
        insetBlockEnd: "1.5rem",
        insetInlineStart: "50%",
        transform: "translateX(-50%)",
        zIndex: 50,
      }}
    >
      <a
        data-ui={UI.projection.human}
        href={humanHref}
        aria-current={projection === "human" ? "true" : undefined}
        style={optionStyle(projection === "human")}
        className="projection-dock__option focus-visible:ring-ring inline-flex h-7 min-w-16 items-center justify-center gap-2 rounded-sm px-2 font-mono text-xs font-medium uppercase transition-opacity focus-visible:ring-2 focus-visible:outline-none max-sm:h-11"
      >
        <span
          aria-hidden
          className="projection-dock__dot size-2.5 rounded-full border border-current"
        />
        {labels.human}
      </a>
      <a
        data-ui={UI.projection.machine}
        href={machineHref}
        aria-current={projection === "machine" ? "true" : undefined}
        style={optionStyle(projection === "machine")}
        className="projection-dock__option focus-visible:ring-ring inline-flex h-7 min-w-16 items-center justify-center gap-2 rounded-sm px-2 font-mono text-xs font-medium uppercase transition-opacity focus-visible:ring-2 focus-visible:outline-none max-sm:h-11"
      >
        <span
          aria-hidden
          className="projection-dock__dot size-2.5 rounded-full border border-current"
        />
        {labels.machine}
      </a>
    </aside>
  );
}
