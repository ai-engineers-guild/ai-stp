"use client";

import { useTheme } from "next-themes";
import { useTranslations } from "next-intl";

import { UI } from "@/lib/ui-selectors";
import { useHydrated } from "@/lib/use-hydrated";
import { Icon } from "@/theme";

export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const t = useTranslations("theme");
  // next-themes resolves the theme on the client's first render, but the server
  // rendered the default. Gate theme-dependent output on hydration so server and
  // first client render are identical and hydration does not mismatch.
  const isDark = useHydrated() && resolvedTheme === "dark";

  return (
    <button
      data-ui={UI.theme.toggle}
      type="button"
      className="inline-flex size-10 items-center justify-center rounded-sm border border-input bg-background transition-colors hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
      aria-label={isDark ? t("switchLight") : t("switchDark")}
      title={isDark ? t("switchLight") : t("switchDark")}
      onClick={() => {
        setTheme(isDark ? "light" : "dark");
      }}
    >
      <Icon name={isDark ? "sun" : "moon"} size="sm" />
    </button>
  );
}
