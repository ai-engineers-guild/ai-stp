import { createElement, forwardRef, type ComponentProps } from "react";
import { createNavigation } from "next-intl/navigation";

import { corporateHref } from "@/lib/features/corporate-path";

import { routing } from "./routing";

const navigation = createNavigation(routing);
const LocalizedLink = navigation.Link;
type LinkProps = ComponentProps<typeof LocalizedLink>;

export const Link = forwardRef<HTMLAnchorElement, LinkProps>(function Link({ href, ...rest }, ref) {
  return createElement(LocalizedLink, {
    ...rest,
    href: typeof href === "string" ? corporateHref(href) : href,
    ref,
  });
});

export const { redirect, usePathname, useRouter, getPathname } = navigation;
