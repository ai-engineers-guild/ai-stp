/* eslint-disable max-lines-per-function, max-lines */
"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/atoms/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/atoms/dialog";
import { CatalogChoiceMenu } from "@/components/molecules/catalog-choice-menu";
import { FormDialog } from "@/components/molecules/form-dialog";
import { SearchableMultiSelect } from "@/components/molecules/searchable-multi-select";
import {
  PeopleSearch,
  PeopleSelect,
  peopleSelectClass,
  usePeopleFilters,
} from "@/components/organisms/corporate-people-ui";
import { CorporatePermissionTable } from "@/components/organisms/corporate-permission-table";
import { CorporateRolePanel } from "@/components/organisms/corporate-role-panel";
import { corporateMutation } from "@/lib/api/corporate-mutation";
import type {
  CorporateBinding,
  CorporateContext,
  CorporateMember,
  CorporatePermissionDefinition,
  CorporateRoleView,
} from "@/lib/api/generated/types.gen";
import { BUILT_IN_ROLES } from "@/lib/corporate-roles";
import { rolePermissions, roleTitle } from "@/lib/corporate-permission-ui";
import {
  collectRoleAssignmentRows,
  type BindingOrigin,
  type RoleAssignmentRow,
} from "@/lib/role-assignments";
import { Link } from "@/lib/i18n/navigation";
import { Icon } from "@/theme";
import type { IconName } from "@/theme";

const rolePanelLabels = (c: ReturnType<typeof useTranslations>) => ({
  name: c("name"),
  renameHint: c("renameRoleHint"),
  permissions: c("permissions"),
  create: c("create"),
  creating: c("creating"),
  update: c("update"),
  saving: c("saving"),
  saved: c("saved"),
  failed: c("failed"),
});

function RoleAssignments({ rows }: { rows: readonly RoleAssignmentRow[] }) {
  const t = useTranslations("accessUi");
  const c = useTranslations("corporate");
  const originLabel: Record<BindingOrigin, string> = {
    membership: c("originMembership"),
    assignment: c("originAssignment"),
    direct: c("originDirect"),
    service_principal: c("originServicePrincipal"),
  };
  return rows.length ? (
    <div className="overflow-x-auto">
      <table className="w-full min-w-96 text-sm">
        <thead>
          <tr className="text-muted-foreground border-border border-b text-xs">
            <th className="p-3 text-left">{t("employee")}</th>
            <th className="p-3 text-left">{t("scope")}</th>
            <th className="p-3 text-left">{c("origin")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key} className="border-border border-b">
              <td className="p-3">
                {row.accountId ? (
                  <Link
                    href={`/corporate/admins/employee-access?employee=${encodeURIComponent(row.accountId)}`}
                    className="hover:underline"
                  >
                    {row.name}
                  </Link>
                ) : (
                  row.name
                )}
              </td>
              <td className="p-3">
                <p>
                  {t.has(`scopes.${row.scopeKind}`) ? t(`scopes.${row.scopeKind}`) : row.scopeKind}
                </p>
                <p className="text-muted-foreground text-xs">{row.scopeLabel}</p>
              </td>
              <td className="p-3">
                {row.origins.map((origin) => originLabel[origin]).join(" · ")}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  ) : (
    <p className="text-muted-foreground text-sm">{t("noAssignments")}</p>
  );
}

