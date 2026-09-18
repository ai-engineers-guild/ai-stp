"use client";

import { useRef, useState, useTransition } from "react";
import { useTranslations } from "next-intl";
import { z } from "zod";
import { corporateMutationAction } from "@/actions/corporate";
import { Button } from "@/components/atoms/button";
import { Label } from "@/components/atoms/label";
import type {
  CorporateCatalogObjectKind,
  CorporateCatalogOwnerMember,
} from "@/lib/api/corporate-catalog-ownership";
import type { CorporateCatalogOwnership } from "@/lib/api/generated/types.gen";
import { tryAsAccountId, tryAsComponentId, tryAsSetupId } from "@/lib/brands";
import { useRouter } from "@/lib/i18n/navigation";

const ownershipSchema = z.object({
  can_edit: z.boolean(),
  object_kind: z.enum(["setup", "component"]),
  organization_id: z.string(),
  owner_account_id: z
    .string()
    .refine((value) => tryAsAccountId(value) !== null, "invalid owner account id")
    .nullable(),
  owner_display_name: z.string().nullable(),
  revision: z.number().int().nonnegative(),
  schema_version: z.literal(1),
  stable_id: z.string(),
});

export function CorporateCatalogOwnerEditor({
  ownership,
  objectKind,
  stableId,
  version,
  organizationId,
  authorizationRevision,
  csrfToken,
  members,
}: {
  ownership: CorporateCatalogOwnership;
  objectKind: CorporateCatalogObjectKind;
  stableId: string;
  version: string;
  organizationId: string;
  authorizationRevision: number;
  csrfToken: string;
  members: readonly CorporateCatalogOwnerMember[] | null;
}) {
  const h = useTranslations("hub");
  const c = useTranslations("corporate");
  const router = useRouter();
  const [owner, setOwner] = useState(ownership.owner_account_id ?? "");
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const receipt = useRef<{ owner: string; key: string } | null>(null);

  function save() {
    if (receipt.current?.owner !== owner) {
      receipt.current = { owner, key: crypto.randomUUID() };
    }
    const idempotencyKey = receipt.current.key;
    startTransition(async () => {
      setError(null);
      const result = await corporateMutationAction({
        organizationId,
        csrfToken,
        method: "PUT",
        path: `/v1/corporate/organizations/${organizationId}/catalog-ownership`,
        body: {
          schema_version: 1,
          object_kind: objectKind,
          stable_id: stableId,
          version,
          owner_account_id: owner || null,
          expected_revision: ownership.revision,
          authorization_revision: authorizationRevision,
          idempotency_key: idempotencyKey,
        },
      });
      if (!result.ok) {
        setError(result.message);
        return;
      }
      const parsed = ownershipSchema.safeParse(result.data);
      const validStableId =
        objectKind === "component" ? tryAsComponentId(stableId) : tryAsSetupId(stableId);
      if (
        !parsed.success ||
        !validStableId ||
        parsed.data.organization_id !== organizationId ||
        parsed.data.object_kind !== objectKind ||
        parsed.data.stable_id !== stableId
      ) {
        setError(c("failed"));
        return;
      }
      receipt.current = null;
      router.refresh();
    });
  }

  return (
    <section className="border-border bg-card space-y-3 rounded-lg border p-4 shadow-sm">
      <div>
        <p className="text-muted-foreground text-xs font-medium tracking-[0.14em] uppercase">
          {h("operationalOwner")}
        </p>
        <p className="mt-1 font-medium">{ownership.owner_display_name ?? h("ownerUnassigned")}</p>
      </div>
      {ownership.can_edit && members ? (
        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault();
            save();
          }}
        >
          <Label htmlFor={`${objectKind}-catalog-owner`}>{h("operationalOwner")}</Label>
          <select
            id={`${objectKind}-catalog-owner`}
            className="border-input bg-background min-h-11 w-full rounded-sm border px-3 text-sm"
            disabled={pending}
            value={owner}
            onChange={(event) => {
              setOwner(event.target.value);
            }}
          >
            <option value="">{h("ownerUnassigned")}</option>
            {members
              .filter((member) => member.state === "active")
              .map((member) => (
                <option key={member.id} value={member.id}>
                  {member.name}
                </option>
              ))}
          </select>
          {error ? (
            <p role="alert" className="text-destructive text-sm">
              {error}
            </p>
          ) : null}
          <Button type="submit" disabled={pending || owner === (ownership.owner_account_id ?? "")}>
            {pending ? c("saving") : h("save")}
          </Button>
        </form>
      ) : null}
    </section>
  );
}
