"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { corporateMutationAction } from "@/actions/corporate";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";

type Props = {
  csrfToken: string;
  organizationId: string;
  authorizationRevision: number;
  resource: "members" | "projects" | "teams" | "roles";
  resourceId: string;
  name: string;
  role?: string;
  parentRole?: string | null;
  rolePermissions?: readonly string[];
  state: string;
  revision: number;
  permissions: readonly string[];
  labels: {
    title: string;
    name: string;
    role: string;
    parentRole: string;
    permissions: string;
    state: string;
    update: string;
    saving: string;
    saved: string;
    delete: string;
    deleting: string;
    confirmDelete: string;
    staff: string;
    lead: string;
    superadmin: string;
    active: string;
    suspended: string;
    archived: string;
  };
};

// Keep resource mutation controls in one server-action boundary.
// eslint-disable-next-line max-lines-per-function
export function CorporateResourceActions({
  csrfToken,
  organizationId,
  authorizationRevision,
  resource,
  resourceId,
  name,
  role,
  parentRole,
  rolePermissions,
  state,
  revision,
  permissions,
  labels,
}: Props) {
  const router = useRouter();
  const [busy, startTransition] = useTransition();
  const [nextName, setNextName] = useState(name);
  const [nextRole, setNextRole] = useState(role ?? "staff");
  const [nextParentRole, setNextParentRole] = useState(parentRole ?? "");
  const [nextPermissions, setNextPermissions] = useState((rolePermissions ?? []).join(", "));
  const [nextState, setNextState] = useState(state);
  const [message, setMessage] = useState<string | null>(null);
  const endpoint = `/v1/corporate/organizations/${organizationId}/${resource}/${resourceId}`;
  const canUpdate = permissions.includes(
    `${resource === "members" ? "member" : resource === "roles" ? "role" : resource.slice(0, -1)}.update`,
  );
  const canDelete = permissions.includes(
    `${resource === "members" ? "member" : resource === "roles" ? "role" : resource.slice(0, -1)}.delete`,
  );

  function submit(method: "PATCH" | "DELETE", body: unknown) {
    setMessage(null);
    startTransition(async () => {
      const result = await corporateMutationAction({
        csrfToken,
        organizationId,
        path: endpoint,
        method,
        body,
      });
      if (!result.ok) {
        setMessage(result.message);
        return;
      }
      setMessage(labels.saved);
      router.refresh();
    });
  }

  return (
    <section className="border-border bg-card space-y-4 rounded-lg border p-5 shadow-sm sm:p-6">
      <h2 className="text-xl font-medium">{labels.title}</h2>
      {canUpdate ? (
        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault();
            submit("PATCH", {
              schema_version: 1,
              ...(resource === "members"
                ? { role: nextRole, state: nextState }
                : resource === "roles"
                  ? {
                      parent_role: nextParentRole || null,
                      permissions: nextPermissions
                        .split(",")
                        .map((permission) => permission.trim())
                        .filter(Boolean),
                    }
                  : { name: nextName, state: nextState }),
              expected_revision: revision,
              authorization_revision: authorizationRevision,
              idempotency_key: crypto.randomUUID(),
            });
          }}
        >
          {resource === "members" ? (
            <>
              <Label htmlFor="corporate-resource-role">{labels.role}</Label>
              <Input
                id="corporate-resource-role"
                required
                pattern="[a-z][a-z0-9_-]*"
                value={nextRole}
                onChange={(event) => {
                  setNextRole(event.target.value);
                }}
              />
            </>
          ) : resource === "roles" ? (
            <>
              <Label htmlFor="corporate-resource-parent-role">{labels.parentRole}</Label>
              <Input
                id="corporate-resource-parent-role"
                value={nextParentRole}
                onChange={(event) => {
                  setNextParentRole(event.target.value);
                }}
              />
              <Label htmlFor="corporate-resource-permissions">{labels.permissions}</Label>
              <Input
                id="corporate-resource-permissions"
                value={nextPermissions}
                onChange={(event) => {
                  setNextPermissions(event.target.value);
                }}
              />
            </>
          ) : (
            <>
              <Label htmlFor="corporate-resource-name">{labels.name}</Label>
              <Input
                id="corporate-resource-name"
                required
                value={nextName}
                onChange={(event) => {
                  setNextName(event.target.value);
                }}
              />
            </>
          )}
          {resource !== "roles" ? (
            <>
              <Label htmlFor="corporate-resource-state">{labels.state}</Label>
              <select
                id="corporate-resource-state"
                value={nextState}
                onChange={(event) => {
                  setNextState(event.target.value);
                }}
                className="border-border bg-background h-9 w-full rounded-sm border px-3 text-sm"
              >
                <option value="active">{labels.active}</option>
                <option value={resource === "members" ? "suspended" : "archived"}>
                  {resource === "members" ? labels.suspended : labels.archived}
                </option>
              </select>
            </>
          ) : null}
          <Button type="submit" disabled={busy}>
            {busy ? labels.saving : labels.update}
          </Button>
        </form>
      ) : null}
      {canDelete ? (
        <Button
          type="button"
          variant="destructive"
          disabled={busy}
          onClick={() => {
            if (!window.confirm(labels.confirmDelete)) return;
            submit("DELETE", {
              schema_version: 1,
              expected_revision: revision,
              authorization_revision: authorizationRevision,
              idempotency_key: crypto.randomUUID(),
            });
          }}
        >
          {busy ? labels.deleting : labels.delete}
        </Button>
      ) : null}
      {message ? (
        <p className="text-muted-foreground text-sm" role="status" aria-live="polite">
          {message}
        </p>
      ) : null}
    </section>
  );
}
