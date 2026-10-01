"use client";

/* eslint-disable max-lines-per-function, @typescript-eslint/no-confusing-void-expression */

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { corporateMutationAction } from "@/actions/corporate";
import { Badge } from "@/components/atoms/badge";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";

import type {
  CorporateRoleView,
  CorporateServicePrincipalView,
  CorporateTeamView,
  CorporateProjectView,
} from "@/lib/api/generated/types.gen";

/**
 * Service-principal management, relocated from the former overloaded admin
 * page (SPEC-096 keeps service principals outside the People & Access slice).
 * Mutations flow through the same CSRF/revision server action as before.
 */
export function CorporateServicePrincipalsPanel({
  csrfToken,
  organizationId,
  authorizationRevision,
  roles,
  servicePrincipals,
  teams,
  projects,
  capabilities,
  labels,
}: {
  csrfToken: string;
  organizationId: string;
  authorizationRevision: number;
  roles: readonly CorporateRoleView[];
  servicePrincipals: readonly CorporateServicePrincipalView[];
  teams: readonly CorporateTeamView[];
  projects: readonly CorporateProjectView[];
  capabilities: readonly string[];
  labels: {
    title: string;
    role: string;
    scope: string;
    organization: string;
    team: string;
    project: string;
    create: string;
    creating: string;
    activate: string;
    suspend: string;
    delete: string;
    deleting: string;
    confirmDelete: string;
    noServicePrincipals: string;
    saved: string;
    failed: string;
  };
}) {
  const router = useRouter();
  const [busy, startTransition] = useTransition();
  const [message, setMessage] = useState<{ text: string; error?: boolean } | null>(null);
  const report = (text: string, error = false) => setMessage({ text, error });
  const [name, setName] = useState("");
  const [role, setRole] = useState(roles[0]?.name ?? "staff");
  const [scope, setScope] = useState(`organization:${organizationId}`);
  const can = (permission: string) => capabilities.includes(permission);
  const selectClass =
    "border-input bg-background focus-visible:ring-ring flex h-10 w-full rounded-md border px-3 text-sm focus-visible:ring-2 focus-visible:outline-none";

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

  return (
    <section className="border-border bg-card space-y-6 rounded-lg border p-5 shadow-sm sm:p-6">
      <h2 className="text-xl font-medium">{labels.title}</h2>
      {can("service_principal.manage") ? (
        <form
          className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"
          onSubmit={(event) => {
            event.preventDefault();
            const [scopeKind, scopeId] = scope.split(":", 2);
            submit("POST", `/v1/corporate/organizations/${organizationId}/service-principals`, {
              schema_version: 1,
              name,
              role,
              scope_kind: scopeKind,
              scope_id: scopeId,
              authorization_revision: authorizationRevision,
              idempotency_key: crypto.randomUUID(),
            });
            setName("");
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="principal-name">{labels.title}</Label>
            <Input
              id="principal-name"
              required
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="principal-role">{labels.role}</Label>
            <select
              id="principal-role"
              required
              value={role}
              onChange={(event) => setRole(event.target.value)}
              className={selectClass}
            >
              {roles.map((item) => (
                <option key={item.name} value={item.name}>
                  {item.name}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="principal-scope">{labels.scope}</Label>
            <select
              id="principal-scope"
              required
              value={scope}
              onChange={(event) => setScope(event.target.value)}
              className={selectClass}
            >
              <option value={`organization:${organizationId}`}>{labels.organization}</option>
              <optgroup label={labels.team}>
                {teams.map((team) => (
                  <option key={team.team_id} value={`team:${team.team_id}`}>
                    {team.name}
                  </option>
                ))}
              </optgroup>
              <optgroup label={labels.project}>
                {projects.map((project) => (
                  <option key={project.project_id} value={`project:${project.project_id}`}>
                    {project.name}
                  </option>
                ))}
              </optgroup>
            </select>
          </div>
          <Button type="submit" disabled={busy} className="self-end">
            {busy ? labels.creating : labels.create}
          </Button>
        </form>
      ) : null}

      {servicePrincipals.length ? (
        <ul className="space-y-2">
          {servicePrincipals.map((principal) => (
            <li
              key={principal.service_principal_id}
              className="border-border flex flex-wrap items-center gap-2 rounded border p-3 text-sm"
            >
              <span className="min-w-0 flex-1 truncate">{principal.name}</span>
              <Badge variant="outline">{principal.binding.role}</Badge>
              {principal.state !== "active" ? (
                <Badge variant="warning">{principal.state}</Badge>
              ) : null}
              {can("service_principal.manage") ? (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={busy}
                  onClick={() =>
                    submit(
                      "PATCH",
                      `/v1/corporate/organizations/${organizationId}/service-principals/${principal.service_principal_id}`,
                      {
                        schema_version: 1,
                        state: principal.state === "active" ? "suspended" : "active",
                        expected_revision: principal.revision,
                        authorization_revision: authorizationRevision,
                        idempotency_key: crypto.randomUUID(),
                      },
                    )
                  }
                >
                  {principal.state === "active" ? labels.suspend : labels.activate}
                </Button>
              ) : null}
              {can("service_principal.delete") ? (
                <Button
                  type="button"
                  variant="destructive"
                  size="sm"
                  disabled={busy}
                  onClick={() => {
                    if (!window.confirm(labels.confirmDelete)) return;
                    submit(
                      "DELETE",
                      `/v1/corporate/organizations/${organizationId}/service-principals/${principal.service_principal_id}`,
                      {
                        schema_version: 1,
                        expected_revision: principal.revision,
                        authorization_revision: authorizationRevision,
                        idempotency_key: crypto.randomUUID(),
                      },
                    );
                  }}
                >
                  {busy ? labels.deleting : labels.delete}
                </Button>
              ) : null}
            </li>
          ))}
        </ul>
      ) : can("service_principal.list") ? (
        <p className="text-muted-foreground text-sm">{labels.noServicePrincipals}</p>
      ) : null}
      {message ? (
        <p
          role="status"
          aria-live="polite"
          className={
            message.error ? "text-destructive text-sm font-medium" : "text-muted-foreground text-sm"
          }
        >
          {message.text}
        </p>
      ) : null}
    </section>
  );
}
