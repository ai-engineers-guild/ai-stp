/* eslint-disable max-lines, max-lines-per-function, @typescript-eslint/no-confusing-void-expression */
"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { corporateMutationAction } from "@/actions/corporate";
import { Badge } from "@/components/atoms/badge";
import { Button } from "@/components/atoms/button";
import { Label } from "@/components/atoms/label";

import type {
  CorporateBinding,
  CorporatePermissionGrant,
  CorporatePermissionDefinition,
  CorporateProjectView,
  CorporateRoleView,
  CorporateTeamView,
} from "@/lib/api/generated/types.gen";

type Method = "POST" | "DELETE";

const field = (formData: FormData, name: string) => {
  const value = formData.get(name);
  return typeof value === "string" ? value.trim() : "";
};

type Labels = {
  bindings: string;
  team: string;
  project: string;
  role: string;
  scope: string;
  organization: string;
  operation: string;
  assign: string;
  remove: string;
  create: string;
  creating: string;
  revoke: string;
  revoking: string;
  coverage: string;
  coverageSelf: string;
  coverageDescendants: string;
  originMembership: string;
  originAssignment: string;
  originDirect: string;
  originServicePrincipal: string;
  noBindings: string;
  directGrants: string;
  directGrantsBody: string;
  grantAction: string;
  permission: string;
  issuer: string;
  noGrants: string;
  saved: string;
  targetRequired: string;
  assignments: string;
  update: string;
  confirmRevoke: string;
};

/**
 * Member-scoped access mutations for the Employee access screen: role
 * bindings, direct scoped allows, and team/project assignment. The server
 * re-checks delegation bounds for every write; grantable roles come from the
 * caller's delegation view so the UI cannot offer a role the API would reject.
 */
