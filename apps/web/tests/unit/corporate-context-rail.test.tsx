import type { ReactNode } from "react";
import { cleanup, render, screen, within, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
const route = vi.hoisted(() => ({ path: "/corporate/teams/team_1" }));
vi.mock("next-intl", () => ({
  useTranslations: () => (key: string, values?: Record<string, string>) =>
    values?.section ? `${key} ${values.section}` : key,
}));
vi.mock("@/lib/use-hydrated", () => ({ useHydrated: () => true }));
vi.mock("@/lib/i18n/navigation", () => ({
  usePathname: () => route.path,
  Link: ({
    href,
    children,
    prefetch,
    ...props
  }: {
    href: string;
    children: ReactNode;
    prefetch?: boolean;
  }) => {
    void prefetch;
    return (
      <a
        href={href}
        {...props}
        onClick={(event) => {
          event.preventDefault();
          (props as { onClick?: () => void }).onClick?.();
        }}
      >
        {children}
      </a>
    );
  },
}));
import { ContextRail } from "@/components/layouts/context-rail";
import { corporateNavPageIds } from "@/lib/corporate-navigation";
import { useUiSlice } from "@/lib/stores/ui-slice";
import { useSessionUiSlice } from "@/lib/stores/session-ui-slice";
const allowed = corporateNavPageIds([
  "role.list",
  "role.read",
  "member.update",
  "member.list",
  "team.list",
  "project.list",
  "technology.list",
  "category.list",
  "service_principal.list",
  "organization.manage",
  "audit.list",
  "landscape.manage",
]);
beforeEach(() => {
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })),
  );
});
afterEach(() => {
  cleanup();
  route.path = "/corporate/teams/team_1";
  sessionStorage.clear();
  useUiSlice.setState({ sidebarCollapsed: false });
  useSessionUiSlice.setState({ signedInHint: false, corporateNavPages: null });
  vi.unstubAllGlobals();
});
function desktop() {
  return document.querySelector('[data-ui="context-sidebar"]') as HTMLElement;
}
function renderCorporate() {
  useSessionUiSlice.setState({ signedInHint: true });
  return render(<ContextRail corporate docsHref="https://docs.test" allowedPages={allowed} />);
}
it("opens the active organization group and returns a detail to its directory", () => {
  renderCorporate();
  const nav = within(desktop());
  expect(nav.getByRole("link", { name: "teams" })).toHaveAttribute("aria-current", "page");
  expect(nav.getByRole("link", { name: "backToSection teams" })).toHaveAttribute(
    "href",
    "/corporate/teams",
  );
  expect(desktop().querySelectorAll('[aria-current="page"]')).toHaveLength(1);
});
it("discloses a group without navigating and lets the sidebar collapse and restore", async () => {
  const user = userEvent.setup();
  renderCorporate();
  const nav = within(desktop());
  await user.click(nav.getByRole("button", { name: "collapseSection organization" }));
  expect(nav.queryByRole("link", { name: "teams" })).toBeNull();
  await user.click(nav.getByRole("button", { name: "expandSection organization" }));
  expect(nav.getByRole("link", { name: "teams" })).toBeVisible();
  act(() => {
    useUiSlice.getState().setSidebarCollapsed(true);
  });
  expect(desktop()).toHaveAttribute("data-collapsed", "true");
  expect(nav.queryByRole("link", { name: "teams" })).toBeNull();
  const parent = nav.getByRole("button", { name: "organization" });
  expect(parent).toHaveAttribute("data-active", "true");
  await user.click(parent);
  expect(screen.getByRole("menuitem", { name: "teams" })).toHaveAttribute("aria-current", "page");
  await user.keyboard("{Escape}");
  expect(parent).toHaveFocus();
  expect(sessionStorage.getItem("ai-stp-sidebar-collapsed")).toBe("true");
  act(() => {
    useUiSlice.getState().setSidebarCollapsed(false);
  });
  expect(desktop()).toHaveAttribute("data-collapsed", "false");
});
it("replaces the rail with grouped administration and omits the redundant overview back link", () => {
  route.path = "/corporate/organization/admins/roles";
  renderCorporate();
  const nav = within(desktop());
  for (const group of ["peopleAndAccess", "referenceData", "security", "organization", "audit"])
    expect(
      nav.getByRole("button", {
        name: `${group === "peopleAndAccess" ? "collapseSection" : "expandSection"} ${group}`,
      }),
    ).toHaveAttribute("aria-expanded", group === "peopleAndAccess" ? "true" : "false");
  expect(nav.queryByRole("link", { name: "backToSection overview" })).toBeNull();
  expect(nav.getByRole("link", { name: "roles" })).toHaveAttribute("aria-current", "page");
  expect(nav.getByRole("link", { name: "employeeAccess" })).toHaveAttribute(
    "href",
    "/corporate/organization/admins/employees",
  );
});
it("never shows admin pages from a URL without server availability", () => {
  route.path = "/corporate/organization/admins";
  render(<ContextRail corporate docsHref="https://docs.test" allowedPages={[]} />);
  expect(desktop()).toBeNull();
});
it("keeps permitted root destinations available on a denied administration page", () => {
  route.path = "/corporate/organization/admins";
  useSessionUiSlice.setState({ signedInHint: true });
  render(
    <ContextRail
      corporate
      docsHref="https://docs.test"
      allowedPages={["overview", "catalog", "organization", "dashboard"]}
    />,
  );
  const nav = within(desktop());
  expect(nav.getByRole("link", { name: "overview" })).toBeVisible();
  expect(nav.getByRole("link", { name: "catalog" })).toBeVisible();
  expect(nav.queryByRole("link", { name: "membersAndInvitations" })).toBeNull();
  expect(nav.queryByRole("button", { name: "backToNavigation" })).toBeNull();
  expect(desktop().querySelectorAll('[aria-current="page"]')).toHaveLength(0);
});
it("uses the same rail for the public SaaS catalog without adding account destinations", () => {
  route.path = "/catalog/components/comp_1";
  useSessionUiSlice.setState({ signedInHint: true });
  render(<ContextRail corporate={false} docsHref="https://docs.test" />);
  const nav = within(desktop());
  expect(nav.getByRole("link", { name: "catalog" })).toHaveAttribute("aria-current", "page");
  expect(nav.getByRole("link", { name: "backToSection catalog" })).toHaveAttribute(
    "href",
    "/catalog",
  );
  expect(nav.getByRole("link", { name: "docs" })).toHaveAttribute("href", "https://docs.test");
  expect(nav.queryByRole("button", { name: "expandSection account" })).toBeNull();
  expect(nav.queryByRole("link", { name: "privacy" })).toBeNull();
});
it.each([false, true])(
  "keeps personal paths out of the drawer (corporate=%s)",
  async (corporate) => {
    route.path = corporate ? "/corporate/account/privacy" : "/account/privacy";
    useSessionUiSlice.setState({ signedInHint: true });
    render(
      <ContextRail corporate={corporate} docsHref="https://docs.test" allowedPages={allowed} />,
    );
    const check = (root: HTMLElement) => {
      expect(
        root.querySelectorAll(
          'a[href*="/account"],a[href$="/objects"],a[href$="/access"],a[href$="/reports"],a[href$="/devices"],a[href$="/assigned"],a[href$="/likes"]',
        ),
      ).toHaveLength(0);
      expect(root.textContent).not.toContain("corporateHub");
    };
    check(desktop());
    await userEvent.setup().click(screen.getByRole("button", { name: "openMenu" }));
    check(screen.getByRole("dialog"));
  },
);
it("contains focus, closes on Escape and navigation, and stays closed on Back/Forward", async () => {
  const user = userEvent.setup();
  const { rerender } = renderCorporate();
  const trigger = screen.getByRole("button", { name: "openMenu" });
  await user.click(trigger);
  expect(screen.getByRole("dialog")).toBeVisible();
  await user.keyboard("{Escape}");
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(trigger).toHaveFocus();
  await user.click(trigger);
  await user.click(within(screen.getByRole("dialog")).getByRole("link", { name: "teams" }));
  expect(screen.queryByRole("dialog")).toBeNull();
  await user.click(trigger);
  route.path = "/corporate/organization/admins";
  rerender(<ContextRail corporate docsHref="https://docs.test" allowedPages={allowed} />);
  expect(screen.queryByRole("dialog")).toBeNull();
  route.path = "/corporate/teams/team_1";
  rerender(<ContextRail corporate docsHref="https://docs.test" allowedPages={allowed} />);
  expect(screen.queryByRole("dialog")).toBeNull();
});

