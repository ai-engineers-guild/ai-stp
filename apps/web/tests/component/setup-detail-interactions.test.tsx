import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { NextIntlClientProvider } from "next-intl";
import messages from "../../messages/en.json";

vi.mock("@/lib/i18n/navigation", () => ({
  Link: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("@/lib/actions/catalog-reactions", () => ({
  updateCatalogReaction: vi.fn((_kind, _stableId, liked: boolean) =>
    Promise.resolve({ schema_version: 1, liked, likes_count: liked ? 13 : 12 }),
  ),
}));

import { ComponentActions } from "@/components/organisms/component-actions";

describe("setup detail actions", () => {
  it("copies a setup id from overflow and exposes the report target", async () => {
    const user = userEvent.setup();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    render(
      <div className="relative">
        <NextIntlClientProvider locale="en" messages={messages}>
          <ComponentActions
            stableId="setup_example"
            sharePath="/en/catalog/setups/setup_example/versions/1.0"
            likesCount={12}
            reportHref="/reports?object_kind=setup&stable_id=setup_example&version=1.0"
            labels={{
              copyUrl: "Copy URL",
              share: "Share",
              copyId: "Copy ID",
              copied: "Copied",
              like: "Like",
              unlike: "Liked",
              more: "More actions",
              report: "Report setup",
            }}
          />
        </NextIntlClientProvider>
      </div>,
    );

    expect(screen.queryByRole("button", { name: "Copy ID" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "More actions" }));
    await user.click(await screen.findByRole("menuitem", { name: /Copy ID/ }));
    expect(writeText).toHaveBeenCalledWith("setup_example");
    await user.click(screen.getByRole("button", { name: "Like · 12" }));
    expect(screen.getByRole("button", { name: "Liked · 13" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await user.click(screen.getByRole("button", { name: "More actions" }));
    await user.click(await screen.findByRole("menuitem", { name: /Report setup/ }));
    expect(await screen.findByRole("dialog")).toBeVisible();
    expect(screen.getByDisplayValue(/setup_example/)).toBeVisible();
  });

  it("keeps setup overflow actions at 44px without leaving the viewport", async () => {
    const user = userEvent.setup();
    render(
      <div className="relative">
        <NextIntlClientProvider locale="en" messages={messages}>
          <ComponentActions
            stableId="setup_example"
            sharePath="/en/catalog/setups/setup_example/versions/1.0"
            likesCount={12}
            reportHref="/reports?object_kind=setup&stable_id=setup_example&version=1.0"
            labels={{
              copyUrl: "Copy URL",
              share: "Share",
              copyId: "Copy ID",
              copied: "Copied",
              like: "Like",
              unlike: "Liked",
              more: "More actions",
              report: "Report setup",
            }}
          />
        </NextIntlClientProvider>
      </div>,
    );
    expect(screen.getByRole("button", { name: "Like · 12" })).toHaveClass("min-h-11");
    const more = screen.getByRole("button", { name: "More actions" });
    expect(more).toHaveClass("size-11");
    await user.click(more);
    const menu = await screen.findByRole("menu");
    expect(menu.className).toContain("max-w-[min(20rem,calc(100vw-1.5rem))]");
    expect(within(menu).getByRole("menuitem", { name: /Copy ID/ })).toHaveClass("min-h-11");
  });
});
