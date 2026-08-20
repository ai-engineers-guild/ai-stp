import { describe, expect, it } from "vitest";
import { parseConsentCookie, serializeConsent } from "@/lib/consent";
describe("cookie consent", () => {
  it("round trips explicit optional categories", () => {
    const encoded = serializeConsent({ analytics: true, marketing: false });
    expect(parseConsentCookie(`other=x; ai_stp_consent=${encoded}`)).toEqual({
      analytics: true,
      marketing: false,
    });
  });
  it("defaults to no optional consent", () => {
    expect(parseConsentCookie("other=x")).toBeNull();
  });
});
