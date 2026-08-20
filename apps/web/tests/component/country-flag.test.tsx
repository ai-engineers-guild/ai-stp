import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CIS_COUNTRY_CODES, CountryFlag } from "@/components/atoms/country-flag";
import { CATALOG_UNSPECIFIED_FILTER } from "@/lib/catalog-query";

describe("CountryFlag", () => {
  it("ships local SVG assets for every current CIS member and never uses emoji", () => {
    expect([...CIS_COUNTRY_CODES].sort()).toEqual([
      "AM",
      "AZ",
      "BY",
      "KG",
      "KZ",
      "MD",
      "RU",
      "TJ",
      "UZ",
    ]);
    const { container } = render(
      <>
        {CIS_COUNTRY_CODES.map((code) => (
          <CountryFlag key={code} code={code} />
        ))}
      </>,
    );
    expect(container.querySelectorAll("img")).toHaveLength(9);
    expect(container.querySelector("img[src^='http']")).toBeNull();
    expect(container.querySelector("img[src='/flags/kz.svg']")).not.toBeNull();
    expect(container.textContent).not.toMatch(/[\u{1F1E6}-\u{1F1FF}]/u);
  });

  it("renders an icon plate for unspecified and an ISO plate for other codes", () => {
    const { container, rerender } = render(<CountryFlag code={CATALOG_UNSPECIFIED_FILTER} />);
    expect(container.querySelector(`[data-flag='${CATALOG_UNSPECIFIED_FILTER}']`)).not.toBeNull();
    expect(container.querySelector("img")).toBeNull();

    rerender(<CountryFlag code="IN" />);
    expect(container.querySelector("[data-flag='IN']")?.textContent).toContain("IN");
    expect(container.querySelector("img")).toBeNull();
  });
});