it("renders no Corporate chrome before sign-in or on authentication pages", () => {
  const { rerender } = render(
    <ContextRail corporate docsHref="https://docs.test" allowedPages={allowed} />,
  );
  expect(desktop()).toBeNull();
  expect(screen.queryByRole("button", { name: "openMenu" })).toBeNull();
  act(() => {
    useSessionUiSlice.getState().setSignedInHint(true);
  });
  expect(desktop()).not.toBeNull();
  route.path = "/corporate/login";
  rerender(<ContextRail corporate docsHref="https://docs.test" allowedPages={allowed} />);
  expect(desktop()).toBeNull();
});

it("retains verified sections during route revalidation and network failure, then clears on logout", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ pages: allowed }) });
  vi.stubGlobal("fetch", fetcher);
  useSessionUiSlice.setState({ signedInHint: true });
  route.path = "/corporate/overview";
  const { rerender } = render(<ContextRail corporate docsHref="https://docs.test" />);
  expect(desktop()).toBeNull();
  await waitFor(() => {
    expect(desktop()).not.toBeNull();
  });
  const original = desktop().querySelectorAll("nav > a, nav > div").length;
  let fail!: (reason: Error) => void;
  fetcher.mockReturnValueOnce(
    new Promise((_resolve, reject) => {
      fail = reject;
    }),
  );
  route.path = "/corporate/catalog";
  rerender(<ContextRail corporate docsHref="https://docs.test" />);
  expect(desktop().querySelectorAll("nav > a, nav > div")).toHaveLength(original);
  await act(async () => {
    fail(new Error("offline"));
    await Promise.resolve();
  });
  expect(within(desktop()).getByRole("link", { name: "catalog" })).toBeVisible();
  act(() => {
    useSessionUiSlice.getState().setSignedInHint(false);
  });
  expect(desktop()).toBeNull();
  expect(useSessionUiSlice.getState().corporateNavPages).toEqual([]);
});

