import { getTranslations, setRequestLocale } from "next-intl/server";

import { Badge } from "@/components/atoms/badge";
import { CopyValue } from "@/components/molecules/copy-value";
import { StatePanel } from "@/components/molecules/state-panel";
import { CorporateRolePanel } from "@/components/organisms/corporate-role-panel";
import { BUILT_IN_ROLES } from "@/lib/corporate-roles";
import { ApiError } from "@/lib/api/errors";
import { apiRequest } from "@/lib/api/http";
import { readCorporateContext, readCorporateWorkspace } from "@/lib/api/corporate";
import type {
  CorporateBinding,
  CorporateMember,
  CorporateRoleView,
  CorporatePermissionMatrix,
} from "@/lib/api/generated/types.gen";
import { canViewCorporateAdministration } from "@/lib/corporate-hub";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";
import { Link } from "@/lib/i18n/navigation";

type PageProps = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

type Workspace = NonNullable<Awaited<ReturnType<typeof readCorporateWorkspace>>>;

type LoadResult =
  | { status: "forbidden" }
  | { status: "unavailable" }
  | { status: "empty" }
  | { status: "ok"; workspace: Workspace };

async function loadWorkspace(): Promise<LoadResult> {
  const session = (await sessionCookieValue()) ?? "";
  const context = await readCorporateContext(session);
  if (!context) return { status: "empty" };
  if (
    !canViewCorporateAdministration(context.capabilities) ||
    !context.capabilities.includes("role.list")
  ) {
    return { status: "forbidden" };
  }
  const workspace = await readCorporateWorkspace(session, false);
  return workspace ? { status: "ok", workspace } : { status: "empty" };
}

const rowClass = "border-border hover:bg-muted/40 border-b transition-colors last:border-0";
const headCellClass = "text-muted-foreground px-3 py-2 text-xs font-medium";

/** Permissions inherited through the parent chain, cycle-safe. */
function inheritedPermissions(
  role: CorporateRoleView,
  roles: readonly CorporateRoleView[],
): { name: string; permissions: string[] }[] {
  const byName = new Map(roles.map((item) => [item.name, item]));
  const chain: { name: string; permissions: string[] }[] = [];
  const seen = new Set([role.name]);
  let parent = role.parent_role;
  while (parent && !seen.has(parent)) {
    seen.add(parent);
    const ancestor = byName.get(parent);
    if (!ancestor) break;
    chain.push({ name: ancestor.name, permissions: ancestor.permissions });
    parent = ancestor.parent_role;
  }
  return chain;
}

function subjectLabel(binding: CorporateBinding, members: readonly CorporateMember[]): string {
  if (binding.account_id) {
    return (
      members.find((member) => member.account_id === binding.account_id)?.display_name ??
      binding.account_id
    );
  }
  return binding.service_principal_id ?? "";
}

function originLabel(origin: CorporateBinding["origin"] | null, t: (key: string) => string) {
  return origin === "membership"
    ? t("originMembership")
    : origin === "assignment"
      ? t("originAssignment")
      : origin === "service_principal"
        ? t("originServicePrincipal")
        : t("originDirect");
}

function panelLabels(t: (key: string) => string) {
  return {
    createRole: t("createRole"),
    editRoleBody: t("editRoleBody"),
    name: t("name"),
    parentRole: t("parentRole"),
    permissions: t("permissions"),
    create: t("create"),
    creating: t("creating"),
    update: t("update"),
    saving: t("saving"),
    delete: t("delete"),
    deleting: t("deleting"),
    deleteConfirm: t("deleteRoleConfirm"),
    saved: t("saved"),
    failed: t("failed"),
    none: "—",
  };
}

