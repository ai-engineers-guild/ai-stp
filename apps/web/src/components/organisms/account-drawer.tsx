"use client";

import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { useLocale, useTranslations } from "next-intl";

import { Button } from "@/components/atoms/button";
import { Link } from "@/lib/i18n/navigation";
import { isShellPrefetchHref } from "@/lib/prefetch-policy";
import { UI } from "@/lib/ui-selectors";
import { Icon, type IconName } from "@/theme";

export function AccountControl({ signedIn }: { signedIn: boolean }) {
  const t = useTranslations("nav");

  if (!signedIn) {
    return (
      <Button asChild size="icon" variant="outline" className="size-11">
        <Link
          data-ui={UI.navigation.account}
          href="/login"
          prefetch={isShellPrefetchHref("/login")}
          title={t("loginHint")}
          aria-label={t("login")}
        >
          <Icon name="user" size="md" />
          <span className="sr-only">{t("profileShortcut")}</span>
        </Link>
      </Button>
    );
  }

  return (
    <DropdownMenu.Root modal={false}>
      <DropdownMenu.Trigger asChild>
        <Button
          type="button"
          size="icon"
          variant="outline"
          className="size-11"
          data-ui={UI.navigation.account}
          title={t("accountHint")}
          aria-label={t("account")}
        >
          <Icon name="user" size="md" />
          <span className="sr-only">{t("profileShortcut")}</span>
        </Button>
      </DropdownMenu.Trigger>
      <AccountMenu />
    </DropdownMenu.Root>
  );
}

export function AccountMenu() {
  const t = useTranslations("nav");
  const locale = useLocale();

  return (
    <DropdownMenu.Portal>
      <DropdownMenu.Content
        align="end"
        sideOffset={8}
        collisionPadding={12}
        aria-label={t("accountMenu")}
        className="border-border bg-popover text-popover-foreground z-[80] max-h-[min(24rem,calc(100dvh-5rem))] w-[min(14rem,calc(100vw-1.5rem))] overflow-x-hidden overflow-y-auto rounded-lg border p-1.5 shadow-md"
      >
        <AccountMenuLink href="/account" icon="user">
          {t("profile")}
        </AccountMenuLink>
        <AccountMenuLink href="/objects" icon="objects" ui={UI.navigation.objects}>
          {t("myObjects")}
        </AccountMenuLink>
        <AccountMenuLink href="/likes" icon="heart">
          {t("myLikes")}
        </AccountMenuLink>
        <AccountMenuLink href="/devices" icon="devices" ui={UI.navigation.devices}>
          {t("devices")}
        </AccountMenuLink>
        <AccountMenuLink href="/access" icon="access" ui={UI.navigation.access}>
          {t("access")}
        </AccountMenuLink>
        <AccountMenuLink href="/reports" icon="flag" ui={UI.navigation.reports}>
          {t("reports")}
        </AccountMenuLink>
        <DropdownMenu.Separator className="bg-border my-1.5 h-px" />
        <DropdownMenu.Item asChild>
          <form action={`/api/auth/logout?locale=${locale}`} method="post">
            <button
              type="submit"
              className="text-destructive hover:bg-destructive/10 focus:bg-destructive/10 flex min-h-11 w-full items-center gap-3 rounded-sm px-3 py-2 text-sm outline-none"
            >
              <Icon name="logout" size="sm" />
              {t("logout")}
            </button>
          </form>
        </DropdownMenu.Item>
      </DropdownMenu.Content>
    </DropdownMenu.Portal>
  );
}

function AccountMenuLink({
  href,
  icon,
  ui,
  children,
}: {
  href: string;
  icon: IconName;
  ui?: string;
  children: string;
}) {
  return (
    <DropdownMenu.Item asChild>
      <Link
        href={href}
        prefetch={false}
        {...(ui ? { "data-ui": ui } : {})}
        className="hover:bg-muted focus:bg-muted flex min-h-11 items-center gap-3 rounded-sm px-3 py-2 text-sm outline-none"
      >
        <Icon name={icon} size="sm" />
        {children}
      </Link>
    </DropdownMenu.Item>
  );
}
