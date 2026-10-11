"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { Input } from "@/components/atoms/input";
import type { CorporatePermissionDefinition } from "@/lib/api/generated/types.gen";
import {
  entityDefinitions,
  entityMeta,
  permissionColumn,
  permissionLabel,
  ROLE_COLUMNS,
} from "@/lib/corporate-permission-ui";
import { Icon } from "@/theme";

/** The role viewer and role form share the same entity/action layout. */
export function CorporatePermissionTable({
  definitions,
  permissions,
  editable = false,
}: {
  definitions: readonly CorporatePermissionDefinition[];
  permissions: readonly string[];
  editable?: boolean;
}) {
  const t = useTranslations("accessUi");
  const [query, setQuery] = useState("");
  const needle = query.trim().toLowerCase();
  const rows = entityDefinitions(definitions)
    .map(([resource, items]) => {
      if (!needle) return [resource, items] as const;
      const entityName = t(`entities.${resource}.name`).toLowerCase();
      const filtered = items.filter(
        (definition) =>
          definition.name.toLowerCase().includes(needle) ||
          permissionLabel(definition, t).toLowerCase().includes(needle) ||
          entityName.includes(needle),
      );
      return [resource, filtered] as const;
    })
    .filter(([, items]) => items.length > 0);
  function mark(definition: CorporatePermissionDefinition, label = false) {
    const granted = permissions.includes(definition.name);
    return (
      <label
        key={definition.name}
        className="flex min-h-9 items-center gap-2 text-xs"
        title={`${definition.name} — ${definition.scopes.join(", ")}`}
      >
        {editable ? (
          <input
            type="checkbox"
            name="permissions"
            value={definition.name}
            defaultChecked={granted}
            aria-label={definition.name}
            className="accent-primary focus-visible:ring-ring size-4 focus-visible:ring-2"
          />
        ) : (
          <span
            role="img"
            className={`grid size-4 shrink-0 place-items-center rounded-sm border ${granted ? "border-primary bg-primary text-primary-foreground" : "border-border"}`}
            aria-label={`${definition.name}: ${t(granted ? "granted" : "notGranted")}`}
          >
            {granted ? <Icon name="verified" size="sm" className="size-3" /> : null}
          </span>
        )}
        {label ? <span>{permissionLabel(definition, t)}</span> : null}
      </label>
    );
  }
  return (
    <div className="space-y-3">
      <Input
        type="search"
        value={query}
        onChange={(event) => {
          setQuery(event.target.value);
        }}
        placeholder={t("searchPermissions")}
        aria-label={t("searchPermissions")}
        className="max-w-xs"
      />
      <div
        className="border-border min-w-0 overflow-x-auto rounded-lg border"
        data-ui="permission-matrix"
      >
        <table
          className="w-full min-w-[44rem] border-collapse text-sm"
          aria-label={t("permissions")}
        >
          <thead>
            <tr className="bg-muted/30 text-muted-foreground text-xs uppercase">
              <th className="px-3 py-3 text-left font-medium">{t("entityAction")}</th>
              {ROLE_COLUMNS.map((action) => (
                <th key={action} className="px-3 py-3 text-center font-medium">
                  {t(`actions.${action}`)}
                </th>
              ))}
              <th className="px-3 py-3 text-left font-medium">{t("otherActions")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(([resource, items]) => (
              <tr key={resource} className="border-border border-t">
                <th scope="row" className="min-w-52 px-3 py-3 text-left">
                  <span className="flex items-center gap-3">
                    <Icon name={entityMeta(resource).icon} />
                    <span>
                      <span className="block font-medium">{t(`entities.${resource}.name`)}</span>
                      <span className="text-muted-foreground block text-xs font-normal">
                        {t(`entities.${resource}.description`)}
                      </span>
                    </span>
                  </span>
                </th>
                {ROLE_COLUMNS.map((action) => (
                  <td key={action} className="px-3 py-3">
                    <div className="flex justify-center">
                      {items
                        .filter((definition) => permissionColumn(definition) === action)
                        .map((definition) => mark(definition))}
                      {!items.some((definition) => permissionColumn(definition) === action) ? (
                        <span className="text-muted-foreground">—</span>
                      ) : null}
                    </div>
                  </td>
                ))}
                <td className="px-3 py-2">
                  {items
                    .filter((definition) => permissionColumn(definition) === "other")
                    .map((definition) => mark(definition, true))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
