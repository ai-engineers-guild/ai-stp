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
        authorLabel="Author"
      />,
    );
    const link = screen.getByRole("link", { name: /Artem/ });
    expect(link).toHaveAttribute("href", "/publishers/account_demo");
    expect(screen.queryByText("Report author")).not.toBeInTheDocument();
  });
});
