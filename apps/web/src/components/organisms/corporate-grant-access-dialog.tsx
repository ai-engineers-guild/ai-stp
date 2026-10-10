/* eslint-disable max-lines-per-function */
"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/atoms/button";
import { Label } from "@/components/atoms/label";
import { FormDialog } from "@/components/molecules/form-dialog";
import { SearchableMultiSelect } from "@/components/molecules/searchable-multi-select";
import { ScopeField } from "@/components/organisms/corporate-people-ui";
import { corporateMutation } from "@/lib/api/corporate-mutation";
import { permissionEntity, permissionLabel, roleTitle } from "@/lib/corporate-permission-ui";
import type {
  CorporateMember,
  CorporatePermissionDefinition,
  CorporateProjectView,
  CorporateRoleView,
  CorporateTeamView,
} from "@/lib/api/generated/types.gen";

const selectClass =
  "border-input bg-background focus-visible:ring-ring flex h-10 w-full rounded-md border px-3 text-sm focus-visible:ring-2 focus-visible:outline-none";

const field = (formData: FormData, name: string) => {
  const value = formData.get(name);
  return typeof value === "string" ? value : "";
};

/**
 * The page-level Grant access flow: pick one or more employees, then grant
 * each of them either a role binding at a chosen scope or a single direct
 * scoped permission. Scoping below the organization narrows the grant, and a
 * direct permission reaches beyond what the person's role allows. The server
 * re-checks delegation bounds on every write; failures are counted, not hidden.
 */
