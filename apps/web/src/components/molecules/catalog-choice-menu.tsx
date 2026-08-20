"use client";

import * as DropdownMenu from "@radix-ui/react-dropdown-menu";

import { Button } from "@/components/atoms/button";
import { Link } from "@/lib/i18n/navigation";
import { Icon } from "@/theme";

type Choice = {
  label: string;
  href: string;
  active: boolean;
  icon?: "list" | "cards";
  separatorBefore?: boolean;
};

export function CatalogChoiceMenu({
  label,
  icon,
  options,
  align = "center",
}: {
  label: string;
  icon: "list" | "cards" | "sort";
  align?: "start" | "center" | "end";
  options: Choice[];
}) {
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <Button
          type="button"
          variant="outline"
          size="icon"
          className="h-11 w-11"
          aria-label={label}
          title={label}
        >
          <Icon name={icon} size="sm" />
        </Button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align={align}
          sideOffset={6}
          collisionPadding={12}
          className="border-border bg-popover z-[70] max-w-[calc(100vw-1.5rem)] min-w-52 rounded-lg border p-1 shadow-md"
        >
          {options.map((option) => (
            <div key={option.label}>
              {option.separatorBefore ? (
                <DropdownMenu.Separator className="bg-border my-1 h-px" />
              ) : null}
              <DropdownMenu.Item asChild>
                <Link
                  href={option.href}
                  prefetch={false}
                  aria-current={option.active ? "true" : undefined}
                  className="hover:bg-muted focus:bg-muted aria-[current=true]:text-primary flex min-h-10 items-center gap-2 rounded-md px-3 text-sm outline-none"
                >
                  {option.icon ? <Icon name={option.icon} size="sm" /> : null}
                  <span className="flex-1">{option.label}</span>
                  {option.active ? <Icon name="check" size="sm" /> : null}
                </Link>
              </DropdownMenu.Item>
            </div>
          ))}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
