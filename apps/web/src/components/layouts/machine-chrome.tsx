"use client";

import { useTranslations } from "next-intl";

import { KeyboardNavigation } from "@/components/molecules/keyboard-navigation";
import { COMPILED_FEATURES } from "@/lib/features/compiled";
import { ThemeToggle } from "@/components/molecules/theme-toggle";
import { usePathname, useRouter } from "@/lib/i18n/navigation";
import { locales } from "@/lib/i18n/routing";
import { siteNavigation } from "@/lib/projection/navigation";
import { projectedHref } from "@/lib/projection/paths";
import { UI } from "@/lib/ui-selectors";

type MachineChromeProps = {
  signedIn: boolean;
  locale: string;
  docsHref: string;
};

function MdLink({ href, children }: { href: string; children: string }) {
  return (
    <a href={href}>
      [{children}]({href})
    </a>
  );
}

export function MachineHeader({ signedIn, locale, docsHref }: MachineChromeProps) {
  const nav = useTranslations("nav");
  const pathname = usePathname();
  const router = useRouter();
  const accountPath = signedIn ? "/account" : "/login";
  // Same model as the human header, rendered as Markdown links.
  const items = siteNavigation({ signedIn, docsHref });

  return (
    <header
      id="machine-header"
      data-ui={UI.machine.header}
      className="border-border bg-background sticky top-0 z-40 border-b font-mono"
    >
      <KeyboardNavigation
        accountHref={accountPath}
        contactEnabled={COMPILED_FEATURES.saas_public_pages}
      />
      <div className="mx-auto flex h-16 max-w-6xl flex-nowrap items-center gap-x-4 px-4 text-xs sm:px-6">
        <span aria-hidden>{"$"}</span>
        {items.map((item) => (
          <span
            key={item.ui}
            data-ui={item.ui}
            className={item.labelKey === "home" ? undefined : "hidden sm:inline"}
          >
            <MdLink href={item.external ? item.href : projectedHref(item.href, locale)}>
              {item.labelKey === "home" ? "ai_stp" : nav(item.labelKey)}
            </MdLink>
          </span>
        ))}
        <span className="hidden lg:inline">
          <MdLink href="/llms.txt">llms.txt</MdLink>
        </span>
        <span className="ml-auto flex shrink-0 items-center gap-2">
          <label htmlFor="machine-locale">lang:</label>
          <select
            id="machine-locale"
            data-ui={UI.machine.locale}
            className="border-border bg-background h-9 border px-2"
            value={locale}
            onChange={(event) => {
              router.replace(pathname, { locale: event.target.value });
            }}
          >
            {locales.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </span>
        <span className="shrink-0">
          <ThemeToggle />
        </span>
      </div>
    </header>
  );
}

export function MachineFooter() {
  const machine = useTranslations("machine");
  return (
    <footer
      id="machine-footer"
      data-ui={UI.machine.footer}
      className="border-border bg-background border-t pb-16 font-mono text-xs"
    >
      <div className="mx-auto flex max-w-4xl flex-col gap-3 px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <p>© 2026 ai_stp · AGPL-3.0-or-later · {machine("projection")}</p>
        <div className="flex items-center gap-3">
          <span>
            {machine(COMPILED_FEATURES.saas_public_pages ? "shortcuts" : "shortcutsSelfHosted")}
          </span>
        </div>
      </div>
    </footer>
  );
}
