import { ApiError } from "@/lib/api/errors";
import { readCorporateContext } from "@/lib/api/corporate";
import { sessionCookieValue } from "@/lib/auth/require-session";
import { readSession } from "@/lib/auth/session";
import { canViewCorporateAdministration } from "@/lib/corporate-hub";
import { corporateNavPageIds } from "@/lib/corporate-navigation";
import { COMPILED_FEATURE_PROFILE } from "@/lib/features/compiled";

export type CorporateNavigationSnapshot = {
  administration: boolean;
  pages: string[];
  status: 200 | 401 | 403 | 503;
};

/** Request-scoped navigation truth for the initial HTML and the revalidation API. */
export async function readCorporateNavigationSnapshot(): Promise<CorporateNavigationSnapshot> {
  if (COMPILED_FEATURE_PROFILE !== "corporate_hub" || !(await readSession())) {
    return { administration: false, pages: [], status: 200 };
  }
  try {
    const token = await sessionCookieValue();
    const context = token ? await readCorporateContext(token) : null;
    if (!context) return { administration: false, pages: [], status: 403 };
    const pages = corporateNavPageIds(context.capabilities);
    return {
      administration: canViewCorporateAdministration(context.capabilities),
      pages,
      status: 200,
    };
  } catch (error) {
    if (!(error instanceof ApiError)) {
      return { administration: false, pages: [], status: 503 };
    }
    const status: 401 | 403 | 503 =
      error.status === 401 || error.status === 403 ? error.status : 503;
    return { administration: false, pages: [], status };
  }
}
