import { apiRequest } from "@/lib/api/http";
import { publicApiGet } from "@/lib/api/public-http";

export type PublicLegalDocument = {
  slug: string;
  revision_id: string;
  locale: string;
  title: string;
  policy_version: string;
  effective_at: string | null;
  source_ref: string | null;
  source_path: string | null;
  html: string;
};

export type LegalOnboarding = {
  account_status: "onboarding_pending" | "active";
  service_rules_revision_id: string;
  personal_data_consent_revision_id: string;
};

export function legalSourceUrl(
  policy: Pick<PublicLegalDocument, "source_ref" | "source_path">,
): string | null {
  if (!policy.source_path?.startsWith("docs-user-facing/legal/")) return null;
  const ref = policy.source_ref?.match(/^[0-9a-f]{40}$/) ? policy.source_ref : "main";
  const path = policy.source_path.split("/").map(encodeURIComponent).join("/");
  return `https://github.com/ai-engineers-guild/ai-stp/blob/${ref}/${path}`;
}

export function readPublicLegalDocument(
  slug: string,
  locale: string,
  revisionId?: string,
): Promise<PublicLegalDocument> {
  return publicApiGet(`/v1/documents/${slug}`, {
    query: { locale, revision_id: revisionId },
  });
}

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
