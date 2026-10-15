import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import {
  Menu,
  MenuContent,
  MenuItem,
  MenuSeparator,
  MenuTrigger,
  MenuSub,
  MenuSubTrigger,
  MenuSubContent,
} from "@/components/atoms/menu";

describe("Menu atom", () => {
  it("keeps copy actions in a keyboard accessible flyout and selects them", async () => {
    const copy = vi.fn();
    const user = userEvent.setup();
    render(
      <Menu modal={false}>
        <MenuTrigger>Actions</MenuTrigger>
        <MenuContent>
          <MenuSub>
            <MenuSubTrigger>Copy and share</MenuSubTrigger>
            <MenuSubContent>
              <MenuItem onSelect={copy}>Copy ID</MenuItem>
            </MenuSubContent>
          </MenuSub>
          <MenuItem>Edit</MenuItem>
        </MenuContent>
      </Menu>,
    );
    await user.click(screen.getByRole("button", { name: "Actions" }));
    expect(screen.queryByRole("menuitem", { name: "Copy ID" })).toBeNull();
    screen.getByRole("menuitem", { name: "Copy and share" }).focus();
    await user.keyboard("{ArrowRight}");
    await screen.findByRole("menuitem", { name: "Copy ID" });
    await user.keyboard("{Enter}");
    expect(copy).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("menu")).toBeNull();
  });
  it("opens on the trigger and selects an item", async () => {
    const onSelect = vi.fn();
    render(
      <Menu modal={false}>
        <MenuTrigger>Open</MenuTrigger>
        <MenuContent>
          <MenuItem onSelect={onSelect}>Copy link</MenuItem>
          <MenuSeparator />
          <MenuItem disabled>Report</MenuItem>
        </MenuContent>
      </Menu>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Open" }));
    expect(await screen.findByRole("menuitem", { name: "Report" })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    await userEvent.click(screen.getByRole("menuitem", { name: "Copy link" }));
    expect(onSelect).toHaveBeenCalled();
  });

  it("renders link items through asChild", async () => {
    render(
      <Menu modal={false} defaultOpen>
        <MenuTrigger>Open</MenuTrigger>
        <MenuContent>
          <MenuItem asChild>
            <a href="/catalog">Catalog</a>
          </MenuItem>
        </MenuContent>
      </Menu>,
    );
    const item = await screen.findByRole("menuitem", { name: "Catalog" });
    expect(item.tagName).toBe("A");
    expect(item).toHaveAttribute("href", "/catalog");
    expect(item.className).toMatch(/min-h-11/);
  });
});
