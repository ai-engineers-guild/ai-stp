"use client";

import { useTransition } from "react";

import { selectCorporateOrganization } from "@/actions/corporate";

export type CorporateOrganizationOption = {
  id: string;
  name: string;
};

/**
 * Session-scoped organization selector for accounts holding more than one
 * corporate membership. The server action validates the choice against live
 * memberships, so this control only ever stores a preference — never a grant.
 */
export function CorporateOrganizationSwitcher({
  organizations,
  selectedId,
  label,
}: {
  organizations: readonly CorporateOrganizationOption[];
  selectedId: string;
  label: string;
}) {
  const [busy, startTransition] = useTransition();
  return (
    <label className="flex min-w-0 items-center gap-2 text-sm">
      <span className="text-muted-foreground shrink-0">{label}</span>
      <select
        name="organization"
        defaultValue={selectedId}
        disabled={busy}
        aria-label={label}
        onChange={(event) => {
          const formData = new FormData();
          formData.set("organization", event.target.value);
          startTransition(() => selectCorporateOrganization(formData));
        }}
        className="border-input bg-background h-9 min-w-0 rounded-sm border px-2 text-sm"
      >
        {organizations.map((item) => (
          <option key={item.id} value={item.id}>
            {item.name}
          </option>
        ))}
      </select>
    </label>
  );
}
