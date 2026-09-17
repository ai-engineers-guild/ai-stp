"use client";

import * as DropdownMenu from "@radix-ui/react-dropdown-menu";

import { Button } from "@/components/atoms/button";
import { Link } from "@/lib/i18n/navigation";
import { Icon } from "@/theme";

export function EntityDetailMenu({
  moreLabel,
  editLabel,
  editHref,
}: {
  moreLabel: string;
  editLabel: string;
  editHref: string;
}) {
  return (
    <DropdownMenu.Root modal={false}>
      <DropdownMenu.Trigger asChild>
        <Button type="button" variant="outline" size="icon" aria-label={moreLabel}>
          <Icon name="more" size="sm" />
        </Button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="end"
          sideOffset={6}
          className="border-border bg-popover text-popover-foreground z-50 min-w-48 rounded-md border p-1 shadow-md"
        >
          <DropdownMenu.Item asChild>
            <Link
              href={editHref}
              className="hover:bg-muted focus-visible:bg-muted flex min-h-11 cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-sm outline-none"
            >
              <Icon name="edit" size="sm" />
              {editLabel}
            </Link>
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
