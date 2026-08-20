export const CONSENT_COOKIE = "ai_stp_consent";
export type Consent = { analytics: boolean; marketing: boolean };

export function parseConsentCookie(source: string): Consent | null {
  const value = source
    .split("; ")
    .find((part) => part.startsWith(`${CONSENT_COOKIE}=`))
    ?.split("=")[1];
  if (!value) return null;
  if (value === "v1.none") return { analytics: false, marketing: false };
  if (value === "v1.all") return { analytics: true, marketing: true };
  const flags = value.split(".")[1]?.split(",") ?? [];
  return { analytics: flags.includes("analytics"), marketing: flags.includes("marketing") };
}

export function serializeConsent(consent: Consent): string {
  if (consent.analytics && consent.marketing) return "v1.all";
  if (!consent.analytics && !consent.marketing) return "v1.none";
  return `v1.${[consent.analytics && "analytics", consent.marketing && "marketing"].filter(Boolean).join(",")}`;
}
