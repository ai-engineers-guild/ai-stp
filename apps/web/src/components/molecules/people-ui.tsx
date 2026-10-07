"use client";

import { useEffect, useRef } from "react";
import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { Badge } from "@/components/atoms/badge";
import { InitialsAvatar } from "@/components/atoms/avatar-image";
import { Select } from "@/components/atoms/select";
import { CompactChipList } from "@/components/molecules/compact-chip-list";
import { Link } from "@/lib/i18n/navigation";
import { Input } from "@/components/atoms/input";
import { Icon } from "@/theme";

export const PEOPLE_PAGE_SIZE = 10;

/** Native history keeps filtering instant, addressable, and restorable on Back. */
export function usePeopleFilters() {
  const params = useSearchParams();
  function update(name: string, value: string) {
    const url = new URL(window.location.href);
    if (value) url.searchParams.set(name, value);
    else url.searchParams.delete(name);
    if (name !== "page") url.searchParams.delete("page");
    window.history.replaceState(null, "", url);
  }
  return { get: (name: string) => params.get(name) ?? "", update };
}

export function PeopleSearch({
  value,
  onChange,
  label,
}: {
  value: string;
  onChange: (value: string) => void;
  label: string;
}) {
  return (
    <div className="relative min-w-0 flex-1 sm:min-w-60">
      <Icon
        name="search"
        size="sm"
        className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 -translate-y-1/2"
      />
      <Input
        type="search"
        name="query"
        aria-label={label}
        placeholder={label}
        value={value}
        autoComplete="off"
        className="h-11 pl-10"
        onChange={(event) => {
          onChange(event.target.value);
        }}
      />
    </div>
  );
}

export function PeopleSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: readonly { value: string; label: string }[];
}) {
  return (
    <Select
      aria-label={label}
      value={value}
      className="sm:w-auto sm:min-w-32"
      onChange={(event) => {
        onChange(event.target.value);
      }}
    >
      <option value="">{label}</option>
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </Select>
  );
}

export function PeopleCheckbox({
  label,
  checked,
  mixed = false,
  onChange,
}: {
  label: string;
  checked: boolean;
  mixed?: boolean;
  onChange: (checked: boolean) => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = mixed;
  }, [mixed]);
  return (
    <label className="inline-flex size-11 shrink-0 items-center justify-center">
      <input
        ref={ref}
        type="checkbox"
        aria-label={label}
        aria-checked={mixed ? "mixed" : checked}
        checked={checked}
        className="accent-primary focus-visible:ring-ring size-4 cursor-pointer rounded-sm focus-visible:ring-2 focus-visible:ring-offset-2"
        onChange={(event) => {
          onChange(event.target.checked);
        }}
      />
    </label>
  );
}

export function PersonIdentity({
  name,
  email,
  you = false,
}: {
  name: string;
  email?: string;
  you?: boolean;
}) {
  const t = useTranslations("people");
  return (
    <div className="flex min-w-0 items-center gap-3">
      <InitialsAvatar name={name} />
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="truncate">{name}</span>
          {you ? (
            <span className="bg-muted text-muted-foreground rounded-md px-1.5 py-0.5 text-xs">
              {t("you")}
            </span>
          ) : null}
        </div>
        {email ? <p className="text-muted-foreground truncate text-xs">{email}</p> : null}
      </div>
    </div>
  );
}

export function PeopleRole({ role }: { role: string }) {
  return (
    <Link
      href={`/corporate/organization/admins/roles?role=${encodeURIComponent(role)}`}
      className="focus-visible:ring-ring inline-block rounded-sm hover:underline focus-visible:ring-2 focus-visible:outline-none"
    >
      <Badge variant="secondary" className="font-sans font-normal tracking-normal">
        {role}
      </Badge>
    </Link>
  );
}
export function PeopleTeams({ teams }: { teams: readonly { team_id: string; name: string }[] }) {
  const t = useTranslations("people");
  return (
    <CompactChipList
      values={teams.map((team) => team.name)}
      label={t("teams")}
      variant="secondary"
      className="[&_[data-ui]]:max-w-36 [&_[data-ui]]:truncate [&_[data-ui]]:font-sans [&_[data-ui]]:font-normal"
      hrefForValue={(name) => {
        const team = teams.find((item) => item.name === name);
        return team ? `/corporate/teams/${encodeURIComponent(team.team_id)}` : undefined;
      }}
    />
  );
}
