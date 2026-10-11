"use client";

import { useState, type ReactNode } from "react";
import { useTranslations } from "next-intl";
import { Badge } from "@/components/atoms/badge";
import { Button } from "@/components/atoms/button";
import { CorporatePermissionTable } from "@/components/organisms/corporate-permission-table";
import type {
  CorporateMember,
  CorporateTeamView,
  CorporateEffectivePermission,
  CorporatePermissionDefinition,
  CorporateAuditEntry,
} from "@/lib/api/generated/types.gen";
import {
  entityDefinitions,
  permissionDefinitions,
  permissionLabel,
  roleTitle,
} from "@/lib/corporate-permission-ui";
import { Link } from "@/lib/i18n/navigation";

/**
 * Read-only employee drawer: a brief identity block, the member's grants
 * (role bindings, direct allows, effective permissions — `children`), and the
 * activity journal. Mutations live in the page-level dialogs, not here.
 */
export function CorporateEmployeeAccessDrawer({
  member,
  teams,
  effective,
  definitions,
  scopeOptions,
  currentScope,
  canAudit,
  activity = [],
  children,
}: {
  member: CorporateMember;
  teams: readonly CorporateTeamView[];
  effective: readonly CorporateEffectivePermission[];
  definitions: readonly CorporatePermissionDefinition[];
  scopeOptions: readonly { value: string; label: string }[];
  currentScope: string;
  canAudit: boolean;
  activity?: readonly CorporateAuditEntry[];
  children: ReactNode;
}) {
  const a = useTranslations("accessUi");
  const c = useTranslations("corporate");
  const p = useTranslations("people");
  const h = useTranslations("hub");
  const [matrix, setMatrix] = useState(false);
  const permissions = effective.map((item) => item.permission);
  const granted = (definitions.length ? definitions : permissionDefinitions(permissions)).filter(
    (definition) => permissions.includes(definition.name),
  );
  const memberTeams = teams
    .filter((team) => team.members.some((entry) => entry.account_id === member.account_id))
    .map((team) => team.name)
    .join(", ");
  return (
    <div className="mt-4 space-y-6">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={member.state === "active" ? "success" : "warning"}>{p(member.state)}</Badge>
        <Badge variant="secondary" className="font-sans">
          {roleTitle(member.role, a)}
        </Badge>
      </div>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
        {[
          [p("jobTitle"), member.job_title_name ?? "—"],
          [p("teams"), memberTeams || "—"],
          [a("joined"), member.joined_at?.slice(0, 10) ?? "—"],
        ].map(([label, value]) => (
          <div key={label}>
            <dt className="text-muted-foreground text-xs">{label}</dt>
            <dd className="mt-0.5 truncate">{value}</dd>
          </div>
        ))}
      </dl>

      <section className="border-border space-y-5 border-t pt-5">
        <h2 className="font-medium">{a("grants")}</h2>
        {children}
      </section>

      <section className="border-border space-y-3 border-t pt-5">
        <div className="flex items-center justify-between gap-2">
          <h2 className="font-medium">
            {a("effectivePermissions")} <Badge variant="secondary">{effective.length}</Badge>
          </h2>
          <Button
            size="sm"
            variant="outline"
            aria-pressed={matrix}
            onClick={() => {
              setMatrix(!matrix);
            }}
          >
            {a(matrix ? "viewAsList" : "viewAsMatrix")}
          </Button>
        </div>
        <form method="get" className="flex flex-wrap items-end gap-2" aria-label={c("selectScope")}>
          <input type="hidden" name="employee" value={member.account_id} />
          <label className="text-muted-foreground w-full text-xs" htmlFor="access-scope">
            {c("selectScope")}
          </label>
          <select
            id="access-scope"
            name="scope"
            defaultValue={currentScope}
            className="border-input bg-background h-10 min-w-0 flex-1 rounded-sm border px-2 text-sm"
          >
            {scopeOptions.map((scope) => (
              <option key={scope.value} value={scope.value}>
                {scope.label}
              </option>
            ))}
          </select>
          <Button type="submit" variant="outline" size="sm">
            {c("openAccess")}
          </Button>
        </form>
        {matrix ? (
          <CorporatePermissionTable definitions={granted} permissions={permissions} />
        ) : (
          entityDefinitions(granted).map(([resource, items]) => (
            <details key={resource} className="border-border border-b py-3">
              <summary className="cursor-pointer text-sm font-medium">
                {a(`entities.${resource}.name`)}{" "}
                <span className="text-muted-foreground font-normal">· {items.length}</span>
              </summary>
              <ul className="mt-3 space-y-3">
                {items.map((definition) => (
                  <li key={definition.name} className="text-sm">
                    <p>{permissionLabel(definition, a)}</p>
                    <div className="mt-1 flex flex-wrap gap-1">
                      {effective
                        .find((item) => item.permission === definition.name)
                        ?.source_records.map((source) => (
                          <Badge
                            key={source.source_id}
                            variant="secondary"
                            title={`${source.scope_kind}:${source.scope_id}`}
                          >
                            {source.role ? roleTitle(source.role, a) : source.kind}
                          </Badge>
                        ))}
                    </div>
                  </li>
                ))}
              </ul>
            </details>
          ))
        )}
        {!granted.length ? <p className="text-muted-foreground text-sm">{a("noResults")}</p> : null}
      </section>

      <section className="border-border space-y-3 border-t pt-5 text-sm">
        <h2 className="font-medium">{a("activity")}</h2>
        <p className="text-muted-foreground">
          {p("lastActivity")}: {member.last_activity_at ?? "—"}
        </p>
        <ul className="divide-border divide-y">
          {activity.map((event) => (
            <li key={event.audit_id} className="space-y-1 py-3">
              <p className="font-medium">{event.action}</p>
              <p className="text-muted-foreground text-xs">
                {event.created_at} · {event.outcome}
              </p>
              <p className="text-muted-foreground text-xs break-all">
                {event.target_table}: {event.target_id}
              </p>
            </li>
          ))}
        </ul>
        {canAudit ? (
          <Button asChild variant="outline">
            <Link
              href={`/corporate/admin/audit?actor_account_id=${encodeURIComponent(member.account_id)}`}
            >
              {h("auditJournal")}
            </Link>
          </Button>
        ) : null}
      </section>
    </div>
  );
}
