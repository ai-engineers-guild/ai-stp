"use client";

import { useEffect, useState } from "react";
import { useTheme } from "next-themes";
import { useTranslations } from "next-intl";

import { UI } from "@/lib/ui-selectors";
import { Icon } from "@/theme";

export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const t = useTranslations("theme");
  // next-themes resolves the theme on the client's first render, but the server
  // rendered the default. Gate theme-dependent output on `mounted` so server and
  // first client render are identical and hydration does not mismatch.
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    setMounted(true);
  }, []);
  const isDark = mounted && resolvedTheme === "dark";

  return (
    <button
      data-ui={UI.theme.toggle}
      type="button"
      className="border-input bg-background hover:bg-muted focus-visible:ring-ring inline-flex size-10 items-center justify-center rounded-sm border transition-colors focus-visible:ring-2 focus-visible:outline-none"
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
