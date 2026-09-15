"use client";

import { useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { corporateMutationAction } from "@/actions/corporate";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import { useRouter } from "@/lib/i18n/navigation";
import type { CorporateMember, CorporateMemberProfileRequest } from "@/lib/api/generated/types.gen";

export function CorporateMemberProfile({
  member,
  organizationId,
  authorizationRevision,
  csrfToken,
}: {
  member: CorporateMember;
  organizationId: string;
  authorizationRevision: number;
  csrfToken: string;
}) {
  const t = useTranslations("corporate");
  const router = useRouter();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(member.display_name ?? "");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const retry = useRef<{ effect: string; key: string } | null>(null);
  async function save() {
    if (!name.trim() || busy) return;
    const effect = {
      display_name: name.trim(),
      expected_revision: member.revision,
      authorization_revision: authorizationRevision,
    };
    const fingerprint = JSON.stringify(effect);
    if (retry.current?.effect !== fingerprint)
      retry.current = { effect: fingerprint, key: crypto.randomUUID() };
    const body: CorporateMemberProfileRequest = {
      ...effect,
      schema_version: 1,
      idempotency_key: retry.current.key,
    };
    setBusy(true);
    setMessage(null);
    try {
      const result = await corporateMutationAction({
        organizationId,
        csrfToken,
        path: `/v1/corporate/organizations/${organizationId}/members/${member.account_id}/profile`,
        method: "PATCH",
        body,
      });
      if (!result.ok) {
        setMessage(result.message);
        return;
      }
      retry.current = null;
      setEditing(false);
      router.refresh();
    } catch {
      setMessage(t("failed"));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="max-w-xl space-y-3">
      {!editing ? (
        <Button
          variant="outline"
          onClick={() => {
            setName(member.display_name ?? "");
            setMessage(null);
            setEditing(true);
          }}
        >
          {t("edit")}
        </Button>
      ) : (
        <form
          className="space-y-3"
          aria-busy={busy}
          onSubmit={(event) => {
            event.preventDefault();
            void save();
          }}
        >
          <Label htmlFor="member-profile-name">{t("displayName")}</Label>
          <Input
            id="member-profile-name"
            value={name}
            maxLength={80}
            required
            disabled={busy}
            onChange={(event) => {
              setName(event.target.value);
            }}
          />
          <div className="flex gap-3">
            <Button type="submit" disabled={busy || !name.trim()}>
              {t(busy ? "saving" : "update")}
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={busy}
              onClick={() => {
                setEditing(false);
                setMessage(null);
              }}
            >
              {t("cancel")}
            </Button>
          </div>
        </form>
      )}
      {message && (
        <p role="alert" className="text-sm">
          {message}
        </p>
      )}
    </section>
  );
}
