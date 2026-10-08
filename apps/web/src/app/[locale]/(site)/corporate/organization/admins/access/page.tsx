import { getTranslations, setRequestLocale } from "next-intl/server";

import { Badge } from "@/components/atoms/badge";
import { Table, TBody, Td, THead, Th, Tr } from "@/components/atoms/table";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import { StatePanel } from "@/components/molecules/state-panel";
import { DetailAccordion } from "@/components/molecules/detail-accordion";
import { NavigationTabs } from "@/components/molecules/navigation-tabs";
import { ApiError } from "@/lib/api/errors";
import { apiRequest } from "@/lib/api/http";
import type {
  CorporatePermissionDefinition,
  CorporatePermissionMatrix,
  CorporateRoleView,
} from "@/lib/api/generated/types.gen";
import { readCorporateContext, readCorporateWorkspace } from "@/lib/api/corporate";
import { canViewCorporateAdministration } from "@/lib/corporate-hub";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { Link } from "@/lib/i18n/navigation";
import { Icon } from "@/theme";

type PageProps = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

function matchesQuery(definition: CorporatePermissionDefinition, query: string): boolean {
  if (!query) return true;
  return [definition.name, definition.resource, definition.action, definition.group].some((value) =>
    value.toLowerCase().includes(query),
  );
}

function groupDefinitions(definitions: readonly CorporatePermissionDefinition[]) {
  const byResource = new Map<string, CorporatePermissionDefinition[]>();
  const byGroup = new Map<string, string[]>();
  for (const definition of definitions) {
    const resourceBucket = byResource.get(definition.resource) ?? [];
    resourceBucket.push(definition);
    byResource.set(definition.resource, resourceBucket);
    const groupBucket = byGroup.get(definition.group) ?? [];
    groupBucket.push(definition.name);
    byGroup.set(definition.group, groupBucket);
  }
  return { byResource, byGroup };
}

function roleHasPermission(
  role: CorporateRoleView,
  permission: string,
  roles: readonly CorporateRoleView[],
): boolean {
  const byName = new Map(roles.map((item) => [item.name, item]));
  const seen = new Set<string>();
  let current: CorporateRoleView | undefined = role;
  while (current && !seen.has(current.name)) {
    if (current.permissions.includes(permission)) return true;
    seen.add(current.name);
    current = current.parent_role ? byName.get(current.parent_role) : undefined;
  }
  return false;
}

function MatrixTable({
  permissions,
  roles,
  labels,
}: {
  permissions: readonly string[];
  roles: readonly CorporateRoleView[];
  labels: { permission: string; granted: string; notGranted: string };
}) {
  return (
    <div className="-mx-4 overflow-x-auto px-4 sm:-mx-5 sm:px-5">
      <Table className="min-w-max">
        <THead>
          <Tr>
            <Th className="py-2 pr-4 pl-0">{labels.permission}</Th>
            {roles.map((role) => (
              <Th key={role.name} className="text-center">
                <Link
                  href={`/corporate/organization/admins/roles?role=${encodeURIComponent(role.name)}`}
                  className="text-foreground underline underline-offset-4"
                >
                  {role.name}
                </Link>
              </Th>
            ))}
          </Tr>
        </THead>
        <TBody>
          {permissions.map((permission) => (
            <Tr key={permission} className="hover:bg-muted/40 transition-colors">
              <Td className="pr-4 pl-0 font-mono text-xs whitespace-nowrap">{permission}</Td>
              {roles.map((role) => (
                <Td key={role.name} className="text-center align-middle">
                  {roleHasPermission(role, permission, roles) ? (
                    <Icon
                      name="check"
                      size="sm"
                      className="text-primary mx-auto"
                      aria-label={labels.granted}
                    />
                  ) : (
                    <>
                      <span className="text-muted-foreground/60" aria-hidden>
                        —
                      </span>
                      <span className="sr-only">{labels.notGranted}</span>
                    </>
                  )}
                </Td>
              ))}
            </Tr>
          ))}
        </TBody>
      </Table>
    </div>
  );
}

