"use client";

import * as DropdownMenu from "@radix-ui/react-dropdown-menu";

import { Button } from "@/components/atoms/button";
import { Icon, type IconName } from "@/theme";

export type SsoOption = {
  label: string;
  href: string;
  icon?: IconName;
};

/**
 * One "Sign in with SSO" affordance (ADR-0218). A single configured provider
 * links straight to its /v1/auth/{provider}/login route under its own name;
 * several open a chooser menu so the page keeps one corporate entry point.
 */
export function SsoSignIn({ label, options }: { label: string; options: SsoOption[] }) {
  if (options.length === 0) {
    return null;
  }
  const [only] = options;
  if (options.length === 1 && only) {
    return (
      <Button asChild variant="outline" className="min-h-11 w-full">
        <a href={only.href}>
          <Icon name={only.icon ?? "access"} size="sm" />
          {only.label}
        </a>
      </Button>
    );
  }
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <Button type="button" variant="outline" className="min-h-11 w-full">
          <Icon name="access" size="sm" />
          {label}
        </Button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="center"
          sideOffset={6}
          collisionPadding={12}
          className="border-border bg-popover z-[70] max-w-[calc(100vw-1.5rem)] min-w-52 rounded-lg border p-1 shadow-md"
        >
          {options.map((option) => (
            <DropdownMenu.Item asChild key={option.href}>
              <a
                href={option.href}
                className="hover:bg-muted focus:bg-muted flex min-h-10 items-center gap-2 rounded-md px-3 text-sm outline-none"
              >
                <Icon name={option.icon ?? "access"} size="sm" />
                <span className="flex-1">{option.label}</span>
              </a>
            </DropdownMenu.Item>
          ))}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
