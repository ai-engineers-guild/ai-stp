"use client";

import { Button } from "@/components/atoms/button";
import { Menu, MenuContent, MenuItem, MenuTrigger } from "@/components/atoms/menu";
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
    <Menu>
      <MenuTrigger asChild>
        <Button type="button" variant="outline" className="min-h-11 w-full">
          <Icon name="access" size="sm" />
          {label}
        </Button>
      </MenuTrigger>
      <MenuContent align="center" sideOffset={6}>
        {options.map((option) => (
          <MenuItem asChild key={option.href}>
            <a href={option.href}>
              <Icon name={option.icon ?? "access"} size="sm" />
              <span className="flex-1">{option.label}</span>
            </a>
          </MenuItem>
        ))}
      </MenuContent>
    </Menu>
  );
}