function EffectiveAccessTable({
  effective,
  labels,
}: {
  effective: NonNullable<CorporatePermissionMatrix["effective"]>;
  labels: { permission: string; scope: string; scopeId: string; grantedBy: string };
}) {
  return (
    <div className="-mx-4 overflow-x-auto px-4 sm:-mx-5 sm:px-5">
      <Table className="min-w-max">
        <THead>
          <Tr>
            {[labels.permission, labels.scope, labels.scopeId, labels.grantedBy].map((label) => (
              <Th key={label}>{label}</Th>
            ))}
          </Tr>
        </THead>
        <TBody>
          {effective.map((item) => (
            <Tr
              key={`${item.permission}:${item.scope_kind}:${item.scope_id}`}
              className="hover:bg-muted/40 transition-colors"
            >
              <Td className="pr-4 pl-0 font-mono text-xs whitespace-nowrap">{item.permission}</Td>
              <Td>
                <Badge variant="outline">{item.scope_kind}</Badge>
              </Td>
              <Td className="font-mono text-xs break-all">{item.scope_id}</Td>
              <Td>
                <span className="inline-flex flex-wrap gap-1">
                  {item.sources.map((source) => (
                    <Badge key={source} variant="secondary">
                      {source}
                    </Badge>
                  ))}
                </span>
              </Td>
            </Tr>
          ))}
        </TBody>
      </Table>
    </div>
  );
}

