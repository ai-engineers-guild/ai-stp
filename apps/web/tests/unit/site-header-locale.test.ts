import { expect, it } from "vitest";
import { localeNeutralPathname } from "@/lib/i18n/locale-path";

it("removes a localized prefix before next-intl changes locale", () => {
  expect(localeNeutralPathname("/en/corporate/overview")).toBe("/corporate/overview");
  expect(localeNeutralPathname("/ru/corporate/overview")).toBe("/corporate/overview");
  expect(localeNeutralPathname("/corporate/overview")).toBe("/corporate/overview");
  expect(localeNeutralPathname("/en")).toBe("/");
});
