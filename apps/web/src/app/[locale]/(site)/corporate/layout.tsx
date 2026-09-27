import type { ReactNode } from "react";
import { cookies } from "next/headers";
import { getTranslations } from "next-intl/server";

import { CorporateHubNavigation } from "@/components/layouts/corporate-hub-navigation";
import { CorporateOrganizationSwitcher } from "@/components/molecules/corporate-organization-switcher";
import {
  readCorporateContext,
  readCorporateOrganizations,
  resolveCorporateOrganization,
} from "@/lib/api/corporate";
import { sessionCookieValue } from "@/lib/auth/require-session";
import { CORPORATE_ORG_COOKIE } from "@/lib/auth/cookies";
import { ApiError } from "@/lib/api/errors";
import { UI } from "@/lib/ui-selectors";
import type { OrganizationSummary } from "@/lib/api/generated/types.gen";

export default async function CorporateHubLayout({ children }: { children: ReactNode }) {
  const session = await sessionCookieValue();
  let capabilities: string[] = [];
  let organizations: OrganizationSummary[] = [];
  try {
    // The page owns its error state; unavailable navigation must not expose forbidden links.
    capabilities = session ? ((await readCorporateContext(session))?.capabilities ?? []) : [];
    organizations = session ? await readCorporateOrganizations(session) : [];
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
  }
  const preferred = (await cookies()).get(CORPORATE_ORG_COOKIE)?.value;
  const organization = resolveCorporateOrganization(organizations, preferred);
  const t = await getTranslations("hub");
  return (
    <>
      {organizations.length > 1 && organization ? (
        <div
          data-ui={UI.corporate.organizationSwitcher}
          className="border-border -mx-4 -mt-6 mb-6 border-b sm:-mx-6"
        >
          <div className="mx-auto flex max-w-6xl items-center justify-end px-4 py-2 sm:px-6">
            <CorporateOrganizationSwitcher
              organizations={organizations.map((item) => ({
                id: item.organization_id,
                name: item.display_name,
              }))}
              selectedId={organization.organization_id}
              label={t("organization")}
            />
          </div>
        </div>
      ) : null}
      <CorporateHubNavigation capabilities={capabilities} bleed={organizations.length <= 1} />
      {children}
    </>
  );
}
