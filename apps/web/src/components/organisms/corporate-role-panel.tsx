"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { corporateMutation } from "@/lib/api/corporate-mutation";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import { CorporatePermissionTable } from "@/components/organisms/corporate-permission-table";
import type {
  CorporatePermissionDefinition,
  CorporateRoleView,
} from "@/lib/api/generated/types.gen";

type Labels = {
  name: string;
  renameHint: string;
  permissions: string;
  create: string;
  creating: string;
  update: string;
  saving: string;
  saved: string;
  failed: string;
};

const field = (formData: FormData, name: string) => {
  const value = formData.get(name);
  return typeof value === "string" ? value.trim() : "";
};

/**
 * The role contract has no rename: create the role under the new name, then
 * delete the old one with `replacement_role` pointing at the new role so its
 * holders are reassigned. Returns the last mutation's result.
 */
async function renameRole({
  csrfToken,
  organizationId,
  authorizationRevision,
  selected,
  nextName,
  permissions,
}: {
  csrfToken: string;
  organizationId: string;
  authorizationRevision: number;
  selected: CorporateRoleView;
  nextName: string;
  permissions: string[];
}) {
  const created = await corporateMutation({
    csrfToken,
    organizationId,
    path: `/v1/corporate/organizations/${organizationId}/roles`,
    method: "POST",
    body: {
      schema_version: 1,
      name: nextName,
      permissions,
      authorization_revision: authorizationRevision,
      idempotency_key: crypto.randomUUID(),
    },
  });
  if (!created.ok) return created;
  return corporateMutation({
    csrfToken,
    organizationId,
    path: `/v1/corporate/organizations/${organizationId}/roles/${encodeURIComponent(selected.name)}`,
    method: "DELETE",
    body: {
      schema_version: 1,
      expected_revision: selected.revision,
      replacement_role: nextName,
      authorization_revision: authorizationRevision,
      idempotency_key: crypto.randomUUID(),
    },
  });
}

/**
 * Flat role editor used inside the roles workspace dialog: a name field on
 * create and edit, the editable permission matrix, and one submit action.
 * Renaming is emulated — the contract has no rename — by creating the role
 * under the new name and deleting the old one with `replacement_role` pointing
 * at it, which reassigns holders. Deletion and member assignment live in
 * their own dialog flows. The server enforces delegation bounds and built-in
 * immutability.
 */
export function CorporateRolePanel({
  csrfToken,
  organizationId,
  authorizationRevision,
  definitions,
  selected,
  labels,
  mode = "create",
  template,
  onSaved,
}: {
  csrfToken: string;
  organizationId: string;
  authorizationRevision: number;
  definitions: readonly CorporatePermissionDefinition[];
  selected: CorporateRoleView | null;
  labels: Labels;
  mode?: "create" | "edit";
  template?: CorporateRoleView | undefined;
  /** Receives the role's final name — it differs from `selected.name` after a rename. */
  onSaved?: (name?: string) => void;
}) {
  const router = useRouter();
  const [busy, startTransition] = useTransition();
  const [message, setMessage] = useState<{
    text: string;
    error?: boolean;
    fields?: string[];
  } | null>(null);
  const role = mode === "edit" ? selected : template;

  return (
    <div className="space-y-4">
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          const formData = new FormData(event.currentTarget);
          setMessage(null);
          startTransition(async () => {
            const permissions = formData.getAll("permissions").map(String);
            const nextName = field(formData, "name");
            const failure = (
              result: Extract<Awaited<ReturnType<typeof corporateMutation>>, { ok: false }>,
            ) => ({
              text: result.message || labels.failed,
              error: true,
              fields: Object.entries(result.fieldErrors ?? {}).map(
                ([path, text]) => `${path}: ${text}`,
              ),
            });
            if (mode === "edit" && selected && nextName !== "" && nextName !== selected.name) {
              const removed = await renameRole({
                csrfToken,
                organizationId,
                authorizationRevision,
                selected,
                nextName,
                permissions,
              });
              setMessage(removed.ok ? { text: labels.saved } : failure(removed));
              if (removed.ok) {
                router.refresh();
                onSaved?.(nextName);
              }
              return;
            }
            const result = await corporateMutation({
              csrfToken,
              organizationId,
              path:
                mode === "edit" && selected
                  ? `/v1/corporate/organizations/${organizationId}/roles/${encodeURIComponent(selected.name)}`
                  : `/v1/corporate/organizations/${organizationId}/roles`,
              method: mode === "edit" ? "PATCH" : "POST",
              body: {
                schema_version: 1,
                ...(mode === "create" ? { name: nextName } : {}),
                permissions,
                ...(mode === "edit" && selected ? { expected_revision: selected.revision } : {}),
                authorization_revision: authorizationRevision,
                idempotency_key: crypto.randomUUID(),
              },
            });
            setMessage(result.ok ? { text: labels.saved } : failure(result));
            if (result.ok) {
              router.refresh();
              onSaved?.(mode === "create" ? nextName : selected?.name);
            }
          });
        }}
      >
        {mode === "create" || selected ? (
          <div className="space-y-1.5">
            <Label htmlFor="role-panel-name">{labels.name}</Label>
            <Input
              id="role-panel-name"
              name="name"
              required
              pattern="[a-z][a-z0-9_-]*"
              defaultValue={mode === "edit" ? selected?.name : undefined}
            />
            {mode === "edit" ? (
              <p className="text-muted-foreground text-xs">{labels.renameHint}</p>
            ) : null}
          </div>
        ) : null}
        <div className="space-y-1.5">
          <span className="text-sm font-medium">{labels.permissions}</span>
          <div className="max-h-[60dvh] overflow-y-auto">
            <CorporatePermissionTable
              definitions={definitions}
              permissions={role?.permissions ?? []}
              editable
            />
          </div>
        </div>
        <Button type="submit" disabled={busy} className="w-full">
          {busy
            ? mode === "edit"
              ? labels.saving
              : labels.creating
            : mode === "edit"
              ? labels.update
              : labels.create}
        </Button>
      </form>
      {message ? (
        <p
          className={
            message.error ? "text-destructive text-sm font-medium" : "text-muted-foreground text-sm"
          }
          role="status"
          aria-live="polite"
        >
          {message.text}
        </p>
      ) : null}
      {message?.fields?.length ? (
        <ul className="text-destructive list-disc space-y-1 pl-5 text-sm">
          {message.fields.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
