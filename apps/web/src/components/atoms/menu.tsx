"use client";

import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import type { ComponentProps } from "react";

import { cn } from "@/lib/cn";

/**
 * Menu — the only file allowed to import `radix-ui/react-dropdown-menu`.
 * Owns the popover surface, item and separator styling; consumers compose
 * these wrappers and never style the primitive inline.
 */
export const Menu = DropdownMenu.Root;
export const MenuTrigger = DropdownMenu.Trigger;
export const MenuPortal = DropdownMenu.Portal;

export function MenuContent({
  className,
  side = "bottom",
  align = "end",
  sideOffset = 4,
  collisionPadding = 12,
  ...props
}: ComponentProps<typeof DropdownMenu.Content>) {
  return (
    <DropdownMenu.Portal>
      <DropdownMenu.Content
        side={side}
        align={align}
        sideOffset={sideOffset}
        collisionPadding={collisionPadding}
        className={cn(
          "border-border bg-popover text-popover-foreground z-[80] max-w-[min(20rem,calc(100vw-1.5rem))] min-w-52 rounded-lg border p-1 shadow-md",
          className,
        )}
        {...props}
      />
    </DropdownMenu.Portal>
  );
}

export function MenuItem({ className, ...props }: ComponentProps<typeof DropdownMenu.Item>) {
  return (
    <DropdownMenu.Item
      className={cn(
        "hover:bg-muted focus:bg-muted focus-visible:bg-muted flex min-h-11 w-full cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-left text-sm outline-none focus-visible:outline-none data-[disabled]:pointer-events-none data-[disabled]:opacity-50",
        className,
      )}
      {...props}
    />
  );
}

export function MenuSeparator({
  className,
  ...props
}: ComponentProps<typeof DropdownMenu.Separator>) {
  return (
    <DropdownMenu.Separator className={cn("bg-border -mx-1 my-1 h-px", className)} {...props} />
  );
}