it.each([401, 403])("removes revoked navigation after HTTP %s", async (status) => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status }));
  useSessionUiSlice.setState({ signedInHint: true, corporateNavPages: allowed });
  render(<ContextRail corporate docsHref="https://docs.test" />);
  await waitFor(() => {
    expect(desktop()).toBeNull();
  });
});

it("does not publish navigation from an aborted earlier request", async () => {
  let finish!: (result: unknown) => void;
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockReturnValueOnce(
        new Promise((resolve) => {
          finish = resolve;
        }),
      )
      .mockResolvedValue({ ok: true, json: () => Promise.resolve({ pages: ["overview"] }) }),
  );
  useSessionUiSlice.setState({ signedInHint: true });
  const { rerender } = render(<ContextRail corporate docsHref="https://docs.test" />);
  route.path = "/corporate/overview";
  rerender(<ContextRail corporate docsHref="https://docs.test" />);
  await waitFor(() => {
    expect(desktop()).not.toBeNull();
  });
  await act(async () => {
    finish({ ok: true, json: () => Promise.resolve({ pages: allowed }) });
    await Promise.resolve();
  });
  expect(within(desktop()).queryByRole("link", { name: "catalog" })).toBeNull();
});

it("closes the mobile modal at the desktop breakpoint and keeps the desktop preference", async () => {
  const media = { matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() };
  vi.stubGlobal("matchMedia", () => media);
  renderCorporate();
  await userEvent.setup().click(screen.getByRole("button", { name: "openMenu" }));
  expect(screen.getByRole("dialog")).toBeVisible();
  act(() => {
    media.matches = true;
    (media.addEventListener.mock.calls[0]?.[1] as () => void)();
  });
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(useUiSlice.getState().sidebarCollapsed).toBe(false);
});

it("returns from any administration route to the main rail without changing the page", async () => {
  route.path = "/corporate/organization/admins/employees/account_a";
  const user = userEvent.setup();
  const { rerender } = renderCorporate();
  await user.click(within(desktop()).getByRole("button", { name: "backToNavigation" }));
  expect(route.path).toBe("/corporate/organization/admins/employees/account_a");
  const nav = within(desktop());
  expect(nav.getByRole("link", { name: "overview" })).toBeVisible();
  expect(nav.getByRole("link", { name: "catalog" })).toBeVisible();
  expect(nav.getByRole("link", { name: "administration" })).toHaveAttribute("aria-current", "page");
  expect(nav.queryByRole("link", { name: "backToSection employeeAccess" })).toBeNull();
  await user.click(nav.getByRole("link", { name: "administration" }));
  expect(within(desktop()).getByRole("button", { name: "backToNavigation" })).toBeVisible();
  await user.click(screen.getByRole("button", { name: "openMenu" }));
  await user.click(
    within(screen.getByRole("dialog")).getByRole("button", { name: "backToNavigation" }),
  );
  expect(within(screen.getByRole("dialog")).getByRole("link", { name: "catalog" })).toBeVisible();
  route.path = "/corporate/organization/admins/roles";
  rerender(<ContextRail corporate docsHref="https://docs.test" allowedPages={allowed} />);
  expect(within(desktop()).getByRole("link", { name: "roles" })).toHaveAttribute(
    "aria-current",
    "page",
  );
});
