"use client";

import { useEffect } from "react";
import { useSearchParams } from "next/navigation";

import { usePathname } from "@/lib/i18n/navigation";
import { isMachinePagePath, projectionSwitchHrefs } from "@/lib/projection/paths";
import { UI } from "@/lib/ui-selectors";

export function ProjectionDockEnhancer({ locale }: { locale: string }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();

  useEffect(() => {
    const dock = document.querySelector<HTMLElement>(`[data-ui="${UI.projection.toggle}"]`);
    if (!dock) return;

    const { humanHref, machineHref } = projectionSwitchHrefs(
      pathname,
      locale,
      searchParams.toString(),
    );
    const machine = isMachinePagePath(pathname);
    const links = [
      {
        element: dock.querySelector<HTMLAnchorElement>(`[data-ui="${UI.projection.human}"]`),
        href: humanHref,
        active: !machine,
      },
      {
        element: dock.querySelector<HTMLAnchorElement>(`[data-ui="${UI.projection.machine}"]`),
        href: machineHref,
        active: machine,
      },
    ];
    for (const link of links) {
      if (!link.element) continue;
      link.element.href = link.href;
      if (link.active) {
        link.element.setAttribute("aria-current", "true");
      } else {
        link.element.removeAttribute("aria-current");
      }
      link.element.style.opacity = link.active ? "1" : "0.9";
    }
  }, [locale, pathname, searchParams]);

  return null;
}
