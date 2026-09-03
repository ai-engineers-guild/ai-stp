import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next-intl", () => ({
  useLocale: () => "en",
  useTranslations: () => (key: string) =>
    ({
      login: "Sign in",
      loginHint: "Sign in to your account",
      account: "Account",
      accountHint: "Open your profile and account",
      accountMenu: "Account menu",
      profile: "Profile",
      myObjects: "My objects",
      devices: "Devices",
      access: "Access",
      logout: "Sign out",
      closeMenu: "Close menu",
      profileShortcut: "Shortcut P",
    })[key] ?? key,
}));

vi.mock("@/lib/i18n/navigation", () => ({
  Link: ({
    href,
    children,
    prefetch,
    ...props
  }: {
    href: string;
    children?: ReactNode;
    prefetch?: boolean;
  }) => {
    void prefetch;
    return (
      <a href={href} {...props}>
        {children}
      </a>
    );
  },
}));

const { AccountControl } = await import("@/components/organisms/account-drawer");
const { MobilePrimaryNav } = await import("@/components/layouts/site-header");

describe("AccountControl", () => {
  it("keeps unauthenticated profile as a sign-in link", () => {
    render(<AccountControl signedIn={false} />);
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveClass("size-11");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("opens a compact anchored account popup without a modal overlay", async () => {
    const user = userEvent.setup();
    render(<AccountControl signedIn />);
    const trigger = screen.getByRole("button", { name: "Account" });
    expect(trigger).toHaveClass("size-11");
    await user.click(trigger);
    const menu = screen.getByRole("menu");
    expect(menu).toBeVisible();
    expect(screen.getByRole("menuitem", { name: "Profile" })).toHaveAttribute("href", "/account");
    expect(screen.getByRole("menuitem", { name: "My objects" })).toHaveAttribute(
      "href",
      "/objects",
    );
    expect(screen.getByRole("menuitem", { name: "Devices" })).toHaveAttribute("href", "/devices");
    expect(screen.getByRole("menuitem", { name: "Access" })).toHaveAttribute("href", "/access");
    expect(screen.getByRole("menuitem", { name: "Sign out" })).toHaveClass("text-destructive");
    expect(screen.getByRole("menuitem", { name: "Profile" })).toHaveClass("min-h-11");
    expect(screen.getByRole("menu").className).toContain("w-[min(14rem,calc(100vw-1.5rem))]");
    expect(document.querySelector(".fixed.inset-0")).toBeNull();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it("opens a keyboard-safe mobile primary nav without overflowing the viewport", async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    const { rerender } = render(
      <MobilePrimaryNav
        items={[
          { ui: "nav-catalog", labelKey: "catalog", href: "/catalog" },
          { ui: "nav-docs", labelKey: "docs", href: "https://docs.example", external: true },
        ]}
        open={false}
        onOpenChange={onOpenChange}
        openLabel="Open menu"
        closeLabel="Close menu"
        title="Primary navigation"
        labelFor={(item) => item.labelKey}
      />,
    );
    const trigger = screen.getByRole("button", { name: "Open menu" });
    expect(trigger).toHaveClass("size-11");
    await user.click(trigger);
    expect(onOpenChange).toHaveBeenCalledWith(true);

    rerender(
      <MobilePrimaryNav
        items={[
          { ui: "nav-catalog", labelKey: "catalog", href: "/catalog" },
          { ui: "nav-docs", labelKey: "docs", href: "https://docs.example", external: true },
        ]}
        open
        onOpenChange={onOpenChange}
        openLabel="Open menu"
        closeLabel="Close menu"
        title="Primary navigation"
        labelFor={(item) => item.labelKey}
      />,
    );
    const dialog = screen.getByRole("dialog", { name: "Primary navigation" });
    expect(dialog).toBeVisible();
    expect(dialog.className).toContain("w-[min(20rem,calc(100vw-1.5rem))]");
    expect(screen.getByRole("link", { name: "catalog" })).toHaveAttribute("href", "/catalog");
    expect(screen.getByRole("link", { name: "catalog" })).toHaveClass("min-h-11");
    await user.keyboard("{Escape}");
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("posts logout from a form that survives the menu unmount", async () => {
    const user = userEvent.setup();
    render(<AccountControl signedIn />);
    await user.click(screen.getByRole("button", { name: "Account" }));
    const menu = screen.getByRole("menu");
    const form = document.querySelector("form[action='/api/auth/logout?locale=en']");
    expect(form).toBeInstanceOf(HTMLFormElement);
    if (!(form instanceof HTMLFormElement)) {
      return;
    }
    expect(form).toHaveAttribute("method", "post");
    expect(menu.contains(form)).toBe(false);
    const requestSubmit = vi.spyOn(form, "requestSubmit").mockImplementation(() => undefined);
    await user.click(screen.getByRole("menuitem", { name: "Sign out" }));
    expect(requestSubmit).toHaveBeenCalledOnce();
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(form).toBeInTheDocument();
    requestSubmit.mockRestore();
  });

  it("posts logout when the sign-out item is activated from the keyboard", async () => {
    const user = userEvent.setup();
    render(<AccountControl signedIn />);
    await user.click(screen.getByRole("button", { name: "Account" }));
    const form = document.querySelector("form[action='/api/auth/logout?locale=en']");
    expect(form).toBeInstanceOf(HTMLFormElement);
    if (!(form instanceof HTMLFormElement)) {
      return;
    }
    const requestSubmit = vi.spyOn(form, "requestSubmit").mockImplementation(() => undefined);
    screen.getByRole("menuitem", { name: "Sign out" }).focus();
    await user.keyboard("{Enter}");
    expect(requestSubmit).toHaveBeenCalledOnce();
    expect(form).toBeInTheDocument();
    requestSubmit.mockRestore();
  });

  it("closes on outside click and returns keyboard focus to the trigger", async () => {
    const user = userEvent.setup();
    render(<AccountControl signedIn />);
    const trigger = screen.getByRole("button", { name: "Account" });
    await user.click(trigger);
    expect(screen.getByRole("menu")).toBeVisible();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });
});
