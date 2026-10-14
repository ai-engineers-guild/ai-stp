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
      className="border-border/70 bg-card/75 text-card-foreground min-w-0 rounded-lg border p-5 shadow-md backdrop-blur-md sm:p-7"
    >
      <h2 id="install-heading" className="text-xl font-medium tracking-tight">
        {t("installHeading")}
      </h2>
      <p className="text-muted-foreground mt-1 text-sm leading-relaxed">{t("installHint")}</p>
      <Button asChild size="lg" className="mt-5 w-full sm:w-auto">
        <a href={CLI_RELEASES_URL}>{t("downloadCli")}</a>
      </Button>
      <p className="text-muted-foreground mt-3 text-sm">{t("platformSupport")}</p>
    </section>
  );
}
