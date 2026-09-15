import { apiRequest } from "@/lib/api/http";

export { legalSourceUrl, readPublicLegalDocument } from "@/lib/api/public-legal";
export type { PublicLegalDocument } from "@/lib/api/public-legal";

export type LegalOnboarding = {
  account_status: "onboarding_pending" | "active";
  service_rules_revision_id: string;
  personal_data_consent_revision_id: string;
};

export function readLegalOnboarding(locale: string): Promise<LegalOnboarding> {
  return apiRequest("/v1/auth/onboarding", { query: { locale } });
}

export function completeLegalOnboarding(
  locale: string,
  revisions: Pick<
    LegalOnboarding,
    "service_rules_revision_id" | "personal_data_consent_revision_id"
  >,
): Promise<LegalOnboarding> {
  return apiRequest("/v1/auth/onboarding/complete", {
    method: "POST",
    query: { locale },
    body: revisions,
  });
}
