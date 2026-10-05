"use client";
import { useState, useTransition } from "react";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { corporateMutation } from "@/lib/api/corporate-mutation";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import { InfoNote } from "@/components/molecules/info-note";
import { SettingsSection } from "@/components/molecules/settings-section";
import { SwitchRow } from "@/components/molecules/switch-row";
import { peopleSelectClass } from "@/components/organisms/corporate-people-ui";
import { Icon } from "@/theme";

let nextDomainKey = 0;
function domainKey() {
  nextDomainKey += 1;
  return `domain-${nextDomainKey}`;
}

// Mirrors _DOMAIN in apps/api .../corporate/invitations.py: multi-label
// lowercase DNS names; the API applies the same normalization on save.
const EMAIL_DOMAIN =
  /^(?=.{1,253}$)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$/;

function normalizeDomain(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/^[.@]+/, "")
    .replace(/\.+$/, "");
}

/** The email-domain allowlist policy, shared with the Security page. */
export function CorporateMembershipPolicyControls({
  csrfToken,
  organizationId,
  authorizationRevision,
  allowedDomains,
  peopleVisibility,
}: {
  csrfToken: string;
  organizationId: string;
  authorizationRevision: number;
  allowedDomains: string[];
  peopleVisibility: "members" | "teammates" | "admins";
}) {
  const t = useTranslations("corporate");
  const router = useRouter();
  const [busy, startTransition] = useTransition();
  const [restricted, setRestricted] = useState(allowedDomains.length > 0);
  const [domains, setDomains] = useState(() =>
    allowedDomains.map((value) => ({ key: domainKey(), value })),
  );
  const [message, setMessage] = useState<{ text: string; error?: boolean } | null>(null);

  function savePolicy(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const visibility = formData.get("peopleVisibility");
    const values = domains.map((entry) => normalizeDomain(entry.value)).filter(Boolean);
    if (restricted && !values.length) {
      setMessage({ text: t("domainsRequired"), error: true });
      return;
    }
    const invalid = values.find((value) => !EMAIL_DOMAIN.test(value));
    if (invalid) {
      setMessage({ text: t("invalidDomain", { domain: invalid }), error: true });
      return;
    }
    setMessage(null);
    startTransition(async () => {
      const result = await corporateMutation({
        csrfToken,
        organizationId,
        method: "PUT",
        path: `/v1/corporate/organizations/${organizationId}/membership/policy`,
        body: {
          schema_version: 1,
          authorization_revision: authorizationRevision,
          allowed_email_domains: restricted ? [...new Set(values)] : [],
          people_visibility:
            typeof visibility === "string" && visibility ? visibility : peopleVisibility,
          idempotency_key: crypto.randomUUID(),
        },
      });
      setMessage({ text: result.ok ? t("saved") : result.message, error: !result.ok });
      if (result.ok) router.refresh();
    });
  }

  return (
    <form onSubmit={savePolicy} aria-busy={busy}>
      <SettingsSection icon="mail" title={t("domainPolicy")} description={t("domainPolicyBody")}>
        <div className="lg:divide-border grid gap-6 lg:grid-cols-2 lg:divide-x">
          <div className="space-y-3">
            <Label>{t("domains")}</Label>
            <div className="space-y-2">
              {domains.map((entry, index) => (
                <div key={entry.key} className="flex items-center gap-2">
                  <Input
                    aria-label={t("domainEntryLabel", { index: index + 1 })}
                    value={entry.value}
                    disabled={busy}
                    placeholder={t("domainPlaceholder")}
                    onChange={(event) => {
                      setDomains((current) =>
                        current.map((item) =>
                          item.key === entry.key ? { ...item, value: event.target.value } : item,
                        ),
                      );
                    }}
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    aria-label={t("removeDomain", { domain: entry.value || t("domain") })}
                    disabled={busy}
                    onClick={() => {
                      setDomains((current) => current.filter((item) => item.key !== entry.key));
                    }}
                  >
                    <Icon name="trash" size="sm" />
                  </Button>
                </div>
              ))}
            </div>
            <Button
              type="button"
              variant="outline"
              className="border-dashed"
              disabled={busy || !restricted}
              onClick={() => {
                setDomains((current) => [...current, { key: domainKey(), value: "" }]);
              }}
            >
              <Icon name="plus" size="sm" aria-hidden />
              {t("addDomain")}
            </Button>
          </div>
          <div className="space-y-4 lg:pl-6">
            <h3 className="text-sm font-medium">{t("policySettings")}</h3>
            <SwitchRow
              id="domain-restrict"
              name="domainRestrict"
              label={t("domainRestrict")}
              description={t("domainRestrictHint")}
              value={restricted}
              disabled={busy}
              onCheckedChange={(next) => {
                setRestricted(next);
                if (next) setDomains((c) => (c.length ? c : [{ key: domainKey(), value: "" }]));
              }}
            />
            <InfoNote>{t("domainPolicyNote")}</InfoNote>
            <div className="space-y-2">
              <Label htmlFor="people-visibility">{t("peopleVisibility")}</Label>
              <select
                id="people-visibility"
                name="peopleVisibility"
                defaultValue={peopleVisibility}
                disabled={busy}
                className={peopleSelectClass}
              >
                <option value="members">{t("peopleVisibilityMembers")}</option>
                <option value="teammates">{t("peopleVisibilityTeammates")}</option>
                <option value="admins">{t("peopleVisibilityAdmins")}</option>
              </select>
              <p className="text-muted-foreground text-xs">{t("peopleVisibilityHint")}</p>
            </div>
          </div>
        </div>
      </SettingsSection>
      <div className="mt-4 flex items-center justify-end gap-4">
        <div aria-live="polite">
          {message ? (
            <p
              className={
                message.error ? "text-destructive text-sm" : "text-muted-foreground text-sm"
              }
            >
              {message.text}
            </p>
          ) : null}
        </div>
        <Button type="submit" size="lg" disabled={busy}>
          {busy ? t("saving") : t("save")}
        </Button>
      </div>
    </form>
  );
}