function RoleTable({
  roles,
  bindings,
  selectedName,
  t,
}: {
  roles: readonly CorporateRoleView[];
  bindings: readonly CorporateBinding[];
  selectedName: string;
  t: (key: string) => string;
}) {
  return (
    <nav className="border-border bg-card min-w-0 rounded-lg border" aria-label={t("roles")}>
      <h2 className="border-border border-b px-4 py-3 font-medium">
        {t("roles")} ({roles.length})
      </h2>
      {roles.map((role) => (
        <Link
          key={role.name}
          href={`/corporate/organization/admins/roles?role=${encodeURIComponent(role.name)}`}
          aria-label={role.name}
          className="border-border hover:bg-muted/40 focus-visible:ring-ring data-[ui-state=selected]:bg-primary/10 block border-b px-4 py-3 text-sm last:border-0 focus-visible:ring-2 focus-visible:outline-none"
          aria-current={role.name === selectedName ? "page" : undefined}
          data-ui-state={role.name === selectedName ? "selected" : undefined}
        >
          <span className="flex flex-wrap items-center gap-2">
            <span className="font-medium">{role.name}</span>
            <Badge variant={BUILT_IN_ROLES.has(role.name) ? "secondary" : "outline"}>
              {BUILT_IN_ROLES.has(role.name) ? t("systemRole") : t("customRole")}
            </Badge>
          </span>
          <span className="text-muted-foreground mt-1 block text-xs">
            {t("permissions")}: {role.permissions.length} · {t("roleUsedBy")}:{" "}
            {bindings.filter((binding) => binding.role === role.name).length}
          </span>
        </Link>
      ))}
      {!roles.length ? <p className="text-muted-foreground p-4 text-sm">{t("noRoles")}</p> : null}
    </nav>
  );
}
function RoleAssignments({
  assignments,
  members,
  t,
}: {
  assignments: readonly CorporateBinding[];
  members: readonly CorporateMember[];
  t: (key: string) => string;
}) {
  if (!assignments.length)
    return <p className="text-muted-foreground mt-2 text-sm">{t("noRoleAssignments")}</p>;
  return (
    <div className="-mx-4 mt-2 overflow-x-auto px-4 sm:-mx-5 sm:px-5">
      <table className="w-full min-w-max border-collapse text-sm">
        <thead>
          <tr className="border-border border-b">
            <th scope="col" className={`${headCellClass} pl-0 text-left`}>
              {t("member")}
            </th>
            <th scope="col" className={`${headCellClass} text-left`}>
              {t("scope")}
            </th>
            <th scope="col" className={`${headCellClass} text-left`}>
              {t("coverage")}
            </th>
            <th scope="col" className={`${headCellClass} text-left`}>
              {t("origin")}
            </th>
          </tr>
        </thead>
        <tbody>
          {assignments.map((binding) => (
            <tr key={binding.binding_id} className={rowClass}>
              <td className="py-2 pr-4">
                {binding.account_id ? (
                  <Link
                    href={`/corporate/organization/admins/employees/${encodeURIComponent(binding.account_id)}`}
                    className="underline-offset-4 hover:underline"
                  >
                    {subjectLabel(binding, members)}
                  </Link>
                ) : (
                  subjectLabel(binding, members)
                )}
              </td>
              <td className="px-3 py-2 font-mono text-xs">
                {binding.scope_kind}:{binding.scope_id}
              </td>
              <td className="px-3 py-2">
                {binding.coverage === "descendants" ? t("coverageDescendants") : t("coverageSelf")}
              </td>
              <td className="px-3 py-2">
                <Badge variant="secondary">{originLabel(binding.origin, t)}</Badge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SelectedRole({
  selected,
  roles,
  workspace,
  assignments,
  definitions,
  t,
  tc,
  csrfToken,
}: {
  selected: CorporateRoleView;
  roles: readonly CorporateRoleView[];
  workspace: Workspace;
  assignments: readonly CorporateBinding[];
  definitions: CorporatePermissionMatrix["definitions"];
  t: (key: string) => string;
  tc: (key: string) => string;
  csrfToken: string;
}) {
  const inherited = inheritedPermissions(selected, roles);
  return (
    <section
      className="border-border bg-card min-w-0 space-y-6 rounded-lg border p-5 shadow-sm sm:p-6"
      aria-label={selected.name}
    >
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-xl font-medium">{selected.name}</h2>
        {BUILT_IN_ROLES.has(selected.name) ? (
          <Badge variant="secondary">{t("systemRole")}</Badge>
        ) : (
          <Badge variant="outline">{t("customRole")}</Badge>
        )}
        <CopyValue
          value={selected.name}
          label={t("copyId")}
          copied={tc("copied")}
          failed={tc("error")}
        />
      </div>

      <dl className="text-muted-foreground flex flex-wrap gap-x-6 gap-y-1 text-sm">
        <div className="flex gap-2">
          <dt>{t("parentRole")}</dt>
          <dd className="text-foreground">{selected.parent_role ?? "—"}</dd>
        </div>
        <div className="flex gap-2">
          <dt>{t("revision")}</dt>
          <dd className="text-foreground">{selected.revision}</dd>
        </div>
      </dl>

      <div>
        <h3 className="font-medium">{t("ownPermissions")}</h3>
        <div className="mt-2 flex flex-wrap gap-1">
          {selected.permissions.length ? (
            selected.permissions.map((permission) => (
              <Badge key={permission} variant="outline">
                {permission}
              </Badge>
            ))
          ) : (
            <span className="text-muted-foreground text-sm">—</span>
          )}
        </div>
      </div>

      {inherited.length ? (
        <div>
          <h3 className="font-medium">{t("inheritedPermissions")}</h3>
          <div className="mt-2 space-y-2">
            {inherited.map((ancestor) => (
              <p key={ancestor.name} className="text-sm">
                <span className="font-medium">{ancestor.name}</span>
                <span className="text-muted-foreground"> · {ancestor.permissions.join(", ")}</span>
              </p>
            ))}
          </div>
        </div>
      ) : null}

      <div>
        <h3 className="font-medium">{t("roleAssignments")}</h3>
        <RoleAssignments assignments={assignments} members={workspace.members?.items ?? []} t={t} />
      </div>

      <CorporateRolePanel
        csrfToken={csrfToken}
        organizationId={workspace.organization.organization_id}
        authorizationRevision={workspace.context.organization.authorization_revision}
        capabilities={workspace.context.capabilities}
        roles={roles}
        definitions={definitions}
        selected={selected}
        labels={panelLabels(t)}
      />
    </section>
  );
}

export default async function CorporateRolesPage({ params, searchParams }: PageProps) {
  const { locale } = await params;
  const filters = await searchParams;
  const selectedName = typeof filters.role === "string" ? filters.role : "";
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/organization/admins/roles`);
  const t = await getTranslations("corporate");
  const tc = await getTranslations("common");
  const h = await getTranslations("hub");
  const technology = await getTranslations("technology");

  let result: LoadResult;
  try {
    result = await loadWorkspace();
  } catch (error) {
    if (error instanceof ApiError && error.code === "AI_STP_UNAVAILABLE") {
      result = { status: "unavailable" };
    } else {
      throw error;
    }
  }
  if (result.status === "unavailable") {
    return <StatePanel kind="error" title={tc("error")} description={tc("apiUnavailable")} />;
  }
  if (result.status === "forbidden") {
    return <StatePanel kind="error" title={h("roles")} description={technology("forbidden")} />;
  }
  if (result.status === "empty") {
    return <StatePanel kind="empty" title={h("roles")} description={t("emptyBody")} />;
  }

  const { workspace } = result;
  const roles = workspace.roles?.items ?? [];
  const bindings = (workspace.bindings?.items ?? []).filter(
    (binding) => binding.state === "active",
  );
  const selected = roles.find((role) => role.name === selectedName) ?? roles[0] ?? null;
  const csrfToken = (await readCsrfToken()) ?? "";
  const session = (await sessionCookieValue()) ?? "";
  const matrix = workspace.context.capabilities.includes("role.read")
    ? await apiRequest<CorporatePermissionMatrix>(
        `/v1/corporate/organizations/${workspace.organization.organization_id}/permissions/matrix`,
        { sessionToken: session },
      )
    : null;
  const definitions: CorporatePermissionMatrix["definitions"] =
    matrix?.definitions ??
    [...new Set([...workspace.context.capabilities, ...roles.flatMap((role) => role.permissions)])]
      .filter((permission) => permission.includes("."))
      .sort()
      .map((name) => {
        const [resource = "", action = ""] = name.split(".", 2);
        return {
          name,
          resource,
          action,
          group: resource,
          scopes: ["organization"],
          create_parent: null,
          implementation: "enforced",
        };
      });

  return (
    <div className="min-w-0 space-y-6">
      <header className="space-y-2">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-3xl font-medium tracking-tight sm:text-4xl">{h("roles")}</h1>
          <Badge variant="secondary">{workspace.context.member.role}</Badge>
        </div>
        <p className="text-muted-foreground max-w-2xl text-sm">{t("rolesBody")}</p>
      </header>

      <div className="grid min-w-0 gap-4 lg:grid-cols-[minmax(15rem,1fr)_minmax(0,3fr)]">
        <RoleTable roles={roles} bindings={bindings} selectedName={selected?.name ?? ""} t={t} />
        {selected ? (
          <SelectedRole
            selected={selected}
            roles={roles}
            workspace={workspace}
            assignments={bindings.filter((binding) => binding.role === selected.name)}
            definitions={definitions}
            t={t}
            tc={tc}
            csrfToken={csrfToken}
          />
        ) : workspace.context.capabilities.includes("role.create") ? (
          <CorporateRolePanel
            csrfToken={csrfToken}
            organizationId={workspace.organization.organization_id}
            authorizationRevision={workspace.context.organization.authorization_revision}
            capabilities={workspace.context.capabilities}
            roles={roles}
            definitions={definitions}
            selected={null}
            labels={panelLabels(t)}
          />
        ) : null}
      </div>
    </div>
  );
}
