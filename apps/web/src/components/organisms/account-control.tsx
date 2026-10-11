"use client";

import { useLocale, useTranslations } from "next-intl";
import { useRef } from "react";

import { Button } from "@/components/atoms/button";
import { Menu, MenuContent, MenuItem, MenuSeparator, MenuTrigger } from "@/components/atoms/menu";
import { Link } from "@/lib/i18n/navigation";
import { isShellPrefetchHref } from "@/lib/prefetch-policy";
import { UI } from "@/lib/ui-selectors";
import { Icon, type IconName } from "@/theme";
import { corporateHref } from "@/lib/features/corporate-path";

export function AccountControl({ signedIn }: { signedIn: boolean }) {
  const t = useTranslations("nav");

  if (!signedIn) {
    return (
      <Button asChild size="icon" variant="outline" className="size-11">
        <Link
          data-ui={UI.navigation.account}
          href={corporateHref("/login")}
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
    <Menu modal={false}>
      <MenuTrigger asChild>
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
      </MenuTrigger>
      <AccountMenu />
    </Menu>
  );
}

export function AccountMenu() {
  const t = useTranslations("nav");
  const locale = useLocale();
  const logoutFormRef = useRef<HTMLFormElement>(null);

  return (
    <>
      {/* Stay mounted outside Content: selecting an item unmounts the portal before a nested form can POST. */}
      <form ref={logoutFormRef} action={`/api/auth/logout?locale=${locale}`} method="post" hidden />
      <MenuContent
        align="end"
        sideOffset={8}
        aria-label={t("accountMenu")}
        className="max-h-[min(24rem,calc(100dvh-5rem))] w-[min(14rem,calc(100vw-1.5rem))] overflow-x-hidden overflow-y-auto p-1.5"
      >
        <AccountMenuLink href="/account" icon="user">
          {t("profile")}
        </AccountMenuLink>
        <AccountMenuLink href="/objects" icon="objects" ui={UI.navigation.objects}>
          {t("myObjects")}
        </AccountMenuLink>
        <AccountMenuLink href="/assigned" icon="team">
          {t("assignedToMe")}
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
        <MenuSeparator />
        <MenuItem
          className="text-destructive hover:bg-destructive/10 focus:bg-destructive/10"
          onSelect={() => {
            logoutFormRef.current?.requestSubmit();
          }}
        >
          <Icon name="logout" size="sm" />
          {t("logout")}
        </MenuItem>
      </MenuContent>
    </>
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
    <MenuItem asChild>
      <Link
        href={corporateHref(href)}
        prefetch={false}
        {...(ui ? { "data-ui": ui } : {})}
        className="gap-3"
      >
        <Icon name={icon} size="sm" />
        {children}
      </Link>
    </MenuItem>
  );
}
