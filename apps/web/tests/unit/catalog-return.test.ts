import { describe, expect, it } from "vitest";
import { catalogReturnHref } from "@/lib/catalog-return";

describe("catalog return path", () => {
  it("preserves search, sorting, paging and view in the current locale", () => {
    const query = "?q=docs&resource=setups&sort=name&page=2&view=list";
    expect(catalogReturnHref(`/ru/catalog${query}`, "ru", "/catalog")).toBe(`/catalog${query}`);
    expect(catalogReturnHref(`/catalog${query}`, "en", "/catalog")).toBe(`/catalog${query}`);
  });
  it.each([
    undefined,
    ["/catalog"],
    "https://evil.test/catalog",
    "//evil.test/catalog",
    "/account",
    "/ru/catalog",
    "/catalog/../account",
    "/catalog%3Fq=x",
  ])("rejects unrelated or ambiguous navigation: %s", (value) => {
    expect(catalogReturnHref(value, "en", "/catalog?resource=setups")).toBe(
      "/catalog?resource=setups",
    );
  });
});
