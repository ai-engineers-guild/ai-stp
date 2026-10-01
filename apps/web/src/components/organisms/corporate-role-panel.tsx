"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { corporateMutationAction } from "@/actions/corporate";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import type {
  CorporatePermissionDefinition,
  CorporateRoleView,
} from "@/lib/api/generated/types.gen";
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

function RoleForm({
  idPrefix,
  labels,
  roles,
  definitions,
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
  definitions: readonly CorporatePermissionDefinition[];
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
        <span className="text-sm font-medium">{labels.permissions}</span>
        <div
          id={`${idPrefix}-permissions`}
          className="border-border max-h-72 space-y-3 overflow-y-auto rounded-md border p-3"
        >
          {[...new Set(definitions.map((definition) => definition.resource))].map((resource) => (
            <fieldset key={resource} className="space-y-1">
              <legend className="mb-1 text-sm font-medium">{resource}</legend>
              {definitions
                .filter((definition) => definition.resource === resource)
                .map((definition) => (
                  <label
                    key={definition.name}
                    className="flex cursor-pointer items-center gap-2 text-sm"
                  >
                    <input
                      type="checkbox"
                      name="permissions"
                      value={definition.name}
                      defaultChecked={role?.permissions.includes(definition.name)}
                      className="accent-primary size-4"
                    />
                    <span>{definition.action}</span>
                    <span className="text-muted-foreground font-mono text-xs">
                      {definition.name}
                    </span>
                  </label>
                ))}
            </fieldset>
          ))}
        </div>
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
  definitions,
  selected,
  labels,
}: {
  csrfToken: string;
  organizationId: string;
  authorizationRevision: number;
  capabilities: readonly string[];
  roles: readonly CorporateRoleView[];
  definitions: readonly CorporatePermissionDefinition[];
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
            definitions={definitions}
            excludeName={selected.name}
            role={selected}
            busy={busy}
            submitLabel={labels.update}
            busyLabel={labels.saving}
            onSubmit={(formData) => {
              submit("PATCH", rolePath(selected.name), {
                schema_version: 1,
                parent_role: field(formData, "parentRole") || null,
                permissions: formData.getAll("permissions").map(String),
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
            definitions={definitions}
            withName
            busy={busy}
            submitLabel={labels.create}
            busyLabel={labels.creating}
            onSubmit={(formData) => {
              submit("POST", `/v1/corporate/organizations/${organizationId}/roles`, {
                schema_version: 1,
                name: field(formData, "name"),
                parent_role: field(formData, "parentRole") || null,
                permissions: formData.getAll("permissions").map(String),
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
