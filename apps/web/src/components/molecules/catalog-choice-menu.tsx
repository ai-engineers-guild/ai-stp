"use client";

import { Button } from "@/components/atoms/button";
import { Menu, MenuContent, MenuItem, MenuSeparator, MenuTrigger } from "@/components/atoms/menu";
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
    <Menu modal={false}>
      <MenuTrigger asChild>
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
      </MenuTrigger>
      <MenuContent align={align} sideOffset={6}>
        {options.map((option) => (
          <div key={option.label}>
            {option.separatorBefore ? <MenuSeparator /> : null}
            {option.href ? (
              <MenuItem
                asChild
                disabled={Boolean(option.disabled)}
                className="aria-[current=true]:text-primary"
              >
                <Link
                  href={option.href}
                  prefetch={false}
                  aria-current={option.active ? "true" : undefined}
                >
                  {option.icon ? <Icon name={option.icon} size="sm" /> : null}
                  <span className="flex-1">{option.label}</span>
                  {option.active ? <Icon name="check" size="sm" /> : null}
                </Link>
              </MenuItem>
            ) : (
              <MenuItem
                onSelect={option.onSelect ?? (() => {})}
                disabled={option.disabled ?? false}
              >
                {option.icon ? <Icon name={option.icon} size="sm" /> : null}
                {option.label}
              </MenuItem>
            )}
          </div>
        ))}
      </MenuContent>
    </Menu>
  );
}
