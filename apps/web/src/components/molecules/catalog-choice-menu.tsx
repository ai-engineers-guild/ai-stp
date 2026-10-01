"use client";

import * as DropdownMenu from "@radix-ui/react-dropdown-menu";

import { Button } from "@/components/atoms/button";
import { Link } from "@/lib/i18n/navigation";
import { Icon, type IconName } from "@/theme";

type Choice = {
  label: string;
  href?: string;
  onSelect?: () => void;
  active?: boolean;
  disabled?: boolean;
  icon?: IconName;
  separatorBefore?: boolean;
};

export function CatalogChoiceMenu({
  label,
  icon,
  options,
  align = "center",
  variant = "outline",
}: {
  label: string;
  icon: IconName;
  variant?: "outline" | "ghost";
  align?: "start" | "center" | "end";
  options: Choice[];
}) {
  return (
    <DropdownMenu.Root modal={false}>
      <DropdownMenu.Trigger asChild>
        <Button
          type="button"
          variant={variant}
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
              <DropdownMenu.Item asChild disabled={Boolean(option.disabled)}>
                {option.href ? (
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
                ) : (
                  <button
                    type="button"
                    onClick={option.onSelect}
                    className="hover:bg-muted focus:bg-muted flex min-h-10 w-full items-center gap-2 rounded-md px-3 text-left text-sm outline-none disabled:opacity-50"
                    disabled={option.disabled}
                  >
                    {option.icon ? <Icon name={option.icon} size="sm" /> : null}
                    {option.label}
                  </button>
                )}
              </DropdownMenu.Item>
            </div>
          ))}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
