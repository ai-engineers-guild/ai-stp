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
  permissions: readonly string[];
  labels: {
    title: string;
    description: string;
    members: string;
    projects: string;
    teams: string;
    roles: string;
    displayName: string;
    email: string;
    name: string;
    role: string;
    parentRole: string;
    permissions: string;
    staff: string;
    lead: string;
    create: string;
    creating: string;
    saved: string;
    failed: string;
  };
};

// The panel keeps the four small CRUD entry forms together so capability
// visibility and revision/idempotency handling stay easy to audit.
// eslint-disable-next-line max-lines-per-function
export function CorporateAdminPanel({
  csrfToken,
  organizationId,
  authorizationRevision,
  permissions,
  labels,
}: Props) {
  const router = useRouter();
  const [busy, startTransition] = useTransition();
  const [member, setMember] = useState({ displayName: "", email: "", role: "staff" });
  const [project, setProject] = useState("");
  const [team, setTeam] = useState("");
  const [roleName, setRoleName] = useState("");
  const [parentRole, setParentRole] = useState("");
  const [rolePermissions, setRolePermissions] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const can = (permission: string) => permissions.includes(permission);

  function submit(path: string, body: unknown) {
    setMessage(null);
    startTransition(async () => {
      const result = await corporateMutationAction({
        csrfToken,
        organizationId,
        path,
        method: "POST",
        body,
      });
      if (!result.ok) {
        setMessage(result.message);
        return;
      }
      setMember({ displayName: "", email: "", role: "staff" });
      setProject("");
      setTeam("");
      setRoleName("");
      setParentRole("");
      setRolePermissions("");
      setMessage(labels.saved);
      router.refresh();
    });
  }

  return (
    <section className="border-border bg-card space-y-6 rounded-lg border p-5 shadow-sm sm:p-6">
      <div>
        <h2 className="text-xl font-medium">{labels.title}</h2>
        <p className="text-muted-foreground mt-2 text-sm">{labels.description}</p>
      </div>
      <div className="grid gap-6 lg:grid-cols-4">
        {can("member.create") ? (
          <form
            className="space-y-3"
            onSubmit={(event) => {
              event.preventDefault();
              submit(`/v1/corporate/organizations/${organizationId}/members`, {
                schema_version: 1,
                display_name: member.displayName,
                email: member.email,
                role: member.role,
                authorization_revision: authorizationRevision,
                idempotency_key: crypto.randomUUID(),
              });
            }}
          >
            <h3 className="font-medium">{labels.members}</h3>
            <Label htmlFor="corporate-member-name">{labels.displayName}</Label>
            <Input
              id="corporate-member-name"
              required
              value={member.displayName}
              onChange={(event) => {
                setMember({ ...member, displayName: event.target.value });
              }}
            />
            <Label htmlFor="corporate-member-email">{labels.email}</Label>
            <Input
              id="corporate-member-email"
              type="email"
              required
              value={member.email}
              onChange={(event) => {
                setMember({ ...member, email: event.target.value });
              }}
            />
            <Label htmlFor="corporate-member-role">{labels.role}</Label>
            <select
              id="corporate-member-role"
              value={member.role}
              onChange={(event) => {
                setMember({ ...member, role: event.target.value });
              }}
              className="border-border bg-background h-9 w-full rounded-sm border px-3 text-sm"
            >
              <option value="staff">{labels.staff}</option>
              <option value="lead">{labels.lead}</option>
            </select>
            <Button type="submit" disabled={busy} className="w-full">
              {busy ? labels.creating : labels.create}
            </Button>
          </form>
        ) : null}
        {can("project.create") ? (
          <form
            className="space-y-3"
            onSubmit={(event) => {
              event.preventDefault();
              submit(`/v1/corporate/organizations/${organizationId}/projects`, {
                schema_version: 1,
                name: project,
                authorization_revision: authorizationRevision,
                idempotency_key: crypto.randomUUID(),
              });
            }}
          >
            <h3 className="font-medium">{labels.projects}</h3>
            <Label htmlFor="corporate-project-name">{labels.name}</Label>
            <Input
              id="corporate-project-name"
              required
              value={project}
              onChange={(event) => {
                setProject(event.target.value);
              }}
            />
            <Button type="submit" disabled={busy} className="w-full">
              {busy ? labels.creating : labels.create}
            </Button>
          </form>
        ) : null}
        {can("team.create") ? (
          <form
            className="space-y-3"
            onSubmit={(event) => {
              event.preventDefault();
              submit(`/v1/corporate/organizations/${organizationId}/teams`, {
                schema_version: 1,
                name: team,
                authorization_revision: authorizationRevision,
                idempotency_key: crypto.randomUUID(),
              });
            }}
          >
            <h3 className="font-medium">{labels.teams}</h3>
            <Label htmlFor="corporate-team-name">{labels.name}</Label>
            <Input
              id="corporate-team-name"
              required
              value={team}
              onChange={(event) => {
                setTeam(event.target.value);
              }}
            />
            <Button type="submit" disabled={busy} className="w-full">
              {busy ? labels.creating : labels.create}
            </Button>
          </form>
        ) : null}
        {can("role.create") ? (
          <form
            className="space-y-3"
            onSubmit={(event) => {
              event.preventDefault();
              submit(`/v1/corporate/organizations/${organizationId}/roles`, {
                schema_version: 1,
                name: roleName,
                parent_role: parentRole || null,
                permissions: rolePermissions
                  .split(",")
                  .map((permission) => permission.trim())
                  .filter(Boolean),
                authorization_revision: authorizationRevision,
                idempotency_key: crypto.randomUUID(),
              });
            }}
          >
            <h3 className="font-medium">{labels.roles}</h3>
            <Label htmlFor="corporate-role-name">{labels.name}</Label>
            <Input
              id="corporate-role-name"
              required
              pattern="[a-z][a-z0-9_-]*"
              value={roleName}
              onChange={(event) => {
                setRoleName(event.target.value);
              }}
            />
            <Label htmlFor="corporate-role-parent">{labels.parentRole}</Label>
            <Input
              id="corporate-role-parent"
              value={parentRole}
              onChange={(event) => {
                setParentRole(event.target.value);
              }}
            />
            <Label htmlFor="corporate-role-permissions">{labels.permissions}</Label>
            <Input
              id="corporate-role-permissions"
              value={rolePermissions}
              onChange={(event) => {
                setRolePermissions(event.target.value);
              }}
            />
            <Button type="submit" disabled={busy} className="w-full">
              {busy ? labels.creating : labels.create}
            </Button>
          </form>
        ) : null}
      </div>
      {message ? (
        <p className="text-muted-foreground text-sm" role="status" aria-live="polite">
          {message}
        </p>
      ) : null}
    </section>
  );
}