function EntitiesView({
  byResource,
  activeEntity,
  query,
  roles,
  t,
}: {
  byResource: Map<string, CorporatePermissionDefinition[]>;
  activeEntity: string;
  query: string;
  roles: readonly CorporateRoleView[];
  t: (key: string, values?: Record<string, string>) => string;
}) {
  return (
    <div className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,3fr)_minmax(19rem,1fr)]">
      <div className="border-border bg-card min-w-0 overflow-x-auto rounded-lg border">
        <Table className="min-w-max">
          <THead>
            <Tr>
              <Th>{t("entitiesAndActions")}</Th>
              <Th>{t("actions")}</Th>
            </Tr>
          </THead>
          <TBody>
            {[...byResource.entries()].map(([resource, resourceDefinitions]) => (
              <Tr key={resource} className="hover:bg-muted/40 transition-colors">
                <Th scope="row" className="px-3 py-3 text-left align-top">
                  <Link
                    href={`/corporate/organization/admins/access?view=entities&entity=${encodeURIComponent(resource)}${query ? `&query=${encodeURIComponent(query)}` : ""}`}
                    aria-current={resource === activeEntity ? "true" : undefined}
                    className="text-foreground font-medium underline-offset-4 hover:underline"
                  >
                    {resource.replaceAll("_", " ")}
                  </Link>
                </Th>
                <Td className="py-3">
                  <span className="flex flex-wrap gap-1">
                    {resourceDefinitions.map((definition) => (
                      <Badge key={definition.name} variant="outline" title={definition.name}>
                        {definition.action.replaceAll("_", " ")}
                      </Badge>
                    ))}
                  </span>
                </Td>
              </Tr>
            ))}
          </TBody>
        </Table>
      </div>
      <aside
        className="border-border bg-card min-w-0 self-start rounded-lg border p-4"
        aria-label={activeEntity}
      >
        <h2 className="text-lg font-medium">{activeEntity.replaceAll("_", " ")}</h2>
        <p className="text-muted-foreground mt-1 text-sm">
          {byResource.get(activeEntity)?.length ?? 0} {t("actions").toLowerCase()}
        </p>
        <ul className="border-border mt-3 divide-y border-t">
          {(byResource.get(activeEntity) ?? []).map((definition) => (
            <li key={definition.name} className="space-y-2 py-3 text-sm">
              <p className="font-medium">{definition.action.replaceAll("_", " ")}</p>
              <p className="text-muted-foreground font-mono text-xs break-all">{definition.name}</p>
              {definition.create_parent ? (
                <p className="text-muted-foreground text-xs">
                  {t("requiresParent", { parent: definition.create_parent })}
                </p>
              ) : null}
              <div className="flex flex-wrap gap-1" aria-label={t("scope")}>
                {definition.scopes.map((scope) => (
                  <Badge key={scope} variant="outline">
                    {scope}
                  </Badge>
                ))}
              </div>
              <div className="flex flex-wrap gap-1" aria-label={t("roles")}>
                {roles
                  .filter((role) => roleHasPermission(role, definition.name, roles))
                  .map((role) => (
                    <Link
                      key={role.name}
                      href={`/corporate/organization/admins/roles?role=${encodeURIComponent(role.name)}`}
                    >
                      <Badge variant="secondary">{role.name}</Badge>
                    </Link>
                  ))}
              </div>
            </li>
          ))}
        </ul>
      </aside>
    </div>
  );
}
export default async function CorporateAccessModelPage({ params, searchParams }: PageProps) {
  const { locale } = await params;
  const filters = await searchParams;
  const view = filters.view === "matrix" ? "matrix" : "entities";
  const query = typeof filters.query === "string" ? filters.query.trim() : "";
  const selectedEntity = typeof filters.entity === "string" ? filters.entity : "";
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/organization/admins/access`);
  const t = await getTranslations("corporate");
  const tc = await getTranslations("common");
  const h = await getTranslations("hub");
  const technology = await getTranslations("technology");

  const session = (await sessionCookieValue()) ?? "";
  let context;
  try {
    context = await readCorporateContext(session);
  } catch (error) {
    if (error instanceof ApiError && error.code === "AI_STP_UNAVAILABLE") {
      return <StatePanel kind="error" title={tc("error")} description={tc("apiUnavailable")} />;
    }
    throw error;
  }
  if (
    !context ||
    !canViewCorporateAdministration(context.capabilities) ||
    !context.capabilities.includes("role.list")
  ) {
    return (
      <StatePanel kind="error" title={h("accessModel")} description={technology("forbidden")} />
    );
  }
  const organizationId = context.organization.organization_id;
  const workspace = await readCorporateWorkspace(session, false);
  const matrix = await apiRequest<CorporatePermissionMatrix>(
    `/v1/corporate/organizations/${organizationId}/permissions/matrix`,
    { sessionToken: session },
  ).catch(() => null);
  const roles = workspace?.roles?.items ?? [];
  const normalized = query.toLowerCase();
  const definitions = (matrix?.definitions ?? []).filter((definition) =>
    matchesQuery(definition, normalized),
  );
  const { byResource, byGroup } = groupDefinitions(definitions);
  const activeEntity = byResource.has(selectedEntity)
    ? selectedEntity
    : (byResource.keys().next().value ?? "");
  const effective = matrix?.effective ?? [];
  const groupsCount = view === "entities" ? byResource.size : byGroup.size;

  return (
    <div className="min-w-0 space-y-6">
      <header className="space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-medium tracking-tight break-words sm:text-3xl">
            {h("accessModel")}
          </h1>
          <Badge variant="secondary">{context.member.role}</Badge>
        </div>
        <p className="text-muted-foreground max-w-2xl text-sm">{t("accessModelBody")}</p>
        <dl className="text-muted-foreground flex flex-wrap gap-x-6 gap-y-1 font-mono text-xs">
          {[
            [t("roles"), roles.length],
            [t("accessMatrixGroups"), groupsCount],
            [t("permission"), definitions.length],
          ].map(([label, value]) => (
            <div key={String(label)} className="flex gap-2">
              <dt>{label}</dt>
              <dd className="text-foreground">{value}</dd>
            </div>
          ))}
        </dl>
      </header>

      <NavigationTabs
        ariaLabel={h("accessModel")}
        items={[
          {
            key: "entities",
            href: "/corporate/organization/admins/access?view=entities",
            label: t("entitiesAndActions"),
            active: view === "entities",
          },
          {
            key: "matrix",
            href: "/corporate/organization/admins/access?view=matrix",
            label: t("roleMatrix"),
            active: view === "matrix",
          },
        ]}
      />

      <form method="get" className="flex items-end gap-2" role="search">
        <input type="hidden" name="view" value={view} />
        <div className="min-w-0 flex-1 space-y-1.5 sm:max-w-sm">
          <Label htmlFor="permission-query">{t("searchPermissions")}</Label>
          <Input
            id="permission-query"
            name="query"
            type="search"
            defaultValue={query}
            autoComplete="off"
          />
        </div>
        <Button type="submit" variant="outline">
          {h("search")}
        </Button>
      </form>

      {groupsCount === 0 ? (
        <StatePanel
          kind="empty"
          title={h("accessModel")}
          description={query ? t("noMatchingPermissions") : t("noRoles")}
        />
      ) : view === "entities" ? (
        <EntitiesView
          byResource={byResource}
          activeEntity={activeEntity}
          query={query}
          roles={roles}
          t={t}
        />
      ) : (
        <div className="space-y-4">
          {[...byGroup.entries()].map(([group, names]) => (
            <DetailAccordion
              key={group}
              title={group}
              summary={String(names.length)}
              defaultOpen={Boolean(query)}
            >
              <MatrixTable
                permissions={names}
                roles={roles}
                labels={{
                  permission: t("permission"),
                  granted: t("granted"),
                  notGranted: t("notGranted"),
                }}
              />
            </DetailAccordion>
          ))}
        </div>
      )}

      {effective.length ? (
        <DetailAccordion title={t("effectiveAccess")} summary={String(effective.length)}>
          <EffectiveAccessTable
            effective={effective}
            labels={{
              permission: t("permission"),
              scope: t("scope"),
              scopeId: t("scopeId"),
              grantedBy: t("grantedBy"),
            }}
          />
        </DetailAccordion>
      ) : null}
    </div>
  );
}
