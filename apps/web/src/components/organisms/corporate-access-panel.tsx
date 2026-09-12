"use client";

/* eslint-disable max-lines, @typescript-eslint/no-confusing-void-expression */

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { corporateMutationAction } from "@/actions/corporate";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";

import type {
  CorporateBinding,
  CorporateMember,
  CorporateProjectView,
  CorporateRoleView,
  CorporateServicePrincipalView,
  CorporateTeamView,
} from "@/lib/api/generated/types.gen";

type ScopeKind = "organization" | "team" | "project";
type Method = "POST" | "PATCH" | "DELETE";
type Submit = (method: Method, path: string, body: unknown) => void;

type Props = {
  csrfToken: string;
  organizationId: string;
  authorizationRevision: number;
  members: readonly CorporateMember[];
  projects: readonly CorporateProjectView[];
  teams: readonly CorporateTeamView[];
  roles: readonly CorporateRoleView[];
  bindings: readonly CorporateBinding[];
  servicePrincipals: readonly CorporateServicePrincipalView[];
  permissions: readonly string[];
  labels: {
    title: string;
    assignments: string;
    bindings: string;
    servicePrincipals: string;
    member: string;
    team: string;
    project: string;
    role: string;
    state: string;
    scope: string;
    organization: string;
    operation: string;
    assign: string;
    remove: string;
    create: string;
    creating: string;
    update: string;
    saving: string;
    delete: string;
    deleting: string;
    activate: string;
    suspend: string;
    staff: string;
    lead: string;
    superadmin: string;
    noBindings: string;
    noServicePrincipals: string;
    confirmDelete: string;
    targetRequired: string;
    saved: string;
    failed: string;
  };
};

