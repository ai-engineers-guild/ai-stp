import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/i18n/navigation", () => ({
  Link: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

import { CatalogAuthorLink } from "@/components/molecules/catalog-author-link";

describe("CatalogAuthorLink", () => {
  it("makes the whole author identity the profile link", () => {
    render(
      <CatalogAuthorLink
        accountId="account_demo"
        displayName="Artem"
        avatarUrl={null}
        verified
        verifiedLabel="Author verified"
      />,
    );
    const link = screen.getByRole("link", { name: /Artem/ });
    expect(link).toHaveAttribute("href", "/publishers/account_demo");
    expect(screen.queryByText("Report author")).not.toBeInTheDocument();
  });

  it("does not invent an author name when the profile is unavailable", () => {
    render(
      <CatalogAuthorLink
        accountId="account_missing"
        displayName={null}
        avatarUrl={null}
        verified={false}
        verifiedLabel="Author verified"
      />,
    );

    expect(screen.getByRole("link", { name: /account_missing/ })).toBeInTheDocument();
    expect(screen.queryByText("Author")).not.toBeInTheDocument();
  });
});
