import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/i18n/navigation", () => ({
  Link: ({ href, children, ...props }: { href: string; children?: ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

const { RegionalServicesExplorer } =
  await import("@/components/organisms/regional-services-explorer");

const labels = {
  title: "Regional services",
  subtitle: "Explore services by market.",
  heroArtAlt: "Original topographic survey of regional markets at dusk.",
  cisRegion: "CIS markets",
  countries: "Countries",
  services: "Services",
  allCountries: "All countries",
  allServices: "All services",
  available: "Available services",
  result: "service",
  results: "services",
  details: "Service details",
  automations: "Components and setups",
  empty: "No services match",
  unspecified: "Not specified",
  openCatalog: "Open in catalog",
};

describe("RegionalServicesExplorer", () => {
  it("filters dependent services and links into catalog results", async () => {
    const user = userEvent.setup();
    render(
      <RegionalServicesExplorer
        locale="en"
        labels={labels}
        services={[
          {
            schema_version: 1,
            name: "Kaspi",
            canonical_domain: "kaspi.kz",
            primary_url: "https://kaspi.kz",
            country_codes: ["KZ"],
          },
          {
            schema_version: 1,
            name: "Global Pay",
            canonical_domain: "global.example",
            primary_url: "https://global.example",
            country_codes: [],
          },
        ]}
      />,
    );

    expect(screen.getByRole("heading", { name: "Kaspi" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Global Pay" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Kazakhstan/i }));
    expect(screen.getByRole("heading", { name: "Kaspi" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Global Pay" })).toBeNull();
    expect(screen.getByRole("link", { name: "Components and setups" })).toHaveAttribute(
      "href",
      expect.stringContaining("service_domains=kaspi.kz"),
    );
    expect(screen.getByRole("link", { name: "Open in catalog" })).toHaveAttribute(
      "href",
      expect.stringContaining("country_codes=KZ"),
    );
    expect(screen.getByRole("link", { name: "Open in catalog" })).toHaveClass("bg-primary");
    expect(document.querySelector("[data-flag='KZ']")).not.toBeNull();
    expect(document.querySelector("img[src^='http']")).toBeNull();
    expect(document.querySelector("img[src='/flags/kz.svg']")).not.toBeNull();
    expect(document.querySelectorAll("[data-cis-flag]")).toHaveLength(9);
    expect(document.body.textContent).not.toMatch(/[\u{1F1E6}-\u{1F1FF}]/u);
    expect(screen.getByRole("img", { name: labels.heroArtAlt })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "CIS markets" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Kazakhstan/i })).toHaveClass("border-primary");
  });

  it("keeps country-less services behind Not specified and shows the empty state", async () => {
    const user = userEvent.setup();
    const { rerender } = render(
      <RegionalServicesExplorer
        locale="en"
        labels={labels}
        services={[
          {
            schema_version: 1,
            name: "Kaspi",
            canonical_domain: "kaspi.kz",
            primary_url: "https://kaspi.kz",
            country_codes: ["KZ"],
          },
          {
            schema_version: 1,
            name: "Global Pay",
            canonical_domain: "global.example",
            primary_url: "https://global.example",
            country_codes: [],
          },
        ]}
      />,
    );

    await user.click(screen.getByRole("button", { name: /Not specified/i }));
    expect(screen.getByRole("heading", { name: "Global Pay" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Kaspi" })).toBeNull();

    rerender(<RegionalServicesExplorer locale="en" labels={labels} services={[]} />);
    expect(screen.getByText("No services match")).toBeInTheDocument();
  });
});
