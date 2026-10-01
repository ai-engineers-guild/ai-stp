"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { corporateMutationAction } from "@/actions/corporate";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import { Textarea } from "@/components/atoms/textarea";
import type { CorporateRoleView } from "@/lib/api/generated/types.gen";
import { BUILT_IN_ROLES } from "@/lib/corporate-roles";

const selectClass =
  "border-input bg-background ring-offset-background focus-visible:ring-ring flex h-10 w-full rounded-md border px-3 py-2 text-sm focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none";

type Labels = {
  createRole: string;
  editRoleBody: string;
  name: string;
  parentRole: string;
  permissions: string;
  create: string;
  creating: string;
  update: string;
  saving: string;
  delete: string;
  deleting: string;
  deleteConfirm: string;
  saved: string;
  failed: string;
  none: string;
};

const field = (formData: FormData, name: string) => {
  const value = formData.get(name);
  return typeof value === "string" ? value.trim() : "";
};

const parsePermissions = (value: string) =>
  value
    .split(/[\s,]+/)
    .map((permission) => permission.trim())
    .filter(Boolean);

function RoleForm({
  idPrefix,
  labels,
  roles,
  excludeName,
  role,
  withName = false,
  busy,
  submitLabel,
  busyLabel,
  onSubmit,
}: {
  idPrefix: string;
  labels: Labels;
  roles: readonly CorporateRoleView[];
  excludeName?: string;
  role?: CorporateRoleView;
  withName?: boolean;
  busy: boolean;
  submitLabel: string;
  busyLabel: string;
  onSubmit: (formData: FormData) => void;
}) {
  const options = roles.filter((item) => item.name !== excludeName);
  return (
    <form
      className="mt-4 grid items-end gap-3 sm:grid-cols-3"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit(new FormData(event.currentTarget));
      }}
    >
      {withName ? (
        <div className="space-y-1.5">
          <Label htmlFor={`${idPrefix}-name`}>{labels.name}</Label>
          <Input id={`${idPrefix}-name`} name="name" required pattern="[a-z][a-z0-9_-]*" />
        </div>
      ) : null}
      <div className="space-y-1.5">
        <Label htmlFor={`${idPrefix}-parent`}>{labels.parentRole}</Label>
        <select
          id={`${idPrefix}-parent`}
          name="parentRole"
          defaultValue={role?.parent_role ?? ""}
          className={selectClass}
        >
          <option value="">{labels.none}</option>
          {options.map((item) => (
            <option key={item.name} value={item.name}>
              {item.name}
            </option>
          ))}
        </select>
      </div>
      <div className="space-y-1.5 sm:col-span-2">
        <Label htmlFor={`${idPrefix}-permissions`}>{labels.permissions}</Label>
        <Textarea
          id={`${idPrefix}-permissions`}
          name="permissions"
          rows={3}
          defaultValue={role?.permissions.join(", ")}
          className="font-mono text-xs"
        />
      </div>
      <Button type="submit" disabled={busy}>
        {busy ? busyLabel : submitLabel}
      </Button>
    </form>
  );
}

/**
 * Role create/edit/delete forms for the Roles workspace. The server enforces
 * delegation bounds and built-in immutability; the panel only offers actions
 * the caller's capabilities advertise.
 */
export function CorporateRolePanel({
  csrfToken,
  organizationId,
  authorizationRevision,
  capabilities,
  roles,
  selected,
  labels,
}: {
  csrfToken: string;
  organizationId: string;
  authorizationRevision: number;
  capabilities: readonly string[];
  roles: readonly CorporateRoleView[];
  selected: CorporateRoleView | null;
  labels: Labels;
}) {
  const router = useRouter();
  const [busy, startTransition] = useTransition();
  const [message, setMessage] = useState<{ text: string; error?: boolean } | null>(null);
  const report = (text: string, error = false) => {
    setMessage({ text, error });
  };
  const can = (permission: string) => capabilities.includes(permission);
  const customSelected = selected && !BUILT_IN_ROLES.has(selected.name);

  function submit(method: "POST" | "PATCH" | "DELETE", path: string, body: unknown) {
    setMessage(null);
    startTransition(async () => {
      const result = await corporateMutationAction({
        csrfToken,
        organizationId,
        path,
        method,
        body,
      });
      report(result.ok ? labels.saved : result.message, !result.ok);
      if (result.ok) router.refresh();
    });
  }

  const rolePath = (name: string) =>
    `/v1/corporate/organizations/${organizationId}/roles/${encodeURIComponent(name)}`;

  return (
    <div className="space-y-4">
      {customSelected && can("role.update") ? (
        <details className="border-border rounded-lg border p-4">
          <summary className="cursor-pointer font-medium">{labels.update}</summary>
          <p className="text-muted-foreground mt-1 text-sm">{labels.editRoleBody}</p>
          <RoleForm
            idPrefix="role-edit"
            labels={labels}
            roles={roles}
            excludeName={selected.name}
            role={selected}
            busy={busy}
            submitLabel={labels.update}
            busyLabel={labels.saving}
            onSubmit={(formData) => {
              submit("PATCH", rolePath(selected.name), {
                schema_version: 1,
                parent_role: field(formData, "parentRole") || null,
                permissions: parsePermissions(field(formData, "permissions")),
                expected_revision: selected.revision,
                authorization_revision: authorizationRevision,
                idempotency_key: crypto.randomUUID(),
              });
            }}
          />
        </details>
      ) : null}
      {customSelected && can("role.delete") ? (
        <Button
          type="button"
          variant="destructive"
          disabled={busy}
          onClick={() => {
            if (!window.confirm(labels.deleteConfirm)) return;
            submit("DELETE", rolePath(selected.name), {
              schema_version: 1,
              expected_revision: selected.revision,
              authorization_revision: authorizationRevision,
              idempotency_key: crypto.randomUUID(),
            });
          }}
        >
          {busy ? labels.deleting : labels.delete}
        </Button>
      ) : null}
      {can("role.create") ? (
        <details className="border-border rounded-lg border p-4">
          <summary className="cursor-pointer font-medium">{labels.createRole}</summary>
          <RoleForm
            idPrefix="role-create"
            labels={labels}
            roles={roles}
            withName
            busy={busy}
            submitLabel={labels.create}
            busyLabel={labels.creating}
            onSubmit={(formData) => {
              submit("POST", `/v1/corporate/organizations/${organizationId}/roles`, {
                schema_version: 1,
                name: field(formData, "name"),
                parent_role: field(formData, "parentRole") || null,
                permissions: parsePermissions(field(formData, "permissions")),
                authorization_revision: authorizationRevision,
                idempotency_key: crypto.randomUUID(),
              });
            }}
          />
        </details>
      ) : null}
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
    </div>
  );
}
