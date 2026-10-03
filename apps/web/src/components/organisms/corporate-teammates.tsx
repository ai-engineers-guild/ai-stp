"use client";

import { useTranslations } from "next-intl";
import { Badge } from "@/components/atoms/badge";
import { Icon } from "@/theme";
import type { CorporateTeammate } from "@/lib/api/generated/types.gen";

const PROJECT_ROLES = new Set(["owner", "lead", "contributor", "staff"]);

/** Scoped people projection — co-members of the caller's teams and projects.
 * Deliberately carries no email, job title, or organization role (ADR-0223). */
export function CorporateTeammatesList({ items }: { items: CorporateTeammate[] }) {
  const h = useTranslations("hub");
  const roleLabel = (kind: string, role: string) =>
    kind === "project"
      ? PROJECT_ROLES.has(role)
        ? h(`projectRole${role.slice(0, 1).toUpperCase()}${role.slice(1)}`)
        : null
      : role === "lead" || role === "staff"
        ? h(role)
        : null;
  return (
    <section className="space-y-4">
      <p className="text-muted-foreground text-sm">{h("teammatesBody")}</p>
      <ul className="divide-border divide-y">
        {items.map((item) => (
          <li key={item.account_id} className="flex flex-wrap items-center gap-3 py-3">
            <span className="bg-muted grid size-9 shrink-0 place-items-center rounded-full">
              <Icon name="user" size="sm" />
            </span>
            <span className="min-w-0 flex-1 truncate text-sm font-medium">
              {item.display_name ?? item.account_id}
            </span>
            <span className="flex flex-wrap gap-1.5">
              {item.contexts.map((context) => {
                const role = roleLabel(context.kind, context.role);
                return (
                  <Badge key={`${context.kind}:${context.id}`} variant="secondary">
                    {context.name}
                    {role ? ` · ${role}` : null}
                  </Badge>
                );
              })}
            </span>
          </li>
        ))}
      </ul>
      {!items.length && <p className="text-muted-foreground text-sm">{h("teammatesEmpty")}</p>}
    </section>
  );
}
