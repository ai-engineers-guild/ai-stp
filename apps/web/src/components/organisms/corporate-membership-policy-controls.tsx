"use client";
import { useState, useTransition } from "react";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { corporateMutationAction } from "@/actions/corporate";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import { Switch } from "@/components/atoms/switch";
function field(data: FormData, name: string) {
  const value = data.get(name);
  return typeof value === "string" ? value.trim() : "";
}
/** The existing domain policy form, shared with its dedicated Security page. */
export function CorporateMembershipPolicyControls({
  csrfToken,
  organizationId,
  authorizationRevision,
  allowedDomains,
}: {
  csrfToken: string;
  organizationId: string;
  authorizationRevision: number;
  allowedDomains: string[];
}) {
  const t = useTranslations("corporate");
  const router = useRouter();
  const [busy, startTransition] = useTransition();
  const [message, setMessage] = useState<{ text: string; error?: boolean } | null>(null);
  const report = (text: string, error = false) => {
    setMessage({ text, error });
  };
  function savePolicy(form: HTMLFormElement) {
    const formData = new FormData(form);
    const restricted = formData.get("domainRestrict") !== null;
    const domains = restricted
      ? field(formData, "domains")
          .split(/[\s,]+/)
          .map((domain) => domain.trim().toLowerCase())
          .filter(Boolean)
      : [];
    setMessage(null);
    startTransition(async () => {
      const result = await corporateMutationAction({
        csrfToken,
        organizationId,
        method: "PUT",
        path: `/v1/corporate/organizations/${organizationId}/membership/policy`,
        body: {
          schema_version: 1,
          authorization_revision: authorizationRevision,
          allowed_email_domains: domains,
          idempotency_key: crypto.randomUUID(),
        },
      });
      report(result.ok ? t("saved") : result.message, !result.ok);
      if (result.ok) router.refresh();
    });
  }

  return (
    <section className="border-border space-y-4 rounded-lg border p-5 sm:p-6">
      <h2 className="text-xl font-medium">{t("domainPolicy")}</h2>
      <div aria-live="polite">
        {message ? (
          <p
            className={message.error ? "text-destructive text-sm" : "text-muted-foreground text-sm"}
          >
            {message.text}
          </p>
        ) : null}
      </div>
      <form
        className="mt-4 space-y-3"
        onSubmit={(event) => {
          event.preventDefault();
          savePolicy(event.currentTarget);
        }}
      >
        <p className="text-muted-foreground mt-1 text-sm">{t("domainPolicyBody")}</p>
        <div className="flex items-center gap-3">
          <Switch
            id="domain-restrict"
            name="domainRestrict"
            defaultChecked={allowedDomains.length > 0}
            aria-label={t("domainRestrict")}
          />
          <Label htmlFor="domain-restrict" className="font-normal">
            {t("domainRestrict")}
          </Label>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="policy-domains">{t("domains")}</Label>
          <Input
            id="policy-domains"
            name="domains"
            placeholder={t("domainsPlaceholder")}
            defaultValue={allowedDomains.join(", ")}
          />
          <p className="text-muted-foreground text-xs">{t("domainsHint")}</p>
        </div>
        <Button type="submit" disabled={busy}>
          {busy ? t("saving") : t("save")}
        </Button>
      </form>
    </section>
  );
}
