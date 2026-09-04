"use client";

import { useId, useMemo, useState } from "react";

type Option = string | { value: string; label: string };

type SearchableMultiSelectProps = {
  name: string;
  label: string;
  searchLabel: string;
  options: readonly Option[];
  selected: readonly string[];
  form?: string;
  onChange?: (values: string[]) => void;
};

function optionValue(option: Option): string {
  return typeof option === "string" ? option : option.value;
}

function optionLabel(option: Option): string {
  return typeof option === "string" ? option : option.label;
}

/** Form-native searchable multiselect with repeated query parameters. */
export function SearchableMultiSelect({
  name,
  label,
  searchLabel,
  options,
  selected,
  form,
  onChange,
}: SearchableMultiSelectProps) {
  const id = useId();
  const [search, setSearch] = useState("");
  const [checked, setChecked] = useState<string[]>(() => [...selected]);
  const filtered = useMemo(
    () =>
      options.filter((option) =>
        optionLabel(option).toLocaleLowerCase().includes(search.toLocaleLowerCase()),
      ),
    [options, search],
  );

  function toggle(value: string, next: boolean) {
    const updated = next ? [...checked, value] : checked.filter((item) => item !== value);
    setChecked(updated);
    onChange?.(updated);
  }

  return (
    <details
      name="catalog-filter"
      onToggle={(event) => {
        if (!event.currentTarget.open) return;
        document
          .querySelectorAll<HTMLDetailsElement>('details[name="catalog-filter"][open]')
          .forEach((details) => {
            if (details !== event.currentTarget) details.open = false;
          });
      }}
      className="border-border bg-background relative min-w-0 rounded-sm border"
    >
      <summary className="focus-visible:ring-ring flex min-h-11 min-w-0 cursor-pointer list-none items-center justify-between gap-3 px-3 py-2 text-sm marker:content-none focus-visible:ring-2 focus-visible:outline-none [&::-webkit-details-marker]:hidden">
        <span className="min-w-0 truncate">
          {label}
          {checked.length > 0 ? ` (${checked.length})` : ""}
        </span>
      </summary>
      <div className="bg-popover border-border relative z-50 min-w-0 space-y-2 rounded-sm border p-3 shadow-md md:absolute md:top-[calc(100%+0.375rem)] md:right-0 md:left-0">
        <label htmlFor={id} className="sr-only">
          {searchLabel}
        </label>
        <input
          id={id}
          type="search"
          value={search}
          onChange={(event) => {
            setSearch(event.target.value);
          }}
          placeholder={searchLabel}
          className="border-input bg-background h-11 w-full rounded-sm border px-3 text-base sm:text-sm"
        />
        {checked
          .filter((value) => !filtered.some((option) => optionValue(option) === value))
          .map((value) => (
            <input key={`hidden:${value}`} type="hidden" form={form} name={name} value={value} />
          ))}
        <div className="max-h-56 space-y-1 overflow-y-auto" role="group" aria-label={label}>
          {filtered.map((option) => {
            const value = optionValue(option);
            const text = optionLabel(option);
            return (
              <label
                key={value || text}
                className="hover:bg-muted flex min-h-11 min-w-0 items-center gap-2 rounded-sm px-2 py-2 text-sm"
              >
                <input
                  form={form}
                  type="checkbox"
                  name={name}
                  value={value}
                  checked={checked.includes(value)}
                  onChange={(event) => {
                    toggle(value, event.target.checked);
                  }}
                />
                <span
                  className={
                    typeof option === "string"
                      ? "min-w-0 font-mono text-xs break-all"
                      : "min-w-0 break-words"
                  }
                >
                  {text}
                </span>
              </label>
            );
          })}
        </div>
      </div>
    </details>
  );
}
