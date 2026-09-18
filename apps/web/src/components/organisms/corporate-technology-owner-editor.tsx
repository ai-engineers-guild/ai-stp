"use client";

import { useRef, useState, useTransition } from "react";
import { useTranslations } from "next-intl";
import { corporateMutationAction } from "@/actions/corporate";
import { Button } from "@/components/atoms/button";
import { Label } from "@/components/atoms/label";
import { entityProfileViewSchema } from "@/lib/corporate-detail";
import { useRouter } from "@/lib/i18n/navigation";

export function CorporateTechnologyOwnerEditor({
  organizationId,
  technologyId,
  ownerAccountId,
  revision,
  authorizationRevision,
  csrfToken,
  members,
}: {
  organizationId: string;
  technologyId: string;
  ownerAccountId: string | null;
  revision: number;
  authorizationRevision: number;
  csrfToken: string;
  members: readonly { account_id: string; display_name?: string | null; state: string }[];
}) {
  const h = useTranslations("hub");
  const c = useTranslations("common");
  const [owner, setOwner] = useState(ownerAccountId ?? "");
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const receipt = useRef<{ owner: string; key: string } | null>(null);
  const router = useRouter();
  function save() {
    if (receipt.current?.owner !== owner) receipt.current = { owner, key: crypto.randomUUID() };
    const idempotency_key = receipt.current.key;
    startTransition(async () => {
      setError(null);
      try {
        const result = await corporateMutationAction({
          organizationId,
          csrfToken,
          method: "PUT",
          path: `/v1/corporate/organizations/${organizationId}/technologies/${technologyId}/owner`,
          body: {
            schema_version: 1,
            owner_account_id: owner || null,
            expected_revision: revision,
            authorization_revision: authorizationRevision,
            idempotency_key,
          },
        });
        if (!result.ok) {
          setError(result.message);
          return;
        }
        if (!entityProfileViewSchema.safeParse(result.data).success) {
          setError(c("error"));
          return;
        }
        receipt.current = null;
        router.refresh();
      } catch {
        setError(c("apiUnavailable"));
      }
    });
  }
  return (
    <form
      className="border-border space-y-3 rounded-lg border p-5"
      onSubmit={(event) => {
        event.preventDefault();
        save();
      }}
    >
      <Label htmlFor="technology-owner">{h("operationalOwner")}</Label>
      <select
        id="technology-owner"
        className="border-input bg-background min-h-11 w-full rounded-sm border px-3 text-sm"
        disabled={pending}
        value={owner}
        onChange={(event) => {
          setOwner(event.target.value);
        }}
      >
        <option value="">{h("ownerUnassigned")}</option>
        {members
          .filter((member) => member.state === "active" || member.account_id === ownerAccountId)
          .map((member) => (
            <option key={member.account_id} value={member.account_id}>
              {member.display_name ?? h("employees")}
            </option>
          ))}
      </select>
      {error ? (
        <p role="alert" className="text-destructive text-sm">
          {error}
        </p>
      ) : null}
      <Button type="submit" disabled={pending || owner === (ownerAccountId ?? "")}>
        {pending ? c("loading") : h("save")}
      </Button>
    </form>
  );
}
