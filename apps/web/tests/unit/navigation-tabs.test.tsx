import type { ReactNode } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

vi.mock("@/lib/i18n/navigation", () => ({
  Link: ({ href, children, ...props }: { href: string; children: ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

import { NavigationTabs } from "@/components/molecules/navigation-tabs";

afterEach(cleanup);

it("renders accessible secondary tabs with one active destination", () => {
  render(
    <NavigationTabs
      ariaLabel="Organization"
      items={[
        { key: "projects", href: "/corporate/projects", label: "Projects", active: false },
        { key: "teams", href: "/corporate/teams", label: "Teams", active: true },
      ]}
    />,
  );

  expect(screen.getByRole("navigation", { name: "Organization" })).toHaveAttribute(
    "data-ui",
    "navigation-tabs",
  );
  expect(screen.getByRole("link", { name: "Teams" })).toHaveAttribute("aria-current", "page");
  expect(screen.getByRole("link", { name: "Projects" })).not.toHaveAttribute("aria-current");
  expect(screen.getByRole("link", { name: "Teams" })).toHaveClass(
    "aria-[current=page]:border-primary",
  );
});

it("uses the selected primary treatment when requested", () => {
  render(
    <NavigationTabs
      ariaLabel="Primary navigation"
      variant="primary"
      items={[
        {
          key: "organization",
          href: "/corporate/organization",
          label: "Organization",
          active: true,
        },
      ]}
    />,
  );

  expect(screen.getByRole("link", { name: "Organization" })).toHaveClass(
    "aria-[current=page]:bg-accent",
  );
});
