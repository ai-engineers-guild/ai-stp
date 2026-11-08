"use client";

import { useTranslations } from "next-intl";

import { Button } from "@/components/atoms/button";
import { CLI_RELEASES_URL } from "@/lib/install/install-command";

/** Landing download panel for the signed native release archives. */
export function InstallBlock() {
  const t = useTranslations("landing");
  return (
    <section
      aria-labelledby="install-heading"
      className="min-w-0 rounded-lg border border-border/70 bg-card/75 p-5 text-card-foreground shadow-md backdrop-blur-md sm:p-7"
    >
      <h2 id="install-heading" className="text-xl font-medium tracking-tight">
        {t("installHeading")}
      </h2>
      <p className="mt-1 text-sm leading-relaxed text-muted-foreground">{t("installHint")}</p>
      <Button asChild size="lg" className="mt-5 w-full sm:w-auto">
        <a href={CLI_RELEASES_URL}>{t("downloadCli")}</a>
      </Button>
      <p className="mt-3 text-sm text-muted-foreground">{t("platformSupport")}</p>
    </section>
  );
}
