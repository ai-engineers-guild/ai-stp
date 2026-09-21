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

it("shows the organization tabs on Overview", () => {
  route.path = "/corporate/overview";
  render(<CorporateHubNavigation capabilities={["team.list"]} />);
  const links = [...screen.getByRole("navigation").querySelectorAll("a")].map(
    (link) => link.textContent,
  );
  expect(links).toContain("teams");
});

it("hides secondary tabs on entity detail pages", () => {
  render(<CorporateHubNavigation capabilities={["team.list", "team.update", "project.list"]} />);
  expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
});

it("orders the Organization tabs as Projects, Teams, Employees, Technologies", () => {
  route.path = "/corporate/organization";
  render(
    <CorporateHubNavigation
      capabilities={["project.list", "team.list", "member.list", "technology.list"]}
    />,
  );
  expect(screen.getByRole("navigation").querySelectorAll("a")).toHaveLength(4);
  expect(
    [...screen.getByRole("navigation").querySelectorAll("a")].map((link) => link.textContent),
  ).toEqual(["projects", "teams", "employees", "technologies"]);
});

it("keeps the technology directory in the Organization section", () => {
  route.path = "/corporate/technologies";
  render(<CorporateHubNavigation capabilities={["technology.list"]} />);
  expect(screen.getByRole("link", { name: "technologies" })).toHaveAttribute(
    "aria-current",
    "page",
  );
  expect(screen.getByRole("link", { name: "technologies" })).toHaveAttribute(
    "href",
    "/corporate/technologies",
  );
});

it("keeps Admins out of the Organization subnavigation", () => {
  render(<CorporateHubNavigation capabilities={["audit.list"]} />);
  expect(screen.queryByRole("link", { name: "admins" })).not.toBeInTheDocument();
});
it("keeps member administration discoverable after separating profile and access", () => {
  render(<CorporateHubNavigation capabilities={["member.update"]} />);
  expect(screen.queryByRole("link", { name: "admins" })).not.toBeInTheDocument();
});

it("routes Landscape technologies to the technology landscape view", () => {
  route.path = "/corporate/technology-landscape";
  render(<CorporateHubNavigation capabilities={["technology.list"]} />);
  expect(screen.queryByRole("link", { name: "landscape" })).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "technologies" })).toHaveAttribute(
    "aria-current",
    "page",
  );
  expect(screen.getByRole("link", { name: "technologies" })).toHaveAttribute(
    "href",
    "/corporate/technology-landscape",
  );
});
