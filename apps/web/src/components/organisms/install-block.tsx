"use client";

import { useTranslations } from "next-intl";

import { ClipboardIconButton } from "@/components/molecules/clipboard-icon-button";
import { INSTALL_COMMAND, INSTALL_PREREQUISITES } from "@/lib/install/install-command";

/** Landing install panel — mono command + secondary copy action. */
export function InstallBlock() {
  const t = useTranslations("landing");
  const tc = useTranslations("common");

  return (
    <section
      aria-labelledby="install-heading"
      className="border-border/70 bg-card/75 text-card-foreground min-w-0 rounded-lg border p-5 shadow-md backdrop-blur-md sm:p-7"
    >
      <h2 id="install-heading" className="text-xl font-medium tracking-tight">
        {t("installHeading")}
      </h2>
      <p className="text-muted-foreground mt-1 text-sm leading-relaxed">{t("installHint")}</p>
      <div className="mt-5 flex min-w-0 flex-col gap-2 sm:flex-row sm:items-center">
        <code className="border-border/70 bg-muted/65 text-foreground block min-w-0 flex-1 overflow-x-auto rounded-sm border p-3 font-mono text-sm break-all whitespace-pre-wrap">
          {INSTALL_COMMAND}
        </code>
        <ClipboardIconButton
          value={INSTALL_COMMAND}
          label={tc("copy")}
          copiedLabel={tc("copied")}
          variant="secondary"
          className="min-h-11 w-full shrink-0 sm:w-auto"
        >
          {tc("copy")}
        </ClipboardIconButton>
      </div>
      <div className="mt-3">
        <h3 className="text-sm font-medium">{t("prerequisites")}</h3>
        <ul className="text-muted-foreground mt-1 list-disc pl-5 text-sm">
          {INSTALL_PREREQUISITES.map((item) => (
            <li key={item}>
              <code className="font-mono text-xs">{item}</code>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
