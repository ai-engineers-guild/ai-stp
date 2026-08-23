"use client";

import { type FormEvent, useState } from "react";
import { useTranslations } from "next-intl";

import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import { Textarea } from "@/components/atoms/textarea";
import { submitComplaint, type ComplaintTargetKind } from "@/lib/actions/complaints";
import { ApiError } from "@/lib/api/errors";
import { UI } from "@/lib/ui-selectors";

type ContactFormProps = {
  targetKind?: ComplaintTargetKind;
  target?: string;
  defaultSubject?: string;
  reportType?: string;
};

export function ContactForm({
  targetKind = "other",
  target = "contact",
  defaultSubject = "",
  reportType,
}: ContactFormProps) {
  const t = useTranslations("contact");
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const field = (name: string) => {
      const value = data.get(name);
      return typeof value === "string" ? value.trim() : "";
    };
    setPending(true);
    setError(null);
    try {
      const subject = field("subject");
      const message = reportType
        ? `${t("requestType")}: ${reportType}\n\n${field("message")}`
        : field("message");
      await submitComplaint({
        targetKind,
        target,
        senderName: field("name"),
        replyEmail: field("email"),
        subject,
        message,
      });
      setSubmitted(true);
    } catch (cause) {
      if (cause instanceof ApiError && cause.code === "AI_STP_RATE_LIMITED") {
        setError(t("rateLimited"));
      } else {
        setError(t("submitError"));
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <form data-ui={UI.contact.form} className="space-y-5" onSubmit={(event) => void submit(event)}>
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
      <Button data-ui={UI.contact.submit} type="submit" disabled={pending || submitted}>
        {t("send")}
      </Button>
      {error ? (
        <p role="alert" className="text-destructive text-sm">
          {error}
        </p>
      ) : null}
      {submitted ? (
        <p role="status" className="text-sm">
          {t("submitted")}
        </p>
      ) : null}
    </form>
  );
}
