"use client";

import { useTranslations } from "next-intl";
import { Link, usePathname } from "@/lib/i18n/navigation";
import { canViewCorporateSection } from "@/lib/corporate-hub";

const sections = [
  { key: "overview", href: "/corporate" },
  { key: "organization", href: "/corporate/organization" },
  { key: "landscape", href: "/corporate/technology-landscape" },
] as const;
const organization = [
  { key: "employees", href: "/corporate/members" },
  { key: "projects", href: "/corporate/projects" },
  { key: "teams", href: "/corporate/teams" },
  { key: "admins", href: "/corporate/organization/admins" },
] as const;
const landscape = [
  { key: "technologies", href: "/corporate/technologies" },
  { key: "categories", href: "/corporate/categories" },
] as const;

export function CorporateHubNavigation({ capabilities }: { capabilities: readonly string[] }) {
  const t = useTranslations("hub");
  const path = usePathname();
  const inLandscape = /\/corporate\/(technologies|categories|technology-landscape)/.test(path);
  const activeSection =
    path === "/corporate" ? "overview" : inLandscape ? "landscape" : "organization";
  return (
    <div className="border-border mb-6 space-y-2 border-b pb-4">
      <nav aria-label={t("navigation")} className="flex flex-wrap gap-2">
        {sections.map((item) => (
          <Link
            key={item.key}
            href={item.href}
            aria-current={activeSection === item.key ? "page" : undefined}
            className="hover:bg-muted aria-[current=page]:bg-muted aria-[current=page]:text-foreground text-muted-foreground inline-flex min-h-11 items-center rounded-sm px-3 text-sm font-medium"
          >
            {t(item.key)}
          </Link>
        ))}
      </nav>
      {activeSection !== "overview" && (
        <nav aria-label={t(activeSection)} className="flex flex-wrap gap-2">
          {(inLandscape ? landscape : organization)
            .filter((item) => canViewCorporateSection(item.key, capabilities))
            .map((item) => (
              <Link
                key={item.key}
                href={item.href}
                aria-current={path.startsWith(item.href) ? "page" : undefined}
                className="text-muted-foreground hover:text-foreground aria-[current=page]:text-primary inline-flex min-h-11 items-center px-3 text-sm"
              >
                {t(item.key)}
              </Link>
            ))}
        </nav>
      )}
    </div>
  );
}
