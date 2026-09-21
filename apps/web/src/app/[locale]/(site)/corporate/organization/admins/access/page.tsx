import { getTranslations, setRequestLocale } from "next-intl/server";

import { Badge } from "@/components/atoms/badge";
import { StatePanel } from "@/components/molecules/state-panel";
import { DetailAccordion } from "@/components/molecules/detail-accordion";
import { HistoryBackButton } from "@/components/molecules/history-back-button";
import { ApiError } from "@/lib/api/errors";
import { apiRequest } from "@/lib/api/http";
import type { CorporatePermissionMatrix, CorporateRoleView } from "@/lib/api/generated/types.gen";
import { readCorporateContext, readCorporateWorkspace } from "@/lib/api/corporate";
import { canViewCorporateAdministration } from "@/lib/corporate-hub";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { Link } from "@/lib/i18n/navigation";
import { Icon } from "@/theme";

type PageProps = { params: Promise<{ locale: string }> };

const rowClass = "border-border hover:bg-muted/40 border-b transition-colors last:border-0";
const headCellClass = "text-muted-foreground px-3 py-2 text-xs font-medium";

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
      <table className="w-full min-w-max border-collapse text-sm">
        <thead>
          <tr className="border-border border-b">
            <th scope="col" className={`${headCellClass} py-2 pr-4 pl-0 text-left`}>
              {labels.permission}
            </th>
            {roles.map((role) => (
              <th key={role.name} scope="col" className={`${headCellClass} text-center`}>
                <Link
                  href={`/corporate/roles/${encodeURIComponent(role.name)}`}
                  className="text-foreground underline underline-offset-4"
                >
                  {role.name}
                </Link>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {permissions.map((permission) => (
            <tr key={permission} className={rowClass}>
              <td className="py-2 pr-4 font-mono text-xs whitespace-nowrap">{permission}</td>
              {roles.map((role) => (
                <td key={role.name} className="px-3 py-2 text-center align-middle">
                  {role.permissions.includes(permission) ? (
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
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
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
      <table className="w-full min-w-max border-collapse text-sm">
        <thead>
          <tr className="border-border border-b">
            {[labels.permission, labels.scope, labels.scopeId, labels.grantedBy].map((label) => (
              <th key={label} scope="col" className={`${headCellClass} text-left`}>
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {effective.map((item) => (
            <tr key={`${item.permission}:${item.scope_kind}:${item.scope_id}`} className={rowClass}>
              <td className="py-2 pr-4 font-mono text-xs whitespace-nowrap">{item.permission}</td>
              <td className="px-3 py-2">
                <Badge variant="outline">{item.scope_kind}</Badge>
              </td>
              <td className="px-3 py-2 font-mono text-xs break-all">{item.scope_id}</td>
              <td className="px-3 py-2">
                <span className="inline-flex flex-wrap gap-1">
                  {item.sources.map((source) => (
                    <Badge key={source} variant="secondary">
                      {source}
                    </Badge>
                  ))}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default async function CorporateAccessMatrixPage({ params }: PageProps) {
  const { locale } = await params;
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
      <StatePanel kind="error" title={t("administration")} description={technology("forbidden")} />
    );
  }
  const organizationId = context.organization.organization_id;
  const workspace = await readCorporateWorkspace(session, false);
  const matrix = await apiRequest<CorporatePermissionMatrix>(
    `/v1/corporate/organizations/${organizationId}/permissions/matrix`,
    { sessionToken: session },
  ).catch(() => null);
  const roles = workspace?.roles?.items ?? [];
  const definitions = matrix?.definitions ?? [];
  const groups = new Map<string, string[]>();
  for (const definition of definitions) {
    const bucket = groups.get(definition.group) ?? [];
    bucket.push(definition.name);
    groups.set(definition.group, bucket);
  }
  const effective = matrix?.effective ?? [];

  return (
    <div className="min-w-0 space-y-8">
      <HistoryBackButton label={h("backToAdmins")} fallback="/corporate/organization/admins" />
      <header className="space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-medium tracking-tight break-words sm:text-3xl">
            {t("accessMatrix")}
          </h1>
          <Badge variant="secondary">{context.member.role}</Badge>
        </div>
        <p className="text-muted-foreground max-w-2xl text-sm">{t("accessMatrixBody")}</p>
        <dl className="text-muted-foreground flex flex-wrap gap-x-6 gap-y-1 font-mono text-xs">
          {[
            [t("roles"), roles.length],
            [t("accessMatrixGroups"), groups.size],
            [t("permission"), definitions.length],
          ].map(([label, value]) => (
            <div key={String(label)} className="flex gap-2">
              <dt>{label}</dt>
              <dd className="text-foreground">{value}</dd>
            </div>
          ))}
        </dl>
      </header>

      {groups.size === 0 ? (
        <StatePanel kind="empty" title={t("accessMatrix")} description={t("noRoles")} />
      ) : (
        <div className="space-y-4">
          {[...groups.entries()].map(([group, names]) => (
            <DetailAccordion key={group} title={group} summary={String(names.length)}>
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