// The panel deliberately uses the existing server action for every mutation so CSRF,
// session, tenant path, and revalidation checks stay in one boundary.
// eslint-disable-next-line max-lines-per-function
export function CorporateAccessPanel({
  csrfToken,
  organizationId,
  authorizationRevision,
  members,
  projects,
  teams,
  roles,
  bindings,
  servicePrincipals,
  permissions,
  labels,
}: Props) {
  const router = useRouter();
  const [busy, startTransition] = useTransition();
  const [message, setMessage] = useState<string | null>(null);
  const [assignment, setAssignment] = useState({
    accountId: members[0]?.account_id ?? "",
    teamId: teams[0]?.team_id ?? "",
    projectId: projects[0]?.project_id ?? "",
    teamRole: "staff",
    operation: "assign",
  });
  const [binding, setBinding] = useState({
    accountId: members[0]?.account_id ?? "",
    role: roles[0]?.name ?? "staff",
    scopeKind: "organization" as ScopeKind,
    scopeId: organizationId,
  });
  const [principal, setPrincipal] = useState({
    name: "",
    role: roles[0]?.name ?? "staff",
    scopeKind: "organization" as ScopeKind,
    scopeId: organizationId,
  });
  const can = (permission: string) => permissions.includes(permission);

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
      setMessage(result.ok ? labels.saved : result.message);
      if (result.ok) router.refresh();
    });
  }

  return (
    <section className="border-border bg-card space-y-6 rounded-lg border p-5 shadow-sm sm:p-6">
      <h2 className="text-xl font-medium">{labels.title}</h2>
      {can("member.manage") ? (
        <form
          className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5"
          onSubmit={(event) => {
            event.preventDefault();
            if (!assignment.teamId && !assignment.projectId) {
              setMessage(labels.targetRequired);
              return;
            }
            submit("POST", `/v1/corporate/organizations/${organizationId}/membership-assignments`, {
              schema_version: 1,
              account_id: assignment.accountId,
              team_id: assignment.teamId || null,
              project_id: assignment.projectId || null,
              team_role: assignment.teamRole,
              operation: assignment.operation,
              authorization_revision: authorizationRevision,
              idempotency_key: crypto.randomUUID(),
            });
          }}
        >
          <h3 className="font-medium sm:col-span-2 lg:col-span-5">{labels.assignments}</h3>
          <SelectField
            id="corporate-assignment-member"
            label={labels.member}
            value={assignment.accountId}
            onChange={(accountId) => setAssignment({ ...assignment, accountId })}
            options={members.map((item) => ({
              value: item.account_id,
              label: item.display_name ?? item.account_id,
            }))}
          />
          <SelectField
            id="corporate-assignment-team"
            label={labels.team}
            value={assignment.teamId}
            onChange={(teamId) => setAssignment({ ...assignment, teamId })}
            options={[
              { value: "", label: "—" },
              ...teams.map((item) => ({ value: item.team_id, label: item.name })),
            ]}
          />
          <SelectField
            id="corporate-assignment-project"
            label={labels.project}
            value={assignment.projectId}
            onChange={(projectId) => setAssignment({ ...assignment, projectId })}
            options={[
              { value: "", label: "—" },
              ...projects.map((item) => ({ value: item.project_id, label: item.name })),
            ]}
          />
          <SelectField
            id="corporate-assignment-operation"
            label={labels.operation}
            value={assignment.operation}
            onChange={(operation) => setAssignment({ ...assignment, operation })}
            options={[
              { value: "assign", label: labels.assign },
              { value: "remove", label: labels.remove },
            ]}
          />
          <Button type="submit" disabled={busy} className="self-end">
            {busy ? labels.creating : labels.update}
          </Button>
        </form>
      ) : null}

      {can("binding.create") ? (
        <form
          className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5"
          onSubmit={(event) => {
            event.preventDefault();
            submit("POST", `/v1/corporate/organizations/${organizationId}/bindings`, {
              schema_version: 1,
              account_id: binding.accountId,
              role: binding.role,
              scope_kind: binding.scopeKind,
              scope_id: binding.scopeId,
              authorization_revision: authorizationRevision,
              idempotency_key: crypto.randomUUID(),
            });
          }}
        >
          <h3 className="font-medium sm:col-span-2 lg:col-span-5">{labels.bindings}</h3>
          <SelectField
            id="corporate-binding-member"
            label={labels.member}
            value={binding.accountId}
            onChange={(accountId) => setBinding({ ...binding, accountId })}
            options={members.map((item) => ({
              value: item.account_id,
              label: item.display_name ?? item.account_id,
            }))}
          />
          <SelectField
            id="corporate-binding-role"
            label={labels.role}
            value={binding.role}
            onChange={(role) => setBinding({ ...binding, role })}
            options={roles.map((item) => ({ value: item.name, label: item.name }))}
          />
          <ScopeFields
            idPrefix="corporate-binding"
            labels={labels}
            value={binding}
            teams={teams}
            projects={projects}
            onChange={(scopeKind, scopeId) =>
              setBinding({
                ...binding,
                scopeKind,
                scopeId: scopeKind === "organization" ? organizationId : scopeId,
              })
            }
          />
          <Button type="submit" disabled={busy} className="self-end">
            {busy ? labels.creating : labels.create}
          </Button>
        </form>
      ) : null}

      {bindings.length ? (
        <section className="space-y-3">
          <h3 className="font-medium">{labels.bindings}</h3>
          <ul className="space-y-2">
            {bindings.map((item) => (
              <BindingRow
                key={item.binding_id}
                binding={item}
                organizationId={organizationId}
                authorizationRevision={authorizationRevision}
                permissions={permissions}
                labels={labels}
                submit={submit}
                busy={busy}
              />
            ))}
          </ul>
        </section>
      ) : can("binding.list") ? (
        <p className="text-muted-foreground text-sm">{labels.noBindings}</p>
      ) : null}

      {can("service_principal.manage") ? (
        <form
          className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5"
          onSubmit={(event) => {
            event.preventDefault();
            submit("POST", `/v1/corporate/organizations/${organizationId}/service-principals`, {
              schema_version: 1,
              name: principal.name,
              role: principal.role,
              scope_kind: principal.scopeKind,
              scope_id: principal.scopeId,
              authorization_revision: authorizationRevision,
              idempotency_key: crypto.randomUUID(),
            });
          }}
        >
          <h3 className="font-medium sm:col-span-2 lg:col-span-5">{labels.servicePrincipals}</h3>
          <div>
            <Label htmlFor="corporate-principal-name">{labels.servicePrincipals}</Label>
            <Input
              id="corporate-principal-name"
              required
              value={principal.name}
              onChange={(event) => setPrincipal({ ...principal, name: event.target.value })}
            />
          </div>
          <SelectField
            id="corporate-principal-role"
            label={labels.role}
            value={principal.role}
            onChange={(role) => setPrincipal({ ...principal, role })}
            options={roles.map((item) => ({ value: item.name, label: item.name }))}
          />
          <ScopeFields
            idPrefix="corporate-principal"
            labels={labels}
            value={principal}
            teams={teams}
            projects={projects}
            onChange={(scopeKind, scopeId) =>
              setPrincipal({
                ...principal,
                scopeKind,
                scopeId: scopeKind === "organization" ? organizationId : scopeId,
              })
            }
          />
          <Button type="submit" disabled={busy} className="self-end">
            {busy ? labels.creating : labels.create}
          </Button>
        </form>
      ) : null}

      {servicePrincipals.length ? (
        <section className="space-y-3">
          <h3 className="font-medium">{labels.servicePrincipals}</h3>
          <ul className="space-y-2">
            {servicePrincipals.map((item) => (
              <ServicePrincipalRow
                key={item.service_principal_id}
                principal={item}
                organizationId={organizationId}
                authorizationRevision={authorizationRevision}
                permissions={permissions}
                labels={labels}
                submit={submit}
                busy={busy}
              />
            ))}
          </ul>
        </section>
      ) : can("service_principal.list") ? (
        <p className="text-muted-foreground text-sm">{labels.noServicePrincipals}</p>
      ) : null}
      {message ? (
        <p className="text-muted-foreground text-sm" role="status" aria-live="polite">
          {message}
        </p>
      ) : null}
    </section>
  );
}

