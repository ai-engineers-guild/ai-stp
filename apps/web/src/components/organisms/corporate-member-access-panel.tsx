/* eslint-disable max-lines-per-function */
"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { useTranslations } from "next-intl";
import { permissionEntity, permissionLabel, roleTitle } from "@/lib/corporate-permission-ui";

import { corporateMutation } from "@/lib/api/corporate-mutation";
import { Badge } from "@/components/atoms/badge";
import { Button } from "@/components/atoms/button";

import type {
  CorporateBinding,
  CorporatePermissionGrant,
  CorporatePermissionDefinition,
  CorporateProjectView,
  CorporateTeamView,
} from "@/lib/api/generated/types.gen";

type Labels = {
  bindings: string;
  role: string;
  scope: string;
  organization: string;
  revoke: string;
  revoking: string;
  coverageSelf: string;
  coverageDescendants: string;
  originMembership: string;
  originAssignment: string;
  originDirect: string;
  originServicePrincipal: string;
  noBindings: string;
  directGrants: string;
  directGrantsBody: string;
  issuer: string;
  noGrants: string;
  saved: string;
  confirmRevoke: string;
};

/**
 * Read-only access record for one member inside the Employee access drawer:
 * role bindings with scope and origin, and direct scoped allows, each with a
 * revoke action. Granting access happens in the page-level Grant access
 * dialog; the server re-checks delegation bounds on every revoke.
 */
export function CorporateMemberAccessPanel({
  csrfToken,
  organizationId,
  authorizationRevision,
  teams,
  projects,
  bindings,
  grants,
  capabilities,
  definitions,
  labels,
  membershipRole,
  scopeOptions = [],
}: {
  csrfToken: string;
  organizationId: string;
  authorizationRevision: number;
  teams: readonly CorporateTeamView[];
  projects: readonly CorporateProjectView[];
  bindings: readonly CorporateBinding[];
  grants: readonly CorporatePermissionGrant[];
  capabilities: readonly string[];
  definitions: readonly CorporatePermissionDefinition[];
  labels: Labels;
  membershipRole?: string;
  scopeOptions?: readonly { value: string; label: string }[];
}) {
  const a = useTranslations("accessUi");
  const router = useRouter();
  const [busy, startTransition] = useTransition();
  const [message, setMessage] = useState<{ text: string; error?: boolean } | null>(null);
  const can = (permission: string) => capabilities.includes(permission);
  const scopeName = (kind: string, id: string) =>
    kind === "organization"
      ? labels.organization
      : (scopeOptions.find((scope) => scope.value === `${kind}:${id}`)?.label ??
        teams.find((team) => team.team_id === id)?.name ??
        projects.find((project) => project.project_id === id)?.name ??
        id);
  const permissionName = (name: string) => {
    const definition = definitions.find((item) => item.name === name);
    return definition
      ? `${a(`entities.${permissionEntity(definition.resource)}.name`)} · ${permissionLabel(definition, a)}`
      : name;
  };

  function submit(path: string, body: unknown) {
    setMessage(null);
    startTransition(async () => {
      const result = await corporateMutation({
        csrfToken,
        organizationId,
        path,
        method: "DELETE",
        body,
      });
      setMessage({ text: result.ok ? labels.saved : result.message, error: !result.ok });
      if (result.ok) router.refresh();
    });
  }

  function revokeBinding(binding: CorporateBinding) {
    if (!window.confirm(labels.confirmRevoke)) return;
    submit(`/v1/corporate/organizations/${organizationId}/bindings/${binding.binding_id}`, {
      schema_version: 1,
      expected_revision: binding.revision,
      authorization_revision: authorizationRevision,
      idempotency_key: crypto.randomUUID(),
    });
  }

  function revokeGrant(grant: CorporatePermissionGrant) {
    if (!window.confirm(labels.confirmRevoke)) return;
    submit(`/v1/corporate/organizations/${organizationId}/permission-grants/${grant.grant_id}`, {
      schema_version: 1,
      expected_revision: grant.revision,
      authorization_revision: authorizationRevision,
      idempotency_key: crypto.randomUUID(),
    });
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
      <div aria-live="polite">
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
        {bindings.length || membershipRole ? (
          <div className="border-border mt-3 overflow-x-auto rounded-md border">
            <table className="w-full text-left text-xs">
              <thead className="bg-muted/30 text-muted-foreground">
                <tr>
                  <th className="p-2">{labels.role}</th>
                  <th className="p-2">{labels.scope}</th>
                  <th className="p-2">{a("source")}</th>
                  <th className="p-2">
                    <span className="sr-only">{labels.revoke}</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {membershipRole && !bindings.some((binding) => binding.origin === "membership") ? (
                  <tr className="border-border border-t">
                    <td className="p-2 font-medium">{roleTitle(membershipRole, a)}</td>
                    <td className="p-2">{labels.organization}</td>
                    <td className="text-muted-foreground p-2">{labels.originMembership}</td>
                    <td />
                  </tr>
                ) : null}
                {bindings.map((binding) => (
                  <tr key={binding.binding_id} className="border-border border-t">
                    <td className="p-2 font-medium">{roleTitle(binding.role, a)}</td>
                    <td className="p-2">
                      <span className="block">
                        {scopeName(binding.scope_kind, binding.scope_id)}
                      </span>
                      <span className="text-muted-foreground">
                        {binding.coverage === "descendants"
                          ? labels.coverageDescendants
                          : labels.coverageSelf}
                      </span>
                    </td>
                    <td className="text-muted-foreground p-2">{originLabel(binding.origin)}</td>
                    <td className="p-2">
                      {binding.state === "active" && can("binding.delete") ? (
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          disabled={busy}
                          onClick={() => {
                            revokeBinding(binding);
                          }}
                        >
                          {busy ? labels.revoking : labels.revoke}
                        </Button>
                      ) : (
                        <Badge variant="warning">{binding.state}</Badge>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-muted-foreground mt-2 text-sm">{labels.noBindings}</p>
        )}
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
                  <span className="text-xs font-medium">{permissionName(grant.permission)}</span>
                  <span className="text-muted-foreground block text-xs">
                    {" "}
                    {scopeName(grant.scope_kind, grant.scope_id)}
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
                    onClick={() => {
                      revokeGrant(grant);
                    }}
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
      </section>
    </div>
  );
}
