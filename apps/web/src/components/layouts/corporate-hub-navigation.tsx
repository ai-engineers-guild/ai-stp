"use client";

import { useTranslations } from "next-intl";
import { usePathname } from "@/lib/i18n/navigation";
import { canViewCorporateSection } from "@/lib/corporate-hub";
import { NavigationTabs } from "@/components/molecules/navigation-tabs";
import { UI } from "@/lib/ui-selectors";

const organization = [
  { key: "projects", href: "/corporate/projects" },
  { key: "teams", href: "/corporate/teams" },
  { key: "employees", href: "/corporate/members" },
  { key: "technologies", href: "/corporate/technologies" },
] as const;
const landscape = [
  { key: "components", href: "/corporate/components" },
  { key: "technologies", href: "/corporate/technology-landscape" },
  { key: "categories", href: "/corporate/categories" },
] as const;

export function CorporateHubNavigation({ capabilities }: { capabilities: readonly string[] }) {
  const t = useTranslations("hub");
  const path = usePathname();
  if (path === "/corporate" || path === "/corporate/overview") return null;
  const inLandscape = /\/corporate\/(components|categories|technology-landscape)(?:\/|$)/.test(
    path,
  );
  const inOrganization =
    /\/corporate\/(organization|members|projects|teams|technologies)(?:\/|$)/.test(path);
  const activeSection =
    path === "/corporate/dashboard" ? "dashboard" : inLandscape ? "landscape" : "organization";
  if (
    (activeSection !== "organization" && activeSection !== "landscape") ||
    (!inOrganization && !inLandscape)
  )
    return null;
  const items = inLandscape ? landscape : organization;
  if (path !== "/corporate/organization" && !items.some((item) => path === item.href)) {
    return null;
  }

  return (
    <div
      data-ui={UI.navigation.secondaryNav}
      className="border-border -mx-4 -mt-6 mb-6 border-b sm:-mx-6"
    >
      <NavigationTabs
        ariaLabel={t(activeSection)}
        className="mx-auto max-w-6xl px-4 sm:px-6"
        items={items
          .filter((item) => canViewCorporateSection(item.key, capabilities))
          .map((item) => ({
            key: item.key,
            href: item.href,
            label: t(item.key),
            active: path === item.href || path.startsWith(`${item.href}/`),
          }))}
      />
    </div>
  );
}
