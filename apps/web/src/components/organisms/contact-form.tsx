"use client";

import { type FormEvent, useState } from "react";
import { useTranslations } from "next-intl";

import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import { Textarea } from "@/components/atoms/textarea";
import { UI } from "@/lib/ui-selectors";

type ContactFormProps = {
  recipient: string;
  placeholderRecipient: boolean;
  defaultSubject?: string;
  reportType?: string;
};

export function ContactForm({
  recipient,
  placeholderRecipient,
  defaultSubject = "",
  reportType,
}: ContactFormProps) {
  const t = useTranslations("contact");
  const [opened, setOpened] = useState(false);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const field = (name: string) => {
      const value = data.get(name);
      return typeof value === "string" ? value.trim() : "";
    };
    const subject = field("subject");
    const body = [
      ...(reportType ? [`${t("requestType")}: ${reportType}`, ""] : []),
      `${t("name")}: ${field("name")}`,
      `${t("email")}: ${field("email")}`,
      "",
      field("message"),
    ].join("\n");
    window.location.href = `mailto:${recipient}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
    setOpened(true);
  }

  return (
    <form data-ui={UI.contact.form} className="space-y-5" onSubmit={submit}>
      {placeholderRecipient ? (
        <p
          role="status"
          className="border-warning text-foreground rounded-sm border px-3 py-2 text-sm"
        >
          {t("placeholderWarning")}
        </p>
      ) : null}
      <div className="grid gap-5 sm:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor={UI.contact.name}>{t("name")}</Label>
          <Input
            id={UI.contact.name}
            data-ui={UI.contact.name}
            name="name"
            autoComplete="name"
            required
            maxLength={120}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor={UI.contact.email}>{t("email")}</Label>
          <Input
            id={UI.contact.email}
            data-ui={UI.contact.email}
            name="email"
            type="email"
            autoComplete="email"
            required
            maxLength={254}
          />
        </div>
      </div>
      <div className="space-y-2">
        <Label htmlFor={UI.contact.subject}>{t("subject")}</Label>
        <Input
          id={UI.contact.subject}
          data-ui={UI.contact.subject}
          name="subject"
          defaultValue={defaultSubject}
          required
          maxLength={160}
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor={UI.contact.message}>{t("message")}</Label>
        <Textarea
          id={UI.contact.message}
          data-ui={UI.contact.message}
          name="message"
          required
          minLength={10}
          maxLength={4000}
          rows={8}
        />
        <p className="text-muted-foreground text-xs">{t("privacyHint")}</p>
      </div>
      <Button data-ui={UI.contact.submit} type="submit" disabled={placeholderRecipient}>
        {t("send")}
      </Button>
      {opened ? (
        <p role="status" className="text-sm">
          {t("opened")}
        </p>
      ) : null}
    </form>
  );
}
