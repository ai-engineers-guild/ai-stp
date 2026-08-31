import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

/**
 * Proves the site shell still renders the consent banner and the analytics tags
 * (`SPEC-023`, `ADR-0112`).
 *
 * Both components have component tests, and both kept passing on a tree where
 * nothing rendered either of them: a consolidation dropped the two elements from
 * `AppShell`, and every test that knew about them tested them in isolation. The
 * site then served no banner and loaded no vendor tag, with a green gate.
 *
 * Reading the source rather than rendering the shell is deliberate. `AppShell`
 * is an async server component that reaches for translations, environment and
 * feature gates; standing all that up would test the harness. What was lost here
 * was a JSX element, and that is what this reads.
 */
describe("the site shell mounts consent and analytics", () => {
  const shell = readFileSync(
    path.resolve(__dirname, "../../src/components/layouts/app-shell.tsx"),
    "utf8",
  );

  it("renders the analytics component with the public configuration", () => {
    expect(shell).toContain("ConsentedAnalytics");
    expect(shell).toContain("publicAnalyticsConfig()");
    expect(shell).toMatch(/<ConsentedAnalytics\b/);
  });

  it("renders the consent banner unless it is explicitly disabled", () => {
    expect(shell).toContain("CookieConsent");
    expect(shell).toMatch(/<CookieConsent\b/);
    // The banner is opt-out, so an unset variable must still render it.
    expect(shell).toContain('NEXT_PUBLIC_COOKIE_CONSENT_ENABLED !== "false"');
  });

  it("points the banner at the privacy document for the current locale", () => {
    expect(shell).toContain("privacyHref={`/${locale}/legal/privacy`}");
  });
});
