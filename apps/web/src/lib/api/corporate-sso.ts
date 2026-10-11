import { apiRequest } from "@/lib/api/http";

/**
 * Organization-level single sign-on configuration (SPEC-095 surface). The
 * mock transport answers this route; a deployment without the endpoint
 * responds 404 and the section renders its unavailable state instead of a
 * dead form.
 */
export type CorporateSsoProvider = "saml" | "oidc";

export type CorporateSsoProviderView = {
  provider: CorporateSsoProvider;
  enabled: boolean;
  issuer_url: string | null;
  client_id: string | null;
  idp_metadata_url: string | null;
  updated_at: string | null;
};

export type CorporateSsoView = {
  providers: CorporateSsoProviderView[];
};

export async function readCorporateSso(
  sessionToken: string,
  organizationId: string,
): Promise<CorporateSsoView> {
  return apiRequest<CorporateSsoView>(`/v1/corporate/organizations/${organizationId}/sso`, {
    sessionToken,
  });
}
