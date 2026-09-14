import type { ReactNode } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

const route = vi.hoisted(() => ({ path: "/corporate/teams/operation_mobile" }));
vi.mock("next-intl", () => ({ useTranslations: () => (key: string) => key }));
vi.mock("@/lib/i18n/navigation", () => ({
  usePathname: () => route.path,
  Link: ({ href, children, ...props }: { href: string; children: ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));
import { CorporateHubNavigation } from "@/components/layouts/corporate-hub-navigation";
afterEach(() => {
  cleanup();
  route.path = "/corporate/teams/operation_mobile";
});

it("does not duplicate the primary navigation on Overview", () => {
  route.path = "/corporate/overview";
  render(<CorporateHubNavigation capabilities={["team.list"]} />);
  expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
});

it("shows authorized directories and selects the team tab on its detail page", () => {
  render(<CorporateHubNavigation capabilities={["team.list", "team.update", "project.list"]} />);
  expect(screen.getByRole("link", { name: "teams" })).toHaveAttribute("aria-current", "page");
  expect(screen.getByRole("link", { name: "projects" })).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "employees" })).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "admins" })).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "organization" })).toHaveAttribute(
    "aria-current",
    "page",
  );
});

it("retains the Admins entry for a read-only audit administrator", () => {
  render(<CorporateHubNavigation capabilities={["audit.list"]} />);
  expect(screen.getByRole("link", { name: "admins" })).toHaveAttribute(
    "href",
    "/corporate/organization/admins",
  );
});
it("keeps member administration discoverable after separating profile and access", () => {
  render(<CorporateHubNavigation capabilities={["member.update"]} />);
  expect(screen.getByRole("link", { name: "admins" })).toHaveAttribute(
    "href",
    "/corporate/organization/admins",
  );
});
