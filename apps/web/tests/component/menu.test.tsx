import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Menu, MenuContent, MenuItem, MenuSeparator, MenuTrigger } from "@/components/atoms/menu";

describe("Menu atom", () => {
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
