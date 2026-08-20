import { describe, expect, it } from "vitest";

import { catalogRelations } from "@/lib/api/catalog";

describe("catalogRelations", () => {
  it("returns empty collections when presentation fields are absent", () => {
    expect(catalogRelations({})).toEqual({ country_codes: [], services: [] });
  });

  it("keeps only well-formed public services", () => {
    expect(
      catalogRelations({
        country_codes: ["KZ", 1],
        services: [
          {
            name: "Kaspi",
            canonical_domain: "kaspi.kz",
            primary_url: "https://kaspi.kz",
            country_codes: ["KZ"],
          },
          { name: "broken" },
        ],
      }),
    ).toEqual({
      country_codes: ["KZ"],
      services: [
        {
          name: "Kaspi",
          canonical_domain: "kaspi.kz",
          primary_url: "https://kaspi.kz",
          country_codes: ["KZ"],
        },
      ],
    });
  });
});