export function CorporateRolesWorkspace({
  roles,
  bindings,
  members,
  definitions,
  context,
  csrfToken,
}: {
  roles: readonly CorporateRoleView[];
  bindings: readonly CorporateBinding[];
  members: readonly CorporateMember[];
  definitions: readonly CorporatePermissionDefinition[];
  context: CorporateContext;
  csrfToken: string;
}) {
  const t = useTranslations("accessUi");
  const c = useTranslations("corporate");
  const filters = usePeopleFilters();
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState("");
  const [tab, setTab] = useState("permissions");
  const [editor, setEditor] = useState<"create" | "edit" | "duplicate" | null>(null);
  const [assignTarget, setAssignTarget] = useState<CorporateRoleView | null>(null);
  const [assignSelection, setAssignSelection] = useState<string[]>([]);
  const [deleteTarget, setDeleteTarget] = useState<CorporateRoleView | null>(null);
  const [replacement, setReplacement] = useState("");
  const [busy, startTransition] = useTransition();
  const [message, setMessage] = useState<{ text: string; error?: boolean } | null>(null);
  const organizationId = context.organization.organization_id;
  const authorizationRevision = context.organization.authorization_revision;
  const can = (permission: string) => context.capabilities.includes(permission);
  const visibleRoles = [...roles]
    .sort(
      (a, b) =>
        (["superadmin", "lead", "staff"].indexOf(a.name) + 1 || 4) -
        (["superadmin", "lead", "staff"].indexOf(b.name) + 1 || 4),
    )
    .filter(
      (role) =>
        (!kind || (BUILT_IN_ROLES.has(role.name) ? "system" : "custom") === kind) &&
        roleTitle(role.name, t).toLowerCase().includes(query.toLowerCase()),
    );
  const selected = roles.find((role) => role.name === filters.get("role")) ?? visibleRoles[0];
  const scopeName = (kind: string, id: string) =>
    context.teams.find((team) => team.team_id === id)?.name ??
    context.projects.find((project) => project.project_id === id)?.name ??
    (kind === "organization" ? context.organization.display_name : id);
  const assignmentRows = selected
    ? collectRoleAssignmentRows({
        bindings,
        members,
        roleName: selected.name,
        organizationId,
        scopeName,
      })
    : [];
  const assignmentCount = assignmentRows.length;
  const selectedSystem = selected ? BUILT_IN_ROLES.has(selected.name) : false;
  const roleDescription = (role: CorporateRoleView) =>
    t(`roleDescriptions.${BUILT_IN_ROLES.has(role.name) ? role.name : "custom"}`);
  const selectRole = (role: CorporateRoleView) => {
    filters.update("role", role.name);
  };
  const openAssign = (role: CorporateRoleView) => {
    selectRole(role);
    setAssignTarget(role);
    setAssignSelection(
      bindings
        .filter(
          (binding) =>
            binding.role === role.name &&
            binding.origin === "direct" &&
            binding.state === "active" &&
            binding.scope_kind === "organization" &&
            binding.account_id !== null,
        )
        .map((binding) => binding.account_id as string),
    );
    setMessage(null);
  };
  const openDelete = (role: CorporateRoleView) => {
    selectRole(role);
    setDeleteTarget(role);
    setReplacement(
      roles.some((item) => item.name !== role.name && item.name === "staff")
        ? "staff"
        : (roles.find((item) => item.name !== role.name)?.name ?? ""),
    );
    setMessage(null);
  };
  const roleChoices = (role: CorporateRoleView) => {
    const system = BUILT_IN_ROLES.has(role.name);
    return [
      ...(can("binding.create")
        ? [
            {
              label: c("assignEmployees"),
              icon: "team" as IconName,
              onSelect: () => {
                openAssign(role);
              },
            },
          ]
        : []),
      ...(!system && can("role.update")
        ? [
            {
              label: t("editRole"),
              icon: "edit" as IconName,
              onSelect: () => {
                selectRole(role);
                setEditor("edit");
              },
            },
          ]
        : []),
      ...(can("role.create")
        ? [
            {
              label: t("duplicateRole"),
              icon: "copy" as IconName,
              onSelect: () => {
                selectRole(role);
                setEditor("duplicate");
              },
            },
          ]
        : []),
      ...(!system && can("role.delete")
        ? [
            {
              label: c("delete"),
              icon: "alert" as IconName,
              separatorBefore: true,
              onSelect: () => {
                openDelete(role);
              },
            },
          ]
        : []),
    ];
  };
  return (
    <div className="min-w-0 space-y-4" data-ui="roles-workspace">
      <div className="flex flex-wrap items-center gap-3">
        <PeopleSearch label={t("searchRoles")} value={query} onChange={setQuery} />
        <PeopleSelect
          label={t("allRoles")}
          value={kind}
          onChange={setKind}
          options={[
            { value: "system", label: t("systemRoles") },
            { value: "custom", label: t("customRoles") },
          ]}
        />
        {can("role.create") ? (
          <Button
            onClick={() => {
              setEditor("create");
            }}
          >
            <Icon name="plus" size="sm" />
            {t("createRole")}
          </Button>
        ) : null}
      </div>
      <div className="grid min-w-0 gap-4 lg:grid-cols-[minmax(13rem,1fr)_minmax(0,3fr)]">
        <nav className="border-border min-w-0 rounded-lg border" aria-label={c("roles")}>
          <h2 className="border-border border-b px-4 py-3 font-medium">
            {c("roles")} ({visibleRoles.length})
          </h2>
          {visibleRoles.map((role) => (
            <div
              key={role.name}
              className={`border-border flex items-start border-b last:border-0 ${role.name === selected?.name ? "bg-primary/10" : "hover:bg-muted/20"}`}
            >
              <button
                type="button"
                aria-current={role.name === selected?.name ? "true" : undefined}
                className="focus-visible:ring-ring min-w-0 flex-1 rounded-sm p-4 text-left focus-visible:ring-2"
                onClick={() => {
                  selectRole(role);
                }}
              >
                <span className="block text-sm font-medium">{roleTitle(role.name, t)}</span>
                <span className="text-muted-foreground mt-1 block text-xs">
                  {roleDescription(role)}
                </span>
              </button>
              <div className="mt-2 mr-1 shrink-0">
                <CatalogChoiceMenu
                  label={t("openDetails", { name: roleTitle(role.name, t) })}
                  icon="more"
                  variant="ghost"
                  align="end"
                  options={roleChoices(role)}
                />
              </div>
            </div>
          ))}
        </nav>
        {selected ? (
          <section
            className="border-border min-w-0 rounded-lg border"
            aria-label={roleTitle(selected.name, t)}
          >
            <header className="flex flex-wrap items-start justify-between gap-3 p-4">
              <div>
                <h2 className="text-xl font-medium">{roleTitle(selected.name, t)}</h2>
                <p className="text-muted-foreground mt-1 text-sm">{roleDescription(selected)}</p>
              </div>
            </header>
            <div className="border-border flex overflow-x-auto border-b px-4">
              {["permissions", "assignments"].map((value) => (
                <Button
                  variant="ghost"
                  key={value}
                  aria-pressed={tab === value}
                  onClick={() => {
                    setTab(value);
                  }}
                  className={`rounded-none ${tab === value ? "border-primary border-b-2" : ""}`}
                >
                  {t(value)}
                  {value === "assignments" ? ` (${assignmentCount})` : ""}
                </Button>
              ))}
            </div>
            <div className="p-3">
              {tab === "permissions" ? (
                <>
                  <CorporatePermissionTable
                    definitions={definitions}
                    permissions={[...rolePermissions(selected)]}
                  />
                  {selectedSystem ? (
                    <p className="text-muted-foreground mt-3 text-xs">{t("immutableRole")}</p>
                  ) : null}
                </>
              ) : (
                <RoleAssignments rows={assignmentRows} />
              )}
            </div>
          </section>
        ) : (
          <p className="text-muted-foreground p-4">{t("noResults")}</p>
        )}
      </div>
      <Dialog
        open={editor !== null}
        onOpenChange={(open) => {
          if (!open) setEditor(null);
        }}
      >
        <DialogContent
          closeLabel={c("close")}
          className="max-h-[calc(100dvh-2rem)] w-[calc(100%-2rem)] max-w-3xl overflow-y-auto"
        >
          <DialogTitle>
            {t(
              editor === "duplicate"
                ? "duplicateRole"
                : editor === "edit"
                  ? "editRole"
                  : "createRole",
            )}
          </DialogTitle>
          <DialogDescription>{c("editRoleBody")}</DialogDescription>
          {editor !== null ? (
            <CorporateRolePanel
              key={`${editor}:${selected?.name ?? ""}`}
              csrfToken={csrfToken}
              organizationId={organizationId}
              authorizationRevision={authorizationRevision}
              definitions={definitions}
              selected={editor === "edit" ? (selected ?? null) : null}
              template={editor === "duplicate" ? selected : undefined}
              labels={rolePanelLabels(c)}
              mode={editor === "edit" ? "edit" : "create"}
              onSaved={(name) => {
                // A real navigation, not history.replaceState: the refresh the
                // panel dispatched must land, and the ?role= param stays a
                // deep-linkable part of the URL.
                if (name && name !== selected?.name)
                  router.replace(`?role=${encodeURIComponent(name)}`, { scroll: false });
                setEditor(null);
              }}
            />
          ) : null}
        </DialogContent>
      </Dialog>
      <FormDialog
        open={assignTarget !== null}
        onOpenChange={(open) => {
          if (!open) setAssignTarget(null);
        }}
        title={c("assignEmployees")}
        description={c("assignRoleBody", {
          name: assignTarget ? roleTitle(assignTarget.name, t) : "",
        })}
        closeLabel={c("close")}
        cancelLabel={c("cancel")}
        submitLabel={c("save")}
        busyLabel={c("saving")}
        busy={busy}
        error={message?.error ? message.text : null}
        onSubmit={() => {
          if (!assignTarget) return;
          const role = assignTarget;
          const after = new Set(assignSelection);
          const direct = bindings.filter(
            (binding) =>
              binding.role === role.name &&
              binding.origin === "direct" &&
              binding.state === "active" &&
              binding.scope_kind === "organization" &&
              binding.account_id !== null,
          );
          setMessage(null);
          startTransition(async () => {
            let failed = 0;
            for (const accountId of after) {
              if (direct.some((binding) => binding.account_id === accountId)) continue;
              const result = await corporateMutation({
                csrfToken,
                organizationId,
                path: `/v1/corporate/organizations/${organizationId}/bindings`,
                method: "POST",
                body: {
                  schema_version: 1,
                  account_id: accountId,
                  role: role.name,
                  scope_kind: "organization",
                  scope_id: organizationId,
                  coverage: "self",
                  authorization_revision: authorizationRevision,
                  idempotency_key: crypto.randomUUID(),
                },
              });
              if (!result.ok) failed += 1;
            }
            for (const binding of direct) {
              if (binding.account_id && after.has(binding.account_id)) continue;
              const result = await corporateMutation({
                csrfToken,
                organizationId,
                path: `/v1/corporate/organizations/${organizationId}/bindings/${binding.binding_id}`,
                method: "DELETE",
                body: {
                  schema_version: 1,
                  expected_revision: binding.revision,
                  authorization_revision: authorizationRevision,
                  idempotency_key: crypto.randomUUID(),
                },
              });
              if (!result.ok) failed += 1;
            }
            setMessage({
              text: failed ? c("assignPartial", { count: failed }) : c("saved"),
              error: Boolean(failed),
            });
            if (!failed) setAssignTarget(null);
            router.refresh();
          });
        }}
      >
        <SearchableMultiSelect
          name="members"
          label={c("assignedEmployees")}
          searchLabel={c("searchEmployees")}
          options={members.map((member) => ({
            value: member.account_id,
            label: member.contact_email
              ? `${member.display_name ?? member.account_id} · ${member.contact_email}`
              : (member.display_name ?? member.account_id),
          }))}
          selected={assignSelection}
          onChange={setAssignSelection}
          inline
          closeLabel={c("close")}
          selectionSuffix={c("selectedSuffix")}
          emptyHint={c("searchEmployees")}
        />
      </FormDialog>
      <FormDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
        title={c("delete")}
        description={
          deleteTarget ? c("deleteRoleBody", { name: roleTitle(deleteTarget.name, t) }) : undefined
        }
        closeLabel={c("close")}
        cancelLabel={c("cancel")}
        submitLabel={c("delete")}
        busyLabel={c("deleting")}
        busy={busy}
        submitVariant="destructive"
        error={message?.error ? message.text : null}
        onSubmit={() => {
          if (!deleteTarget) return;
          const role = deleteTarget;
          setMessage(null);
          startTransition(async () => {
            const result = await corporateMutation({
              csrfToken,
              organizationId,
              path: `/v1/corporate/organizations/${organizationId}/roles/${encodeURIComponent(role.name)}`,
              method: "DELETE",
              body: {
                schema_version: 1,
                expected_revision: role.revision,
                replacement_role: replacement || null,
                authorization_revision: authorizationRevision,
                idempotency_key: crypto.randomUUID(),
              },
            });
            setMessage({
              text: result.ok ? c("saved") : result.message || c("failed"),
              error: !result.ok,
            });
            if (result.ok) {
              setDeleteTarget(null);
              router.refresh();
            }
          });
        }}
      >
        <div className="space-y-1.5">
          <label htmlFor="role-replacement" className="text-sm font-medium">
            {c("replacementRole")}
          </label>
          <select
            id="role-replacement"
            value={replacement}
            onChange={(event) => {
              setReplacement(event.target.value);
            }}
            className={peopleSelectClass}
          >
            {roles
              .filter((item) => item.name !== deleteTarget?.name)
              .map((item) => (
                <option key={item.name} value={item.name}>
                  {roleTitle(item.name, t)}
                </option>
              ))}
          </select>
          <p className="text-muted-foreground text-xs">{c("replacementRoleBody")}</p>
        </div>
      </FormDialog>
    </div>
  );
}
