"use client";

import { useState } from "react";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { useTranslations } from "next-intl";
import { Button } from "@/components/atoms/button";
import { Link } from "@/lib/i18n/navigation";
import { cn } from "@/lib/cn";
import { UI } from "@/lib/ui-selectors";
import { Icon, type IconName } from "@/theme/icons";

export type RailItem = {
  id: string;
  href: string;
  label: string;
  icon: IconName;
  active: boolean;
  external?: boolean | undefined;
  children?: RailItem[] | undefined;
  /** Pinned under a divider at the rail bottom (leaf items only). */
  pinned?: boolean | undefined;
};

export const railItemClass =
  "text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:ring-ring flex min-h-11 min-w-0 items-center gap-3 rounded-sm px-3 text-sm outline-none focus-visible:ring-2";
const activeClass =
  "bg-primary/5 dark:bg-primary/10 text-primary font-medium before:absolute before:inset-y-2 before:left-0 before:w-1 before:rounded-sm before:bg-primary";

export function RailItems({
  items,
  collapsed,
  scope,
  onNavigate,
}: {
  items: RailItem[];
  collapsed: boolean;
  scope: string;
  onNavigate: () => void;
}) {
  const t = useTranslations("nav");
  const [disclosures, setDisclosures] = useState<Record<string, boolean>>({});
  function link(item: RailItem, child = false) {
    const props = {
      "data-ui":
        item.id === UI.navigation.account || item.id === UI.navigation.contact
          ? `sidebar-${item.id}`
          : item.id,
      "aria-current": item.active ? ("page" as const) : undefined,
      title: collapsed ? item.label : undefined,
      className: cn(
        railItemClass,
        "relative",
        child && !collapsed && "pl-6",
        collapsed && "justify-center px-0",
        item.active && activeClass,
      ),
      onClick: onNavigate,
    };
    const content = (
      <>
        <Icon name={item.icon} size="md" />
        <span className={collapsed ? "sr-only" : "min-w-0 flex-1"}>{item.label}</span>
      </>
    );
    return item.external ? (
      <a key={item.id} href={item.href} {...props}>
        {content}
      </a>
    ) : (
      <Link key={item.id} href={item.href} prefetch={false} {...props}>
        {content}
      </Link>
    );
  }
  return items.map((item) => {
    if (!item.children?.length) {
      const node = link(item);
      return item.pinned ? (
        <div key={item.id} className="border-border mt-auto space-y-1 border-t pt-2">
          {node}
        </div>
      ) : (
        node
      );
    }
    const key = `${scope}:${item.id}`;
    const open = disclosures[key] ?? (item.active || item.children.some((child) => child.active));
    const toggle = () => {
      setDisclosures((current) => ({ ...current, [key]: !open }));
    };
    const label = t(open ? "collapseSection" : "expandSection", { section: item.label });
    if (collapsed)
      return (
        <DropdownMenu.Root key={item.id} modal={false}>
          <DropdownMenu.Trigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              data-ui={item.id}
              aria-label={item.label}
              title={item.label}
              data-active={item.active || item.children.some((child) => child.active)}
              className={cn(
                railItemClass,
                "relative w-full justify-center px-0",
                (item.active || item.children.some((child) => child.active)) && activeClass,
              )}
            >
              <Icon name={item.icon} size="md" />
            </Button>
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content
              side="right"
              align="start"
              sideOffset={8}
              collisionPadding={12}
              aria-label={item.label}
              className="border-border bg-popover text-popover-foreground z-[70] max-h-[var(--radix-dropdown-menu-content-available-height)] max-w-[calc(100vw-1.5rem)] min-w-52 overflow-y-auto rounded-lg border p-1 shadow-md"
            >
              {(item.href ? [item, ...item.children] : item.children).map((child) => (
                <DropdownMenu.Item key={child.id} asChild>
                  <Link
                    href={child.href}
                    prefetch={false}
                    data-ui={child.id}
                    aria-current={child.active ? "page" : undefined}
                    className={cn(
                      railItemClass,
                      "focus:bg-muted",
                      child.active && "text-primary font-medium",
                    )}
                    onClick={onNavigate}
                  >
                    <Icon name={child.icon} size="md" />
                    <span className="min-w-0 flex-1 break-words">{child.label}</span>
                  </Link>
                </DropdownMenu.Item>
              ))}
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>
      );
    return (
      <div key={item.id} className="space-y-1">
        <div className="flex min-w-0 items-center">
          {item.href ? <div className="min-w-0 flex-1">{link(item)}</div> : null}
          <Button
            type="button"
            variant="ghost"
            size={item.href ? "icon" : "default"}
            aria-label={label}
            aria-expanded={open}
            aria-controls={`${scope}-${item.id}`}
            className={cn("h-11 shrink-0", !item.href && "w-full justify-start gap-3 px-3 text-sm")}
            onClick={toggle}
          >
            {!item.href ? (
              <>
                <Icon name={item.icon} size="md" />
                <span className="flex-1 text-left">{item.label}</span>
              </>
            ) : null}
            <Icon name={open ? "chevronUp" : "chevronDown"} size="sm" />
          </Button>
        </div>
        <div id={`${scope}-${item.id}`} hidden={!open} className="space-y-1">
          {item.children.map((child) => link(child, true))}
        </div>
      </div>
    );
  });
}