function SelectField({
  id,
  label,
  value,
  onChange,
  options,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: readonly { value: string; label: string }[];
}) {
  return (
    <div>
      <Label htmlFor={id}>{label}</Label>
      <select
        id={id}
        required
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="border-border bg-background h-9 w-full rounded-sm border px-3 text-sm"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}

function ScopeFields({
  idPrefix,
  labels,
  value,
  teams,
  projects,
  onChange,
}: {
  idPrefix: string;
  labels: Props["labels"];
  value: { scopeKind: ScopeKind; scopeId: string };
  teams: readonly CorporateTeamView[];
  projects: readonly CorporateProjectView[];
  onChange: (scopeKind: ScopeKind, scopeId: string) => void;
}) {
  const options =
    value.scopeKind === "organization"
      ? [{ value: "organization", label: labels.organization }]
      : value.scopeKind === "team"
        ? teams.map((item) => ({ value: item.team_id, label: item.name }))
        : projects.map((item) => ({ value: item.project_id, label: item.name }));
  return (
    <>
      <SelectField
        id={`${idPrefix}-scope-kind`}
        label={labels.scope}
        value={value.scopeKind}
        onChange={(event) => {
          const scopeKind = event as ScopeKind;
          const scopeId =
            scopeKind === "organization"
              ? ""
              : scopeKind === "team"
                ? (teams[0]?.team_id ?? "")
                : (projects[0]?.project_id ?? "");
          onChange(scopeKind, scopeId);
        }}
        options={[
          { value: "organization", label: labels.organization },
          { value: "team", label: labels.team },
          { value: "project", label: labels.project },
        ]}
      />
      {value.scopeKind === "organization" ? null : (
        <SelectField
          id={`${idPrefix}-scope-id`}
          label={value.scopeKind === "team" ? labels.team : labels.project}
          value={value.scopeId}
          onChange={(scopeId) => onChange(value.scopeKind, scopeId)}
          options={options}
        />
      )}
    </>
  );
}

function BindingRow({
  binding,
  organizationId,
  authorizationRevision,
  permissions,
  labels,
  submit,
  busy,
}: {
  binding: CorporateBinding;
  organizationId: string;
  authorizationRevision: number;
  permissions: readonly string[];
  labels: Props["labels"];
  submit: Submit;
  busy: boolean;
}) {
  const [role, setRole] = useState(binding.role);
  const [state, setState] = useState(binding.state);
  const canUpdate = permissions.includes("binding.update");
  const canDelete = permissions.includes("binding.delete");
  return (
    <li className="border-border flex flex-wrap items-center gap-2 rounded border p-3 text-sm">
      <span className="min-w-0 flex-1 truncate font-mono text-xs">
        {binding.account_id ?? binding.service_principal_id} · {binding.scope_kind}:
        {binding.scope_id}
      </span>
      {canUpdate ? (
        <select
          aria-label={labels.role}
          value={role}
          onChange={(event) => setRole(event.target.value)}
          className="border-border bg-background h-8 rounded-sm border px-2"
        >
          <option value={role}>{role}</option>
          <option value="superadmin">{labels.superadmin}</option>
          <option value="lead">{labels.lead}</option>
          <option value="staff">{labels.staff}</option>
        </select>
      ) : (
        <span>{binding.role}</span>
      )}
      {canUpdate ? (
        <select
          aria-label={labels.state}
          value={state}
          onChange={(event) => setState(event.target.value as "active" | "revoked")}
          className="border-border bg-background h-8 rounded-sm border px-2"
        >
          <option value="active">{labels.activate}</option>
          <option value="revoked">{labels.remove}</option>
        </select>
      ) : null}
      {canUpdate ? (
        <Button
          type="button"
          disabled={busy}
          onClick={() =>
            submit(
              "PATCH",
              `/v1/corporate/organizations/${organizationId}/bindings/${binding.binding_id}`,
              {
                schema_version: 1,
                role,
                scope_kind: binding.scope_kind,
                scope_id: binding.scope_id,
                state,
                expected_revision: binding.revision,
                authorization_revision: authorizationRevision,
                idempotency_key: crypto.randomUUID(),
              },
            )
          }
        >
          {busy ? labels.saving : labels.update}
        </Button>
      ) : null}
      {canDelete ? (
        <Button
          type="button"
          variant="destructive"
          disabled={busy}
          onClick={() => {
            if (!window.confirm(labels.confirmDelete)) return;
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
          }}
        >
          {busy ? labels.deleting : labels.delete}
        </Button>
      ) : null}
    </li>
  );
}

function ServicePrincipalRow({
  principal,
  organizationId,
  authorizationRevision,
  permissions,
  labels,
  submit,
  busy,
}: {
  principal: CorporateServicePrincipalView;
  organizationId: string;
  authorizationRevision: number;
  permissions: readonly string[];
  labels: Props["labels"];
  submit: Submit;
  busy: boolean;
}) {
  const canUpdate = permissions.includes("service_principal.manage");
  const canDelete = permissions.includes("service_principal.delete");
  return (
    <li className="border-border flex flex-wrap items-center gap-2 rounded border p-3 text-sm">
      <span className="min-w-0 flex-1 truncate">{principal.name}</span>
      <span className="text-muted-foreground">{principal.binding.role}</span>
      <span className="text-muted-foreground">{principal.state}</span>
      {canUpdate ? (
        <Button
          type="button"
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
      {canDelete ? (
        <Button
          type="button"
          variant="destructive"
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
  );
}