export function CorporateGrantAccessDialog({
  open,
  onOpenChange,
  csrfToken,
  organizationId,
  authorizationRevision,
  members,
  roles,
  grantableRoleNames,
  teams,
  projects,
  scopeOptions,
  definitions,
  capabilities,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  csrfToken: string;
  organizationId: string;
  authorizationRevision: number;
  members: readonly CorporateMember[];
  roles: readonly CorporateRoleView[];
  grantableRoleNames: readonly string[] | null;
  teams: readonly CorporateTeamView[];
  projects: readonly CorporateProjectView[];
  scopeOptions: readonly { value: string; label: string }[];
  definitions: readonly CorporatePermissionDefinition[];
  capabilities: readonly string[];
}) {
  const a = useTranslations("accessUi");
  const c = useTranslations("corporate");
  const p = useTranslations("people");
  const router = useRouter();
  const [busy, startTransition] = useTransition();
  const [selected, setSelected] = useState<string[]>([]);
  const [kind, setKind] = useState<"role" | "permission">("role");
  const [scopeKind, setScopeKind] = useState("organization");
  const [message, setMessage] = useState<{ text: string; error?: boolean } | null>(null);
  const roleOptions =
    grantableRoleNames !== null ? grantableRoleNames : roles.map((role) => role.name);
  const permissionOptions = (
    definitions.length
      ? definitions
          .filter(
            (definition) =>
              definition.scopes.includes(scopeKind as (typeof definition.scopes)[number]) &&
              capabilities.includes(definition.name),
          )
          .map((definition) => definition.name)
      : capabilities.filter((permission) => permission.includes("."))
  ).map((permission) => {
    const definition = definitions.find((item) => item.name === permission);
    return {
      value: permission,
      label: definition
        ? `${a(`entities.${permissionEntity(definition.resource)}.name`)} · ${permissionLabel(definition, a)}`
        : permission,
    };
  });

  return (
    <FormDialog
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          setSelected([]);
          setMessage(null);
        }
        onOpenChange(next);
      }}
      title={a("grantAccess")}
      description={a("grantAccessBody")}
      closeLabel={c("close")}
      cancelLabel={c("cancel")}
      submitLabel={a("grantAccess")}
      busyLabel={c("saving")}
      busy={busy}
      submitDisabled={selected.length === 0}
      error={message?.error ? message.text : null}
      onSubmit={(event) => {
        const formData = new FormData(event.currentTarget);
        const [grantScopeKind, scopeId] = field(formData, "scope").split(":", 2);
        if (!grantScopeKind || !scopeId) {
          setMessage({ text: c("targetRequired"), error: true });
          return;
        }
        const accountIds = [...selected];
        const body =
          kind === "role"
            ? (accountId: string) => ({
                schema_version: 1,
                account_id: accountId,
                role: field(formData, "role"),
                scope_kind: grantScopeKind,
                scope_id: scopeId,
                coverage: field(formData, "coverage") || "self",
                authorization_revision: authorizationRevision,
                idempotency_key: crypto.randomUUID(),
              })
            : (accountId: string) => ({
                schema_version: 1,
                account_id: accountId,
                permission: field(formData, "permission"),
                scope_kind: grantScopeKind,
                scope_id: scopeId,
                authorization_revision: authorizationRevision,
                idempotency_key: crypto.randomUUID(),
              });
        const path =
          kind === "role"
            ? `/v1/corporate/organizations/${organizationId}/bindings`
            : `/v1/corporate/organizations/${organizationId}/permission-grants`;
        setMessage(null);
        startTransition(async () => {
          let failed = 0;
          for (const accountId of accountIds) {
            const result = await corporateMutation({
              csrfToken,
              organizationId,
              path,
              method: "POST",
              body: body(accountId),
            });
            if (!result.ok) failed += 1;
          }
          if (failed) {
            setMessage({ text: c("assignPartial", { count: failed }), error: true });
            router.refresh();
            return;
          }
          onOpenChange(false);
          setSelected([]);
          router.refresh();
        });
      }}
    >
      <SearchableMultiSelect
        name="members"
        label={p("members")}
        searchLabel={a("searchEmployees")}
        options={members.map((member) => ({
          value: member.account_id,
          label: member.contact_email
            ? `${member.display_name ?? member.account_id} · ${member.contact_email}`
            : (member.display_name ?? member.account_id),
        }))}
        selected={selected}
        onChange={setSelected}
        inline
        closeLabel={c("close")}
        selectionSuffix={c("selectedSuffix")}
        emptyHint={a("searchEmployees")}
      />
      <fieldset className="space-y-3">
        <legend className="text-sm font-medium">{a("grantKind")}</legend>
        <div className="flex gap-2" role="radiogroup" aria-label={a("grantKind")}>
          {(["role", "permission"] as const).map((value) => (
            <Button
              key={value}
              type="button"
              variant={kind === value ? "default" : "outline"}
              size="sm"
              aria-pressed={kind === value}
              onClick={() => {
                setKind(value);
              }}
            >
              {a(value === "role" ? "grantRoleMode" : "grantPermissionMode")}
            </Button>
          ))}
        </div>
        {kind === "role" ? (
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="grant-access-role">{c("role")}</Label>
              <select id="grant-access-role" name="role" required className={selectClass}>
                {roleOptions.map((name) => (
                  <option key={name} value={name}>
                    {roleTitle(name, a)}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="grant-access-coverage">{c("coverage")}</Label>
              <select
                id="grant-access-coverage"
                name="coverage"
                defaultValue="self"
                className={selectClass}
              >
                <option value="self">{c("coverageSelf")}</option>
                <option value="descendants">{c("coverageDescendants")}</option>
              </select>
            </div>
          </div>
        ) : (
          <div className="space-y-1.5">
            <Label htmlFor="grant-access-permission">{c("permission")}</Label>
            <select
              id="grant-access-permission"
              name="permission"
              required
              className={`${selectClass} font-mono text-xs`}
            >
              {permissionOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
        )}
        <div className="space-y-1.5">
          <Label htmlFor="grant-access-scope">{c("selectScope")}</Label>
          <ScopeField
            id="grant-access-scope"
            teams={teams}
            projects={projects}
            organizationId={organizationId}
            organizationLabel={c("allScopes")}
            options={scopeOptions}
            onKindChange={setScopeKind}
          />
          <p className="text-muted-foreground text-xs">{a("grantScopeHint")}</p>
        </div>
      </fieldset>
    </FormDialog>
  );
}
