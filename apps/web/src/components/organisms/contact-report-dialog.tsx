"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { Button } from "@/components/atoms/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/atoms/dialog";
import { ContactForm } from "@/components/organisms/contact-form";
import { CONTACT_EMAIL_PLACEHOLDER } from "@/lib/site";
import { Icon } from "@/theme";

export function ContactReportDialog({
  kind,
  target,
  label,
  triggerVariant = "ghost",
  asMenuItem = false,
  open: openProp,
  onOpenChange,
  hideTrigger = false,
}: {
  kind: "component" | "setup" | "author";
  target: string;
  label: string;
  triggerVariant?: "ghost" | "outline";
  asMenuItem?: boolean;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  hideTrigger?: boolean;
}) {
  const t = useTranslations("contact");
  const [uncontrolledOpen, setUncontrolledOpen] = useState(false);
  const open = openProp ?? uncontrolledOpen;
  const setOpen = onOpenChange ?? setUncontrolledOpen;
  const recipient = process.env.NEXT_PUBLIC_CONTACT_EMAIL ?? CONTACT_EMAIL_PLACEHOLDER;
  const type = t(
    kind === "author"
      ? "reportAuthorType"
      : kind === "setup"
        ? "reportSetupType"
        : "reportComponentType",
  );
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      {hideTrigger ? null : (
        <DialogTrigger asChild>
          {asMenuItem ? (
            <button
              type="button"
              role="menuitem"
              className="hover:bg-muted focus-visible:bg-muted flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm focus-visible:outline-none"
            >
              <Icon name="flag" size="sm" />
              {label}
            </button>
          ) : (
            <Button type="button" variant={triggerVariant} size="sm">
              <Icon name="flag" size="sm" />
              {label}
            </Button>
          )}
        </DialogTrigger>
      )}
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{type}</DialogTitle>
          <DialogDescription>{t("reportDialogHint")}</DialogDescription>
        </DialogHeader>
        <ContactForm
          recipient={recipient}
          placeholderRecipient={recipient === CONTACT_EMAIL_PLACEHOLDER}
          defaultSubject={`${type}: ${target}`}
          reportType={type}
        />
      </DialogContent>
    </Dialog>
  );
}
