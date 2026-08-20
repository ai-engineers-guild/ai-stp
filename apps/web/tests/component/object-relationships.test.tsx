import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/i18n/navigation", () => ({
  Link: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

import { ObjectRelationships } from "@/components/molecules/object-relationships";

const labels = {
  localization: "Localization",
  linkedServices: "Linked services",
  notExclusive: "Listed services are related, not exclusive.",
};

describe("ObjectRelationships", () => {
  it("renders nothing when both lists are empty", () => {
    const { container } = render(
      <ObjectRelationships countryCodes={[]} services={[]} locale="en" labels={labels} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("shows localized country names and service chips without exclusivity", () => {
    render(
      <ObjectRelationships
        countryCodes={["KZ"]}
        services={[
          {
            name: "Kaspi",
            canonical_domain: "kaspi.kz",
            primary_url: "https://kaspi.kz",
            country_codes: ["KZ"],
          },
        ]}
        locale="en"
        labels={labels}
      />,
    );
    expect(screen.getByRole("link", { name: "Kazakhstan" })).toHaveAttribute(
      "href",
      "/countries/KZ",
    );
    expect(screen.getByRole("link", { name: "Kaspi" })).toHaveAttribute(
      "href",
      "/services/kaspi.kz",
    );
    expect(screen.getByText(labels.notExclusive)).toBeVisible();
  });
});