export function CorporateMemberAccessPanel({
  csrfToken,
  organizationId,
  authorizationRevision,
  accountId,
  teams,
  projects,
  roles,
  grantableRoleNames,
  bindings,
  grants,
  capabilities,
  definitions,
  labels,
}: {
  csrfToken: string;
  organizationId: string;
  authorizationRevision: number;
  accountId: string;
  teams: readonly CorporateTeamView[];
  projects: readonly CorporateProjectView[];
  roles: readonly CorporateRoleView[];
  grantableRoleNames: readonly string[] | null;
  bindings: readonly CorporateBinding[];
  grants: readonly CorporatePermissionGrant[];
  capabilities: readonly string[];
  definitions: readonly CorporatePermissionDefinition[];
  labels: Labels;
}) {
  const router = useRouter();
  const [busy, startTransition] = useTransition();
  const [message, setMessage] = useState<{ text: string; error?: boolean } | null>(null);
  const [grantScopeKind, setGrantScopeKind] = useState("organization");
  const report = (text: string, error = false) => setMessage({ text, error });
  const can = (permission: string) => capabilities.includes(permission);
  const roleOptions =
    grantableRoleNames !== null ? grantableRoleNames : roles.map((role) => role.name);

  function submit(method: Method, path: string, body: unknown) {
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

  function revokeBinding(binding: CorporateBinding) {
    if (!window.confirm(labels.confirmRevoke)) return;
    submit(
      "DELETE",
      `/v1/corporate/organizations/${organizationId}/bindings/${binding.binding_id}`,
      {
        schema_version: 1,
        expected_revision: binding.revision,
        authorization_revision: authorizationRevision,
        idempotency_key: crypto.randomUUID(),
      },
    );
  }

  function revokeGrant(grant: CorporatePermissionGrant) {
    if (!window.confirm(labels.confirmRevoke)) return;
    submit(
      "DELETE",
      `/v1/corporate/organizations/${organizationId}/permission-grants/${grant.grant_id}`,
      {
        schema_version: 1,
        expected_revision: grant.revision,
        authorization_revision: authorizationRevision,
        idempotency_key: crypto.randomUUID(),
      },
    );
  }

  const originLabel = (origin: CorporateBinding["origin"] | null) =>
    origin === "membership"
      ? labels.originMembership
      : origin === "assignment"
        ? labels.originAssignment
        : origin === "service_principal"
          ? labels.originServicePrincipal
          : labels.originDirect;

  return (
    <div className="space-y-6">
      <div aria-live="polite" className="min-h-5">
        {message ? (
          <p
            role={message.error ? "alert" : undefined}
            className={
              message.error
                ? "text-destructive text-sm font-medium"
                : "text-muted-foreground text-sm"
            }
          >
            {message.text}
          </p>
        ) : null}
      </div>

      <section>
        <h3 className="font-medium">{labels.bindings}</h3>
        {bindings.length ? (
          <ul className="mt-3 space-y-2">
            {bindings.map((binding) => (
              <li
                key={binding.binding_id}
                className="border-border flex flex-wrap items-center justify-between gap-2 rounded border p-3 text-sm"
              >
                <span className="min-w-0">
                  <span className="font-medium">{binding.role}</span>
                  <span className="text-muted-foreground font-mono text-xs">
                    {" "}
                    {binding.scope_kind}:{binding.scope_id}
                  </span>
                </span>
                <span className="flex shrink-0 items-center gap-2">
                  <Badge variant="secondary">{originLabel(binding.origin)}</Badge>
                  <Badge variant="outline">
                    {binding.coverage === "descendants"
                      ? labels.coverageDescendants
                      : labels.coverageSelf}
                  </Badge>
                  {binding.state === "active" && can("binding.delete") ? (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={busy}
                      onClick={() => revokeBinding(binding)}
                    >
                      {busy ? labels.revoking : labels.revoke}
                    </Button>
                  ) : (
                    <Badge variant="warning">{binding.state}</Badge>
                  )}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-muted-foreground mt-2 text-sm">{labels.noBindings}</p>
        )}

        {can("binding.create") && roleOptions.length ? (
          <details className="mt-4">
            <summary className="cursor-pointer text-sm font-medium">{labels.create}</summary>
            <form
              className="mt-3 grid items-end gap-3 sm:grid-cols-2 lg:grid-cols-5"
              onSubmit={(event) => {
                event.preventDefault();
                const formData = new FormData(event.currentTarget);
                const [scopeKind, scopeId] = field(formData, "scope").split(":", 2);
                if (!scopeKind || !scopeId) {
                  report(labels.targetRequired, true);
                  return;
                }
                submit("POST", `/v1/corporate/organizations/${organizationId}/bindings`, {
                  schema_version: 1,
                  account_id: accountId,
                  role: field(formData, "role"),
                  scope_kind: scopeKind,
                  scope_id: scopeId,
                  coverage: field(formData, "coverage") || "self",
                  authorization_revision: authorizationRevision,
                  idempotency_key: crypto.randomUUID(),
                });
              }}
            >
              <div className="space-y-1.5">
                <Label htmlFor="binding-role">{labels.role}</Label>
                <select
                  id="binding-role"
                  name="role"
                  required
                  className="border-input bg-background focus-visible:ring-ring flex h-10 w-full rounded-md border px-3 text-sm focus-visible:ring-2 focus-visible:outline-none"
                >
                  {roleOptions.map((name) => (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="binding-scope">{labels.scope}</Label>
                <ScopeField
                  id="binding-scope"
                  teams={teams}
                  projects={projects}
                  organizationId={organizationId}
                  organizationLabel={labels.organization}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="binding-coverage">{labels.coverage}</Label>
                <select
                  id="binding-coverage"
                  name="coverage"
                  className="border-input bg-background focus-visible:ring-ring flex h-10 w-full rounded-md border px-3 text-sm focus-visible:ring-2 focus-visible:outline-none"
                >
                  <option value="self">{labels.coverageSelf}</option>
                  <option value="descendants">{labels.coverageDescendants}</option>
                </select>
              </div>
              <Button type="submit" disabled={busy}>
                {busy ? labels.creating : labels.create}
              </Button>
            </form>
          </details>
        ) : null}
      </section>

      <section>
        <h3 className="font-medium">{labels.directGrants}</h3>
        <p className="text-muted-foreground mt-1 text-sm">{labels.directGrantsBody}</p>
        {grants.length ? (
          <ul className="mt-3 space-y-2">
            {grants.map((grant) => (
              <li
                key={grant.grant_id}
                className="border-border flex flex-wrap items-center justify-between gap-2 rounded border p-3 text-sm"
              >
                <span className="min-w-0">
                  <span className="font-mono text-xs font-medium">{grant.permission}</span>
                  <span className="text-muted-foreground font-mono text-xs">
                    {" "}
                    {grant.scope_kind}:{grant.scope_id}
                  </span>
                  <span className="text-muted-foreground block text-xs">
                    {labels.issuer} {grant.issuer_account_id}
                  </span>
                </span>
                {grant.state === "active" && can("binding.delete") ? (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={busy}
                    onClick={() => revokeGrant(grant)}
                  >
                    {busy ? labels.revoking : labels.revoke}
                  </Button>
                ) : (
                  <Badge variant="warning">{grant.state}</Badge>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-muted-foreground mt-2 text-sm">{labels.noGrants}</p>
        )}

        {can("binding.create") ? (
          <details className="mt-4">
            <summary className="cursor-pointer text-sm font-medium">{labels.grantAction}</summary>
            <form
              className="mt-3 grid items-end gap-3 sm:grid-cols-2 lg:grid-cols-4"
              onSubmit={(event) => {
                event.preventDefault();
                const formData = new FormData(event.currentTarget);
                const [scopeKind, scopeId] = field(formData, "scope").split(":", 2);
                if (!scopeKind || !scopeId) {
                  report(labels.targetRequired, true);
                  return;
                }
                submit("POST", `/v1/corporate/organizations/${organizationId}/permission-grants`, {
                  schema_version: 1,
                  account_id: accountId,
                  permission: field(formData, "permission"),
                  scope_kind: scopeKind,
                  scope_id: scopeId,
                  authorization_revision: authorizationRevision,
                  idempotency_key: crypto.randomUUID(),
                });
              }}
            >
              <div className="space-y-1.5">
                <Label htmlFor="grant-permission">{labels.permission}</Label>
                <select
                  id="grant-permission"
                  name="permission"
                  required
                  className="border-input bg-background focus-visible:ring-ring h-10 w-full rounded-md border px-3 font-mono text-xs focus-visible:ring-2 focus-visible:outline-none"
                >
                  <option value="">—</option>
                  {(definitions.length
                    ? definitions
                        .filter(
                          (definition) =>
                            definition.scopes.includes(
                              grantScopeKind as (typeof definition.scopes)[number],
                            ) && capabilities.includes(definition.name),
                        )
                        .map((definition) => definition.name)
                    : capabilities.filter((permission) => permission.includes("."))
                  ).map((permission) => (
                    <option key={permission} value={permission}>
                      {permission}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="grant-scope">{labels.scope}</Label>
                <ScopeField
                  id="grant-scope"
                  teams={teams}
                  projects={projects}
                  organizationId={organizationId}
                  organizationLabel={labels.organization}
                  onKindChange={setGrantScopeKind}
                />
              </div>
              <Button type="submit" disabled={busy}>
                {busy ? labels.creating : labels.grantAction}
              </Button>
            </form>
          </details>
        ) : null}
      </section>

      {can("member.manage") ? (
        <section>
          <h3 className="font-medium">{labels.assignments}</h3>
          <form
            className="mt-3 grid items-end gap-3 sm:grid-cols-2 lg:grid-cols-4"
            onSubmit={(event) => {
              event.preventDefault();
              const formData = new FormData(event.currentTarget);
              const teamId = field(formData, "teamId");
              const projectId = field(formData, "projectId");
              if (!teamId && !projectId) {
                report(labels.targetRequired, true);
                return;
              }
              submit(
                "POST",
                `/v1/corporate/organizations/${organizationId}/membership-assignments`,
                {
                  schema_version: 1,
                  account_id: accountId,
                  team_id: teamId || null,
                  project_id: projectId || null,
                  team_role: field(formData, "teamRole") || "staff",
                  operation: field(formData, "operation") || "assign",
                  authorization_revision: authorizationRevision,
                  idempotency_key: crypto.randomUUID(),
                },
              );
            }}
          >
            <div className="space-y-1.5">
              <Label htmlFor="assign-team">{labels.team}</Label>
              <select
                id="assign-team"
                name="teamId"
                className="border-input bg-background focus-visible:ring-ring flex h-10 w-full rounded-md border px-3 text-sm focus-visible:ring-2 focus-visible:outline-none"
              >
                <option value="">—</option>
                {teams.map((team) => (
                  <option key={team.team_id} value={team.team_id}>
                    {team.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="assign-project">{labels.project}</Label>
              <select
                id="assign-project"
                name="projectId"
                className="border-input bg-background focus-visible:ring-ring flex h-10 w-full rounded-md border px-3 text-sm focus-visible:ring-2 focus-visible:outline-none"
              >
                <option value="">—</option>
                {projects.map((project) => (
                  <option key={project.project_id} value={project.project_id}>
                    {project.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="assign-operation">{labels.operation}</Label>
              <select
                id="assign-operation"
                name="operation"
                className="border-input bg-background focus-visible:ring-ring flex h-10 w-full rounded-md border px-3 text-sm focus-visible:ring-2 focus-visible:outline-none"
              >
                <option value="assign">{labels.assign}</option>
                <option value="remove">{labels.remove}</option>
              </select>
            </div>
            <Button type="submit" disabled={busy}>
              {busy ? labels.creating : labels.update}
            </Button>
          </form>
        </section>
      ) : null}
    </div>
  );
}

/**
 * One select carrying both scope kind and id as `kind:id`, so the chosen scope
 * can never mix a team kind with a project id.
 */
function ScopeField({
  id,
  teams,
  projects,
  organizationId,
  organizationLabel,
  onKindChange,
}: {
  id: string;
  teams: readonly CorporateTeamView[];
  projects: readonly CorporateProjectView[];
  organizationId: string;
  organizationLabel: string;
  onKindChange?: (kind: string) => void;
}) {
  return (
    <select
      id={id}
      name="scope"
      defaultValue={`organization:${organizationId}`}
      onChange={(event) => onKindChange?.(event.target.value.split(":", 1)[0] ?? "organization")}
      className="border-input bg-background focus-visible:ring-ring flex h-10 w-full rounded-md border px-3 text-sm focus-visible:ring-2 focus-visible:outline-none"
    >
      <option value={`organization:${organizationId}`}>{organizationLabel}</option>
      <optgroup label="teams">
        {teams.map((team) => (
          <option key={team.team_id} value={`team:${team.team_id}`}>
            {team.name}
          </option>
        ))}
      </optgroup>
      <optgroup label="projects">
        {projects.map((project) => (
          <option key={project.project_id} value={`project:${project.project_id}`}>
            {project.name}
          </option>
        ))}
      </optgroup>
    </select>
  );
}
