/* eslint-disable max-lines-per-function, complexity */
"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Badge } from "@/components/atoms/badge";
import { Button } from "@/components/atoms/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/atoms/dialog";
import {
  CorporateDetailDrawer,
  PeopleSearch,
  PeopleSelect,
  usePeopleFilters,
} from "@/components/organisms/corporate-people-ui";
import { CorporatePermissionTable } from "@/components/organisms/corporate-permission-table";
import { CorporateRolePanel } from "@/components/organisms/corporate-role-panel";
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
                    href={`/corporate/organization/admins/employees?employee=${encodeURIComponent(row.accountId)}`}
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
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState("");
  const [tab, setTab] = useState("permissions");
  const [drawer, setDrawer] = useState(false);
  const [editor, setEditor] = useState<"create" | "edit" | "duplicate" | null>(null);
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
        organizationId: context.organization.organization_id,
        scopeName,
      })
    : [];
  const assignmentCount = assignmentRows.length;
  const labels = {
    createRole: c("createRole"),
    editRoleBody: c("editRoleBody"),
    name: c("name"),
    parentRole: c("parentRole"),
    permissions: c("permissions"),
    create: c("create"),
    creating: c("creating"),
    update: c("update"),
    saving: c("saving"),
    delete: c("delete"),
    deleting: c("deleting"),
    deleteConfirm: c("deleteRoleConfirm"),
    saved: c("saved"),
    failed: c("failed"),
    none: "—",
  };
  const selectedSystem = selected ? BUILT_IN_ROLES.has(selected.name) : false;
  const roleDescription = (role: CorporateRoleView) =>
    t(`roleDescriptions.${BUILT_IN_ROLES.has(role.name) ? role.name : "custom"}`);
  const scopes = selected
    ? [
        ...new Set(
          definitions
            .filter((item) => rolePermissions(selected, roles).has(item.name))
            .flatMap((item) => item.scopes),
        ),
      ]
    : [];
  return (
    <div
      className={`min-w-0 space-y-4 ${drawer ? "2xl:pr-[27rem]" : ""}`}
      data-ui="roles-workspace"
    >
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
        {context.capabilities.includes("role.create") ? (
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
                  filters.update("role", role.name);
                }}
              >
                <span className="block text-sm font-medium">{roleTitle(role.name, t)}</span>
                <span className="text-muted-foreground mt-1 block text-xs">
                  {roleDescription(role)}
                </span>
              </button>
              <Button
                variant="ghost"
                size="icon"
                className="mt-2 mr-1 shrink-0"
                aria-label={t("openDetails", { name: roleTitle(role.name, t) })}
                onClick={() => {
                  filters.update("role", role.name);
                  setDrawer(true);
                }}
              >
                <Icon name="more" size="sm" />
              </Button>
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
              <div className="flex gap-2">
                {context.capabilities.includes("role.create") ? (
                  <Button
                    variant="outline"
                    onClick={() => {
                      setEditor("duplicate");
                    }}
                  >
                    {t("duplicateRole")}
                  </Button>
                ) : null}
                {!selectedSystem && context.capabilities.includes("role.update") ? (
                  <Button
                    variant="outline"
                    onClick={() => {
                      setEditor("edit");
                    }}
                  >
                    <Icon name="edit" size="sm" />
                    {t("editRole")}
                  </Button>
                ) : null}
                <Button
                  variant="outline"
                  onClick={() => {
                    setDrawer(true);
                  }}
                >
                  {t("details")}
                </Button>
              </div>
            </header>
            <div className="border-border flex overflow-x-auto border-b px-4">
              {["permissions", "details", "assignments"].map((value) => (
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
                    permissions={[...rolePermissions(selected, roles)]}
                  />
                  {selected.parent_role ? (
                    <p className="text-muted-foreground mt-3 text-xs">
                      {t("inherited", { role: roleTitle(selected.parent_role, t) })}
                    </p>
                  ) : null}
                  {selectedSystem ? (
                    <p className="text-muted-foreground mt-3 text-xs">{t("immutableRole")}</p>
                  ) : null}
                </>
              ) : tab === "assignments" ? (
                <RoleAssignments rows={assignmentRows} />
              ) : (
                <dl className="space-y-4 p-2 text-sm">
                  <div>
                    <dt className="text-muted-foreground">{c("name")}</dt>
                    <dd>{selected.name}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">{c("parentRole")}</dt>
                    <dd>{selected.parent_role ?? "—"}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">{c("revision")}</dt>
                    <dd>{selected.revision}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">{t("scope")}</dt>
                    <dd>{scopes.map((scope) => t(`scopes.${scope}`)).join(", ")}</dd>
                  </div>
                </dl>
              )}
            </div>
          </section>
        ) : (
          <p className="text-muted-foreground p-4">{t("noResults")}</p>
        )}
      </div>
      <CorporateDetailDrawer
        open={drawer && Boolean(selected)}
        onOpenChange={setDrawer}
        title={t("roleDetails")}
      >
        {selected ? (
          <div className="space-y-5">
            <div className="flex gap-3">
              <Icon name="access" size="lg" />
              <div>
                <h3 className="font-medium">{roleTitle(selected.name, t)}</h3>
                <Badge variant="secondary" className="mt-1 font-sans">
                  {t(selectedSystem ? "systemRole" : "customRole")}
                </Badge>
              </div>
            </div>
            <div>
              <h3 className="text-sm font-medium">{t("description")}</h3>
              <p className="text-muted-foreground mt-2 text-sm">{roleDescription(selected)}</p>
            </div>
            <div>
              <h3 className="text-sm font-medium">{t("scope")}</h3>
              <div className="mt-2 flex flex-wrap gap-1">
                {scopes.map((scope) => (
                  <Badge key={scope} variant="secondary" className="font-sans">
                    {t(`scopes.${scope}`)}
                  </Badge>
                ))}
              </div>
            </div>
            <div className="border-border space-y-3 border-t pt-4">
              <h3 className="font-medium">
                {t("assignments")} ({assignmentCount})
              </h3>
              <RoleAssignments rows={assignmentRows} />
            </div>
          </div>
        ) : null}
      </CorporateDetailDrawer>
      <Dialog
        open={editor !== null}
        onOpenChange={(open) => {
          if (!open) setEditor(null);
        }}
      >
        <DialogContent
          className="max-h-[90dvh] w-[calc(100%-2rem)] max-w-5xl overflow-y-auto"
          closeLabel={c("cancel")}
        >
          <DialogTitle>{t(editor === "edit" ? "editRole" : "createRole")}</DialogTitle>
          <DialogDescription>{c("editRoleBody")}</DialogDescription>
          <CorporateRolePanel
            key={`${editor}:${selected?.name ?? ""}`}
            csrfToken={csrfToken}
            organizationId={context.organization.organization_id}
            authorizationRevision={context.organization.authorization_revision}
            capabilities={context.capabilities}
            roles={roles}
            definitions={definitions}
            selected={editor === "edit" ? (selected ?? null) : null}
            template={editor === "duplicate" ? selected : undefined}
            labels={labels}
            mode={editor === "edit" ? "edit" : "create"}
          />
        </DialogContent>
      </Dialog>
    </div>
  );
}
