import { UI } from "@/lib/ui-selectors";
import { COMPILED_FEATURES, COMPILED_FEATURE_PROFILE } from "@/lib/features/compiled";
import type { FeatureKey } from "@/lib/features/definitions";

export type NavItem = {
  /** Stable selector so both projections expose the same item to automation. */
  ui: string;
  /** Message key inside the `nav` namespace. */
  labelKey: string;
  href: string;
  /** External targets are never rewritten into a projection. */
  external?: boolean;
  feature?: FeatureKey;
};

type NavigationInput = {
  signedIn: boolean;
  docsHref: string;
  corporateAdministration?: boolean;
};

/**
 * One navigation model for both projections. The human header renders it as
 * links and the machine header renders it as Markdown links, so the two views
 * can never drift apart (SPEC-036).
 */
export function siteNavigation({
  signedIn,
  docsHref,
  corporateAdministration = false,
}: NavigationInput): NavItem[] {
  const corporate = COMPILED_FEATURE_PROFILE === "corporate_hub";
  const items: NavItem[] = [
    { ui: UI.navigation.home, labelKey: "home", href: "/" },
    ...(corporate
      ? [{ ui: UI.navigation.overview, labelKey: "overview", href: "/corporate/overview" }]
      : []),
    { ui: UI.navigation.catalog, labelKey: "catalog", href: "/catalog" },
    ...(corporate
      ? [
          {
            ui: UI.navigation.organization,
            labelKey: "organization",
            href: "/corporate/organization",
          },
          {
            ui: UI.navigation.landscape,
            labelKey: "landscape",
            href: "/corporate/technology-landscape",
          },
          { ui: UI.navigation.dashboard, labelKey: "dashboard", href: "/corporate/dashboard" },
          ...(signedIn && corporateAdministration
            ? [
                {
                  ui: UI.navigation.admins,
                  labelKey: "admins",
                  href: "/corporate/organization/admins",
                },
              ]
            : []),
        ]
      : [{ ui: UI.navigation.services, labelKey: "services", href: "/services" }]),
    ...(!corporate
      ? [{ ui: UI.navigation.docs, labelKey: "docs", href: docsHref, external: true }]
      : []),
  ];
  items.push({
    ui: UI.navigation.content,
    labelKey: "content",
    href: "/content",
    feature: "content_hub",
  });

  if (signedIn) {
    items.push(
      { ui: UI.navigation.objects, labelKey: "objects", href: "/objects" },
      { ui: UI.navigation.access, labelKey: "access", href: "/access" },
      { ui: UI.navigation.reports, labelKey: "reports", href: "/reports" },
      { ui: UI.navigation.devices, labelKey: "devices", href: "/devices" },
    );
  }

  items.push({
    ui: UI.navigation.contact,
    labelKey: "contact",
    href: "/contact",
    feature: "saas_public_pages",
  });
  items.push({
    ui: UI.navigation.account,
    labelKey: signedIn ? "account" : "login",
    href: signedIn ? "/account" : "/login",
  });

  return items.filter((item) => item.feature === undefined || COMPILED_FEATURES[item.feature]);
}
