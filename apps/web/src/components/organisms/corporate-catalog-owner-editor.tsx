"use client";

import { loadTechnologyOwnerEditor } from "@/actions/entity-actions";
import { FormDialog } from "@/components/molecules/form-dialog";
import { MenuItem } from "@/components/atoms/menu";
import { Icon } from "@/theme";
import { toast } from "sonner";
import type { EntityActionSubject } from "@/lib/api/generated/types.gen";
import { Select } from "@/components/atoms/select";
import { SearchableMultiSelect } from "@/components/molecules/searchable-multi-select";
import { useRef, useState, useTransition } from "react";
import { useTranslations } from "next-intl";
import { z } from "zod";
import { corporateMutation } from "@/lib/api/corporate-mutation";
import { Button } from "@/components/atoms/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/atoms/dialog";
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

export type CorporateCatalogOwnerEdit = {
  ownership: CorporateCatalogOwnership;
  objectKind: CorporateCatalogObjectKind;
  stableId: string;
  version: string;
  organizationId: string;
  authorizationRevision: number;
  csrfToken: string;
  members: readonly CorporateCatalogOwnerMember[];
};

export function CorporateCatalogOwnerEditor({
  ownership,
}: {
  ownership: CorporateCatalogOwnership;
}) {
  const h = useTranslations("hub");
  return (
    <section className="border-border bg-card space-y-3 rounded-lg border p-4 shadow-sm">
      <div>
        <p className="text-muted-foreground text-xs font-medium tracking-[0.14em] uppercase">
          {h("operationalOwner")}
        </p>
        <p className="mt-1 font-medium">{ownership.owner_display_name ?? h("ownerUnassigned")}</p>
      </div>
    </section>
  );
}

export function CorporateCatalogOwnerDialog({
  open,
  onOpenChange,
  ownerEdit,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  ownerEdit: CorporateCatalogOwnerEdit;
}) {
  const h = useTranslations("hub");
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{h("assignOwner")}</DialogTitle>
          <DialogDescription>{ownerEdit.stableId}</DialogDescription>
        </DialogHeader>
        <OwnerEditForm
          ownerEdit={ownerEdit}
          onDone={() => {
            onOpenChange(false);
          }}
        />
      </DialogContent>
    </Dialog>
  );
}

function OwnerEditForm({
  ownerEdit,
  onDone,
}: {
  ownerEdit: CorporateCatalogOwnerEdit;
  onDone: () => void;
}) {
  const h = useTranslations("hub");
  const c = useTranslations("corporate");
  const router = useRouter();
  const {
    ownership,
    objectKind,
    stableId,
    version,
    organizationId,
    authorizationRevision,
    csrfToken,
    members,
  } = ownerEdit;
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
      const result = await corporateMutation({
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
      onDone();
      router.refresh();
    });
  }

  return (
    <form
      className="space-y-4"
      onSubmit={(event) => {
        event.preventDefault();
        save();
      }}
    >
      <div className="space-y-2 text-sm">
        <fieldset disabled={pending}>
          <SearchableMultiSelect
            name="owner_account_id"
            label={h("operationalOwner")}
            searchLabel={h("search")}
            options={members.map((member) => ({ value: member.id, label: member.name }))}
            selected={owner ? [owner] : []}
            onChange={(values) => {
              setOwner(values[0] ?? "");
            }}
            multiple={false}
            inline
            emptyHint={h("ownerUnassigned")}
            closeLabel={h("cancel")}
          />
        </fieldset>
      </div>
      {error ? (
        <p role="alert" className="text-destructive text-sm">
          {error}
        </p>
      ) : null}
      <DialogFooter>
        <Button type="button" variant="outline" disabled={pending} onClick={onDone}>
          {h("cancel")}
        </Button>
        <Button type="submit" disabled={pending || owner === (ownership.owner_account_id ?? "")}>
          {pending ? c("saving") : h("save")}
        </Button>
      </DialogFooter>
    </form>
  );
}

export function TechnologyOwnerMenuAction({ subject }: { subject: EntityActionSubject }) {
  const hub = useTranslations("hub");
  const corporate = useTranslations("corporate");
  const common = useTranslations("common");
  const router = useRouter();
  const [context, setContext] = useState<Awaited<
    ReturnType<typeof loadTechnologyOwnerEditor>
  > | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, start] = useTransition();
  const retry = useRef<{ owner: string; key: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  return (
    <>
      <MenuItem
        disabled={busy}
        onSelect={(event) => {
          event.preventDefault();
          start(async () => {
            try {
              setContext(await loadTechnologyOwnerEditor(subject));
              retry.current = null;
              setError(null);
              setOpen(true);
            } catch {
              toast.error(common("requestFailed"));
            }
          });
        }}
      >
        <Icon name="user" size="sm" />
        {hub("assignOwner")}
      </MenuItem>
      <FormDialog
        open={open}
        onOpenChange={setOpen}
        title={hub("assignOwner")}
        closeLabel={corporate("close")}
        cancelLabel={corporate("cancel")}
        submitLabel={corporate("update")}
        busy={busy}
        error={error}
        onSubmit={(event) => {
          if (!context || !subject.organization_id) return;
          const selectedOwner = new FormData(event.currentTarget).get("owner");
          const owner = typeof selectedOwner === "string" ? selectedOwner : "";
          const organizationId = subject.organization_id;
          if (retry.current?.owner !== owner) retry.current = { owner, key: crypto.randomUUID() };
          const idempotencyKey = retry.current.key;
          start(async () => {
            const result = await corporateMutation({
              organizationId,
              csrfToken: context.csrfToken,
              path: `/v1/corporate/organizations/${subject.organization_id}/technologies/${subject.id}/owner`,
              method: "PUT",
              body: {
                schema_version: 1,
                owner_account_id: owner || null,
                expected_revision: context.presentation.revision,
                authorization_revision: context.presentation.authorization_revision,
                idempotency_key: idempotencyKey,
              },
            });
            if (!result.ok) setError(result.message);
            else {
              retry.current = null;
              setOpen(false);
              router.refresh();
            }
          });
        }}
      >
        <Label htmlFor={`owner-${subject.id}`}>{hub("operationalOwner")}</Label>
        <Select
          id={`owner-${subject.id}`}
          name="owner"
          defaultValue={context?.presentation.owner_account_id ?? ""}
        >
          <option value="">{hub("ownerUnassigned")}</option>
          {context?.members.map((member) => (
            <option key={member.account_id} value={member.account_id}>
              {member.display_name ?? member.account_id}
            </option>
          ))}
        </Select>
      </FormDialog>
    </>
  );
}
